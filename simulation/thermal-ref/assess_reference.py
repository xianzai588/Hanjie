"""审计实际 Elmer 输出并与冻结的 FVM 历史比较；不自动开放结构准入。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np

import elmer_reference as ref


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cooling_metric(times, temperatures):
    """只取最近一次完整冷却，末端未降到 500°C 时明确记为截尾。"""
    t800=t500=None
    for a,b,ta,tb in zip(times[:-1],times[1:],temperatures[:-1],temperatures[1:]):
        if ta<800<=tb:
            t800=t500=None
        if ta>=800>tb:
            t800=float(a+(b-a)*(ta-800)/(ta-tb)); t500=None
        if ta>=500>tb and t800 is not None:
            t500=float(a+(b-a)*(ta-500)/(ta-tb))
    return dict(t8_5_s=None if t800 is None or t500 is None else t500-t800,
                status="complete" if t800 is not None and t500 is not None else "right_censored" if np.max(temperatures)>=800 else "not_reached_800c")


def nonlinear_check(log, tolerance, expected_steps):
    groups=re.split(r"MAIN: Time:\s*\d+/\d+:",log)[1:]
    endings=[]
    for group in groups:
        values=re.findall(r"ComputeChange: NS .*?\(\s*[-+\d.Ee]+\s+([-+\d.Ee]+)\s*\)",group)
        endings.append(float(values[-1]) if values else float("inf"))
    return len(endings)==expected_steps and all(x<=tolerance for x in endings)


def export_vtu(out,mesh,field):
    nodes,conn=mesh["nodes"],mesh["conn"]-1
    root=ET.Element("VTKFile",type="UnstructuredGrid",version="0.1",byte_order="LittleEndian")
    grid=ET.SubElement(root,"UnstructuredGrid")
    piece=ET.SubElement(grid,"Piece",NumberOfPoints=str(len(nodes)),NumberOfCells=str(len(conn)))
    def array(parent,name,values,kind="Float64",components=None):
        attrs=dict(type=kind,Name=name,format="ascii")
        if components:
            attrs["NumberOfComponents"]=str(components)
        item=ET.SubElement(parent,"DataArray",attrs)
        item.text=" ".join(map(str,np.asarray(values).ravel()))
    array(ET.SubElement(piece,"Points"),"Points",nodes,components=3)
    cells=ET.SubElement(piece,"Cells")
    array(cells,"connectivity",conn,"Int32")
    array(cells,"offsets",np.arange(1,len(conn)+1)*8,"Int32")
    array(cells,"types",np.full(len(conn),12),"UInt8")
    pd=ET.SubElement(piece,"PointData",Scalars="Temperature_C")
    array(pd,"Temperature_C",field[:,0]); array(pd,"Nodal_peak_envelope_C",field[:,1])
    array(ET.SubElement(piece,"CellData"),"Material_ID",mesh["material"],"Int32")
    ET.ElementTree(root).write(out/"temperature.vtu",encoding="utf-8",xml_declaration=True)


def assess(out, verification, fvm_dirs):
    inputs=read(out/"run-inputs.json")
    spec=inputs["specification"]; rules=spec["acceptance"]
    config=inputs["config"]; p=config["process"]; path=config["heat_source_path"]
    execution=read(out/"execution.json")
    history=np.atleast_1d(np.genfromtxt(out/"history.csv",delimiter=",",names=True))
    sensors=np.atleast_2d(np.loadtxt(out/"sensors.dat"))
    steps=round(spec["solver"]["duration_s"]/spec["solver"]["time_step_s"])
    expected_times=np.arange(1,steps+1)*spec["solver"]["time_step_s"]
    complete=not inputs["smoke"] and len(history)==steps and len(sensors)==steps
    complete=bool(complete and np.allclose(history["time_s"],expected_times,atol=1.e-8,rtol=0) and np.allclose(sensors[:,0],expected_times,atol=1.e-8,rtol=0))
    duration=(path["source_end_s_mm"]-path["source_start_s_mm"])/p["travel_speed_mm_s"]
    expected_volume=inputs["bead_area_mm2"]*p["travel_speed_mm_s"]*np.minimum(history["time_s"],duration)
    expected_source=p["net_power_w"]*np.minimum(history["time_s"],duration)
    source_error=float(np.max(np.abs(history["source_j"]-expected_source)/np.maximum(expected_source,1.e-30)))
    volume_error=float(np.max(np.abs(history["deposit_volume_mm3"]-expected_volume)/np.maximum(expected_volume,1.e-30)))
    energy_pct=float(abs(history["residual_j"][-1])/max(expected_source[-1],1.e-30)*100)
    worst_energy_pct=float(np.max(np.abs(history["residual_j"])/np.maximum(expected_source,1.e-30))*100)
    verify=read(verification/"assessment.json")
    callback_key="simulation/thermal-ref/ReferenceCallbacks.F90"
    checks=dict(full_history=complete,solver_exit_success=execution["returncode"]==0,
                nonlinear_convergence=nonlinear_check((out/"solver.log").read_text(encoding="utf-8"),spec["solver"]["nonlinear_tolerance"],steps),
                declared_temperature_domain=bool(np.all(history["min_c"]>=19.9)&np.all(history["max_c"]<=3000.1)&np.all(np.isfinite(sensors))),
                component_verification=verify["passed"] and verify["callback_sha256"]==inputs["input_hashes"][callback_key],
                source_integral=source_error<=rules["source_relative_error_limit"],
                continuous_deposition_mass=volume_error<=rules["deposited_volume_relative_error_limit"],
                final_enthalpy_balance=energy_pct<=rules["energy_residual_pct_limit"],
                transient_enthalpy_balance=worst_energy_pct<=rules["energy_residual_pct_limit"],
                reference_spatial_convergence=False,activation_discretization_checked=False,physical_calibration=False)
    comparisons={}
    curves={}
    if complete:
        for fvm in fvm_dirs:
            data=read(fvm/"fixed-point-reconstructed-history.json")
            fvm_summary=read(fvm/"summary.json")
            times=np.array([row["time_s"] for row in data["rows"]])
            if times[0]>sensors[0,0]+1.e-8 or times[-1]<sensors[-1,0]-1.e-8:
                raise ValueError("FVM history does not cover Elmer output; extrapolation forbidden")
            point_results={}; curves[fvm.name]={}
            for col,point in enumerate(inputs["sensor_stencils"],1):
                name=point["name"]
                fvm_t=np.interp(sensors[:,0],times,[row[name] for row in data["rows"]])
                valid=np.ones(len(sensors),dtype=bool)
                if name=="weld_center":
                    # 出生前的空域没有材料温度，不能把虚单元值当测点曲线。
                    valid=sensors[:,0]>(point["coordinate"][0]-path["source_start_s_mm"])/p["travel_speed_mm_s"]+1.e-8
                et=sensors[valid,col]; ft=fvm_t[valid]; t=sensors[valid,0]
                delta=et-ft
                rms=float(np.sqrt(np.mean(delta**2))); peak_difference=float(abs(et.max()-ft.max()))
                point_results[name]=dict(rms_c=rms,maximum_same_time_difference_c=float(np.max(np.abs(delta))),
                    peak_difference_c=peak_difference,elmer_peak_c=float(et.max()),fvm_peak_c=float(ft.max()),
                    elmer_peak_time_s=float(t[np.argmax(et)]),fvm_peak_time_s=float(t[np.argmax(ft)]),
                    comparison_start_s=float(t[0]),elmer_cooling=cooling_metric(t,et),fvm_cooling=cooling_metric(t,ft),
                    diagnostic_threshold_pass=bool(rms<=rules["fixed_point_rms_limit_c"] and peak_difference<=rules["fixed_point_peak_limit_c"]))
                curves[fvm.name][name]=(t,et,ft)
            comparisons[fvm.name]=dict(points=point_results,absorbed_source_difference_j=float(history["source_j"][-1]-fvm_summary["energy"]["absorbed_source_j"]),
                                      evidence_use="Diagnostic only: mesh and activation schemes differ; no solver superiority inference.",
                                      history_sha256=ref.digest(fvm/"fixed-point-reconstructed-history.json"))
    field_path=out/f"field-{steps:05d}.dat"
    proxies={}
    if complete and field_path.exists():
        field=np.loadtxt(field_path)
        with np.load(out/"mesh-data.npz") as mesh:
            export_vtu(out,mesh,field)
            np.savez_compressed(out/"temperature-field.npz",nodes=mesh["nodes"],conn=mesh["conn"],material=mesh["material"],
                                volume=mesh["volume"],temperature_final=field[:,0],nodal_peak_envelope=field[:,1])
            # 节点各自历史峰值的插值是上包络，必须与同一时刻的熔化体积分开命名。
            envelope=field[mesh["conn"]-1,1].mean(axis=1)
            physics=ref.load(ref.ROOT/spec["thermal_properties"])
            for code,name in enumerate(ref.NAMES,1):
                mask=mesh["material"]==code
                threshold=physics["materials"][name]["phase_change"]["solidus_c"]
                proxies[name]=dict(solidus_c=threshold,nodal_peak_envelope_solidus_proxy_mm3=float(mesh["volume"][mask&(envelope>threshold)].sum()),
                                   nodal_peak_envelope_400c_proxy_mm3=float(mesh["volume"][mask&(envelope>400)].sum()))
    result=dict(stage="THERMAL-REF",case=inputs["case"],evidence_level="solver_result_unvalidated",
                execution_status="full_history_executed" if complete else "incomplete_or_rejected",
                acceptance_result="not_admitted",checks=checks,
                energy=dict(source_j=float(history["source_j"][-1]),loss_j=float(history["loss_j"][-1]),
                            birth_j=float(history["birth_j"][-1]),internal_energy_change_j=float(history["energy_change_j"][-1]),
                            residual_j=float(history["residual_j"][-1]),final_residual_pct=energy_pct,worst_transient_residual_pct=worst_energy_pct,
                            definition="Nodal enthalpy quadrature audited independently from native HeatSolver mass assembly.",source_relative_error=source_error),
                mass=dict(final_volume_mm3=float(history["deposit_volume_mm3"][-1]),maximum_relative_error=volume_error),
                comparisons=comparisons,geometry_proxies=proxies,
                geometry_proxy_boundary="Interpolated nodal peak envelope, not simultaneous melt volume, fusion, HAZ validation or measured weld profile.",
                discretization_differences=["Hex8 Galerkin with Elmer native lumped mass and secant heat capacity.",
                    "Birth source reconstruction matches nodal cold mass addition; this adapter requires component verification.",
                    "Continuous fill is homogenized in density and isotropic conductivity; partial-cell contact is not geometrically remeshed.",
                    "Pure dormant nodes are held at birth temperature; inactive mass and conductivity use a recorded epsilon."],
                thermal_1_allowed=False,formal_struct_0_allowed=False,
                next_action="Resolve native enthalpy/activation discretization audit, then perform reference mesh and activation sensitivity before judging FVM agreement.")
    ref.write_json(out/"assessment.json",result)
    if curves:
        plot(out,curves,inputs,history)
    return result


def plot(out,curves,inputs,history):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False})
    fig,axes=plt.subplots(3,2,figsize=(11,10),layout="constrained")
    for ax,point in zip(axes.flat,inputs["sensor_stencils"]):
        name=point["name"]
        for i,(level,points) in enumerate(curves.items()):
            t,et,ft=points[name]
            if i==0:
                ax.plot(t,et,color="#c44e52",lw=1.6,label=f"Elmer {inputs['case']}")
            ax.plot(t,ft,lw=1.2,ls="--" if i==0 else ":",label=f"FVM {level}")
        ax.set(title=name.replace('_',' '),xlabel="Time (s)",ylabel="Temperature (C)")
        ax.grid(alpha=.15); ax.legend(fontsize=8)
    ax=axes.flat[-1]
    ax.plot(history["time_s"],history["residual_j"],color="#555555")
    ax.set(title="Independent enthalpy balance defect",xlabel="Time (s)",ylabel="Energy defect (J)")
    ax.axhline(0,color="#aaaaaa",lw=.7); ax.grid(alpha=.15)
    fig.suptitle("THERMAL-REF / numerical diagnostic - NOT ADMITTED",fontsize=14)
    fig.savefig(out/"comparison.png",dpi=180)
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_dir",type=Path)
    parser.add_argument("--verification",type=Path,default=ref.HERE/"results/verification")
    args=parser.parse_args()
    fvmroot=ref.ROOT/"simulation/thermal-v5/results/boundary-neumann-plan6"
    result=assess(args.case_dir.resolve(),args.verification,[fvmroot/"NEST-F",fvmroot/"NEST-VF"])
    print(json.dumps({k:result[k] for k in ("execution_status","acceptance_result","checks","energy")},ensure_ascii=False),flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
