"""Quantitative manufacturing-envelope audit; completed FE data only.

Five ordered bore geometries resolve the 2 um manufacturing interval. A
three-point versus five-point response-envelope comparison is independent of
mesh/time refinement. Contact and plastic histories are checked separately.
The numerical interpolation reserve is a design envelope, not an exact
mathematical error theorem for arbitrary nonlinear responses.
"""
from pathlib import Path
import json
import numpy as np

OUT = Path(__file__).parent / 'results'
PHYSICS_KEYS = ('materials', 'fusion_enthalpy_model', 'stage_sequence', 'seat_geometry',
    'h_mm', 'dt_s', 'structural_step_s', 'cold_structural_step_s',
    'mechanical_event_temperature_increment_C', 'source_r_mm', 'source_radius_mm',
    'source_depth_mm', 'net_W', 'travel_mm_s', 'root_leg_mm', 'leg_mm',
    'weld_mesh_mm', 'copper_water_model', 'fixture_thermal',
    'fixture_thermal_coupling_policy', 'mandrel_penalty_N_mm3',
    'initial_radial_preload_N', 'unilateral_pads', 'paired_opposed_sources',
    'stress_free_birth', 'stress_free_interface_birth', 'Ni99_thin_layer_mm')


def interval_cases(upper):
    return [upper.replace('bore008', f'bore{tag}') for tag in ('006','0065','007','0075','008')]


def evaluate(upper, out=OUT):
    from check_bore_size import endpoint_quality, finish_geometry
    cases = interval_cases(upper)
    result = dict(endpoint_cases=[cases[0], cases[-1]], interior_cases=cases[1:-1],
        response_envelope_validation_pass=False, contact_and_plastic_path_checks_pass=False,
        pending_cases=[c for c in cases if not (out/c/'free-release-fields.npz').exists()],
        response_bound_basis='five completed geometries; nested 3/5-point envelopes, twice the largest adjacent response change plus 0.1 um; contact/plastic-path audit required')
    if result['pending_cases']:
        return result
    from postprocess import measure
    data = [measure(out/c, free_shell=True) for c in cases]
    rows = [d[0] for d in data]; inputs = [d[2] for d in data]
    diameters = np.array([i['initial_bore_diameter_mm'] for i in inputs])
    identical = all(all(i.get(k) == inputs[0].get(k) for k in PHYSICS_KEYS) for i in inputs)
    ordered = bool(np.allclose(diameters, [40.006,40.0065,40.007,40.0075,40.008], atol=1e-9, rtol=0))
    quality = [endpoint_quality(c, r, i) for c,r,i in zip(cases,rows,inputs)]
    metrics = ('sampled_bore_two_point_diameter_min_mm', 'sampled_bore_two_point_diameter_max_mm', 'position_diameter_mm')
    response = np.array([[r['fit'][k] for k in metrics] for r in rows])
    response[:,:2] -= diameters[:,None]
    # A diameter tolerance must not masquerade as a FE response slope.
    adjacent = np.max(abs(np.diff(response, axis=0)), axis=0)
    reserve = 2*adjacent + .0001
    nested_change = np.max(abs(response[[1,3]]-(response[[0,2]]+response[[2,4]])/2),axis=0)
    nested_relative = nested_change/np.maximum(np.max(abs(response),axis=0),1e-12)
    path_checks = []
    for case in cases:
        path = out/case/'manufacturing-path-audit.json'
        audit = json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
        # This separate audit must use resolved contact/plastic histories, not
        # a count of nonzero final plastic cells or a case-name assertion.
        checks = audit.get('checks', {})
        passed = audit.get('case') == case and audit.get('initial_bore_diameter_mm') == inputs[cases.index(case)]['initial_bore_diameter_mm']
        passed = passed and all(checks.get(k) is True for k in (
            'contact_active_set_resolved', 'plastic_loading_unloading_resolved',
            'no_unresolved_path_transition', 'actual_cold_release_and_metrology'))
        path_checks.append(dict(case=case, passed=bool(passed), evidence=audit))
    finished = [finish_geometry(r) for r in rows]
    bounds = dict(minimum_diameter_mm=float(min(r['fit'][metrics[0]] for r in rows)-reserve[0]),
        maximum_diameter_mm=float(max(r['fit'][metrics[1]] for r in rows)+reserve[1]),
        maximum_raw_position_mm=float(max(r['fit'][metrics[2]] for r in rows)+reserve[2]),
        maximum_nominal_finished_position_mm=float(max(f['final_sampled_fit']['position_diameter_mm'] for f in finished)+reserve[2]),
        maximum_nominal_radial_stock_mm=float(max(f['maximum_local_radial_stock_mm'] for f in finished)+reserve[0]/2))
    path_pass = all(p['passed'] for p in path_checks)
    result.update(records=rows, inputs=inputs, physics_keys=list(PHYSICS_KEYS),
        numerical_bounds=bounds, interpolation_reserve_mm=dict(zip(metrics,reserve.tolist())),
        nested_response_relative_differences=dict(zip(metrics,nested_relative.tolist())),
        endpoint_and_interior_quality=quality, contact_plastic_path_records=path_checks,
        contact_and_plastic_path_checks_pass=path_pass,
        response_envelope_validation_pass=bool(identical and ordered and path_pass
            and all(all(q.values()) for q in quality) and np.all(nested_relative<=.05)))
    return result


def write(upper):
    result = evaluate(upper)
    path = OUT/'manufacturing-interval-verification.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


if __name__ == '__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--upper',required=True)
    print(json.dumps(write(p.parse_args().upper),ensure_ascii=False,indent=2))
