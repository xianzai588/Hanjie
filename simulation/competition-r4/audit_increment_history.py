"""Replay actual thermal-reset / return-map records against saved state."""
from pathlib import Path
import argparse,json
import numpy as np


def audit(folder):
    folder=Path(folder);hp=folder/'increment-history'
    manifest=json.loads((hp/'manifest.json').read_text())
    mapping=np.load(hp/'contact-mapping.npz',allow_pickle=False)
    nb=len(mapping['bore_nodes']);npad=len(mapping.get('pad_hosts',[]));pn=mapping['pad_nodes']
    plastic=np.zeros((manifest['elements'],6));eqp=np.zeros(manifest['elements']);ref=plastic.copy()
    times=[];yield_steps=0;reset_steps=0;contact_ok=True;nodal_ok=True;max_trace=0.;last_bore=None;last_pad=None;transitions=[]
    for chunk in manifest['chunks']:
        with np.load(hp/chunk['file'],allow_pickle=False) as d:
            for j,t in enumerate(d['time_s']):
                times.append(float(t));released=bool(d['released'][j])
                bm=np.unpackbits(d['bore_mask'][j])[:nb].astype(bool);pm=np.unpackbits(d['pad_mask'][j])[:npad].astype(bool)
                contact_ok &= np.array_equal(bm,(d['bore_gap'][j]<0)&(not released)) and np.array_equal(pm,(d['pad_gap'][j]<=0)&(not released))
                nm=np.unpackbits(d['pad_node_mask'][j])[:len(pn)].astype(bool);wanted=np.zeros(len(pn),bool)
                if pm.any():wanted[np.searchsorted(pn,np.unique(mapping['pad_hosts'][pm]))]=True
                nodal_ok &= np.array_equal(nm,wanted)
                if last_bore is not None and (np.any(bm!=last_bore) or np.any(pm!=last_pad)):transitions.append(float(t))
                last_bore=bm;last_pad=pm
                lo,hi=d['reset_offset'][j:j+2];ids=d['reset_ids'][lo:hi]
                plastic[ids]=0.;eqp[ids]=0.;ref[ids]=d['reset_reference'][lo:hi]
                reset_steps+=int(len(ids)>0)
                lo,hi=d['plastic_offset'][j:j+2];ids=d['plastic_ids'][lo:hi];inc=d['plastic_increment'][lo:hi]
                plastic[ids]+=inc
                if len(ids):max_trace=max(max_trace,float(abs(inc[:,:3].sum(axis=1)).max()))
                lo,hi=d['eqp_offset'][j:j+2];ids=d['eqp_ids'][lo:hi];inc=d['eqp_increment'][lo:hi]
                if np.any(inc<0):raise ValueError('negative plastic return increment')
                eqp[ids]+=inc;yield_steps+=int(len(ids)>0)
    cp=np.load(folder/'continuation-checkpoint.npz',allow_pickle=False);meta=json.loads(str(cp['metadata']))
    state_errors={key:float(abs(actual-cp[key]).max()) for key,actual in [('plastic',plastic),('eqp',eqp),('ref',ref)]}
    stored_times=np.asarray(meta['struct'])[:,0]
    checks=dict(all_mechanical_steps_recorded=np.array_equal(np.asarray(times),stored_times),
       contact_mask_matches_actual_gap=bool(contact_ok),pad_nodal_support_matches_quadrature=bool(nodal_ok),
       thermal_reset_and_plastic_replay_matches_state=all(e<1e-12 for e in state_errors.values()),
       deviatoric_J2_plastic_increment=bool(max_trace<1e-10))
    result=dict(checks=checks,record_integrity_pass=all(checks.values()),mechanical_steps=len(times),
        thermal_reset_steps=reset_steps,plastic_return_steps=yield_steps,contact_transition_times_s=transitions,
        maximum_plastic_increment_trace=max_trace,replay_maximum_absolute_error=state_errors,
        completed_cold_release=bool(meta['rel'] and cp['temp'].max()<=20.5),
        interval_branch_refinement_verified=False)
    (folder/'increment-history-audit.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True)
    print(json.dumps(audit(p.parse_args().case),indent=2))
