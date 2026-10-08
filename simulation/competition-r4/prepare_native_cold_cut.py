"""Limited native cold-cut continuation; no solver or state reconstruction.

The actual one-wing C3D4 mesh, numbering, .rout and surviving integration-point
history stay unchanged. A tool surface crossing an element is a hard geometric
interface stop. The nominal inspection is geometry only and never supplies a
cold manufacturing state. Previously executed tool benchmarks are read, not run.
"""
import argparse
import json
from pathlib import Path
import shutil

import numpy as np
from OCP.Precision import Precision

from audit_calculix_manufacturing_benchmark import read_states
from build_second_layer_from_cut import normal_surface
from mma_literature_profile import ROOT
from precoat_machining import retained_moments
from run_first_layer_machining import datum_frame

BENCHMARK = ROOT / 'simulation/competition-r4/results/calculix-plastic-deposition-cut-benchmark-restartfix-20261007'
NOMINAL_SOURCE = ROOT / 'simulation/competition-r4/results/mma-first-end80-r12-phase-front-dt0125-20261007'


def remove_step(element_ids):
    ids = [int(v) for v in element_ids]
    if not ids or len(ids) != len(set(ids)) or min(ids) < 1:
        raise ValueError('A nonempty set of existing one-based elements is required')
    rows = ''.join(','.join(map(str, ids[j:j + 16])) + '\n' for j in range(0, len(ids), 16))
    # Temperatures, constraints and constitutive state are inherited by restart.
    return ('*STEP,NLGEOM,INC=100\n*STATIC,SOLVER=SPOOLES\n.1,1,1e-6,.25\n'
            '*MODEL CHANGE,TYPE=ELEMENT,REMOVE\n' + rows +
            '*NODE PRINT,NSET=ALLN,FREQUENCY=99999\nU,RF\n'
            '*EL PRINT,ELSET=ALLE,FREQUENCY=99999\nS,PEEQ,ME\n'
            '*NODE FILE,FREQUENCY=99999\nU\n*EL FILE,FREQUENCY=99999\nS,PEEQ\n'
            '*RESTART,WRITE\n*END STEP\n')


def saved_capabilities():
    folder = BENCHMARK / 'reactivated-substrate-history'
    record = json.loads((folder / 'reactivation-history-audit.json').read_text(encoding='utf8'))
    previous = read_states(BENCHMARK / 'benchmark.dat')[2]['peeq']
    restored = read_states(folder / 'reactivation.dat')[4]['peeq']
    before = previous[previous[:, 0] <= 40]
    after = restored[restored[:, 0] <= 40]
    if not np.array_equal(before[:, :2], after[:, :2]):
        raise ValueError('Saved QT integration-point identities do not match')
    difference = float(np.max(abs(before[:, 2] - after[:, 2])))
    if difference != record['maximum_cumulative_plastic_difference']:
        raise ValueError('Saved reactivation audit does not match actual DAT')
    binary = folder / 'reactivation.rout'
    # Read the file as binary; its solver-owned internals are never translated.
    with binary.open('rb') as stream:
        header_present = len(stream.read(16)) == 16
    log = (folder / 'reactivation.log').read_text(encoding='utf8')
    deck = (folder / 'reactivation.inp').read_text(encoding='ascii')
    generated = remove_step(range(21, 41))
    existing_remove = deck[deck.index('*MODEL CHANGE,TYPE=ELEMENT,REMOVE'):deck.index('*NODE PRINT')]
    generated_remove = generated[generated.index('*MODEL CHANGE,TYPE=ELEMENT,REMOVE'):generated.index('*NODE PRINT')]
    return dict(existing_element_QT_before_PEEQ_range=[float(before[:, 2].min()), float(before[:, 2].max())],
                existing_element_QT_after_PEEQ_range=[float(after[:, 2].min()), float(after[:, 2].max())],
                maximum_existing_QT_PEEQ_difference=difference,
                native_history_audit=json.loads((BENCHMARK / 'native-history-audit.json').read_text(encoding='utf8')),
                reactivation_restart_binary_bytes=binary.stat().st_size,
                binary_header_present=header_present,
                saved_job_finished='Job finished' in log and '*ERROR' not in log,
                new_remove_block_matches_existing_executed_block=existing_remove == generated_remove,
                new_solver_runs=0,
                scope='existing-element history and limited continuation generation; no melting/mass/cold-volume/hardening or competition qualification')


