"""公共P0观测空间与材料分区账本；Plan 8结束后保留分歧，不自动准入。"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

import elmer_reference as ref
from assess_reference import read
from run_plan8 import PLAN, RESULTS


def weights(centres,ids,valid,point,material):
    """独立公共probe：同材料P0均值的仿射精确最小二乘，不调用任何求解器重构。"""
    candidates=np.flatnonzero((ids==material)&valid)
    distance=np.linalg.norm(centres[candidates]-point,axis=1)
    order=np.lexsort((candidates,distance)); count=min(12,len(candidates))
    if not count:
        raise ValueError("无活动同材料观测支撑")
    if distance[order[0]]<1.e-12:
        return candidates[order[:1]],np.ones(1)
    while True:
        selected=candidates[order[:count]]; offsets=centres[selected]-point
        A=np.column_stack([np.ones(count),offsets])
        if np.linalg.matrix_rank(A,tol=1.e-12)==4:
            break
        if count==len(candidates):
            raise ValueError("共同观测空间秩不足")
        count=min(len(candidates),count*2)
    d=distance[order[:count]]; diagonal=1/np.maximum(d,np.median(d)*1.e-6)**2
    w=np.linalg.solve(A.T@(diagonal[:,None]*A),[1.,0.,0.,0.])@(A.T*diagonal)
    if not np.allclose(w@A,[1,0,0,0],rtol=0,atol=1.e-9):
        raise ValueError("公共probe未达到仿射精度")
    return selected,w


def partition_summary(out):
    data=np.genfromtxt(out/"partition.csv",delimiter=",",names=True)
    H=np.column_stack([data[f"H_{m}_j"] for m in ("q235","qt","weld")])
    terms={key:np.column_stack([data[f"{key}_{m}_j"] for m in ("q235","qt","weld")]) for key in ("source","loss","birth","mix")}
    incoming=np.column_stack([data["weld_to_q235_j"],data["weld_to_qt_j"],-data["weld_to_q235_j"]-data["weld_to_qt_j"]])
    physical=terms["source"]-terms["loss"]+terms["birth"]+incoming-np.vstack([np.zeros(3),np.diff(H,axis=0)])
    discrete=physical-terms["mix"]
    result=dict(materials={},weld_to_qt_j=float(data["weld_to_qt_j"].sum()),weld_to_q235_j=float(data["weld_to_q235_j"].sum()),
                maximum_material_physical_step_discrepancy_j=float(np.max(abs(physical))),maximum_material_solver_discrete_step_residual_j=float(np.max(abs(discrete))))
    for j,name in enumerate(ref.NAMES):
        result["materials"][name]=dict(initial_enthalpy_j=float(H[0,j]),final_enthalpy_j=float(H[-1,j]),enthalpy_change_j=float(H[-1,j]-H[0,j]),
                                     **{key+"_j":float(value[:,j].sum()) for key,value in terms.items()},
                                     physical_enthalpy_discrepancy_j=float(physical[:,j].sum()),solver_discrete_residual_j=float(discrete[:,j].sum()))
    cumulative=np.column_stack([data["time_s"],H,np.cumsum(data["weld_to_qt_j"]),np.cumsum(data["weld_to_q235_j"]),np.cumsum(terms["source"].sum(axis=1)),np.cumsum(terms["loss"],axis=0)])
    np.savetxt(out/"partition-cumulative.csv",cumulative,delimiter=",",comments="",header="time_s,H_q235_j,H_qt_j,H_weld_j,weld_to_qt_j,weld_to_q235_j,source_total_j,loss_q235_j,loss_qt_j,loss_weld_j",fmt="%.15g")
    return result


def observations(directory,mode):
    eout,fout=directory/f"elmer-{mode}",directory/f"fvm-{mode}"
    emesh,fmesh=np.load(eout/"mesh-data.npz"),np.load(fout/"mesh-data.npz")
    ef,ff=np.load(eout/"window-fields.npz"),np.load(fout/"window-fields.npz")
    for k in ("s_edges","n_edges","z_edges"):
        if not np.array_equal(emesh[k],fmesh[k]):
            raise ValueError("公共观测网格不一致")
    if not np.allclose(ef["times"],ff["times"],atol=1.e-8,rtol=0):
        raise ValueError("公共观测时间不一致")
    fmap={tuple(index):i for i,index in enumerate(fmesh["index"])}
    fidx=np.array([fmap[tuple(index)] for index in emesh["index"]])
    if not np.allclose(ef["fraction"],ff["fraction"][:,fidx],atol=1.e-8,rtol=0):
        raise ValueError("公共观测出生状态不一致")
    ids=emesh["material"]; conn=emesh["conn"]-1; nodes=emesh["nodes"]
    if not np.array_equal(ids,fmesh["material"][fidx]):
        raise ValueError("共同控制体材料不一致")
    centres=nodes[conn].mean(axis=1); boxmap={tuple(index):i for i,index in enumerate(emesh["index"])}
    axes=[emesh[k] for k in ("s_edges","n_edges","z_edges")]
    cfg=ref.load(PLAN)
    nativepoints=ref.load(ref.ROOT/ref.load(ref.SPEC)["baseline"])["observation_points"]
    points=[(p["name"],np.array(p["coordinate_s_n_z_mm"]),p["material_id"]) for p in nativepoints]
    for i,n in enumerate(np.round(np.arange(-1.5,1.001,.1),10)):
        p=np.array([0.,n,round(n+1.,10)])
        index=tuple(np.searchsorted(a,x,side="right")-1 for a,x in zip(axes,p))
        cell=boxmap.get(index)
        if cell is not None:
            points.append((f"line_{i:02d}",p,int(ids[cell])))
    rows=[]
    e_native=np.loadtxt(eout/"sensors.dat"); f_native=np.loadtxt(fout/"sensors.dat")
    for t,et,ft,frac in zip(ef["times"],ef["temperature"],ff["temperature"],ef["fraction"]):
        # Hex8全盒均值等于八节点平均；共同P0盒固定，出生比例另列，不伪装为新网格。
        ep0=et[conn].mean(axis=1); fp0=ft[fidx]
        for name,p,material in points:
            if name.startswith("line_") and not any(abs(t-s)<1.e-8 for s in cfg["sample_times_s"]):
                continue
            index=tuple(np.searchsorted(a,x,side="right")-1 for a,x in zip(axes,p)); cell=boxmap[index]
            if frac[cell]<=0:
                common_e=common_f=native_e=native_f=float("nan")
            else:
                selected,w=weights(centres,ids,frac>0,p,material)
                common_e=float(w@ep0[selected]); common_f=float(w@fp0[selected])
                lo=nodes[conn[cell,0]]; dims=nodes[conn[cell,6]]-lo
                local=(p-lo)/dims
                native_e=float(np.prod(np.where(ref.CORNERS,local,1-local),axis=1)@et[conn[cell]])
                if name.startswith("line_"):
                    native_f=float("nan")
                else:
                    col=1+[x["name"] for x in nativepoints].index(name)
                    native_e=float(np.interp(t,e_native[:,0],e_native[:,col])); native_f=float(np.interp(t,f_native[:,0],f_native[:,col]))
            rows.append(dict(time_s=float(t),probe=name,s_mm=p[0],n_mm=p[1],z_mm=p[2],material_id=material,birth_fraction=float(frac[cell]),
                             elmer_common_c=common_e,fvm_common_c=common_f,delta_common_c=common_e-common_f,
                             elmer_native_c=native_e,fvm_native_c=native_f,delta_native_c=native_e-native_f))
    with (directory/f"common-probes-{mode}.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    summary={}
    for name,_,_ in points[:5]:
        selected=[r for r in rows if r["probe"]==name and np.isfinite(r["delta_common_c"])]
        e=np.array([r["elmer_common_c"] for r in selected]); f=np.array([r["fvm_common_c"] for r in selected])
        summary[name]=dict(common_peak_gap_c=float(abs(e.max()-f.max())),common_rms_c=float(np.sqrt(np.mean((e-f)**2))),
                           native_peak_gap_c=float(abs(max(r["elmer_native_c"] for r in selected)-max(r["fvm_native_c"] for r in selected))),
                           common_elmer_peak_c=float(e.max()),common_fvm_peak_c=float(f.max()))
    return summary


def assess(directory):
    parts={f"{solver}-{mode}":partition_summary(directory/f"{solver}-{mode}") for mode in ("dynamic","constant") for solver in ("elmer","fvm")}
    obs={mode:observations(directory,mode) for mode in ("dynamic","constant")}
    checks={mode:read(directory/f"elmer-{mode}/partition-assessment.json") for mode in ("dynamic","constant")}
    limits=ref.load(PLAN)["checks"]
    source_difference=max(abs(parts[f"elmer-{mode}"]["materials"][m]["source_j"]-parts[f"fvm-{mode}"]["materials"][m]["source_j"]) for mode in ("dynamic","constant") for m in ref.NAMES)
    checks_passed=all(c["complete"] and c["nonlinear_convergence"] and c["maximum_interface_pair_residual_j"]<limits["interface_reaction_balance_j"] for c in checks.values())
    checks_passed=checks_passed and checks["dynamic"]["replay_temperature_difference_c"]<limits["replay_temperature_tolerance_c"] and source_difference/3960.<limits["source_relative_error"]
    result=dict(stage="THERMAL-REF-PLAN8",route="B_no_physical_experiment",diagnostic_iterations_used=2,diagnostic_iterations_maximum=2,
                diagnostic_execution_checks_passed=bool(checks_passed),
                window_s=[18.,26.],partitions=parts,observations=obs,elmer_checks=checks,
                source_partition_maximum_difference_j=float(source_difference),
                further_thermal_diagnostic_allowed=False,ref_m_allowed=False,ref_f_allowed=False,ref_vf_allowed=False,
                thermal_1_allowed=False,formal_struct_0_allowed=False,evidence_level="solver_disagreement_physical_unvalidated",
                next_route="STRUCT-UNCERTAINTY_nonformal",experimental_data_required=False,
                energy_definitions="Report solver-discrete residual and physical enthalpy discrepancy separately; retain original physical 0.02% gate.",
                limits=["FE interface reactions include shared-node load/storage partition; sided face-gradient fluxes are not interchangeable with conservative FVM face fluxes.","Common P0 projection uses nominal C boxes and records birth fraction; cannot remove spatial field error.","Constant properties at 150 C with zero latent heat are a diagnostic control, not a calibrated material set."],plan_sha256=ref.digest(PLAN))
    ref.write_json(directory/"assessment.json",result)
    print({mode:{name:round(v["common_peak_gap_c"],3) for name,v in values.items()} for mode,values in obs.items()})
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--output-dir",type=Path,default=RESULTS)
    assess(parser.parse_args().output_dir)
