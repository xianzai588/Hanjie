"""Audit available actual nonlinear history; never invent missing plastic paths."""
from pathlib import Path
import argparse,json
import numpy as np

OUT=Path(__file__).parent/'results'


def evaluate(case):
    folder=OUT/case;inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    required=['pad-contact-history.csv','mandrel-vector-history.csv','equilibrium-history.csv']
    missing=[name for name in required if not (folder/name).exists()]
    checks=dict(contact_active_set_resolved=False,plastic_loading_unloading_resolved=False,
        no_unresolved_path_transition=False,actual_cold_release_and_metrology=False)
    records={}
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
    release_path=folder/'free-release-verification.json';measure_path=folder/'measurement.json'
    if release_path.exists() and measure_path.exists():
        release=json.loads(release_path.read_text(encoding='utf8'));measure=json.loads(measure_path.read_text(encoding='utf8'))
        checks['actual_cold_release_and_metrology']=bool(release.get('free_shell_release_pass') and measure.get('measurement_sampling',{}).get('sampling_stability_pass'))
    result=dict(case=case,initial_bore_diameter_mm=inp['initial_bore_diameter_mm'],missing_files=missing,
        observed_histories=records,checks=checks,
        required_additional_evidence=['actual mandrel nodal gap/active mask at every mechanical increment',
            'actual material-point plastic increment, yield and thermal-reset events at every mechanical increment',
            'refined parameter brackets around changes of contact/plastic branch; a quantified interior response bound'],
        contact_and_plastic_path_checks_pass=all(checks.values()))
    (folder/'manufacturing-path-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cases',nargs='+',required=True)
    for c in p.parse_args().cases:print(json.dumps(evaluate(c),ensure_ascii=False,indent=2))
