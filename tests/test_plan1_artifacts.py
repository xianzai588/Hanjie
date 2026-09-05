"""计划一关键交付物和证据边界回归测试。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_plan1_outputs_are_traceable_and_unvalidated() -> None:
    inputs = yaml.safe_load((ROOT / "project/g-inputs-v5.2.yaml").read_text(encoding="utf-8"))
    thermal = json.loads((ROOT / "simulation/thermal-v5/results/thermal0-summary.json").read_text(encoding="utf-8"))
    metallurgy = json.loads((ROOT / "simulation/metallurgy-v5/results/metallurgy0-summary.json").read_text(encoding="utf-8"))

    assert inputs["status"] == "frozen_for_digital_baseline"
    assert inputs["process"]["net_line_energy_j_per_mm"] == 330.0
    assert thermal["evidence_level"] == "solver_result_unvalidated"
    assert thermal["energy"]["power_definition_relative_error"] < 1e-12
    assert thermal["energy"]["line_energy_definition_relative_error"] < 1e-12
    thermal_manifest = json.loads((ROOT / "simulation/thermal-v5/results/thermal0-result-manifest.json").read_text(encoding="utf-8"))
    assert thermal_manifest["input_sha256"] == thermal["input_sha256"]
    assert all(len(value) == 64 for value in thermal_manifest["files"].values())
    assert metallurgy["thermal_input"].endswith("thermal0-field.npz")
    assert metallurgy["evidence_level"] == "literature_supported_plus_solver_result_unvalidated"
    dilution = metallurgy["weld_dilution_and_composition"]
    assert dilution["dilution_method"] == "geometry_based_nominal"
    assert dilution["thermal_fusion_validated"] is False
    assert dilution["chemistry_validated"] is False
    assert abs(sum(dilution["nominal_dilution_fraction"].values()) - 1.0) < 1e-12
    assert metallurgy["material_statistics"]["qt450_10_side_region"]["peak_temperature_c"] > metallurgy["material_statistics"]["qt450_10_material_zone"]["peak_temperature_c"]
    assert metallurgy["risk_assessment"]["qt450_10"]["martensite_high_hardening_risk"] == "High"
    metallurgy_manifest = json.loads((ROOT / "simulation/metallurgy-v5/results/metallurgy0-result-manifest.json").read_text(encoding="utf-8"))
    assert metallurgy_manifest["thermal_input_sha256"] == metallurgy["thermal_input_sha256"]
    assert "phase fraction" not in json.dumps(metallurgy, ensure_ascii=False).lower()


def test_plan1_field_is_finite_and_peak_is_below_fusion_gate() -> None:
    field_path = ROOT / "simulation/thermal-v5/results/thermal0-field.npz"
    with np.load(field_path) as field:
        for key in ("temperature_final", "temperature_peak", "max_cooling_rate_c_s"):
            assert np.isfinite(field[key]).all(), key
        assert field["temperature_peak"].max() < 1350.0
        assert field["t8_5_valid"].sum() == 49
        assert np.all(field["t8_5_s"][field["t8_5_valid"]] > 0.0)


def test_plan1_evidence_graph_registers_new_outputs() -> None:
    graph = yaml.safe_load((ROOT / "evidence/evidence_graph.yaml").read_text(encoding="utf-8"))
    simulations = graph["taxonomy"]["simulations"]
    assert simulations["SIM-THERMAL0-V5"]["evidence_level"] == "solver_result_unvalidated"
    assert simulations["SIM-METALLURGY0-V5"]["evidence_level"] == "solver_result_unvalidated"
    assert simulations["SIM-THERMAL0-AUDIT-V5"]["evidence_level"] == "solver_result_unvalidated"
    assert "CLAIM-007" in graph["claims_graph"]


def test_g_thermal_audit_separates_energy_pass_from_gate_review() -> None:
    audit = json.loads((ROOT / "simulation/thermal-v5/results/g-thermal-audit/G-THERMAL-audit.json").read_text(encoding="utf-8"))
    assert audit["energy_audit"]["pass"] is True
    assert audit["gate_checks"]["time_step_pass"] is True
    assert audit["gate_checks"]["mesh_pass"] is False
    assert audit["gate_status"] == "review_required"
    assert max(item["energy_balance_error_pct"] for item in audit["energy_audit"]["cases"]) < 1.0
