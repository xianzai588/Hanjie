"""0.4R1串联热阻修正版的热量去向、源/物性情景及条件收敛。"""
import argparse
import copy
import importlib.util
from pathlib import Path
import sys

import numpy as np
from threadpoolctl import threadpool_limits

PROJECT_ROOT=Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT/"src") not in sys.path:
    sys.path.insert(0,str(PROJECT_ROOT/"src"))

from credibility_source import projected_weights
from hanjie.simulation.thermal_ledgers import DetailedThermalLedger, build_material_point_stencil
from run_physics03 import ROOT, load, digest, write_json

SPEC = ROOT/"project/thermal-credibility-v5.4r1.yaml"
OUTPUT = ROOT/"simulation/thermal-v5/results/credibility04r1"
NAMES = ("q235b","qt450_10","ernife_ci")


def isolated_core():
    # 每次载入独立模块实例，只替换本次运行的观测/源接口，不改历史文件或共享全局对象。
    descriptor = importlib.util.spec_from_file_location("_thermal04r_core",Path(__file__).with_name("run_mass_closed04.py"))
    core = importlib.util.module_from_spec(descriptor)
    sys.modules[descriptor.name] = core
    descriptor.loader.exec_module(core)
    return core


def material_scenario(materials, physics, scenario):
    materials,physics = copy.deepcopy(materials),copy.deepcopy(physics)
    if scenario not in ("nominal","lower","upper"):
        raise ValueError("未知物性情景")
    if scenario!="nominal":
        index = 0 if scenario=="lower" else 1
        for name in NAMES:
            spec = physics["materials"][name]
            for key,bounds in spec["phase_change"]["uncertainty"].items():
                spec["phase_change"][key] = bounds[index]
            thermal = spec["high_temperature"] if name=="ernife_ci" else materials["materials"][name]["temperature_dependent"]
            for key,scale in (("specific_heat_j_kgk","cp_scale_range"),("thermal_conductivity_w_mk","k_scale_range")):
                thermal[key] = [v*spec["high_temperature"][scale][index] for v in thermal[key]]
    return materials,physics


