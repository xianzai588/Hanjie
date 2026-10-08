"""Audit the accepted ring calculations, not a fabricated manufacturing pass."""
import json
import copy
import importlib.util
from pathlib import Path

import numpy as np
import yaml
import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "simulation/ring-baseline-manufacturing"
spec = importlib.util.spec_from_file_location('ring_thermal_inputs', BASE / 'thermal_inputs.py')
inputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs)


def read(path):
    return json.loads((BASE / path).read_text())


def test_born_root_exposes_interface_until_cap_exists_and_enthalpy_reference_is_zero():
    # One root and one future cap sharing a face: no future internal interface
    # conductance or duplicated environment loss can exist before cap birth.
    owners = np.array([[0, -1], [0, 1], [1, -1]])
    assert inputs.active_exterior_faces(np.array([True, False]), owners).tolist() == [True, True, False]
    assert inputs.active_exterior_faces(np.array([True, True]), owners).tolist() == [True, False, True]
    reference = read("results/coarse-dt0.5-stop12.1212-root0-r75/thermal-result.json")
    for table in reference['material_inputs']:
        value = inputs.specific_enthalpy(np.array([20., 100., 200.]), table)
        assert value[0] == 0
        assert 0 < value[1] < value[2]


def test_changed_prefix_state_or_inputs_are_rejected():
    expected = dict(mesh_cache_key={'geometry': 'current', 'size': 6.}, process_version='current', arc_dt_s=1.,
                    declared_source={'root_z_mm': 115., 'radial_mm': 75.}, material_inputs=[{'cp': 500.}])
    identity = dict(schema='ring-final-accepted-arc-prefix-v1', state_npz_sha256='accepted',
                    mesh_cache_key=expected['mesh_cache_key'], thermal_result={k:v for k,v in expected.items() if k != 'mesh_cache_key'})
    inputs.validate_arc_prefix_metadata(identity, expected, 'accepted')
    with pytest.raises(RuntimeError):
        inputs.validate_arc_prefix_metadata(identity, expected, 'changed-state')
    for field, value in [('process_version', 'new'), ('arc_dt_s', .5), ('declared_source', {'root_z_mm': 116.2}), ('material_inputs', [{'cp': 700.}]), ('mesh_cache_key', {'geometry': 'different'})]:
        changed = copy.deepcopy(expected);changed[field] = value
        with pytest.raises(RuntimeError):
            inputs.validate_arc_prefix_metadata(identity, changed, 'accepted')


def test_tooling_exit_requires_both_minimum_hold_and_strict_temperature_gate():
    policy=dict(minimum_post_arc_hold_s=120.,part_max_temperature_exclusive_C=55.)
    assert not inputs.tools_may_release(119.,0.,54.,policy)
    assert not inputs.tools_may_release(120.,0.,55.,policy)
    assert inputs.tools_may_release(120.,0.,54.,policy)


def test_a_b_metrology_is_invariant_to_whole_object_rigid_motion():
    from hanjie.simulation.structural_prep import fit_position_diameter
    theta = np.arange(96) * 2 * np.pi / 96
    def circle(radius, height, offset=(0., 0.)):
        return np.c_[radius*np.cos(theta)+offset[0], radius*np.sin(theta)+offset[1], np.full(96,height)]
    A=circle(77.5,0);B=np.vstack([circle(75,20),circle(75,180)]);bore=np.vstack([circle(20,z,(.03,.02)) for z in (100,107.5,115)])
    original=fit_position_diameter(A,B,bore)
    cy,sy=np.cos(.2),np.sin(.2);cz,sz=np.cos(.3),np.sin(.3)
    rotation=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1]]) @ np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])
    move=lambda points:points @ rotation.T + [2.,-3.,4.]
    transformed=fit_position_diameter(move(A),move(B),move(bore))
    assert abs(original['position_diameter_mm']-transformed['position_diameter_mm']) < 1e-10


def test_actual_16_arcs_energy_and_cold_exit_close():
    result = read("results/coarse-dt1-root0-r75/thermal-result.json")
    baseline = yaml.safe_load((ROOT / "project/submission-baseline.yaml").read_text())
    assert result["process_version"] == baseline["version"]
    assert result["complete_final_thermal_cycle"]
    assert result["actual_path_320mm"]
    assert abs(result["source_energy_J"] - 96000) < 1e-6
    assert abs(result["executed_path_mm"] - 320) < 1e-8
    arcs, starts = result["arc_schedule"], result["start_records"]
    assert len(arcs) == len(starts) == 16
    assert [r["segment"] for r in arcs] == baseline["weld_layout"]["sequence"] * 2
    for arc, start in zip(arcs, starts):
        assert (arc["pass"], arc["segment"], arc["start_s"]) == (start["pass"], start["segment"], start["start_s"])
        assert abs((arc["end_s"] - arc["start_s"]) * result["travel_mm_s"] - 20) < 1e-10
        assert start["interpass_100C"] == (start["second_layer_current_max_C"] <= 100)
    assert result["interpass_limits_pass"] == all(r["interpass_100C"] for r in starts)
    history = np.loadtxt(BASE / "results/coarse-dt1-root0-r75/thermal-history.csv", delimiter=",", skiprows=1)
    assert np.all(np.diff(history[:, 0]) > 0)
    assert np.all(np.diff(history[:, 5]) >= -1e-8)
    assert abs(history[-1, 5] - 96000) < 1e-6
    assert abs(history[-1, 0] - result["end_s"]) < 1e-8
    # Global energy mismatch is the sum of nodal residuals times dt.  Its bound
    # follows Cauchy-Schwarz; a mesh-independent arbitrary tighter cutoff would
    # contradict the declared nodal residual and reject a valid solve.
    energy_bound = history[:, 1] * np.sqrt(result['mesh']['nodes']) * history[:, 8] + 1e-7
    assert np.all(abs(history[:, 7]) <= energy_bound)
    assert np.max(history[:, 8]) < 1e-7
    assert result["tooling_exit"]["part_max_C"] < 55
    assert arcs[-1]["end_s"] + 120 <= result["tooling_exit"]["time_s"] < result["end_s"]
    assert result['tooling_release_policy']['minimum_post_arc_hold_s'] == baseline['fixture_feasibility']['release_minimum_post_arc_hold_s']
    assert result['tooling_release_policy']['part_max_temperature_exclusive_C'] == baseline['fixture_feasibility']['release_part_max_temperature_exclusive_C']
    assert result['start_temperature_permissions_pass']
    for start in starts:
        assert start['control_maximum_C'] == (35. if start['pass']==0 else 100.)
        assert start['control_minimum_C'] <= start['second_layer_current_max_C'] <= start['control_maximum_C']
    assert result["final_max_C"] < 21
    assert not result["mechanical_state_computed"]
    assert not result["full_manufacturing_chain_passed"]


