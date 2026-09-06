"""计划一关键交付物和证据边界回归测试。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]


def _load_thermal_module():
    spec = importlib.util.spec_from_file_location("thermal0_for_test", ROOT / "simulation/thermal-v5/run_thermal0.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_goldak_capture_gate_distinguishes_buffered_and_truncated_domains() -> None:
    thermal = _load_thermal_module()
    parameters = (6.0, 10.0, 2.5, 2.5, 0.6, 1.4, False)
    buffered = thermal._goldak_domain_capture_fraction(30.0, ((-70.0, 70.0), (-36.0, 5.0), (-12.0, 12.0)), *parameters)
    truncated = thermal._goldak_domain_capture_fraction(42.0, ((-36.0, 36.0), (-36.0, 5.0), (-12.0, 12.0)), *parameters)
    assert buffered >= 0.999
    assert truncated < 0.995


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
    assert metallurgy["region_semantics"]["parent_risk_mask_includes_weld_cells"] == 0
    assert metallurgy["region_semantics"]["parent_haz_width_includes_weld"] is False
    assert metallurgy["risk_assessment"]["qt450_10"]["risk_location"]["n_mm"] < -3.0
    assert metallurgy["risk_assessment"]["q235b"]["risk_location"]["n_mm"] > 3.0
    metallurgy_manifest = json.loads((ROOT / "simulation/metallurgy-v5/results/metallurgy0-result-manifest.json").read_text(encoding="utf-8"))
    assert metallurgy_manifest["thermal_input_sha256"] == metallurgy["thermal_input_sha256"]
    assert "phase fraction" not in json.dumps(metallurgy, ensure_ascii=False).lower()


def test_plan1_field_is_finite_and_matches_reported_fusion_threshold_status() -> None:
    field_path = ROOT / "simulation/thermal-v5/results/thermal0-field.npz"
    summary = json.loads((ROOT / "simulation/thermal-v5/results/thermal0-summary.json").read_text(encoding="utf-8"))
    with np.load(field_path) as field:
        for key in ("temperature_final", "temperature_peak", "max_cooling_rate_c_s"):
            assert np.isfinite(field[key]).all(), key
        threshold_exceeded = bool(field["temperature_peak"].max() >= summary["fusion_threshold_c"])
        assert threshold_exceeded is summary["fusion_threshold_exceeded"]
        assert field["t8_5_valid"].sum() > 0
        assert np.all(field["t8_5_s"][field["t8_5_valid"]] > 0.0)


def test_thermal02_sampling_uses_fixed_physical_coordinates() -> None:
    sensors = json.loads((ROOT / "simulation/thermal-v5/results/thermal0-sensors.json").read_text(encoding="utf-8"))
    assert sensors["sampling"]["method"] == "trilinear_interpolation"
    assert sensors["sampling"]["coordinate_system"] == "fixed_local_window_moving_source_s_n_z_cell_centers"
    assert sensors["sampling"]["maximum_coordinate_drift_mm"] == 0.0
    assert sensors["sensors"]["QT_HAZ"]["requested_coordinate_mm"][1] == -5.0
    assert sensors["sensors"]["QT_HAZ"]["material_region"] == "QT450-10"
    assert sensors["sensors"]["Q235B_HAZ"]["material_region"] == "Q235B"
    assert sensors["sensors"]["WELD_CENTER"]["requested_coordinate_mm"][1] == 0.0
    assert sensors["sensors"]["QT_SURROGATE_INTERFACE_REF"]["requested_coordinate_mm"][1] == -3.0
    assert sensors["sensors"]["Q235B_SURROGATE_INTERFACE_REF"]["requested_coordinate_mm"][1] == 3.0
    assert all(
        sensor["requested_coordinate_mm"] == sensor["sampled_coordinate_mm"]
        for sensor in sensors["sensors"].values()
    )


def test_thermal02_energy_and_source_capture_accounting_are_explicit() -> None:
    thermal = json.loads((ROOT / "simulation/thermal-v5/results/thermal0-summary.json").read_text(encoding="utf-8"))
    energy = thermal["energy"]
    balance = energy["global_thermal_energy_balance"]
    source_path = thermal["source_path"]
    capture = energy["source_domain_capture"]
    assert thermal["grid"]["coordinate_mode"] == "fixed_local_window_moving_source"
    assert source_path["start_s_mm"] == -30.0
    assert source_path["end_s_mm"] == 30.0
    assert source_path["center_outside_domain_steps"] == 0
    assert source_path["minimum_s_boundary_margin_mm"] >= 30.0
    assert thermal["peak_location_gate"]["at_artificial_s_boundary_cell"] is False
    assert capture["status"] == "PASS"
    assert capture["minimum_fraction"] >= capture["required_minimum_fraction"] >= 0.999
    assert energy["source_energy_normalization"]["status"] == "PASS"
    assert balance["status"] == "PASS"
    assert abs(balance["residual_percent_of_source"]) < 0.02


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
    assert audit["gate_checks"]["mesh_pass"] is True
    assert audit["gate_checks"]["source_domain_capture_pass"] is True
    assert audit["gate_checks"]["source_center_inside_domain_pass"] is True
    assert audit["gate_checks"]["peak_not_at_artificial_s_boundary_pass"] is True
    assert audit["gate_status"] == "review_required"
    assert max(item["energy_balance_error_pct"] for item in audit["energy_audit"]["cases"]) < 1.0
    assert audit["gate_checks"]["source_resolution_pass"] is True
    cases = {item["case"]: item for item in audit["cases"]}
    assert cases["mesh-medium"]["time"]["time_step_s"] == cases["mesh-fine"]["time"]["time_step_s"]
    assert max(item["global_thermal_energy_balance"]["residual_percent_of_source"] for item in audit["energy_audit"]["cases"]) < 0.02
