"""Audit available actual nonlinear history; never invent missing plastic paths."""
from pathlib import Path
import argparse,json
import numpy as np

OUT=Path(__file__).parent/'results'


def audit_journal(folder):
    """Reconstruct tensor plastic state, rather than infer it from resultants."""
    folder=Path(folder);journal=folder/'nonlinear-path'
    records=sorted(journal.glob('step-*.npz'))
    if not records:return dict(available=False,complete_prefix=False)
    with np.load(folder/'continuation-checkpoint.npz',allow_pickle=False) as cp:
        meta=json.loads(str(cp['metadata']));endpoint=float(meta['t'])
        reference_plastic=cp['plastic'].copy();reference_eqp=cp['eqp'].copy()
    plastic=np.zeros_like(reference_plastic);eqp=np.zeros_like(reference_eqp)
    anchor_time=None
    if (journal/'anchor.npz').exists():
        with np.load(journal/'anchor.npz',allow_pickle=False) as anchor:
            anchor_time=float(anchor['t_s']);plastic=anchor['plastic'].copy();eqp=anchor['eqp'].copy()
        if plastic.shape!=reference_plastic.shape or eqp.shape!=reference_eqp.shape:
            raise ValueError('journal anchor state has a different discretisation')
    times=[];contact_changes=[];yield_changes=[];resets=[];last_contact=None;last_yield=None
    bore=None
    for path in records:
        with np.load(path,allow_pickle=False) as p:
            t=float(p['t_s'])
            if t>endpoint+1e-8:continue
            if anchor_time is not None and t<=anchor_time:continue
            if times and t<=times[-1]:raise ValueError('nonmonotone mechanical journal')
            times.append(t)
            if bore is None:bore=p['bore_nodes'].copy()
            if not np.array_equal(bore,p['bore_nodes']):raise ValueError('journal bore nodes changed')
            ids=p['plastic_element'];dl=p['delta_eqp'];dp=p['delta_plastic_Mandel']
            if dp.shape!=(len(ids),6) or dl.shape!=(len(ids),) or np.any(dl<=0) or not np.isfinite(dp).all():
                raise ValueError('invalid material-point plastic record')
            if len(ids) and np.max(abs(dp[:,:3].sum(axis=1)))>1e-10:
                raise ValueError('J2 plastic update is not isochoric')
            reset=p['reset_element'];plastic[reset]=0;eqp[reset]=0
            plastic[ids]+=dp;eqp[ids]+=dl
            contact=p['mandrel_active'];gap=p['mandrel_gap_mm']
            if gap.shape!=bore.shape or not np.isfinite(gap).all():raise ValueError('invalid nodal contact gap')
            if not np.array_equal(contact,(gap<0)&(not bool(p['released']))):raise ValueError('contact mask differs from converged gap')
            if last_contact is not None and np.any(contact!=last_contact):
                contact_changes.append(dict(t_s=t,node_ids=bore[contact!=last_contact].tolist()))
            if last_yield is not None and not np.array_equal(ids,last_yield):
                yield_changes.append(dict(t_s=t,newly_yielding_elements=np.setdiff1d(ids,last_yield).tolist(),
                    no_longer_yielding_elements=np.setdiff1d(last_yield,ids).tolist()))
            if len(reset):resets.append(dict(t_s=t,elements=int(len(reset)),maximum_erased_eqp=float(p['eqp_before_reset'].max())))
            last_contact=contact.copy();last_yield=ids.copy()
    mechanical_times=np.array([r[0] for r in meta['struct']])
    coverage=bool(times and abs(times[0])<1e-10 and np.array_equal(np.array(times),mechanical_times))
    suffix_coverage=bool(anchor_time is not None and times and np.array_equal(np.array(times),mechanical_times[mechanical_times>anchor_time]))
    plastic_error=float(np.max(abs(plastic-reference_plastic)));eqp_error=float(np.max(abs(eqp-reference_eqp)))
    reconstruction=coverage and plastic_error<1e-12 and eqp_error<1e-12
    return dict(available=True,complete_prefix=coverage,recorded_steps=len(times),checkpoint_t_s=endpoint,
        maximum_plastic_tensor_reconstruction_error=plastic_error,maximum_eqp_reconstruction_error=eqp_error,
        state_reconstruction_pass=reconstruction,anchor_t_s=anchor_time,
        recorded_suffix_state_reconstruction_pass=suffix_coverage and plastic_error<1e-12 and eqp_error<1e-12,
        contact_transitions=contact_changes,
        yield_transitions=yield_changes,thermal_reset_events=resets,
        interval_interior_guarantee=False)


def evaluate(case):
    folder=OUT/case;inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    required=['pad-contact-history.csv','mandrel-vector-history.csv','equilibrium-history.csv']
    missing=[name for name in required if not (folder/name).exists()]
    checks=dict(contact_active_set_resolved=False,plastic_loading_unloading_resolved=False,
        no_unresolved_path_transition=False,actual_cold_release_and_metrology=False)
    records={}
    journal=audit_journal(folder)
    if journal.get('state_reconstruction_pass'):
        checks['contact_active_set_resolved']=True
        checks['plastic_loading_unloading_resolved']=True
    if not missing:
        pads,mandrel,equilibrium=[np.atleast_2d(np.loadtxt(folder/name,delimiter=',',skiprows=1)) for name in required]
        same=np.array_equal(pads[:,0],equilibrium[:,0]) and np.array_equal(mandrel[:,0],equilibrium[:,0])
        records.update(mechanical_history_times_identical=same,mechanical_steps=len(equilibrium),
            pad_area_transition_steps=np.flatnonzero(np.any(abs(np.diff(pads[:,5:8],axis=0))>1e-8,axis=1)).tolist(),
            maximum_equilibrium_residual_N=float(equilibrium[:,2].max()),
            minimum_pad_reaction_N=float(pads[:,2:5].min()),maximum_compression_sum_N=float(mandrel[:,4].max()))
        # Pad areas and total mandrel force are insufficient to recover which
        # bore nodes opened, or when each material point yielded/annealed.
        records['history_coverage']='per-step pad areas and reaction resultants exist; per-node mandrel active sets and per-element plastic increments/reset events were not saved'
        if journal.get('state_reconstruction_pass'):
            records['history_coverage']='converged nodal gaps/masks and sparse material-point tensor increments/reset events reconstruct checkpoint state'
    release_path=folder/'free-release-verification.json';measure_path=folder/'measurement.json'
    if release_path.exists() and measure_path.exists():
        release=json.loads(release_path.read_text(encoding='utf8'));measure=json.loads(measure_path.read_text(encoding='utf8'))
        checks['actual_cold_release_and_metrology']=bool(release.get('free_shell_release_pass') and measure.get('measurement_sampling',{}).get('sampling_stability_pass'))
    result=dict(case=case,initial_bore_diameter_mm=inp['initial_bore_diameter_mm'],missing_files=missing,
        observed_histories=records,nonlinear_journal=journal,checks=checks,
        required_additional_evidence=['actual mandrel nodal gap/active mask at every mechanical increment',
            'actual material-point plastic increment, yield and thermal-reset events at every mechanical increment',
            'refined parameter brackets around changes of contact/plastic branch; a quantified interior response bound'],
        contact_and_plastic_path_checks_pass=all(checks.values()))
    (folder/'manufacturing-path-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cases',nargs='+',required=True)
    for c in p.parse_args().cases:print(json.dumps(evaluate(c),ensure_ascii=False,indent=2))
