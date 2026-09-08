"""设计修订关键链：独立守恒复算、几何反例和缺失信号闭锁。"""
import copy
import math
from pathlib import Path
import numpy as np
import pytest
import yaml
from hanjie.domain.competition_design import (read_spec, process_balance, precision_budget,
                                             cycle_permission, run_design, current_assessment)

ROOT = Path(__file__).resolve().parents[1]


def test_fixed_feed_closes_both_efficiency_endpoints():
    spec = read_spec(ROOT)
    nominal = yaml.safe_load((ROOT / spec["process_source"]).read_text(encoding="utf-8"))["process"]["nominal"]
    result = process_balance(spec, nominal)
    p = spec["process"]
    for eta, leg in zip(p["deposition_efficiency_range"], result["equivalent_leg_range_mm"]):
        volume_one_second = math.pi * p["wire_diameter_mm"]**2/4 * result["fixed_feed_mm_s"] * eta * p["pass_count"]
        assert volume_one_second == pytest.approx(leg**2/2*nominal["travel_speed_mm_s"])
    assert result["equivalent_leg_range_mm"][0] == 3.5
    assert result["equivalent_leg_range_mm"][1] < 3.8
    spec["process"]["clearance_leg_mm"] = 3.5
    with pytest.raises(ValueError, match="包络"):
        process_balance(spec, nominal)


def test_support_plane_budget_matches_independent_plane_fit():
    spec = read_spec(ROOT)
    f, p = spec["fixture"], spec["precision"]
    theta = np.arange(3) * 2*np.pi/3
    xy = f["support_radius_mm"] * np.column_stack((np.cos(theta), np.sin(theta)))
    matrix = np.column_stack((xy, np.ones(3)))
    slopes = []
    for heights in ((0, 0, p["support_height_spread_limit_mm"]), (0, p["support_height_spread_limit_mm"], p["support_height_spread_limit_mm"])):
        plane = np.linalg.solve(matrix, heights)
        slopes.append(np.linalg.norm(plane[:2]))
    budget = precision_budget(spec)
    assert max(slopes) == pytest.approx(budget["support_tilt_rad"])
    assert budget["design_budget_closes"]
    assert not budget["thermal_residual_verified"]
    spec["precision"]["radial_allocations_mm"]["thermal_residual_target"] = .012
    assert not precision_budget(spec)["design_budget_closes"]


@pytest.fixture(scope="module")
def design():
    return run_design(ROOT)[0]


def test_revised_access_has_no_named_body_collision(design):
    g = design["geometry"]
    assert all(g["shape_validity"].values())
    assert all(row["clear"] for row in g["poses"])
    assert g["torch_feed_clearance_mm"] >= 1.5
    assert max(g["cartridge_intersections_mm3"].values()) < 1e-6
    assert g["bottom_route_allowed"]
    assert g["nominal_vertical_drop_coverage"]
    assert not any(design["release"].values())


def test_internal_cone_has_positive_return_even_if_self_locking(design):
    f = design["fixture"]
    assert f["positive_return_stroke_available_mm"] > f["positive_return_stroke_required_mm"]
    assert f["cone_force_scenarios"][-1]["self_lock_possible"]
    assert f["nominal_average_band_pressure_mpa"] < .25


def test_weld_interlocks_fail_closed():
    ready = dict(shield_present=True, bottom_open=True, fixture_locked=True, path_checked=True,
                 temperature_min=150, temperature_max=160, gas_flow_l_min=10)
    assert cycle_permission("weld", **ready)
    for field, value in (("shield_present",False),("bottom_open",False),("fixture_locked",False),
                         ("path_checked",False),("temperature_max",200),("gas_flow_l_min",None),
                         ("temperature_min",float("nan"))):
        assert not cycle_permission("weld", **{**ready, field:value})


def test_withdraw_requires_cooling_and_positive_return():
    ready = dict(shield_present=True, bottom_open=True, return_confirmed=True,
                 clamp_released=True, temperature_max=50, time_after_arc=120)
    assert cycle_permission("withdraw", **ready)
    for field, value in (("return_confirmed",False),("clamp_released",False),
                         ("temperature_max",55),("time_after_arc",119),("bottom_open",False)):
        assert not cycle_permission("withdraw", **{**ready, field:value})


def test_acceptance_uses_diameter_uncertainty_and_measurement_temperature():
    ready = dict(shield_present=False, bottom_open=True, return_confirmed=True, clamp_released=True,
                 inspection_passed=True, measurement_diameter=.048, uncertainty_diameter=.002, temperature_max=20)
    assert cycle_permission("accept", **ready)
    for field, value in (("measurement_diameter",.049),("uncertainty_diameter",None),
                         ("temperature_max",50),("inspection_passed",False)):
        assert not cycle_permission("accept", **{**ready, field:value})


def test_release_threshold_matches_baseline_band():
    baseline = yaml.safe_load((ROOT / "project/baseline.yaml").read_text(encoding="utf-8"))["fixture"]
    prep = yaml.safe_load((ROOT / "project/struct-0-prep.yaml").read_text(encoding="utf-8"))["fixture"]["release_logic"]
    assert prep["interface_max_below_c"] == baseline["release_temperature_c"] + baseline["release_temperature_band_c"]


def test_report_rejects_stale_inputs(monkeypatch):
    import hanjie.domain.competition_design as module
    snapshot = copy.deepcopy(current_assessment(ROOT)["inputs"])
    snapshot["structured"]["project/process.yaml"]["process"]["nominal"]["current_a"] += 1
    monkeypatch.setattr(module, "input_snapshot", lambda root:snapshot)
    with pytest.raises(ValueError, match="输入已变化"):
        current_assessment(ROOT)


def test_current_drawing_manifest_excludes_legacy_fixture():
    import json
    manifest = json.loads((ROOT/"cad/generated/engineering-drawings/drawing-manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "COMPETITION-R1"
    assert len(manifest["drawings"]) == 4
    assert "fixture-part.svg" not in manifest["drawings"]
    assert "weld-assembly.svg" not in manifest["drawings"]


@pytest.mark.parametrize("key",["fixed_feed_mm_s","total_net_heat_j","arc_on_time_s"])
def test_report_blocks_stale_summary_numbers(key):
    import importlib.util
    spec = importlib.util.spec_from_file_location("competition_report", ROOT/"deliverables/report/build_technical_report_pdf.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = copy.deepcopy(current_assessment(ROOT))
    module.validate_report_numbers(result)
    result["process"][key] *= 1.2
    with pytest.raises(ValueError, match="正文关键数值"):
        module.validate_report_numbers(result)