def cut_geometry(mesh, displacement):
    x, e, material, volume = (mesh[k] for k in ('x', 'e', 'material', 'volume_mm3'))
    if e.shape[1] != 4 or displacement.shape != x.shape:
        raise ValueError('Only the unchanged actual one-wing C3D4 mesh is supported')
    registered, frame = datum_frame(x, displacement, e, material)
    original_det = np.linalg.det((x[e[:, 1:]] - x[e[:, :1]]).transpose(0, 2, 1))
    spatial_det = np.linalg.det((registered[e[:, 1:]] - registered[e[:, :1]]).transpose(0, 2, 1))
    if np.any(original_det == 0) or np.any(spatial_det / original_det <= 0):
        raise ValueError('The actual cold C3D4 geometry is singular or inverted')
    native_reference_volume = abs(original_det) / 6
    spatial_volume = abs(spatial_det) / 6
    moments = retained_moments(registered, e, material)
    remaining = moments.sum(axis=1)
    deposit = material == 3
    partial = deposit & (remaining > 1e-10) & (remaining < 1 - 1e-10)
    removed = deposit & (remaining <= 1e-10)
    signed = normal_surface(registered)[e[partial]]
    crossing_depth = np.minimum(signed.max(axis=1), -signed.min(axis=1))
    cad_reference = json.loads((ROOT / 'cad/generated/independent-precoat-curved/geometry-audit.json').read_text(encoding='utf8'))
    # OCP's point-coincidence precision in this model's mm units. This is a
    # numerical CAD zero classification, not a manufacturing tolerance change.
    cad_zero = float(Precision.Confusion_s())
    partial_ids = np.flatnonzero(partial)
    zero_ids = partial_ids[crossing_depth <= cad_zero]
    zero_volume_error = float(volume[zero_ids] @ np.minimum(remaining[zero_ids], 1 - remaining[zero_ids]))
    allowed_zero_volume_error = float(volume[deposit].sum() * cad_reference['geometric_integration_relative_tolerance'])
    if zero_volume_error > allowed_zero_volume_error:
        zero_ids = np.array([], dtype=int)
    engineering_partial = partial.copy()
    engineering_partial[zero_ids] = False
    removed[zero_ids] = remaining[zero_ids] < .5
    return dict(datum_registration=frame,
                tool_surface='actual A/B frame: flat z114.20 and normal R0.80 corner; first layer normal .70 mm',
                volume_policy='saved volume_mm3 is the thermal CAD-corrected accounting ledger; native C3D4 reference volume follows original coordinates; actual deformed tetrahedron volume is a third spatial ledger. No ledger is substituted for another',
                first_layer_saved_thermal_accounting_volume_mm3=float(volume[deposit].sum()),
                P1_removed_saved_thermal_accounting_volume_mm3=float(volume @ (1 - remaining)),
                whole_element_removed_saved_thermal_accounting_volume_mm3=float(volume[removed].sum()),
                saved_thermal_volume_difference_from_P1_mm3=float(volume @ (1 - remaining) - volume[removed].sum()),
                first_layer_native_reference_volume_mm3=float(native_reference_volume[deposit].sum()),
                P1_removed_native_reference_volume_mm3=float(native_reference_volume @ (1 - remaining)),
                whole_element_removed_native_reference_volume_mm3=float(native_reference_volume[removed].sum()),
                first_layer_actual_spatial_volume_mm3=float(spatial_volume[deposit].sum()),
                P1_removed_actual_spatial_volume_mm3=float(spatial_volume @ (1 - remaining)),
                whole_element_removed_actual_spatial_volume_mm3=float(spatial_volume[removed].sum()),
                intersected_first_layer_elements=int(partial.sum()),
                intersected_parent_saved_thermal_accounting_volume_mm3=float(volume[partial].sum()),
                P1_removed_partial_saved_thermal_accounting_volume_mm3=float(volume[partial] @ (1 - remaining[partial])),
                maximum_smaller_P1_crossing_depth_mm=float(crossing_depth.max()) if len(crossing_depth) else 0.,
                source_geometric_zero_tolerance_mm=1e-9,
                CAD_point_coincidence_tolerance_mm=cad_zero,
                CAD_point_coincidence_source='local OCP.Precision.Precision.Confusion_s() and its original API documentation; model units mm',
                CAD_volume_error_reference='cad/generated/independent-precoat-curved/geometry-audit.json: geometric_integration_relative_tolerance',
                allowed_CAD_zero_volume_error_mm3=allowed_zero_volume_error,
                classified_CAD_numerical_zero_elements=int(len(zero_ids)),
                classified_CAD_zero_discarded_volume_mm3=zero_volume_error,
                engineering_crossed_elements=int(engineering_partial.sum()),
                whole_element_interface_ready=bool(not engineering_partial.any()),
                whole_element_remove_ids=(np.flatnonzero(removed) + 1).tolist())


