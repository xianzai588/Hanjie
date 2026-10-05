"""Recompute the complete gate from separate incremental and welded evidence."""
from pathlib import Path
import json

OUT = Path(__file__).parent / 'results'


def aggregate(out=OUT):
    def read(name):
        path = out / name
        return json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
    incremental = read('service-increment-verification.json')
    welded = read('welded-strength-verification.json')
    manufacturing = read('bore-size-verification.json')
    accepted = read('verification.json')
    checked = welded.get('checks', {})
    required = ('cold_residual_state_pass', 'same_mesh_tensor_combination_pass',
                'load_and_geometry_pass', 'combined_bulk_strength_pass',
                'Ni99_layer_strength_pass', 'QT_PMZ_strength_pass',
                'both_interfaces_mixed_mode_pass', 'spatial_and_time_precision_pass',
                'fusion_and_metallurgy_design_pass')
    cases = incremental.get('cases', [])
    welded_cases = welded.get('incremental_cases', [])
    expected_bore = manufacturing.get('manufacturing_window_mm', [None, None])[-1]
    input_bores = [];actual_inputs=[]
    for case in cases:
        path = out / case / 'input.json'
        inp = json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
        input_bores.append(inp.get('initial_bore_diameter_mm'))
        actual_inputs.append(inp)
    checks = dict(
        incremental_service_pass=incremental.get('static_service_design_pass') is True,
        independent_welded_evidence_pass=bool(checked) and all(checked.get(k) is True for k in required),
        evidence_cases_match=bool(cases) and cases == welded_cases,
        current_input_snapshots_match=bool(actual_inputs) and incremental.get('input_snapshots') == actual_inputs
            and welded.get('residual_input_snapshots') == actual_inputs,
        residual_cases_match=bool(accepted.get('cases')) and welded.get('residual_cases') == accepted['cases'],
        manufacturing_geometry_match=expected_bore is not None and bool(input_bores)
            and all(d == expected_bore for d in input_bores)
            and welded.get('initial_bore_diameter_mm') == expected_bore,
        manufacturing_interval_pass=manufacturing.get('bore_size_design_pass') is True)
    summary = {**incremental, 'complete_welded_strength_design_pass': all(checks.values()),
               'complete_strength_checks': checks, 'welded_strength_evidence': welded,
               'evidence_files': ['service-increment-verification.json',
                                  'welded-strength-verification.json', 'bore-size-verification.json'],
               'missing_welded_checks': [k for k in required if checked.get(k) is not True]}
    path = out / 'service-verification.json'
    temporary = path.with_suffix('.next.json')
    temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    temporary.replace(path)
    return summary


if __name__ == '__main__':
    print(json.dumps(aggregate(), ensure_ascii=False, indent=2))
