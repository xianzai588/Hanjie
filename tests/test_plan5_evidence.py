"""Plan 5 冻结规则与 STRUCT-0-PREP 证据边界。"""
import json
from pathlib import Path

import yaml


ROOT=Path(__file__).resolve().parents[1]


def _json(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


def test_plan5_mesh_sequence_is_preregistered_as_integer_nested():
    plan=yaml.safe_load((ROOT/"project/thermal-nested-refinement-v5.6.yaml").read_text(encoding="utf-8"))
    assert [row["mesh_overrides"]["cross_local_subdivision_factor"] for row in plan["cases"]]==[1,2,4]
    assert len({row["mesh_overrides"]["cross_local_base_spacing_mm"] for row in plan["cases"]})==1
    assert plan["acceptance"]["asymptotic_reduction_ratio_max"]==.5
    assert plan["detailed_ledgers"] is True


def test_struct_prep_passes_components_but_rejects_unresolved_weld_mesh():
    result=_json("simulation/structural-v4/results/struct0-prep/struct0-prep-plan5-assessment.json")
    assert result["checks"]["global_j2_newton_retained"] is True
    assert result["checks"]["frictionless_normal_contact_benchmarks"] is True
    assert result["checks"]["local_thermal_mapping_benchmark"] is True
    assert result["checks"]["global_small_mesh_activation_stress_free_birth"] is True
    assert result["checks"]["continuous_weld_mesh_quality_closed"] is False
    assert result["struct_0_prep_ready_pending_admitted_thermal_history"] is False
    assert result["formal_struct_0_allowed"] is False


def test_mapping_never_promotes_local_field_to_formal_struct_load():
    result=_json("simulation/structural-v4/results/struct0-prep/thermal-mapping-benchmark.json")
    assert result["thermal_mapping_benchmark_pass"] is True
    assert result["formal_struct_0_thermal_load_allowed"] is False
    assert result["checks"]["outside_domain_explicitly_unavailable"] is True
    assert result["checks"]["cross_material_explicitly_unavailable"] is True


def test_nested_assessment_stops_xfine_and_time_step_when_local_fields_fail():
    result=_json("simulation/thermal-v5/results/nested-refinement-study/assessment.json")
    assert result["gate_components"]["strict_nesting"] is True
    assert result["gate_components"]["interface_flux"] is True
    assert result["gate_components"]["local_source_distribution"] is True
    assert result["gate_components"]["continuous_peak_and_flips"] is False
    assert result["gate_components"]["fixed_coordinate_full_history"] is False
    assert result["spatial_gate_pass"] is False
    assert result["xfine_allowed"] is False
    assert result["time_step_recheck_allowed"] is False
    assert result["formal_struct_0_allowed"] is False
