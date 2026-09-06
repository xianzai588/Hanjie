import json
from pathlib import Path

import pytest


ROOT=Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


def test_xsec_sequence_was_executed_and_stops_before_xfine_or_time_refinement():
    result=load("simulation/thermal-v5/results/xsec-refinement-study/assessment.json")
    assert list(result["levels"])==["XSEC-M","XSEC-F","XSEC-VF"]
    assert all(result["mesh_isolation_checks"].values())
    first=result["pairs"]["XSEC-M_to_XSEC-F"]["continuous_peak_field"]["ernife_ci"]
    second=result["pairs"]["XSEC-F_to_XSEC-VF"]["continuous_peak_field"]["ernife_ci"]
    assert first["volume_weighted_p95_abs_peak_difference_c"]==pytest.approx(9.60,abs=.01)
    assert second["volume_weighted_p95_abs_peak_difference_c"]==pytest.approx(18.26,abs=.01)
    assert result["asymptotic_diagnosis"]["entered_asymptotic_region"] is False
    assert result["xfine_allowed"] is False
    assert result["time_step_recheck_allowed"] is False
    assert result["spatial_gate_pass"] is False
    assert result["thermal_1_allowed"] is False


def test_xsec_second_layer_diagnosis_keeps_unresolved_causes_open():
    diagnosis=load("simulation/thermal-v5/results/xsec-refinement-study/assessment.json")["second_layer_diagnosis"]
    assert max(diagnosis["direct_source_partition_spread_j"].values())<1e-9
    assert max(diagnosis["cumulative_net_conduction_relative_spread"].values())<.005
    assert diagnosis["local_edge_nesting_fraction"]["XSEC-F_to_XSEC-VF"]["n"]<.9
    assert "异材界面逐面通量" in diagnosis["still_open"]


def test_global_newton_benchmarks_pass_without_opening_struct_gate():
    result=load("simulation/structural-v4/results/struct0-prep/global-newton-benchmarks.json")
    assert all(result["checks"].values())
    assert result["tensile_bar"]["computed_final_strain"]==pytest.approx(result["tensile_bar"]["expected_final_strain"],rel=1e-8)
    assert result["stress_free_birth"]["born_max_abs_stress_mpa"]<1e-9
    assert result["constrained_thermal_release"]["steps"][4]["name"]=="release_at_600c"
    assert result["constrained_thermal_release"]["steps"][4]["converged"] is True
    assert result["struct_prep_gate_pass"] is False


def test_continuous_mesh_has_regions_and_interfaces_but_records_quality_debt():
    result=load("simulation/structural-v4/results/struct0-prep/continuous-unified-mesh.json")
    assert result["counts"]["tetrahedra"]>100000
    assert all(value>0 for value in result["regions"]["tetrahedron_counts"].values())
    assert all(result["checks"].values())
    assert result["quality"]["nonpositive_count"]==0
    assert result["quality"]["below_0p1_count"]>0
    assert result["heat_to_structure_mapping"]["status"]=="not_executed"
    assert result["contact"]["status"]=="surfaces_registered_solver_not_implemented"
    assert result["struct_prep_gate_pass"] is False
