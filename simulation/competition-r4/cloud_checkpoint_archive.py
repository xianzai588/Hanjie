"""Immutable recoverable archive of an actually committed manufacturing state."""
from pathlib import Path
import json,os,tempfile,zipfile
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def build(case):
    folder=ROOT/'simulation/competition-r4/results'/case
    out=ROOT/'output/cloud-20261005/durable-checkpoints';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as stage:
        cp=Path(stage)/'continuation-checkpoint.npz'
        # The solver replaces its checkpoint atomically. The hardlink pins
        # one committed inode without changing or reserialising its metadata.
        os.link(folder/'continuation-checkpoint.npz',cp)
        with np.load(cp,allow_pickle=False) as data:
            meta=json.loads(str(data['metadata']));t=meta['t']
            endpoint_temperature=float(data['temp'].max());eqp=float(data['eqp'].max())
        files=[(cp,folder/'continuation-checkpoint.npz'),
            (folder/'mesh.npz',folder/'mesh.npz'),(folder/'input.json',folder/'input.json')]
        journal=folder/'nonlinear-path';records=[]
        for p in sorted(journal.glob('step-*.npz')):
            with np.load(p,allow_pickle=False) as r:
                if float(r['t_s'])>t+1e-8:continue
            records.append(p);files.append((p,p))
        for name in ('anchor.npz','anchor-provenance.json'):
            if (journal/name).exists():files.append((journal/name,journal/name))
        manifest=dict(case=case,committed_t_s=t,current_max_C=endpoint_temperature,
            maximum_eqp=eqp,mechanical_equilibrium_residual_N=meta['struct'][-1][2],
            mandrel_released=bool(meta['rel']),shell_free_release_included=False,
            recorded_path_steps=len(records),complete_path_from_zero=bool(records and float(np.load(records[0])['t_s'])==0),
            original_checkpoint_metadata_preserved=True,
            scope='recoverable compute snapshot; not complete welding-design qualification')
        target=out/f'{case}.zip';temporary=Path(stage)/'archive.zip'
        with zipfile.ZipFile(temporary,'w') as z:
            for source,name in files:
                z.write(source,name.relative_to(ROOT).as_posix(),compress_type=zipfile.ZIP_STORED if source.suffix=='.npz' else zipfile.ZIP_DEFLATED)
            z.writestr('checkpoint-status.json',json.dumps(manifest,indent=2),compress_type=zipfile.ZIP_DEFLATED)
        temporary.replace(target)
    return target,manifest
