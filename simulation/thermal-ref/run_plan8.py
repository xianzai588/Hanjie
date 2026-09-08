"""最后一轮热机制诊断：复用既有回调，仅生成重放与常物性输入。"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np

import elmer_reference as ref
from run_plan7 import mechanism

PLAN=ref.ROOT/"project/thermal-partition-plan8.yaml"
RESULTS=ref.HERE/"results/plan8"


def prepare(out,constant=False):
    cfg=ref.load(PLAN); spec=ref.load(ref.SPEC)
    spec["solver"]["output_interval_steps"]=1
    record=ref.prepare(out,"REF-C",spec)
    offset=0. if constant else cfg["elmer_restart_s"]
    end=cfg["constant_control"]["end_s"] if constant else cfg["window_s"][1]
    steps=round((end-offset)/spec["solver"]["time_step_s"])
    (out/"case.sif").write_text(ref.sif(spec["solver"],steps),encoding="ascii")
    mechanism(out,preborn=constant,offset=offset)
    if constant:
        lines=(out/"reference.dat").read_text(encoding="ascii").splitlines()
        cursor=2; constants=[]
        for _ in range(3):
            header=lines[cursor].split(); count=int(header[4]); header[3]="0"
            table=np.array([[float(x) for x in line.split()] for line in lines[cursor+1:cursor+count+1]])
            cp=np.interp(150.,table[:,0],table[:,1]); k=np.interp(150.,table[:,0],table[:,2])
            lines[cursor]=" ".join(header)
            lines[cursor+1:cursor+count+1]=[f"{t:.16g} {cp:.16g} {k:.16g}" for t in table[:,0]]
            constants.append(dict(cp_j_kgk=float(cp),k_w_mk=float(k*1000)))
            cursor+=count+1
        (out/"reference.dat").write_text("\n".join(lines)+"\n",encoding="ascii")
        record["constant_materials"]=constants
    else:
        source=ref.HERE/"results/REF-C/field-00150.dat"
        mesh=np.load(out/"mesh-data.npz")
        checkpoint=RESULTS/"elmer-dynamic/restart-state.npz"
        ahash=lambda a:hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
        if source.exists():
            original=np.load(source.parent/"mesh-data.npz")
            for k in ("nodes","conn","material"):
                if not np.array_equal(original[k],mesh[k]):
                    raise ValueError("15 s重放网格不匹配")
            temperature=np.loadtxt(source)[:,0]; source_hash=ref.digest(source)
        else:
            saved=np.load(checkpoint)
            for k in ("nodes","conn","material"):
                if str(saved[k+"_sha256"])!=ahash(mesh[k]):
                    raise ValueError("15 s检查点网格不匹配")
            temperature=saved["temperature_c"]; source_hash=str(saved["source_sha256"])
        np.savetxt(out/"initial-temperature.dat",temperature,fmt="%.16g")
        np.savez_compressed(out/"restart-state.npz",temperature_c=temperature,time_s=offset,source_sha256=source_hash,
                            **{k+"_sha256":ahash(mesh[k]) for k in ("nodes","conn","material")})
        record["restart_sha256"]=source_hash
    record.update(stage="THERMAL-REF-PLAN8",preborn=constant,constant_properties=constant,restart_time_s=offset,end_time_s=end,local_steps=steps,
                  plan_sha256=ref.digest(PLAN),thermal_1_allowed=False,formal_struct_0_allowed=False)
    ref.write_json(out/"run-inputs.json",record)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["dynamic","constant"])
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--elmer-home",type=Path,default=ref.DEFAULT_HOME)
    args=parser.parse_args()
    out=(args.output_dir or RESULTS/f"elmer-{args.mode}").resolve()
    prepare(out,args.mode=="constant"); ref.run(out,args.elmer_home)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