def cold_thermal_screen(source, mesh, qualification):
    check = qualification.get('cold_thermal_dimension_check', {})
    required_sources = ('alpha_applicability_source', 'dimension_budget_source', 'gradient_budget_source')
    if any(not check.get(key) for key in required_sources) or check.get('alpha_applicability_qualified') is not True:
        raise ValueError('Applicable expansion and allocated thermal-dimension/gradient budgets have not been qualified')
    if float(check.get('temperature_reference_C', float('nan'))) != 20.:
        raise ValueError('The manufacturing design dimensional reference is 20 C')
    temperature, raw_displacement, identity = verified_cold_temperature(source, mesh, qualification)
    length = float(check['characteristic_length_mm'])
    alpha = float(check['qualified_alpha_upper_per_K'])
    dimension_budget = float(check['allowed_reference_dimension_error_mm'])
    gradient_budget = float(check['allowed_gradient_dimension_error_mm'])
    values = [length, alpha, dimension_budget, gradient_budget]
    if not all(np.isfinite(values)) or min(values) <= 0 or length < float(np.ptp(mesh['x'], axis=0).max()):
        raise ValueError('A positive, source-qualified full-part characteristic length and thermal budgets are required')
    reference_bound = alpha * length * float(abs(temperature - 20.).max())
    gradient_bound = alpha * length * float(np.ptp(temperature))
    if reference_bound > dimension_budget or gradient_bound > gradient_budget:
        raise ValueError('Actual cold temperatures exceed the reviewed thermal dimensional allocation; preserve temperatures and continue actual cooling')
    return dict(actual_cold_temperature_range_C=[float(temperature.min()), float(temperature.max())],
                reference_temperature_C=20., characteristic_length_mm=length, alpha_upper_per_K=alpha,
                reference_dimension_bound_mm=reference_bound, allowed_reference_dimension_error_mm=dimension_budget,
                gradient_dimension_bound_mm=gradient_bound, allowed_gradient_dimension_error_mm=gradient_budget,
                sources={key: check[key] for key in required_sources},
                actual_temperature_identity=identity,
                scope='reviewed engineering thermal-dimension screening, not a substitute for equilibrium or full nonuniform thermal deformation',
                saved_temperature_policy='actual nodal temperatures retained without replacement or resetting'), raw_displacement


