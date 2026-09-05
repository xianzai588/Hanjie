"""验证三维静力筛查的结果闭包与报告一致性。"""

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT_ROOT = ROOT / "simulation" / "structural-v4" / "results" / "static-screening"


def test_static_screening_has_complete_direction_matrix():
    payload = json.loads((RESULT_ROOT / "static-screening-raw.json").read_text(encoding="utf-8"))
    rows = payload["rows"]
    assert payload["evidence_level"] == "solver_result_unvalidated"
    assert len(rows) == 42
    assert all(row["direction_count"] == 7 for row in rows)
    assert all(len(row["direction_results"]) == 7 for row in rows)
    assert all(
        math.isfinite(row["worst_position_diameter_mm"])
        and math.isfinite(row["worst_stress_mpa"])
        for row in rows
    )


def test_static_screening_analysis_passes_without_thermal_claim():
    summary = json.loads((RESULT_ROOT / "static-screening-analysis.json").read_text(encoding="utf-8"))
    assert summary["static_screening_pass"] is True
    assert summary["full_thermal_structural_gate_pass"] is False
    assert all(item["pass"] for item in summary["convergence"])
    assert all(item["pass"] for item in summary["boundary_sensitivity"])
    assert all(item["pass"] for item in summary["6P_A_B_equivalence"])