def test_current_root_source_and_first_arc_refinement_are_same_case():
    full = read("results/coarse-dt1-root0-r75/thermal-result.json")
    small = read("results/coarse-dt0.5-stop12.1212-root0-r75/thermal-result.json")
    assert full["declared_source"] == small["declared_source"]
    assert full["declared_source"]["radial_mm"] == 75
    assert full["declared_source"]["root_z_mm"] == 115
    assert full["declared_source"]["cap_z_mm"] == 117
    assert full["material_inputs"] == small["material_inputs"]
    assert full["mesh"]["cache_key"] == small["mesh"]["cache_key"]
    assert abs(small["source_energy_J"] - 6000) < 1e-7
    assert abs(small["executed_path_mm"] - 20) < 1e-7
    assert not small["actual_path_320mm"]
    assert not small["complete_final_thermal_cycle"]


def test_support_geometry_and_combined_stress_inputs_are_honest():
    coarse = read("results/coarse/cold-response.json")
    medium = read("results/medium/cold-response.json")
    current = read("results/assessment.json")
    assert "p1-current-coarse-safe" in coarse["mesh"]["source_snapshot"]
    assert coarse["mesh"]["original_cache_identity_available"]
    assert coarse["mesh"]["nodes"] > 0
    assert coarse["elastic_inputs"] == medium["elastic_inputs"]
    assert coarse["elastic_inputs"]["5"]["E_MPa"] == 200000
    for result in (coarse, medium):
        audit = result["mesh"]["actual_faceted_gap_audit"]
        assert audit["unwelded_gap_geometry_verified"]
        assert audit["minimum_faceted_shell_inner_radius_in_z100_115_mm"] > 74.98
        assert audit["direct_precoated_seat_shell_shared_nodes"] == 0
        assert result["mesh"]["effective_segment_length_mm"] == 18
        assert result["mesh"]["fillet_leg_mm"] == 3.5
        assert not result["material_capacity_assigned"]
        assert not result["full_manufacturing_chain_passed"]
        for response in result["responses"].values():
            assert response["input_microstrain"] == 100
            assert response["free_residual_N"] < 1e-4
            assert response["gauge_reaction_N"] < 1e-5
    assert len(coarse["responses"]) == 6
    assert len(medium["responses"]) == 3
    assert len(coarse["conditional_scans"]) == 120
    for row in coarse["conditional_scans"]:
        stress = json.loads(row["combined_VM_by_material_MPa"])
        assert abs(row["combined_maximum_von_Mises_MPa"] - max(stress.values())) < 1e-9
        assert not row["material_feasibility_established"]
        assert abs(row["initial_bore_allowable_low_mm"] - (40 - row["minimum_diameter_change_um"] / 1000)) < 1e-12
        assert abs(row["initial_bore_allowable_high_mm"] - (40.025 - row["maximum_diameter_change_um"] / 1000)) < 1e-12
    assert current["example_conditional_state"]["first_harmonic_precoat_redistribution_microstrain"] > 0
    assert current["cold_space_comparison"]["symmetric_final_shrink"]["maximum_von_Mises_MPa"]["relative_difference"] > .05
    assert current["thermal_cycle_completed"]
    assert not current["current_fusion_verified"]
    assert not current["residual_position_verified"]
    assert not current["bore_size_verified"]
    assert not current["production_release"]


def test_rejected_diagnostics_cannot_be_current_evidence():
    for path in ("results/diagnostic-gap-penetrating-cold/cold-response.json",
                 "results/diagnostic-static-interface/coarse-dt0.5-stop12.1212-root0-r75/thermal-result.json"):
        assert not read(path)["current_evidence_usable"]
    current = read("results/assessment.json")
    assert current["cold_response_summary"]["first_harmonic_final_shrink"]["position_diameter_um"] == read("results/coarse/cold-response.json")["responses"]["first_harmonic_final_shrink"]["position_diameter_um"]
