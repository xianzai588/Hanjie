"""校核体积、承载、边界选择和预算口径，防止条件筛查被误作验收。"""

import math
from pathlib import Path

import pytest

from hanjie.domain.route_b_design import (
    build_design_study, deposited_section, precision_requirements, select_low_heat,
)

ROOT = Path(__file__).resolve().parents[1]


def test_fixed_feed_deposition_loss_reduces_leg_by_square_root():
    area, leg = deposited_section(1.2, 2., 1.5, 1, 1.)
    lower_area, lower_leg = deposited_section(1.2, 2., 1.5, 1, .85)
    assert area == pytest.approx(.48 * math.pi)
    assert lower_area / area == pytest.approx(.85)
    assert lower_leg / leg == pytest.approx(math.sqrt(.85))
    for efficiency in (0, -1, 1.01, float("nan")):
        with pytest.raises(ValueError):
            deposited_section(1.2, 2., 1.5, 1, efficiency)


def test_capacity_boundary_ties_and_no_feasible_candidate():
    candidates = [
        {"candidate_id": "A", "worst_required_allowable_mpa": 100., "nominal_net_heat_input_j": 10.},
        {"candidate_id": "B", "worst_required_allowable_mpa": 100., "nominal_net_heat_input_j": 10.},
        {"candidate_id": "C", "worst_required_allowable_mpa": 50., "nominal_net_heat_input_j": 20.},
    ]
    assert select_low_heat(candidates, 1., 100.)["selected_for_further_study"] == ["A", "B"]
    assert select_low_heat(candidates, 1., 99.)["selected_for_further_study"] == ["C"]
    result = select_low_heat(candidates, 1., 49.)
    assert result["selected_for_further_study"] == []
    assert result["status"] == "no_capacity_feasible_candidate"
    assert result["engineering_recommendation_released"] is False


@pytest.fixture(scope="module")
def study():
    return build_design_study(ROOT)


def test_circular_weld_capacity_matches_closed_form(study):
    row = next(r for r in study["candidates"] if r["candidate_id"] == "Continuous/1pass")
    radius = row["weld_length_mm"] / (2 * math.pi)
    throat = row["equivalent_leg_range_mm"][0] / math.sqrt(2)
    area = 2 * math.pi * radius * throat
    shear = math.hypot(5000., 5000.) / area
    bending = 250000. / (math.pi * radius**2 * throat)
    assert row["worst_required_allowable_mpa"] == pytest.approx(math.sqrt(3 * shear**2 + bending**2))


def test_each_candidate_uses_its_own_volume_and_energy(study):
    assert study["case_count"] == len(study["cases"]) == 108
    assert study["candidate_count"] == 6
    by_id = {r["candidate_id"]: r for r in study["candidates"]}
    for row in by_id.values():
        assert row["gross_arc_energy_j"] * .55 == pytest.approx(row["nominal_net_heat_input_j"])
        assert row["nominal_deposited_area_mm2"] * row["weld_length_mm"] == pytest.approx(row["nominal_total_deposited_volume_mm3"])
        assert row["purchased_wire_mass_g"] == pytest.approx(row["nominal_retained_filler_mass_g"])
        assert row["cad_target_section_matches_nominal"] == (row["pass_count"] == 4)
        assert row["thermal_history_solved_for_this_candidate"] is False
        assert row["total_cycle_time_s"] is None
    assert by_id["6P-FAIR_B/1pass"]["nominal_net_heat_input_j"] / by_id["8P-FAIR_B/1pass"]["nominal_net_heat_input_j"] == pytest.approx(.75)
    assert by_id["6P-FAIR_B/4pass"]["nominal_net_heat_input_j"] / by_id["6P-FAIR_B/1pass"]["nominal_net_heat_input_j"] == pytest.approx(4.)
    assert all(value is False for value in study["release"].values())


def test_budget_inversion_keeps_unclosed_authority_and_diameter_units(study):
    result = study["precision"]
    assert result["radial_deficit_mm"] == pytest.approx(.01)
    assert result["thermal_budget_if_other_items_unchanged_mm"] == pytest.approx(.002)
    for row in result["rows"]:
        assert row["thermal_radial_allocation_mm"] + row["fixture_and_assembly_budget_max_mm"] + result["fixed_other_contributions_mm"] == pytest.approx(.025)
    assert result["budget_status"] == "not_closed"
    assert study["structural_evidence"]["robust_candidate_ranking_established"] is False


def test_budget_rejects_inconsistent_sum():
    tolerance = {"product_geometry_chain": {"contributions_mm": {"a": .02}, "worst_case_design_sum_mm": .01}}
    with pytest.raises(ValueError, match="总和"):
        precision_requirements(tolerance, {})


def test_nominal_capacity_pass_is_rejected_when_deposition_loss_fails(study):
    nominal = next(row for row in study["cases"] if row["candidate_id"] == "8P-FAIR_B/1pass"
                   and row["deposition_efficiency"] == 1. and row["load_scale"] == 1.)
    assert nominal["required_allowable_mpa"] < 80.
    decision = select_low_heat(study["candidates"], 1., 80.)
    assert decision["selected_for_further_study"] == ["6P-FAIR_B/4pass"]
    assessed = next(row for row in decision["assessed_candidates"] if row["candidate_id"] == "8P-FAIR_B/1pass")
    assert assessed["conditional_capacity_screen_pass"] is False


def test_report_rejects_stale_design_result(monkeypatch):
    import hanjie.domain.route_b_design as design
    from hanjie.reporting.current_status import collect_current_status

    read = design.read_data

    def changed_input(path):
        data = read(path)
        if path == ROOT / design.SPEC:
            data["load_scales"] = [.75]
        return data

    monkeypatch.setattr(design, "read_data", changed_input)
    with pytest.raises(ValueError, match="选型结果已过期"):
        collect_current_status(ROOT)
