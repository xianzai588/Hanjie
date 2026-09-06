"""执行 THERMAL-0.3-PHYS 双模型、受约束工艺采样及 G-PHYSICS。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import itertools
import json
from pathlib import Path
import sys
import time

import numpy as np
import yaml

from physics import material_tables, solve
from run_thermal0 import _cell_centers, _goldak_domain_capture_fraction

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "project/thermal-physics-v5.3.yaml"
OUT = ROOT / "simulation/thermal-v5/results/physics03"


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def admissible_cases(spec, process_file):
    window = process_file["process"]["acceptable_window"]
    scan = spec["scan"]
    candidates = []
    for current, voltage, speed in itertools.product(scan["current_a"], scan["voltage_v"], scan["travel_speed_mm_s"]):
        p = scan["efficiency"]*current*voltage
        e = p/speed
        if not window["heat_input_j_per_mm"]["min"] <= e <= window["heat_input_j_per_mm"]["max"]:
            continue
        for key,value in (("current_a",current),("voltage_v",voltage),("travel_speed_mm_s",speed)):
            if not window[key]["min"] <= value <= window[key]["max"]:
                raise ValueError("扫描参数越过冻结工艺域")
        candidates.append(dict(current_a=current,voltage_v=voltage,travel_speed_mm_s=speed,
                               efficiency=scan["efficiency"],net_power_w=p,net_line_energy_j_per_mm=e))
    return candidates


def selected_cases(spec, process_file):
    candidates = admissible_cases(spec, process_file)
    # 固定 DOE：取能量、功率、速度边界，去重；不根据算出的温度选择工况。
    selected = [next(c for c in candidates if c["current_a"]==75 and c["voltage_v"]==12 and c["travel_speed_mm_s"]==1.5)]
    for key in ("net_line_energy_j_per_mm", "net_power_w", "travel_speed_mm_s"):
        for fn in (min,max):
            item = fn(candidates, key=lambda c:c[key])
            if item not in selected:
                selected.append(item)
    cases = []
    for i, c in enumerate(selected):
        for preheat in ([150.] if i==0 else [130.,180.]):
            cases.append((f"process-{i:02d}-preheat-{preheat:g}",dict(c,preheat_temperature_c=preheat)))
    return candidates, cases


def deposition_audit(config, process_file):
    p = process_file["process"]["nominal"]
    wire_area = np.pi*float(p["filler_diameter_mm"])**2/4
    volume_per_length = wire_area*p["filler_feed_rate_mm_s"]/p["travel_speed_mm_s"]
    grid = config["thermal_grid"]
    n,dn = _cell_centers(grid["radial_min_offset_mm"],grid["radial_max_offset_mm"],grid["radial_points"])
    width = np.sum(np.abs(n)<=config["metallurgy"]["surrogate_weld_half_width_mm"])*dn
    band_area = width*(grid["axial_max_offset_mm"]-grid["axial_min_offset_mm"])
    fillet_area = .5*config["geometry"]["fillet_leg_length_mm"]**2
    return dict(evidence_level="design_assumption_geometry_audit",wire_volume_per_length_mm2=float(volume_per_length),
                nominal_fillet_area_mm2=fillet_area,discrete_surrogate_band_area_mm2=float(band_area),
                band_to_wire_volume_ratio=float(band_area/volume_per_length),
                band_to_nominal_fillet_ratio=float(band_area/fillet_area),
                wire_to_fillet_ratio=float(volume_per_length/fillet_area),
                status="FAIL", note="按100%沉积率估计；旧焊缝带不能代表该送丝量。角焊缝面积还含母材稀释，需实测截面和增重闭合，不能直接反算调大送丝率。")


def run_case(config, materials, spec, case_id, process_override, activation, output_dir, scales=None, latent=True, dt_scale=1.):
    cfg = copy.deepcopy(config)
    cfg["process"].update(process_override)
    p,g,hs = cfg["process"],cfg["thermal_grid"],cfg["heat_source"]
    if not np.isclose(p["net_power_w"],p["efficiency"]*p["current_a"]*p["voltage_v"]) or not np.isclose(p["net_line_energy_j_per_mm"],p["net_power_w"]/p["travel_speed_mm_s"]):
        raise ValueError("I/U/v/eta 与功率、线能量不守恒")
    s,ds = _cell_centers(g["arc_min_offset_mm"],g["arc_max_offset_mm"],g["arc_points"])
    n,dn = _cell_centers(g["radial_min_offset_mm"],g["radial_max_offset_mm"],g["radial_points"])
    z,dz = _cell_centers(g["axial_min_offset_mm"],g["axial_max_offset_mm"],g["axial_points"])
    _,nn,_ = np.meshgrid(s,n,z,indexing="ij")
    half = cfg["metallurgy"]["surrogate_weld_half_width_mm"]
    ids = np.where(nn < -half,2,np.where(nn > half,1,3)).astype(np.int8)
    path = cfg["heat_source_path"]
    start,end = path["source_start_s_mm"],path["source_end_s_mm"]
    capture = min(_goldak_domain_capture_fraction(pos,((g["arc_min_offset_mm"],g["arc_max_offset_mm"]),(g["radial_min_offset_mm"],g["radial_max_offset_mm"]),(g["axial_min_offset_mm"],g["axial_max_offset_mm"])),hs["a_front_mm"],hs["a_rear_mm"],hs["b_radial_mm"],hs["c_axial_mm"],hs["front_fraction"],hs["rear_fraction"],False) for pos in (start,end))
    if capture < g["minimum_source_domain_capture_fraction"]:
        raise ValueError("热源被计算域截断")
    packed,lengths,rho = material_tables(materials,spec["materials"],scales,latent)
    params = np.array([p[k] for k in ("net_power_w","travel_speed_mm_s","preheat_temperature_c","cooling_environment_c","convection_coefficient_w_m2k","emissivity")],float)
    source = np.array([start,end,*[hs[k] for k in ("a_front_mm","a_rear_mm","b_radial_mm","c_axial_mm","front_fraction","rear_fraction")]],float)
    sim = spec["simulation"]
    before = time.perf_counter()
    t,peak,active,t800,t500,cooling,ledger = solve(s,n,z,ids,packed,lengths,rho,params,source,
        0 if activation=="pre_existing" else 1,sim["activation_lead_mm"],sim["deposition_temperature_c"],sim["cooling_after_source_s"],sim["time_step_s"]*dt_scale)
    source_j,absorbed,birth,conv,rad,delta,mass,min_fraction,min_dt,steps = ledger
    residual = absorbed+birth-conv-rad-delta
    valid = (peak>800)&np.isfinite(t800)&np.isfinite(t500)&(t500>t800)&active
    stats = {}
    for name,code in (("q235b",1),("qt450_10",2),("ernife_ci",3)):
        mask = (ids==code)&active
        phase = spec["materials"][name]["phase_change"]
        melted = mask & (peak >= phase["solidus_c"])
        liquid = mask & (peak >= phase["liquidus_c"])
        stats[name] = dict(peak_temperature_c=float(peak[mask].max()),t8_5_valid_count=int(np.sum(valid&mask)),
             solidus_c=phase["solidus_c"],liquidus_c=phase["liquidus_c"],
             solidus_exceeded_volume_mm3=float(melted.sum()*ds*dn*dz),
             liquidus_exceeded_volume_mm3=float(liquid.sum()*ds*dn*dz),
             max_section_solidus_area_mm2=float(melted.sum(axis=(1,2)).max()*dn*dz),
             maximum_liquid_fraction=float(np.clip((peak[mask].max()-phase["solidus_c"])/(phase["liquidus_c"]-phase["solidus_c"]),0,1)))
    result = dict(case_id=case_id,activation=activation,evidence_level="solver_result_unvalidated",wall_seconds=time.perf_counter()-before,
        process={k:p[k] for k in ("current_a","voltage_v","travel_speed_mm_s","efficiency","net_power_w","net_line_energy_j_per_mm","preheat_temperature_c")},
        effective_scales=scales or {},latent_heat_enabled=latent,grid_shape=list(ids.shape),time_step_limit_s=sim["time_step_s"]*dt_scale,
        time=dict(weld_duration_s=(end-start)/p["travel_speed_mm_s"],cooling_after_source_s=sim["cooling_after_source_s"],steps=int(steps),minimum_dt_s=min_dt),
        peak_temperature_c=float(peak.max()),material_statistics=stats,
        energy=dict(nominal_source_j=source_j,absorbed_source_j=absorbed,unabsorbed_void_j=source_j-absorbed,
            birth_enthalpy_j=birth,convection_j=conv,radiation_j=rad,delta_internal_j=delta,residual_j=residual,
            residual_pct=abs(residual)/source_j*100,minimum_active_source_fraction=min_fraction,domain_capture_fraction=capture),
        activated_mass_kg=mass,two_parent_solidus_exceeded=all(stats[k]["solidus_exceeded_volume_mm3"]>0 for k in ("q235b","qt450_10")),
        plausible_fusion_geometry=False,calibrated=False,not_shop_floor_qualified=True,
        limitations=["全高度焊缝带是质量不闭合的敏感性代理；即使超过固相线也不是合理熔合几何。",
            "空域热源不重新归一化，未吸收能量单列；该源沉积模型还需宏观截面约束。",
            "仅焊后20s，未完成的 t8/5 不计有效；不提供结构耦合热历史。",
            "高温曲线和相变区间含未验证工程假设；液相率是焓模型变量，不是组织相含量。"])
    dest = output_dir/case_id/activation
    write_json(dest/"summary.json",result)
    if case_id in ("process-00-preheat-150","dt-half","latent-off"):
        np.savez_compressed(dest/"field.npz",s=s,n=n,z=z,material_id=ids,active=active,temperature_final=t,temperature_peak=peak,
            t8_5_s=np.where(valid,t500-t800,np.nan),t8_5_valid=valid,max_cooling_rate_c_s=cooling)
    print(json.dumps({"case":case_id,"activation":activation,"peak_c":result["peak_temperature_c"],"seconds":result["wall_seconds"]}),flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=OUT)
    parser.add_argument("--baseline-only",action="store_true")
    args = parser.parse_args()
    spec = load(SPEC)
    config = load(ROOT/spec["baseline_input"])
    materials = load(ROOT/spec["baseline_materials"])["materials"]
    proc = load(ROOT/spec["scan"]["source"])
    candidates,cases = selected_cases(spec,proc)
    if args.baseline_only:
        cases = cases[:1]
    sources = [SPEC,ROOT/spec["baseline_input"],ROOT/spec["baseline_materials"],ROOT/spec["scan"]["source"],Path(__file__),Path(__file__).with_name("physics.py")]
    write_json(args.output_dir/"run-inputs.json",dict(specification=spec,selected_process_cases=cases,candidate_count=len(candidates),
        hashes={str(p.relative_to(ROOT)).replace("\\","/"):digest(p) for p in sources},python=sys.version))
    results = []
    for name, overrides in cases:
        for mode in spec["simulation"]["activation"]:
            results.append(run_case(config,materials,spec,name,overrides,mode,args.output_dir))
    if not args.baseline_only:
        for label,scales in (("nife-low-cp",{"ernife_ci":(.75,1.)}),("nife-high-cp",{"ernife_ci":(1.25,1.)}),
                             ("nife-low-k",{"ernife_ci":(1.,.6)}),("nife-high-k",{"ernife_ci":(1.,1.4)})):
            results.append(run_case(config,materials,spec,label,cases[0][1],"pre_existing",args.output_dir,scales=scales))
        results.append(run_case(config,materials,spec,"latent-off",cases[0][1],"pre_existing",args.output_dir,latent=False))
        for mode in spec["simulation"]["activation"]:
            results.append(run_case(config,materials,spec,"dt-half",cases[0][1],mode,args.output_dir,dt_scale=.5))
    audit = deposition_audit(config,proc)
    comparisons = []
    for name,_ in cases:
        pair = [r for r in results if r["case_id"]==name]
        comparisons.append(dict(case_id=name,pre_existing_peak_c=pair[0]["peak_temperature_c"],progressive_peak_c=pair[1]["peak_temperature_c"],
            progressive_minus_pre_existing_c=pair[1]["peak_temperature_c"]-pair[0]["peak_temperature_c"]))
    gate = dict(stage="G-PHYSICS",gate_status="REVIEW",evidence_level="solver_result_unvalidated",
        thermal02_status="numerically_verified_physically_uncalibrated_baseline",thermal_1_allowed=False,formal_struct_0_allowed=False,
        deposition_mass_audit=audit,activation_comparison=comparisons,completed_case_count=len(results),
        process_candidate_count=len(candidates),sampled_process_count=len(cases),
        scan_status="baseline_only" if args.baseline_only else "finite_predeclared_sampling_completed",
        sampled_two_parent_solidus_cases=sum(r["two_parent_solidus_exceeded"] for r in results),
        plausible_fusion_found=False,continuous_domain_infeasibility_proven=False,
        maximum_energy_residual_pct=max(r["energy"]["residual_pct"] for r in results),
        blockers=["代理焊缝体积与送丝质量不闭合：先核实接头/填丝几何，禁止调 eta 追温度。",
                  "高温物性尤其 ERNiFe-CI 缺少本批次证据；当前只能进行情景敏感性。",
                  "真实填丝几何未进入求解器，0.2 的网格收敛不能自动覆盖激活空腔问题。",
                  "宏观截面、实测 I/U/v 和独立验证数据未取得。"],
        action="stop_calibration_and_reconcile_geometry_filler_and_process",results=results)
    write_json(args.output_dir/"G-PHYSICS.json",gate)
    print(json.dumps({"gate":"REVIEW","cases":len(results),"mass_ratio":audit["band_to_wire_volume_ratio"]}),flush=True)


if __name__ == "__main__":
    main()
