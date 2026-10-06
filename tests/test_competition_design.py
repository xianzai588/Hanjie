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
        d = p["wire_diameter_mm"] + (-p["wire_diameter_tolerance_mm"] if eta == p["deposition_efficiency_range"][0] else p["wire_diameter_tolerance_mm"])
        feed = result["fixed_feed_mm_s"] + (-p["feed_tolerance_mm_s"] if eta == p["deposition_efficiency_range"][0] else p["feed_tolerance_mm_s"])
        speed = nominal["travel_speed_mm_s"] * (1 + p["travel_relative_tolerance"] if eta == p["deposition_efficiency_range"][0] else 1 - p["travel_relative_tolerance"])
        volume_one_second = math.pi * d**2/4 * feed * eta * p["pass_count"] / speed
        assert volume_one_second == pytest.approx(leg**2/2)
    assert result["equivalent_leg_range_mm"][0] >= 3.5
    assert result["equivalent_leg_range_mm"][1] < 4.3
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
    assert not budget["thermal_residual_design_verified"]
    assert budget["physical_validation_recommended"]
    assert budget['thermal_diameter_allowance_with_honing_mm']==pytest.approx(.0135)
    assert budget['thermal_diameter_allowance_without_removal_mm']==pytest.approx(.020)
    # The former 16 um thermal target does not fit the honing branch even
    # though the budget before material removal appears to fit.
    spec['precision']['radial_allocations_mm']['thermal_residual_target']=.008
    old_target=precision_budget(spec)
    assert old_target['diameter_with_uncertainty_target_mm']<.05
    assert old_target['diameter_with_honing_and_uncertainty_target_mm']>.05
    assert not old_target['design_budget_closes']
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
    assert not design["release"]["design_verified"] and design["release"]["physical_validation_recommended"]
    assert not design["release"]["product_conformity_claimed"]


def test_internal_cone_has_positive_return_even_if_self_locking(design):
    f = design["fixture"]
    assert f["positive_return_stroke_available_mm"] > f["positive_return_stroke_required_mm"]
    assert f["cone_force_scenarios"][-1]["self_lock_possible"]
    assert f["nominal_average_band_pressure_mpa"] < .25


def test_weld_interlocks_fail_closed():
    ready = dict(shield_present=True, bottom_open=True, fixture_locked=True, path_checked=True,
                 temperature_min=20, temperature_max=35, gas_flow_l_min=10, curtain_flow_l_min=10,
                 curtain_manifold_pressure_pa=1000,copper_temperature_c=30,lower_ring_temperature_c=30,seal_band_temperature_c=120,coolant_flow_l_min=.6,
                 coolant_branch_flows_l_min=[.075]*8,
                 water_leak_free=True,energy_in_range=True,guard_closed=True)
    assert cycle_permission("weld", **ready)
    for field, value in (("shield_present",False),("bottom_open",False),("fixture_locked",False),
                         ("path_checked",False),("temperature_max",101),("gas_flow_l_min",None),
                         ("temperature_min",float("nan")),("temperature_min",10),
                         ("curtain_manifold_pressure_pa",200),("curtain_manifold_pressure_pa",3000),("curtain_manifold_pressure_pa",None),
                         ("copper_temperature_c",46),("lower_ring_temperature_c",49),("lower_ring_temperature_c",None),("seal_band_temperature_c",181),("coolant_flow_l_min",.5),
                         ("water_leak_free",False),("energy_in_range",None),("guard_closed",False)):
        assert not cycle_permission("weld", **{**ready, field:value})
    # An unchanged total flow cannot hide one blocked circuit.
    assert not cycle_permission("weld", **{**ready,"coolant_branch_flows_l_min":[0]+[.086]*7})
    assert not cycle_permission("weld", **{**ready,"coolant_branch_flows_l_min":None})
    assert not cycle_permission("first_weld", **{**ready,"temperature_max":60})
    dual = {**ready, "simultaneous_heads":2, "head_gas_flows_l_min":[10,10],
            "head_energy_in_range":[True,True], "head_path_checked":[True,True]}
    assert cycle_permission("weld", **dual)
    for field, value in (("head_gas_flows_l_min",None),("head_gas_flows_l_min",[10,7]),
                         ("head_gas_flows_l_min",[10,float("nan")]),
                         ("head_energy_in_range",[True,False]),("head_path_checked",[True,None]),
                         ("simultaneous_heads",3)):
        assert not cycle_permission("weld", **{**dual,field:value})


