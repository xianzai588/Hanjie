"""Plan 7：原生 Elmer 的零传热出生、40 s 重放及预出生机制隔离。"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

import elmer_reference as ref

PLAN = ref.ROOT / "project/thermal-mechanism-plan7.yaml"
RESULTS = ref.HERE / "results/plan7"


def heat(t, material, offset=0.):
    """独立积分分段线性比热；焓零点平移用来检验非零出生焓。"""
    t = np.asarray(t)
    knots, cp = material["knots"], material["cp"]
    h = np.full(t.shape, offset, dtype=float)
    h += cp[0] * np.minimum(t-knots[0], 0)
    for a, b, ca, cb in zip(knots[:-1], knots[1:], cp[:-1], cp[1:]):
        d = np.clip(t-a, 0, b-a)
        h += ca*d + .5*(cb-ca)/(b-a)*d*d
    h += cp[-1]*np.maximum(t-knots[-1], 0)
    return h + material["latent"]*np.clip((t-material["ts"])/(material["tl"]-material["ts"]), 0, 1)


def materials():
    spec = ref.load(ref.SPEC)
    return ref.material_data(ref.load(ref.ROOT/spec["material_input"]), ref.load(ref.ROOT/spec["thermal_properties"]))


def mechanism(out, preborn=False, offset=0., gauge=0.):
    (out/"mechanism.dat").write_text(f"{int(preborn)} {offset} {gauge} 1\n", encoding="ascii")


def require_refinement(case, evidence=RESULTS):
    """准入发生在网格生成之前；缺证据、旧插件证据和失败结果均拒绝。"""
    if case=="REF-C":
        return
    if case!="REF-M":
        raise ValueError("Plan 7 禁止 REF-F/VF；只允许前置通过后的 C→M")
    final_diagnostic=evidence.parent/"plan8/assessment.json"
    if final_diagnostic.exists():
        last=json.loads(final_diagnostic.read_text(encoding="utf-8"))
        if last.get("ref_m_allowed") is not True:
            raise ValueError("REF-M 前置未通过：Plan 8诊断预算已用尽，保留分歧并转入非正式结构不确定性路线")
    try:
        birth_result=json.loads((evidence/"birth/assessment.json").read_text(encoding="utf-8"))
        switch=json.loads((evidence/"source-off/assessment.json").read_text(encoding="utf-8"))
        switch_input=json.loads((evidence/"source-off/run-inputs.json").read_text(encoding="utf-8"))
    except (OSError,ValueError) as exc:
        raise ValueError("REF-M 缺少 Plan 7 出生与40 s审计证据") from exc
    cases=birth_result.get("cases",[])
    current=ref.digest(ref.HERE/"ReferenceCallbacks.F90")
    spec=ref.load(ref.SPEC)
    frozen=[ref.SPEC,*[ref.ROOT/spec[k] for k in ("baseline","inputs","process_input","material_input","thermal_properties")]]
    input_hashes=switch_input.get("input_hashes",{})
    passed=(birth_result.get("birth_only_all_passed") is True and switch.get("source_off_explained") is True
            and {c.get("case") for c in cases}=={"constant","nominal-150","nominal-1500","gauge-1500"}
            and all(c.get("passed") is True and c.get("callback_sha256")==current and c.get("plan_sha256")==ref.digest(PLAN) for c in cases)
            and input_hashes.get("simulation/thermal-ref/ReferenceCallbacks.F90")==current
            and all(input_hashes.get(p.relative_to(ref.ROOT).as_posix())==ref.digest(p) for p in frozen))
    if not passed:
        raise ValueError("REF-M 前置未通过或证据已失效：birth-only 全通过且40 s严格审计通过才可加密")


def birth_case(out, home, hot, constant=False, gauge=0.):
    cfg = ref.load(PLAN)["birth_only"]
    out.mkdir(parents=True, exist_ok=False)
    mesh = out/"mesh"; mesh.mkdir()
    nodes = np.array([[x,y,z] for x in (-1.,0.,1.) for y in (0.,1.) for z in (0.,1.)])
    conn = np.array([[4*i+j for j in (1,5,7,3,2,6,8,4)] for i in range(2)])
    ids = np.array([2,3])
    faces, meta = [], []
    for e in range(2):
        for axis in range(3):
            for sign in (-1,1):
                if axis == 0 and ((e == 0 and sign == 1) or (e == 1 and sign == -1)):
                    continue
                faces.append(conn[e, ref.FACE_NODES[axis,sign]])
                meta.append([e+1,0,axis+1,sign,1,0,0,0])
    nb = len(faces)
    np.savetxt(mesh/"mesh.nodes", np.column_stack([np.arange(1,13),np.full(12,-1),nodes]), fmt="%.16g")
    np.savetxt(mesh/"mesh.elements", np.column_stack([np.arange(1,3),ids,np.full(2,808),conn]), fmt="%d")
    np.savetxt(mesh/"mesh.boundary", np.column_stack([np.arange(1,nb+1),np.ones(nb),np.array(meta)[:,0],np.zeros(nb),np.full(nb,404),faces]), fmt="%d")
    (mesh/"mesh.header").write_text(f"12 2 {nb}\n2\n808 2\n404 {nb}\n", encoding="ascii")
    mats = materials()
    for m in mats:
        m["k"] = np.zeros_like(m["k"])
        if constant:
            m["cp"] = np.full_like(m["cp"], m["cp"][0]); m["latent"] = 0.
    eps = ref.load(ref.SPEC)["solver"]["inactive_fraction"]
    with (out/"reference.dat").open("w", encoding="ascii") as f:
        f.write(f"12 2 {nb} 1\n0 .25 0 1 {hot} 20 20 0 0 1 1 1 1 {eps} 1\n")
        for m in mats:
            f.write(f"{m['rho']} {m['ts']} {m['tl']} {m['latent']} {len(m['knots'])}\n")
            np.savetxt(f,np.column_stack([m["knots"],m["cp"],m["k"]]),fmt="%.16g")
        for e in range(2):
            f.write(" ".join(map(str,[ids[e],e-1,1,1,*conn[e]]))+"\n")
        np.savetxt(f,np.column_stack([meta,faces]),fmt="%.16g")
        f.write(" ".join(map(str,[1,*conn[0],*([.125]*8)]))+"\n")
    settings = ref.load(ref.SPEC)["solver"].copy()
    settings.update(time_step_s=cfg["time_step_s"], nonlinear_tolerance=1.e-10, nonlinear_iterations=80)
    (out/"case.sif").write_text(ref.sif(settings,round(cfg["duration_s"]/cfg["time_step_s"]),hot),encoding="ascii")
    mechanism(out,gauge=gauge)
    definition = dict(hot_parent_c=hot, cold_birth_c=20., constant_cp=constant, enthalpy_gauge_j_kg=gauge,
                      source_w=0., conductivity_w_mk=0., convection_w_m2k=0., emissivity=0.,
                      parent_volume_mm3=1., final_weld_volume_mm3=1., speed_mm_s=.25,
                      inactive_fraction=eps, callback_sha256=ref.digest(ref.HERE/"ReferenceCallbacks.F90"),
                      plan_sha256=ref.digest(PLAN),
                      material_tables=[{k:np.asarray(v).tolist() for k,v in m.items()} for m in mats])
    ref.write_json(out/"run-inputs.json",definition)
    failure = None
    try:
        ref.run(out,home)
    except RuntimeError as exc:
        if not (out/"execution.json").exists():
            raise
        failure = str(exc)
    ledger = np.atleast_1d(np.genfromtxt(out/"mechanism-ledger.csv",delimiter=",",names=True))
    if len(ledger)==0:
        result=dict(**definition,steps=0,execution_failure=failure or "No completed steps",passed=False)
        ref.write_json(out/"assessment.json",result)
        return result
    times = ledger["time_s"]
    expected_mass = mats[2]["rho"]*np.diff(np.minimum(np.r_[0.,times],cfg["birth_end_s"])/cfg["birth_end_s"])
    effective_mass = expected_mass.copy(); effective_mass[0] -= mats[2]["rho"]*eps
    theoretical_birth = effective_mass*heat(20.,mats[2],gauge)
    # 初始虚质量单列；以已知初始热库存归一化，避免无热源时除零。
    initial_t = np.full(12,20.); initial_t[conn[0]-1] = hot
    initial_energy = float(mats[1]["rho"]*heat(hot,mats[1],gauge) +
                           mats[2]["rho"]*eps*np.mean(heat(initial_t[conn[1]-1],mats[2],gauge)))
    field_energy = []
    for step in range(1,len(times)+1):
        t = np.loadtxt(out/f"field-{step:05d}.dat")[:,0]
        fill = max(eps,min(times[step-1]/cfg["birth_end_s"],1.))
        field_energy.append(sum(mats[m-1]["rho"]*f*np.mean(heat(t[c-1],mats[m-1],gauge)) for m,f,c in zip(ids,[1.,fill],conn)))
    change = np.diff(np.r_[initial_energy,field_energy])
    defect = theoretical_birth-change
    cumulative = np.cumsum(defect)
    np.savetxt(out/"birth-audit.csv",np.column_stack([np.arange(1,len(times)+1),times,expected_mass,effective_mass,theoretical_birth,change,theoretical_birth,defect,cumulative]),delimiter=",",comments="",
               header="step,time_s,birth_mass_kg,effective_birth_mass_kg,birth_enthalpy_j,FE_enthalpy_change_j,expected_change_j,step_defect_j,cumulative_defect_j",fmt="%.15g")
    max_step = float(np.max(np.abs(defect)))
    relative = float(np.max(np.abs(cumulative))/abs(initial_energy))
    mass_error = float(np.max(np.abs(ledger["physical_birth_mass_kg"]-expected_mass))/mats[2]["rho"])
    observer_error = float(np.max(np.abs(defect-ledger["step_defect_j"])))
    result = dict(**definition,steps=len(times),execution_failure=failure,initial_enthalpy_j=initial_energy,maximum_step_defect_j=max_step,
                  maximum_cumulative_defect_j=float(np.max(np.abs(cumulative))),maximum_cumulative_relative_defect=relative,
                  physical_mass_relative_error=mass_error,independent_vs_observer_error_j=observer_error,
                  maximum_unexplained_step_j=float(np.max(np.abs(ledger["unexplained_step_j"]))),
                  passed=bool(failure is None and len(times)==round(cfg["duration_s"]/cfg["time_step_s"]) and max_step<=cfg["step_absolute_energy_limit_j"] and relative<=cfg["cumulative_relative_energy_limit"] and mass_error<=cfg["physical_mass_relative_limit"] and observer_error<1.e-10))
    ref.write_json(out/"assessment.json",result)
    return result


def birth(out, home):
    results=[]
    for name,hot,constant,gauge in [("constant",150.,True,0.),("nominal-150",150.,False,0.),("nominal-1500",1500.,False,0.),("gauge-1500",1500.,False,12345.)]:
        result=birth_case(out/name,home,hot,constant,gauge)
        results.append(dict(case=name,**result)); print(name,result["passed"],result.get("maximum_step_defect_j"),flush=True)
    summary=dict(cases=results,birth_only_all_passed=all(r["passed"] for r in results),scope="Global enthalpy audit; shared FE nodes still share temperature at zero conductivity.")
    ref.write_json(out/"assessment.json",summary)
    return summary


def prepare_welding(out, mode):
    spec=ref.load(ref.SPEC)
    record=ref.prepare(out,"REF-C",spec)
    record.update(stage="THERMAL-REF-PLAN7",diagnostic=mode,thermal_1_allowed=False,formal_struct_0_allowed=False)
    if mode=="source-off":
        cfg=ref.load(PLAN)["source_off"]
        offset=cfg["restart_time_s"]
        source=ref.HERE/"results/REF-C"/f"field-{round(offset/spec['solver']['time_step_s']):05d}.dat"
        # Git 保留紧凑检查点；原始中间场可删除，但重放不能静默退回冷启动。
        checkpoint=RESULTS/"source-off/restart-state.npz"
        current=np.load(out/"mesh-data.npz")
        array_hash=lambda value: hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()
        if source.exists():
            t=np.loadtxt(source)[:,0]
            baseline=np.load(source.parent/"mesh-data.npz")
            for name in ("nodes","conn","material"):
                if not np.array_equal(baseline[name],current[name]):
                    raise ValueError(f"重放网格 {name} 已改变")
            source_hash=ref.digest(source)
        else:
            with np.load(checkpoint) as saved:
                if float(saved["time_s"])!=offset:
                    raise ValueError("检查点时间与重放计划不一致")
                for name in ("nodes","conn","material"):
                    if str(saved[name+"_sha256"])!=array_hash(current[name]):
                        raise ValueError(f"检查点网格 {name} 不匹配")
                t=saved["temperature_c"].copy(); source_hash=str(saved["source_sha256"])
        if len(t)!=record["nodes"]:
            raise ValueError("重放网格与原始温度不匹配")
        np.savez_compressed(out/"restart-state.npz",temperature_c=t,time_s=offset,source_sha256=source_hash,
                            **{name+"_sha256":array_hash(current[name]) for name in ("nodes","conn","material")})
        np.savetxt(out/"initial-temperature.dat",t,fmt="%.16g")
        steps=round((cfg["end_time_s"]-offset)/spec["solver"]["time_step_s"])
        (out/"case.sif").write_text(ref.sif(spec["solver"],steps),encoding="ascii")
        mechanism(out,offset=offset)
        record.update(restart_time_s=offset,restart_temperature_source=str(source.relative_to(ref.ROOT)),restart_sha256=source_hash,local_steps=steps)
    else:
        mechanism(out,preborn=True)
        record.update(initial_temperature_c=150.,preborn=True,initial_state_note=ref.load(PLAN)["preborn"]["initial_state"])
    ref.write_json(out/"run-inputs.json",record)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["birth","source-off","preborn-elmer"])
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--elmer-home",type=Path,default=ref.DEFAULT_HOME)
    args=parser.parse_args()
    out=(args.output_dir or RESULTS/args.mode).resolve()
    if args.mode=="birth":
        birth(out,args.elmer_home)
    else:
        prepare_welding(out,args.mode)
        ref.run(out,args.elmer_home)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