def run_case(plan, case, out, specification_path=SPEC):
    if out.exists():
        raise FileExistsError(f"结果目录已存在，避免覆盖证据：{out}")
    core = isolated_core()
    spec = load(ROOT/plan["baseline"])
    if "mesh_overrides" in case:
        spec["mesh"].update(case["mesh_overrides"])
        spec["mesh"]["status"] = "controlled_spatial_discretization_study"
    elif case["mesh"]!="baseline":
        spec["mesh"].update(plan["meshes"][case["mesh"]])
        spec["mesh"]["status"] = "conditional_convergence_study_not_yet_accepted"
    spec["solver"]["time_step_s"] = case["dt"]
    source = plan["sources"][case["source"]]
    spec["source"].update(source,model=case["source"],evidence_level="design_assumption_not_calibrated")
    angle = np.deg2rad(source["angle_deg"])
    spec["source"]["direction_n_z"] = [float(np.sin(angle)),float(-np.cos(angle))]
    spec["source"]["cross_coordinate"] = "u=n*cos(angle_deg)+z*sin(angle_deg)"
    spec["source"]["normalization"] = plan["source_basis"]+"；无限投影平面归一化，有限材料透射单独记账。"
    mat,phy = material_scenario(load(ROOT/spec["material_input"]),load(ROOT/spec["thermal_properties"]),case["properties"])
    old_load = core.load
    def scenario_load(path):
        if path==ROOT/spec["material_input"]:
            return mat
        if path==ROOT/spec["thermal_properties"]:
            return phy
        return old_load(path)
    core.load = scenario_load
    core.surface_weights = lambda g,b,w: projected_weights(g,b,w,**source)
    g = core.build_geometry(load(ROOT/spec["inputs"]),load(ROOT/spec["process_input"]),spec)
    ids = g["ids"]
    config = load(ROOT/spec["inputs"])
    duration = (config["heat_source_path"]["source_end_s_mm"]-config["heat_source_path"]["source_start_s_mm"])/config["process"]["travel_speed_mm_s"]
    total = duration+spec["solver"]["cooling_after_source_s"]
    source_fn,step_fn,matrix_fn = core.source_power,core.enthalpy_step,core._conductance_matrix
    ledger = dict(time=0.,q=np.zeros(len(ids)),source=np.zeros(3),conductive=np.zeros(3),rows=[])
    detailed = DetailedThermalLedger(g) if plan.get("detailed_ledgers",False) else None
    observation_cells = []
    for point in plan.get("observation_points",[]):
        requested = np.asarray(point["coordinate_s_n_z_mm"],float)
        axes = (g["s_edges"],g["n_edges"],g["z_edges"])
        grid_index = tuple(int(np.searchsorted(edge,value,side="right")-1) for edge,value in zip(axes,requested))
        if any(index<0 or index>=len(edge)-1 for index,edge in zip(grid_index,axes)):
            raise ValueError(f"固定观测点超出计算域：{point['name']}")
        cell = int(g["lattice"][grid_index])
        if cell<0 or int(ids[cell])!=int(point["material_id"]):
            raise ValueError(f"固定观测点未落入预期材料：{point['name']}")
        actual = [float(g["s_left"][cell]+g["dims"][cell,0]/2),
                  float((g["n_edges"][grid_index[1]]+g["n_edges"][grid_index[1]+1])/2),
                  float((g["z_edges"][grid_index[2]]+g["z_edges"][grid_index[2]+1])/2)]
        observation_cells.append(dict(name=point["name"],material_id=int(ids[cell]),requested_coordinate_s_n_z_mm=requested.tolist(),
                                      represented_cell_center_s_n_z_mm=actual,represented_cell_dimensions_mm=g["dims"][cell].tolist(),cell=cell))
    observation_rows = []
    reconstructed_stencils = [
        {"name":point["name"],**build_material_point_stencil(
            g,point["coordinate_s_n_z_mm"],point["material_id"],point.get("stencil_neighbours",8)
        )}
        for point in plan.get("observation_points",[])
    ] if detailed is not None else []
    reconstructed_rows = []
    def partition(vector):
        return np.bincount(ids,weights=vector,minlength=4)[1:4]
    def observe_source(*args):
        q = source_fn(*args)
        ledger["q"] = q
        return q
    def observe_matrix(*args):
        matrix,exposed = matrix_fn(*args)
        if detailed is not None:
            fraction,dt = args[1],args[3]
            face_area = core.face_geometry(g,fraction)[0]
            detailed.prepare_step(fraction,matrix,dt,face_area)
        return matrix,exposed
    def observe_step(*args):
        result = step_fn(*args)
        dt = min(case["dt"],total-ledger["time"])
        if ledger["time"]<duration:
            dt = min(dt,duration-ledger["time"])
        direct = partition(ledger["q"])*dt
        conductive = partition(-(args[3]@result[0]))
        ledger["source"] += direct
        ledger["conductive"] += conductive
        ledger["time"] += dt
        if detailed is not None:
            detailed.record_step(result[0],ledger["q"])
            reconstructed_rows.append({
                "time_s":ledger["time"],
                **{
                    item["name"]:float(np.dot(result[0][item["cell_indices"]],item["weights"]))
                    for item in reconstructed_stencils
                },
            })
        if observation_cells:
            observation_rows.append({"time_s":ledger["time"],**{item["name"]:float(result[0][item["cell"]]) for item in observation_cells}})
        ledger["rows"].append(dict(time_s=ledger["time"],source_step_j=direct.tolist(),
            cumulative_source_j=ledger["source"].tolist(),net_conductive_step_j=conductive.tolist(),
            cumulative_net_conductive_j=ledger["conductive"].tolist()))
        ledger["q"] = np.zeros(len(ids))
        return result
    core.source_power,core.enthalpy_step,core._conductance_matrix = observe_source,observe_step,observe_matrix
    sources = [specification_path,ROOT/plan["baseline"],Path(__file__),Path(__file__).with_name("credibility_source.py")]
    sources += [Path(__file__).with_name(n) for n in ("run_mass_closed04.py","mass_closed_geometry.py","physics.py","run_physics03.py")]
    if detailed is not None:
        sources.append(ROOT/"src/hanjie/simulation/thermal_ledgers.py")
    sources += [ROOT/spec[k] for k in ("inputs","process_input","material_input","thermal_properties")]
    write_json(out/"run-inputs.json",dict(case=case,specification=spec,materials=mat,physics=phy,
        hashes={p.relative_to(ROOT).as_posix():digest(p) for p in sources}))
    with threadpool_limits(limits=1):
        summary = core.run(spec,out)
    summary["stage"] = plan.get("version","THERMAL-0.4R1")
    summary["case"] = case
    summary["energy"]["direct_source_by_material_j"] = dict(zip(NAMES,ledger["source"].tolist()))
    summary["energy"]["direct_source_by_material_fraction"] = dict(zip(NAMES,(ledger["source"]/ledger["source"].sum()).tolist()))
    summary["energy"]["net_conductive_by_material_j"] = dict(zip(NAMES,ledger["conductive"].tolist()))
    summary["energy"]["material_source_partition_residual_j"] = float(ledger["source"].sum()-summary["energy"]["absorbed_source_j"])
    field = np.load(out/"field.npz")
    for code,name in enumerate(NAMES,1):
        mask = (ids==code)&(field["filled_fraction"]>0)
        molten = mask&(field["temperature_peak"]>phy["materials"][name]["phase_change"]["solidus_c"])
        stat = summary["material_statistics"][name]
        # 逐截面单元外缘包络；这是热暴露范围，不是实测自由表面或金相熔合线。
        widths,depths = [],[]
        for si in np.unique(g["index"][molten,0]):
            selected = molten&(g["index"][:,0]==si)
            transverse = "z" if code==1 else "n"
            dim = 2 if code==1 else 1
            lo = field[transverse][selected]-g["dims"][selected,dim]/2
            hi = field[transverse][selected]+g["dims"][selected,dim]/2
            widths.append(float(hi.max()-lo.min()))
            depth = field["n"][selected]+g["dims"][selected,1]/2 if code==1 else -field["z"][selected]+g["dims"][selected,2]/2
            depths.append(max(0.,float(depth.max())))
        stat["maximum_section_solidus_width_mm"] = max(widths,default=0.) if code!=3 else None
        stat["maximum_section_solidus_depth_mm"] = max(depths,default=0.) if code!=3 else None
        valid = mask&field["t8_5_valid"]
        stat["t8_5_valid_volume_mm3"] = float((g["volumes"]*field["filled_fraction"])[valid].sum())
        stat["t8_5_volume_weighted_mean_s"] = float(np.average(field["t8_5_s"][valid],weights=g["volumes"][valid]*field["filled_fraction"][valid])) if valid.any() else None
    field.close()
    if observation_cells:
        write_json(out/"fixed-point-history.json",dict(
            definition="有限体积中包含固定物理坐标的控制体温度；记录控制体中心和尺寸，不冒充点值插值",
            points=[{key:value for key,value in item.items() if key!="cell"} for item in observation_cells],rows=observation_rows))
        summary["fixed_point_history"] = "fixed-point-history.json"
    if detailed is not None:
        interface_ledger,source_ledger = detailed.finish()
        write_json(out/"interface-flux-ledger.json",interface_ledger)
        write_json(out/"source-density-ledger.json",source_ledger)
        write_json(out/"fixed-point-reconstructed-history.json",dict(
            definition="固定物理坐标的同材料逆距离平方重构；模板随网格生成但坐标固定，禁止跨材料和域外静默外推。",
            points=[{key:value for key,value in item.items() if key!="cell_indices"} for item in reconstructed_stencils],
            stencils=reconstructed_stencils,rows=reconstructed_rows))
        summary["detailed_thermal_ledgers"] = {
            "interface_flux":"interface-flux-ledger.json",
            "source_density":"source-density-ledger.json",
            "fixed_point_reconstructed":"fixed-point-reconstructed-history.json",
        }
    write_json(out/"summary.json",summary)
    write_json(out/"material-energy-history.json",dict(material_order=NAMES,definition="直接源输入与净导热分别记账；净导热正值为该材料从其余材料吸热，不含源/散热/出生焓。",steps=ledger["rows"]))
    write_json(out/"manifest.json",dict(files={p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name!="manifest.json"},evidence_level="solver_result_unvalidated"))
    return summary


def cases(plan):
    result = [dict(name="baseline",source="surface45",properties="nominal",mesh="baseline",dt=.1)]
    result += [dict(name=s,source=s,properties="nominal",mesh="baseline",dt=.1) for s in ("shallow45","surface30")]
    result += [dict(name="properties-"+p,source="surface45",properties=p,mesh="baseline",dt=.1) for p in ("lower","upper")]
    result += [dict(name=m,source="surface45",properties="nominal",mesh=m,dt=plan["convergence"]["spatial_dt_s"]) for m in plan["meshes"]]
    result += [dict(name="dt-"+str(dt),source="surface45",properties="nominal",mesh=plan["convergence"]["temporal_mesh"],dt=dt) for dt in plan["convergence"]["time_steps_s"][1:]]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",default="all")
    parser.add_argument("--output-dir",type=Path,default=OUTPUT)
    args = parser.parse_args()
    plan = load(SPEC)
    selected = [c for c in cases(plan) if args.case in ("all",c["name"])]
    if not selected:
        parser.error("未知工况名称")
    for case in selected:
        print(case,flush=True)
        run_case(plan,case,args.output_dir/case["name"])


if __name__=="__main__":
    main()