def verified_cold_temperature(source, mesh, qualification):
    """Verify the existing one-wing deck/chunk/DAT identity, not a new format."""
    identity_keys = ('source', 'cold_restart_step', 'cold_actual_time_s', 'cold_thermal_state_file')
    if any(key not in qualification for key in identity_keys):
        raise ValueError('Cold thermal source/step/actual-time/chunk identity is missing; interface not ready')
    metadata = json.loads((source / 'input.json').read_text(encoding='utf8'))
    if (ROOT / qualification['source']).resolve() != source.resolve():
        raise ValueError('Cold qualification identifies a different native source')
    step = int(qualification['cold_restart_step'])
    actual_time = float(qualification['cold_actual_time_s'])
    recorded_time = float(metadata['last_time_s'])
    time_roundoff = 16 * np.finfo(float).eps * max(abs(recorded_time), 1.)
    if step != int(metadata['selected_steps']) + 1 or abs(actual_time - recorded_time) > time_roundoff:
        raise ValueError('Cold step/time do not identify the recorded terminal native thermal step')
    initial_source = Path(metadata['source'])
    furnace = Path(metadata['furnace'])
    if not initial_source.is_absolute():
        initial_source = ROOT / initial_source
    if not furnace.is_absolute():
        furnace = ROOT / furnace
    with np.load(initial_source / 'thermal-fields.npz') as handle:
        if any(not np.array_equal(mesh[key], handle[key]) for key in ('x', 'e', 'material', 'volume_mm3')):
            raise ValueError('Native numbering/topology/reference accounting differ from its recorded thermal mesh')
    history_folder = furnace / 'nodal-thermal-history'
    manifest = json.loads((history_folder / 'manifest.json').read_text(encoding='utf8'))
    thermal_file = (ROOT / qualification['cold_thermal_state_file']).resolve()
    allowed = {(history_folder / chunk['file']).resolve() for chunk in manifest['chunks']}
    if thermal_file not in allowed:
        raise ValueError('Cold temperature file is not a recorded chunk of this native source furnace history')
    with np.load(thermal_file) as handle:
        times = handle['time_s'].copy()
        rows = np.flatnonzero(abs(times - recorded_time) <= time_roundoff)
        if len(rows) != 1:
            raise ValueError('Recorded terminal thermal time is absent or ambiguous in the selected original chunk')
        row = int(rows[0])
        temperature = handle['temperature_C'][row].copy()
        if 'node_ids' in handle.files and not np.array_equal(handle['node_ids'], np.arange(1, len(mesh['x']) + 1)):
            raise ValueError('Original thermal chunk node IDs do not match the native node order')
    if temperature.shape != (len(mesh['x']),) or not np.isfinite(temperature).all():
        raise ValueError('Actual terminal thermal array does not match the unchanged native nodes')

    # The existing chunks use implicit original-mesh node order. Prove that
    # order from the native model and its per-ID terminal TEMPERATURE values.
    nnode, nelement = len(mesh['x']), len(mesh['e'])
    node_rows = element_rows = temperature_rows = current_step = 0
    section = None
    pending_time = None
    terminal_time = None
    restart_write_at_terminal = terminal_ended = False
    with (source / 'onewing.inp').open('r', encoding='ascii') as stream:
        for raw in stream:
            if raw.startswith('** Actual thermal time '):
                pending_time = float(raw.split()[4])
                continue
            if raw.startswith('**') or not raw.strip():
                continue
            if raw.startswith('*'):
                line = raw.strip().upper()
                keyword = line.split(',')[0]
                section = None
                if keyword == '*STEP':
                    current_step += 1
                    if current_step == step:
                        terminal_time = pending_time
                elif current_step == 0 and keyword == '*NODE':
                    section = 'nodes'
                elif current_step == 0 and keyword == '*ELEMENT':
                    if 'TYPE=C3D4' not in line:
                        raise ValueError('Only the existing one-wing C3D4 native model is supported')
                    section = 'elements'
                elif current_step == step and keyword == '*TEMPERATURE':
                    section = 'temperature'
                elif current_step == step and line == '*RESTART,WRITE':
                    restart_write_at_terminal = True
                elif current_step == step and keyword == '*END STEP':
                    terminal_ended = True
                continue
            if section == 'nodes':
                values = raw.strip().split(',')
                if node_rows >= nnode or int(values[0]) != node_rows + 1:
                    raise ValueError('Native NODE IDs are not the original ascending thermal mesh order')
                coordinates = np.array([float(value) for value in values[1:4]])
                tolerance = 5e-12 * np.maximum(abs(mesh['x'][node_rows]), 1.)
                if not np.all(abs(coordinates - mesh['x'][node_rows]) <= tolerance):
                    raise ValueError('Native node coordinates differ from the recorded original thermal mesh')
                node_rows += 1
            elif section == 'elements':
                values = [int(value) for value in raw.strip().split(',')]
                if element_rows >= nelement or values[0] != element_rows + 1 or not np.array_equal(values[1:], mesh['e'][element_rows] + 1):
                    raise ValueError('Native element IDs/connectivity differ from the recorded thermal mesh')
                element_rows += 1
            elif section == 'temperature':
                values = raw.strip().split(',')
                if temperature_rows >= nnode or int(values[0]) != temperature_rows + 1:
                    raise ValueError('Terminal native temperature IDs do not preserve original node order')
                printed = float(values[1])
                tolerance = 5e-12 * max(abs(temperature[temperature_rows]), 1.)
                if abs(printed - temperature[temperature_rows]) > tolerance:
                    raise ValueError('Terminal native nodal temperature differs from the selected original thermal snapshot')
                temperature_rows += 1
    printed_time_tolerance = 5e-12 * max(abs(recorded_time), 1.)
    if (current_step != step or terminal_time is None or abs(terminal_time - recorded_time) > printed_time_tolerance
            or node_rows != nnode or element_rows != nelement or temperature_rows != nnode
            or not restart_write_at_terminal or not terminal_ended):
        raise ValueError('Native terminal step/time/node/temperature/restart identity is incomplete')
    states = read_states(source / 'onewing.dat')
    if step not in states or step != max(states) or 'u' not in states[step]:
        raise ValueError('Native DAT has no accepted terminal cold step; temperature identity is not a completed mechanical state')
    raw_displacement = states[step]['u']
    if not np.array_equal(raw_displacement[:, 0], np.arange(1, nnode + 1)):
        raise ValueError('Accepted terminal DAT node IDs differ from the verified native thermal order')
    binary = source / 'onewing.rout'
    if not binary.is_file() or binary.stat().st_size == 0:
        raise ValueError('The terminal native step has no binary restart; the cold interface is not ready')
    return temperature, raw_displacement, dict(native_source=str(source.relative_to(ROOT)),
        native_cold_restart_step=step, actual_thermal_time_s=recorded_time,
        original_furnace_manifest=str((history_folder / 'manifest.json').relative_to(ROOT)),
        original_temperature_chunk=str(thermal_file.relative_to(ROOT)), original_temperature_row=row,
        native_model_node_order_verified=True, native_element_connectivity_verified=True,
        original_chunk_and_terminal_per_ID_temperature_verified=True,
        accepted_native_DAT_step_verified=True, terminal_restart_write_present=True,
        snapshot_identity_policy='only recorded original furnace chunk; original mesh, terminal step/time and per-node native temperature must agree')


