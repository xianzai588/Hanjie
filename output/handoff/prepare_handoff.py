"""Read-only checkpoint preflight and bounded cloud handoff packaging."""
from pathlib import Path
import argparse,json,zipfile
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'simulation/competition-r4/results'
DEST=ROOT/'output/handoff'
CASES=[('8p-E285-k2500-f2-bore008-h1125-dt0125-s025',11068,60492),
       ('8p-E285-k2500-f2-bore008-h085-dt0125-s025',53020,40856),
       ('8p-E285-k2500-f2-bore008-h1125-dt00625-s0125',52148,60764)]


def verify():
    rows=[]
    for case,wrapper,solver in CASES:
        folder=OUT/case;p=folder/'continuation-checkpoint.npz';before=p.stat()
        with np.load(p,allow_pickle=False) as src:data={k:src[k] for k in src.files}
        meta=json.loads(data['metadata'].item());inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
        with np.load(folder/'mesh.npz',allow_pickle=False) as mesh:
            geometry=np.array_equal(data['x'],mesh['x']) and np.array_equal(data['e'],mesh['e'])
        after=p.stat()
        stable=(before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
        finite=all(np.all(np.isfinite(v)) for k,v in data.items() if v.dtype.kind in 'fci')
        checks=dict(all_npz_members_readable=True,metadata_matches_input=meta['inputs']==inp,
            saved_geometry_matches_mesh=geometry,all_numeric_members_finite=finite,
            file_unchanged_during_read=stable,converged_structural_checkpoint=abs(meta['t']-meta['last_struct_t'])<1e-8)
        row=dict(case=case,wrapper_pid=wrapper,solver_pid=solver,model_time_s=meta['t'],
            current_maximum_temperature_C=float(data['temp'].max()),peak_nodal_temperature_C=float(data['peaknode'].max()),
            current_tool_maximum_C=float(data['tool_temperature'].max()),checkpoint_bytes=after.st_size,
            checkpoint_mtime_ns=after.st_mtime_ns,checks=checks,resumable_file_state=all(checks.values()),
            completion=False,design_pass=False)
        rows.append(row)
    result=dict(cases=rows,all_checkpoints_valid=all(r['resumable_file_state'] for r in rows))
    (DEST/'checkpoint-stop-preflight.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    if not result['all_checkpoints_valid']:raise RuntimeError('checkpoint preflight did not pass; no stop/package approval')
    return result


def package():
    result=verify();files=[]
    for case,_,_ in CASES:
        folder=OUT/case
        for name in ['continuation-checkpoint.npz','mesh.npz','input.json','progress.json','worker-status.json',
                     'worker-status-before-cloud-handoff.json','handoff-stop-status.json','gauge-schedule-audit.json']:
            p=folder/name
            if p.exists():files.append(p)
        files+=list(folder.glob('*.log'))
    files += [DEST/'checkpoint-stop-preflight.json',ROOT/'docs/review/2026-10-05-云端交接.md']
    archive=DEST/'candidate-resume-data-20261005.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as z:
        for p in files:z.write(p,p.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise RuntimeError('handoff ZIP member could not be read')
    info=dict(path=str(archive),bytes=archive.stat().st_size,members=len(files),
        scope='three stopped candidate checkpoints/meshes/inputs and short logs; source code and tracked drawings obtained by git pull',
        file_checks=result['all_checkpoints_valid'])
    (DEST/'handoff-package-manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf8')
    return info


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--package',action='store_true')
    print(json.dumps(package() if p.parse_args().package else verify(),ensure_ascii=False,indent=2))