def test_withdraw_requires_cooling_and_positive_return():
    ready = dict(shield_present=True, bottom_open=True, return_confirmed=True,
                 clamp_released=True, temperature_max=50, time_after_arc=120,
                 seal_retracted=True,water_leak_free=True,upper_stop_open=True,
                 upper_lift_mm=260,datum_holder_locked=True,transfer_support_locked=[True]*6,nest_lock_released=True)
    assert cycle_permission("withdraw", **ready)
    for field, value in (("return_confirmed",False),("clamp_released",False),
                         ("temperature_max",55),("time_after_arc",119),("bottom_open",False),
                         ("seal_retracted",None),("water_leak_free",False),("upper_stop_open",False),
                         ("upper_lift_mm",None),("upper_lift_mm",259),("datum_holder_locked",False),
                         ("transfer_support_locked",None),("transfer_support_locked",[True]*5),
                         ("transfer_support_locked",[True]*5+[False]),("nest_lock_released",False)):
        assert not cycle_permission("withdraw", **{**ready, field:value})


def test_acceptance_uses_diameter_uncertainty_and_measurement_temperature():
    ready = dict(shield_present=False, bottom_open=True, return_confirmed=True, clamp_released=True,
                 shell_base_released=True, inspection_passed=True, measurement_diameter=.048, uncertainty_diameter=.002, temperature_max=20,
                 bore_diameter_min_mm=40.001,bore_diameter_max_mm=40.024,bore_uncertainty_mm=.0005,bore_temperature_c=20)
    assert cycle_permission("accept", **ready)
    for field, value in (("measurement_diameter",.049),("uncertainty_diameter",None),
                         ("temperature_max",50),("inspection_passed",False),("shell_base_released",False),
                         ("bore_diameter_max_mm",40.025),("bore_diameter_min_mm",40.0),
                         ("bore_uncertainty_mm",None),("bore_temperature_c",21)):
        assert not cycle_permission("accept", **{**ready, field:value})
    finished={**ready,'finish_applied':True,'pre_finish_position_mm':.045,'finish_radial_stock_mm':.0025}
    assert cycle_permission('accept',**finished)
    assert not cycle_permission('accept',**{**finished,'pre_finish_position_mm':.049})
    assert not cycle_permission('accept',**{**finished,'finish_radial_stock_mm':.004})


def test_release_threshold_matches_baseline_band():
    baseline = yaml.safe_load((ROOT / "project/baseline.yaml").read_text(encoding="utf-8"))["fixture"]
    prep = yaml.safe_load((ROOT / "project/struct-0-prep.yaml").read_text(encoding="utf-8"))["fixture"]["release_logic"]
    assert prep["interface_max_below_c"] == baseline["release_temperature_c"] + baseline["release_temperature_band_c"]


def test_report_rejects_stale_inputs(monkeypatch):
    import hanjie.domain.competition_design as module
    snapshot = copy.deepcopy(current_assessment(ROOT)["inputs"])
    snapshot["structured"]["project/process-r3.yaml"]["process"]["nominal"]["current_a"] += 1
    monkeypatch.setattr(module, "input_snapshot", lambda root:snapshot)
    with pytest.raises(ValueError, match="输入已变化"):
        current_assessment(ROOT)


def test_current_drawing_manifest_excludes_legacy_fixture():
    import json
    manifest = json.loads((ROOT/"cad/generated/engineering-drawings/drawing-manifest.json").read_text(encoding="utf-8"))
    design = yaml.safe_load((ROOT/"project/competition-design.yaml").read_text(encoding="utf-8"))
    assert manifest["version"] == design["version"]
    assert "following-peener.svg" in manifest["drawings"]
    assert "sleeve-detail.svg" in manifest["supplemental_drawings"]
    assert "inspection-and-release.svg" in manifest["drawings"]
    assert "fixture-part.svg" not in manifest["drawings"]
    assert "weld-assembly.svg" not in manifest["drawings"]
    assert "gas-water-detail.svg" in manifest["drawings"]


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