def prepare(source, output, qualification_path):
    qualification = json.loads(qualification_path.read_text(encoding='utf8'))
    if (ROOT / qualification.get('source', '')).resolve() != source.resolve():
        raise ValueError('The qualification record does not identify this native source directory')
    required = ('native_solver_completed', 'cold_geometry_qualified', 'input_qualification_passed',
                'actual_first_layer_joint_passed', 'cold_material_reference_qualified', 'history_survival_qualified')
    if any(qualification.get(key) is not True for key in required):
        raise ValueError('Native cold/source/connection/reference/history qualification is incomplete')
    execution = json.loads((source / 'execution.json').read_text(encoding='utf8'))
    if execution.get('native_solver_completed') is not True:
        raise ValueError('The source native solve did not complete')
    step = int(qualification['cold_restart_step'])
    with np.load(source / 'mesh.npz') as handle:
        mesh = {key: handle[key].copy() for key in handle.files}
    thermal_check, raw = cold_thermal_screen(source, mesh, qualification)
    if not np.array_equal(raw[:, 0].astype(int), np.arange(1, len(mesh['x']) + 1)):
        raise ValueError('Actual cold native node numbering differs from the unchanged mesh')
    audit = cut_geometry(mesh, raw[:, 1:4])
    if not audit['whole_element_interface_ready']:
        raise ValueError(f"Prescribed cut crosses {audit['engineering_crossed_elements']} C3D4 elements at engineering scale; this unchanged-mesh restart interface is unsupported, not a physical process failure")
    if not (source / 'onewing.rout').is_file():
        raise ValueError('No native binary restart is available')
    if output.exists():
        raise ValueError('Preserve previously staged continuations')
    output.mkdir(parents=True)
    shutil.copyfile(source / 'onewing.rout', output / 'coldcut.rin')
    (output / 'coldcut.inp').write_text(f'*RESTART,READ,STEP={step}\n' + remove_step(audit['whole_element_remove_ids']), encoding='ascii')
    audit.update(source=str(source.relative_to(ROOT)), qualification=str(qualification_path.relative_to(ROOT)),
                 cold_thermal_dimension_screen=thermal_check,
                 native_restart_staged=True, new_solver_runs=0, cold_cut_equilibrated=False,
                 state_policy='binary history retained; no new nodes/elements/material coordinates; no stress/plastic/reference/temperature initialization')
    (output / 'coldcut-interface.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf8')
    return audit


