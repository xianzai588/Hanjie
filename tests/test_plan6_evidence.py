"""Plan 6 数值准入证据的机械一致性检查。"""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_swept_continuous_mesh_meets_frozen_quality_gate():
    result = _load("simulation/structural-v4/results/struct0-prep/continuous-swept-plan6-admitted.json")
    assert result["mesh_acceptance_pass"] is True
    assert result["quality"]["below_0p1_count"] == 0
    assert result["quality"]["nonpositive_count"] == 0
    assert result["interfaces"]["conforming_by_construction"] is True
    assert all(result["checks"].values())


def test_structural_dress_rehearsal_passes_but_formal_run_remains_closed():
    result = _load("simulation/structural-v4/results/struct0-prep/struct0-prep-dress-rehearsal-plan6.json")
    assert result["dress_rehearsal_pass"] is True
    assert result["checks"]["sparse_global_newton_path"] is True
    assert result["checks"]["thermal_contact_activated_then_separated"] is True
    assert result["struct0_prep_status"] == "ready_pending_admitted_thermal_history"
    assert result["formal_struct_0_allowed"] is False
    assert result["bore_axis_fit"]["engineering_meaning"] == "none_synthetic_rehearsal_only"


def test_boundary_neumann_gate_obeys_conditional_m_rule_when_results_exist():
    path = ROOT / "simulation/thermal-v5/results/boundary-neumann-plan6/assessment.json"
    if not path.exists():
        return
    result = json.loads(path.read_text(encoding="utf-8"))
    field = result["continuous_peak_field"]["ernife_ci"]
    eligible = field["volume_weighted_p95_abs_peak_difference_c"] < 10.0 and field["volume_weighted_mean_abs_peak_difference_c"] < 5.0 and result["gate_components"]["fixed_histories"]
    assert result["new_nest_m_allowed"] is eligible
    assert result["formal_struct_0_allowed"] is False
