"""独立复算机制账本及成对消融结果；失败前置条件必须阻止加密。"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

import elmer_reference as ref
from assess_reference import read, nonlinear_check, cooling_metric
from run_plan7 import PLAN, RESULTS, heat, materials


def gaussian_mass_defect(mesh, old, new, time_s, config):
    """显式八点 Gauss 构造一致质量，再按原生算法缩放对角；不调用插件混合算子。"""
    conn=mesh["conn"]-1; ids=mesh["material"]
    coords=np.array([[a,b,c] for a in (-1.,1.) for b in (-1.,1.) for c in (-1.,1.)])/np.sqrt(3.)
    shapes=np.prod((1.+coords[:,None,:]*(2*ref.CORNERS[None,:,:]-1))/2,axis=2)
    result=[]
    for index,m in enumerate(materials(),1):
        mask=ids==index; c=conn[mask]; delta=new[c]-old[c]
        mid=(new[c]+old[c])/2
        cap=np.interp(mid,m["knots"],m["cp"])+m["latent"]/(m["tl"]-m["ts"])*((mid>=m["ts"])&(mid<m["tl"]))
        np.divide(heat(new[c],m)-heat(old[c],m),delta,out=cap,where=np.abs(delta)>1.e-7)
        # 每个积分点权重为参考体积的1/8；保留整矩阵以独立检查对角缩放。
        matrix=np.einsum("eq,qi,qj->eij",cap@shapes.T,shapes,shapes)/8
        diagonal=np.diagonal(matrix,axis1=1,axis2=2)
        lump=diagonal*(matrix.sum(axis=(1,2))/diagonal.sum(axis=1))[:,None]
        fill=np.ones(mask.sum())
        if index==3:
            left=mesh["nodes"][c[:,0],0]
            dx=mesh["nodes"][c[:,1],0]-left
            path=config["heat_source_path"]
            front=min(path["source_end_s_mm"],path["source_start_s_mm"]+time_s*config["process"]["travel_speed_mm_s"])
            fill=np.maximum(1.e-8,np.clip((front-left)/dx,0,1))
        result.append(float(np.sum(m["rho"]*mesh["volume"][mask]*fill*np.sum((lump-cap/8)*delta,axis=1))))
    return result


def source_off(out):
    cfg=ref.load(PLAN)["source_off"]
    record=read(out/"run-inputs.json")
    ledger=np.genfromtxt(out/"mechanism-ledger.csv",delimiter=",",names=True)
    sensors=np.loadtxt(out/"sensors.dat")
    baseline=ref.HERE/"results/REF-C"
    original=np.loadtxt(baseline/"sensors.dat")
    matching=np.array([np.interp(sensors[:,0],original[:,0],original[:,j]) for j in range(1,6)]).T
    temperature_error=float(np.max(np.abs(sensors[:,1:]-matching)))
    mesh=np.load(out/"mesh-data.npz")
    dt=record["specification"]["solver"]["time_step_s"]
    checks=[]
    for t in np.arange(39.9,40.51,.1):
        step=round((t-cfg["restart_time_s"])/dt)
        old=np.loadtxt(out/f"field-{step-1:05d}.dat")[:,0]
        new=np.loadtxt(out/f"field-{step:05d}.dat")[:,0]
        native=ledger[step-1]
        prediction=gaussian_mass_defect(mesh,old,new,t,record["config"])
        checks.append(dict(time_s=round(t,1),measured_step_defect_j=float(native["step_defect_j"]),
                           gaussian_mass_prediction_j=sum(prediction),by_material_j=dict(zip(ref.NAMES,prediction)),
                           unexplained_j=float(native["step_defect_j"]-sum(prediction)),
                           gaussian_vs_callback_j=float(sum(prediction)-native["predicted_capacity_mix_j"])))
    config=record["config"]; p=config["process"]; path=config["heat_source_path"]
    end=(path["source_end_s_mm"]-path["source_start_s_mm"])/p["travel_speed_mm_s"]
    t=ledger["time_s"]
    powered=t-dt<end-1.e-10
    source_error=float(np.max(np.abs(ledger["source_step_j"]-p["net_power_w"]*dt*powered)))
    born=materials()[2]["rho"]*record["bead_area_mm2"]*p["travel_speed_mm_s"]*np.maximum(0,np.minimum(t,end)-np.minimum(t-dt,end))
    mass_error=float(np.max(np.abs(ledger["physical_birth_mass_kg"]-born)))
    centers=path["source_start_s_mm"]+p["travel_speed_mm_s"]*(t-dt/2)
    maximum_unexplained=float(np.max(np.abs(ledger["unexplained_step_j"])))
    complete=len(ledger)==record["local_steps"] and read(out/"execution.json")["returncode"]==0
    converged=nonlinear_check((out/"solver.log").read_text(encoding="utf-8"),record["specification"]["solver"]["nonlinear_tolerance"],record["local_steps"])
    result=dict(complete=bool(complete),nonlinear_convergence=converged,replay_sensor_maximum_difference_c=temperature_error,
                source_step_maximum_error_j=source_error,birth_step_maximum_mass_error_kg=mass_error,
                source_center_maximum_error_mm=float(np.max(np.abs(ledger["source_center_s_mm"]-centers))),
                maximum_unexplained_step_j=maximum_unexplained,
                maximum_unexplained_time_s=float(t[np.argmax(np.abs(ledger["unexplained_step_j"]))]),
                unexplained_step_energy_limit_j=cfg["unexplained_step_energy_limit_j"],gauss_cross_checks=checks,
                source_off_mechanism_identified=bool(temperature_error<=cfg["replay_temperature_tolerance_c"] and max(abs(x["unexplained_j"]) for x in checks)<cfg["unexplained_step_energy_limit_j"]),
                source_off_explained=bool(complete and converged and temperature_error<=cfg["replay_temperature_tolerance_c"] and source_error<1.e-8 and mass_error<1.e-14 and maximum_unexplained<cfg["unexplained_step_energy_limit_j"] and max(abs(x["gaussian_vs_callback_j"]) for x in checks)<1.e-8),
                finding="The 40.1 s jump is quantitatively accounted for by spatial mixing of temporal secant heat capacity in native diagonal-scaled lumped Hex8 mass. No missing/double source or birth step is observed. This diagnoses the defect; it does not remove it.")
    ref.write_json(out/"assessment.json",result)
    return result


def pair_metrics(elmer,fvm,points,preborn):
    et=np.loadtxt(elmer/"sensors.dat"); ft=np.loadtxt(fvm/"sensors.dat")
    if et.shape!=ft.shape or et.shape[0]!=600 or not np.allclose(et[:,0],ft[:,0],atol=1.e-8,rtol=0):
        raise ValueError("成对诊断必须有同时间的完整600步")
    if any(read(path/"run-inputs.json").get("preborn",False)!=preborn for path in (elmer,fvm)):
        raise ValueError("禁止动态出生与预出生历史交叉配对")
    rows={}
    for col,point in enumerate(points,1):
        name=point["name"]
        mask=np.ones(len(et),bool) if preborn or name!="weld_center" else et[:,0]>20.+1.e-8
        t,e,f=et[mask,0],et[mask,col],ft[mask,col]
        rows[name]=dict(rms_c=float(np.sqrt(np.mean((e-f)**2))),peak_difference_c=float(abs(e.max()-f.max())),
                        elmer_peak_c=float(e.max()),fvm_peak_c=float(f.max()),elmer_peak_time_s=float(t[e.argmax()]),fvm_peak_time_s=float(t[f.argmax()]),
                        elmer_cooling=cooling_metric(t,e),fvm_cooling=cooling_metric(t,f))
        common=et[:,0]>20.+1.e-8 if name=="weld_center" else np.ones(len(et),bool)
        rows[name]["common_window_rms_c"]=float(np.sqrt(np.mean((et[common,col]-ft[common,col])**2)))
    return rows


def welding_audit(out,preborn):
    h=np.genfromtxt(out/"history.csv",delimiter=",",names=True)
    cfg=ref.load(ref.ROOT/ref.load(ref.SPEC)["inputs"])
    execution=read(out/"execution.json")
    total=19800.; mass_density=materials()[2]["rho"]
    vol=read(ref.HERE/"results/REF-C/run-inputs.json")["bead_area_mm2"]*60.
    expected_volume=np.full(len(h),vol) if preborn else vol*np.minimum(h["time_s"]/40.,1.)
    result=dict(complete=bool(len(h)==600 and execution["returncode"]==0 and np.allclose(h["time_s"],np.arange(1,601)*.1,atol=1.e-8,rtol=0)),
                source_total_j=float(h["source_j"][-1]),source_relative_error=float(np.max(np.abs(h["source_j"]-cfg["process"]["net_power_w"]*np.minimum(h["time_s"],40.))/np.maximum(h["source_j"],1.e-30))),
                final_weld_mass_kg=float(h["deposit_volume_mm3"][-1]*mass_density),mass_relative_error=float(np.max(np.abs(h["deposit_volume_mm3"]-expected_volume)/expected_volume)),
                added_weld_mass_kg=0. if preborn else float(h["deposit_volume_mm3"][-1]*mass_density),
                final_enthalpy_defect_j=float(h["residual_j"][-1]),final_enthalpy_defect_pct=float(abs(h["residual_j"][-1])/total*100),
                maximum_transient_defect_pct=float(np.max(np.abs(h["residual_j"])/np.maximum(h["source_j"],1.e-30))*100))
    if (out/"solver.log").exists():
        result["nonlinear_convergence"]=nonlinear_check((out/"solver.log").read_text(encoding="utf-8"),1.e-8,600)
    return result


def assess(directory):
    born=read(directory/"birth/assessment.json")
    switch=source_off(directory/"source-off")
    points=ref.load(ref.ROOT/ref.load(ref.SPEC)["baseline"])["observation_points"]
    dynamic=ref.HERE/"results/REF-C"
    mesh=np.load(directory/"preborn-elmer/mesh-data.npz")
    grid_checks={}
    for mode in ("dynamic","preborn"):
        axes=np.load(directory/f"fvm-{mode}/grid-axes.npz")
        grid_checks[mode]=all(np.array_equal(mesh[k],axes[k]) for k in ("s_edges","n_edges","z_edges"))
    if not all(grid_checks.values()):
        raise ValueError("成对C级消融网格边界不一致")
    pairs=dict(dynamic=pair_metrics(dynamic,directory/"fvm-dynamic",points,False),preborn=pair_metrics(directory/"preborn-elmer",directory/"fvm-preborn",points,True))
    audits={name:welding_audit(path,preborn) for name,path,preborn in [("elmer_dynamic",dynamic,False),("elmer_preborn",directory/"preborn-elmer",True),("fvm_dynamic",directory/"fvm-dynamic",False),("fvm_preborn",directory/"fvm-preborn",True)]}
    components=read(directory/"components/assessment.json")
    component_ok=components["passed"] and components["callback_sha256"]==ref.digest(ref.HERE/"ReferenceCallbacks.F90")
    component_ok=component_ok and all(nonlinear_check((directory/"components"/name/"solver.log").read_text(encoding="utf-8"),1.e-10,1 if name=="interface" else 3) for name in ("interface","latent","birth"))
    result=dict(stage="THERMAL-REF-PLAN7",diagnostic_iteration=1,maximum_diagnostic_iterations=2,
                physical_parameters_retuned=False,birth_only_all_passed=born["birth_only_all_passed"],source_off_explained=switch["source_off_explained"],
                source_off_mechanism_identified=switch["source_off_mechanism_identified"],
                native_component_checks_passed=component_ok,
                same_grid_axes=grid_checks,comparisons=pairs,welding_audits=audits,
                preborn_peak_gap_reduction_pct={name:100*(1-pairs["preborn"][name]["peak_difference_c"]/pairs["dynamic"][name]["peak_difference_c"]) for name in ("weld_center","qt_near_interface")},
                ref_m_allowed=bool(born["birth_only_all_passed"] and switch["source_off_explained"]),ref_m_executed=False,ref_f_allowed=False,ref_vf_allowed=False,
                thermal_1_allowed=False,formal_struct_0_allowed=False,
                evidence_limits=["Matched C/C ablation changes both activation and initial weld enthalpy inventory; it does not alone isolate contact geometry.","Historical C/VF errors include spatial-resolution differences; no verdict assigning solver correctness.","Diagnosed enthalpy defect is retained, not subtracted to manufacture an energy pass."],
                next_action="At most one further targeted enthalpy-consistency or interface/interpolation diagnostic; if near-field disagreement persists, use thermocouple data to arbitrate. No eta retuning or unrestricted refinement.",
                plan_sha256=ref.digest(PLAN))
    ref.write_json(directory/"assessment.json",result)
    return result


def plot(directory):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig,axes=plt.subplots(2,2,figsize=(12,8),layout="constrained")
    fig.suptitle("Plan 7 | Mechanism isolation on matched C grids",fontsize=16)
    runs=[("Elmer dynamic",ref.HERE/"results/REF-C","#0072B2","-"),
          ("FVM dynamic",directory/"fvm-dynamic","#D55E00","-"),
          ("Elmer preborn",directory/"preborn-elmer","#0072B2","--"),
          ("FVM preborn",directory/"fvm-preborn","#D55E00","--")]
    for ax,col,title in ((axes[0,0],1,"Weld center"),(axes[0,1],2,"QT near interface")):
        for label,path,color,style in runs:
            data=np.loadtxt(path/"sensors.dat")
            mask=data[:,0]>20.+1.e-8 if col==1 and "dynamic" in label else np.ones(len(data),bool)
            ax.plot(data[mask,0],data[mask,col],color=color,ls=style,lw=1.6,label=label)
        ax.set(title=title,xlabel="Time (s)",ylabel="Temperature (°C)",xlim=(0,60))
        ax.legend(fontsize=8,loc="upper right")
    ax=axes[1,0]
    ledger=np.genfromtxt(directory/"source-off/mechanism-ledger.csv",delimiter=",",names=True)
    keep=(ledger["time_s"]>=39.)&(ledger["time_s"]<=41.)
    t=ledger["time_s"][keep]
    ax.plot(t,ledger["step_defect_j"][keep],color="#0072B2",label="Measured step defect",lw=2)
    ax.plot(t,ledger["predicted_capacity_mix_j"][keep],color="#D55E00",label="Native mass-mixing prediction",marker="o",ms=4,fillstyle="none",ls="none")
    ax.axvline(40.,color="0.5",ls=":",label="Source and birth end")
    ax.set(title="40 s switch: defect remains in the ledger",xlabel="Time (s)",ylabel="Step energy defect (J)")
    ax.legend(fontsize=8)
    ax=axes[1,1]
    for name,label,color in (("constant","Constant cp, 150°C","#009E73"),("nominal-150","Variable cp, 150°C","#0072B2"),("nominal-1500","Variable cp, 1500°C (partial)","#D55E00")):
        d=np.genfromtxt(directory/"birth"/name/"birth-audit.csv",delimiter=",",names=True)
        values=np.abs(d["step_defect_j"])
        ax.plot(d["time_s"],np.where(values>0,values,np.nan),label=label,color=color,lw=1.5)
    ax.axhline(1.e-7,color="0.3",ls="--",label="Frozen step limit")
    ax.axvline(1.1,color="#D55E00",ls=":",lw=1)
    ax.set(title="Birth only: zero source / conduction / surface loss",xlabel="Time (s)",ylabel="Absolute step defect (J)",yscale="log",xlim=(0,4.2))
    ax.legend(fontsize=8,loc="center right")
    for ax in axes.flat:
        ax.grid(alpha=.18)
        ax.spines[["top","right"]].set_visible(False)
    fig.savefig(directory/"mechanism-diagnostics.png",dpi=180,facecolor="white")
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=RESULTS)
    parser.add_argument("--source-off-only",action="store_true")
    args=parser.parse_args()
    result=source_off(args.output_dir/"source-off") if args.source_off_only else assess(args.output_dir)
    if not args.source_off_only:
        plot(args.output_dir)
    print({k:v for k,v in result.items() if isinstance(v,(bool,str,int,float))})
    return 0


if __name__=="__main__":
    raise SystemExit(main())