def inspect_saved_geometry(output):
    # This saved mesh is used for geometry only, with zero nominal displacement.
    # No failed thermal/FRD values are inherited as manufacturing state.
    with np.load(NOMINAL_SOURCE / 'thermal-fields.npz') as handle:
        mesh = {key: handle[key].copy() for key in ('x', 'e', 'material', 'volume_mm3')}
    geometry = cut_geometry(mesh, np.zeros_like(mesh['x']))
    geometry.pop('whole_element_remove_ids')
    result = dict(saved_capabilities=saved_capabilities(), nominal_A_B_cut_geometry=geometry,
                  geometry_scope='nominal undeformed mesh only; not an actual cold A/B cut or a physical state transfer',
                  cold_temperature_identity_readback='simulation/competition-r4/results/native-interface-adaptation-20261008/temperature-identity-readback.json',
                  temperature_identity_policy='original furnace manifest chunk, native terminal step and actual thermal time, original nodes/topology, per-node native temperatures, accepted DAT and binary restart are required; equal-sized external snapshots are rejected',
                  current_actual_native_cold_restart_available=False,
                  current_actual_native_cut_executable=False,
                  current_actual_second_layer_native_interface=False,
                  current_actual_shell_fixture_native_interface=False,
                  current_actual_release_and_same_state_service_interface=False,
                  new_solver_runs=0, full_manufacturing_chain_passed=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    fragment = output.parent / 'generation-check-remove-block.txt'
    fragment.write_text('** Generation check against the previously executed tool benchmark; not a competition solve.\n' + remove_step(range(21, 41)), encoding='ascii')
    result['generation_check_fragment'] = str(fragment.relative_to(ROOT))
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect-saved-geometry', action='store_true')
    parser.add_argument('--source', type=lambda value: ROOT / value)
    parser.add_argument('--qualification', type=lambda value: ROOT / value)
    parser.add_argument('--output', type=lambda value: ROOT / value, required=True)
    args = parser.parse_args()
    if args.inspect_saved_geometry:
        answer = inspect_saved_geometry(args.output)
    elif args.source and args.qualification:
        try:
            answer = prepare(args.source, args.output, args.qualification)
        except (ValueError, KeyError, FileNotFoundError) as error:
            answer = dict(native_restart_staged=False, cold_cut_equilibrated=False,
                          interface_ready=False, reason=str(error), new_solver_runs=0,
                          source=str(args.source.relative_to(ROOT)),
                          qualification=str(args.qualification.relative_to(ROOT)))
            if not args.output.exists():
                args.output.mkdir(parents=True)
                (args.output / 'coldcut-interface-not-ready.json').write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding='utf8')
            print(json.dumps(answer, ensure_ascii=False, indent=2))
            raise SystemExit(2)
    else:
        parser.error('Preparation requires --source and --qualification; inspection uses --inspect-saved-geometry')
    print(json.dumps(answer, ensure_ascii=False, indent=2))
