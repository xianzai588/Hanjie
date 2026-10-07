"""Preserve native manufacturing failures and the actual phase-input mismatch.

Reads saved inputs/results only. It does not run another structural variant or
promote a best unsuccessful iterate to an accepted manufacturing state.
"""
import gzip
import json
from pathlib import Path
import re
import shutil
import numpy as np
from mma_literature_profile import ROOT
from run_calculix_one_wing import history

OUT=ROOT/'output/review/native-manufacturing-stop-20261007'
RESULTS=ROOT/'simulation/competition-r4/results'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    runs=[]
    for folder in sorted(RESULTS.glob('calculix-one-wing-native-*')):
        execution=json.loads((folder/'execution.json').read_text()) if (folder/'execution.json').exists() else None
        metadata=json.loads((folder/'input.json').read_text()) if (folder/'input.json').exists() else {}
        log=(folder/'solver.log').read_text(errors='replace') if (folder/'solver.log').exists() else ''
        sta=(folder/'onewing.sta').read_text(errors='replace') if (folder/'onewing.sta').exists() else ''
        times=np.loadtxt(folder/'cluster-events.csv',delimiter=',',skiprows=1,ndmin=2)[:,0] if (folder/'cluster-events.csv').exists() else []
        complete=[];fail=[]
        for line in sta.splitlines():
            q=line.split()
            if len(q)!=7 or not q[0].isdigit():continue
            step=int(q[0]);unaccepted=q[2].endswith('U')
            if unaccepted:fail.append(step)
            elif abs(float(q[5])-1)<1e-7:complete.append(step)
        accepted_step=max(complete,default=0)
        accepted_time=float(times[accepted_step-2]) if accepted_step>=2 and accepted_step-2<len(times) else 0.
        row=dict(run=folder.name,execution=execution,
                 last_fully_completed_native_step=accepted_step,last_completed_actual_thermal_time_s=accepted_time,
                 native_restart_available=(folder/'onewing.rout').exists(),
                 native_error='*ERROR' in log,native_job_finished='Job finished' in log,
                 cold_mechanical_state_qualified=False,cutting_allowed=False,
                 representation=metadata.get('engineering_representation'),
                 phase_sampling=metadata.get('phase_sampling','whole-corner phase gate'),
                 reference_policy=metadata.get('reference_policy'),
                 raw_location=str(folder.relative_to(ROOT)),
                 unsuccessful_FRD_identity='best unsuccessful iterate only; not the last accepted state')
        runs.append(row)
        dest=OUT/folder.name;dest.mkdir(exist_ok=True)
        for name in ['input.json','execution.json','onewing.sta','solver.log','execution-note.json','representation-stop-note.json','cluster-events.csv']:
            if (folder/name).exists():shutil.copyfile(folder/name,dest/name)
    source=RESULTS/'mma-first-end80-r12-phase-front-dt0125-20261007'
    f=np.load(source/'thermal-fields.npz');e,m,V=f['e'],f['material'],f['volume_mm3']
    inp=json.loads((source/'input.json').read_text());Ts=inp['materials'][1]['fusion_enthalpy']['solidus_C']
    _,T,_,_=next(q for q in history(source) if abs(q[0]-.25)<1e-10)
    corner=(m==1)&(T[e].max(1)>Ts);gauss=(m==1)&(T[e].mean(1)>Ts)
    near=np.flatnonzero((m==1)&np.any(e==4793,axis=1))
    mismatch=dict(actual_time_s=.25,QT_solidus_C=Ts,
                  corner_removed_elements=int(corner.sum()),corner_removed_volume_mm3=float(V[corner].sum()),
                  gauss_removed_elements=int(gauss.sum()),gauss_removed_volume_mm3=float(V[gauss].sum()),
                  still_coherent_gauss_material_removed_by_corner_volume_mm3=float(V[corner&~gauss].sum()),
                  actual_tip_one_based_node=4794,
                  neighborhood=[dict(one_based_element=int(i+1),corners_C=T[e[i]].tolist(),native_one_point_C=float(T[e[i]].mean()),corner_removes=bool(corner[i]),gauss_removes=bool(gauss[i])) for i in near],
                  result='Input mismatch is demonstrated, but its correction plus cold-reference retention also failed at0.25s. It does not establish the sole cause or physical process failure.')
    selected=RESULTS/'calculix-one-wing-native-gauss-coldref-cold-20261007'
    dest=OUT/selected.name
    for name in ['onewing.inp','onewing.frd']:
        if (selected/name).exists() and not (dest/(name+'.gz')).exists():
            with (selected/name).open('rb') as a,gzip.open(dest/(name+'.gz'),'wb',compresslevel=6) as b:shutil.copyfileobj(a,b)
    record=dict(actual_runs=runs,phase_input_mismatch=mismatch,
                conclusion='Native plastic/deposition/cut restart functionality passed its independent fixed benchmark; the actual transient wing representation has not produced a restorable cold state. Stop additional native mesh, solver, numerical damping, contact or hardening variants. Do not use failed FRD fields for physical cutting or component position verification.',
                last_custom_accepted_recovery='simulation/competition-r4/results/mma-one-wing-finite-spectral-cold-t4-20261007/fields.npz at7.625s, not a cold/coherently joined state',
                full_manufacturing_chain_passed=False)
    (OUT/'native-stop-audit.json').write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps(dict(runs=len(runs),phase_input_mismatch=mismatch),indent=2,ensure_ascii=False))

if __name__=='__main__':main()
