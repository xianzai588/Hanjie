"""P1A-1.1 几何接口与独立回读回归测试。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "simulation" / "structural-v4" / "geometry-independent-audit.json"


def _audit() -> dict:
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def test_independent_geometry_audit_passes_all_models() -> None:
    payload = _audit()
    assert payload["pass"] is True
    assert len(payload["models"]) == 7
    assert all(model["checks"]["pass"] is True for model in payload["models"])


def test_cad_interface_targets_and_shell_clearance() -> None:
    models = {model["model_id"]: model for model in _audit()["models"]}
    expected = {
        "4P-FAIR_A": 108.0,
        "4P-FAIR_B": 72.0,
        "6P-FAIR_A": 108.0,
        "6P-FAIR_B": 108.0,
        "8P-FAIR_A": 108.0,
        "8P-FAIR_B": 144.0,
    }
    for model_id, target in expected.items():
        model = models[model_id]
        assert abs(model["cad_measured_total_weld_length_mm"] - target) <= 1e-5
        assert model["seat_shell_max_penetration_mm"] == 0.0
        assert model["seat_shell_intersection_volume_mm3"] == 0.0
        assert model["seat_shell_min_gap_mm"] >= 0.0199


def test_6p_fair_a_and_b_are_geometry_equivalent() -> None:
    models = {model["model_id"]: model for model in _audit()["models"]}
    assert abs(models["6P-FAIR_A"]["brep_volume_mm3"] - models["6P-FAIR_B"]["brep_volume_mm3"]) < 1e-6
    assert abs(
        models["6P-FAIR_A"]["cad_measured_total_weld_length_mm"]
        - models["6P-FAIR_B"]["cad_measured_total_weld_length_mm"]
    ) < 1e-6


def test_discrete_minimum_ligament_accounts_for_slot_root() -> None:
    for model in _audit()["models"]:
        if model["model_id"] == "Continuous":
            continue
        assert abs(model["independent_minimum_ligament_mm"] - 19.0) < 1e-9


def test_common_shell_artifacts_exist() -> None:
    assert (ROOT / "simulation" / "structural-v4" / "common" / "shell.brep").is_file()
    assert (ROOT / "simulation" / "structural-v4" / "common" / "shell.step").is_file()
