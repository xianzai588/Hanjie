from pathlib import Path
import json
import yaml


def test_competition_authority_uses_conservative_endpoint():
    root = Path(__file__).parents[1]
    authority = yaml.safe_load((root / "project/competition-authority.yaml").read_text(encoding="utf-8"))
    assessment = json.loads((root / "studies/COMPETITION-DESIGN/results/assessment.json").read_text(encoding="utf-8"))
    six_p = next(row for row in assessment["four_pass_comparison"] if row["layout"] == "6P-FAIR_B")
    eight_p = next(row for row in assessment["four_pass_comparison"] if row["layout"] == "8P-FAIR_B")
    assert authority["selected_candidate"] == "6P-FAIR_B/4pass"
    assert authority["engineering_selection_status"] == "pending_release_gates"
    assert authority["digital_baseline"] == "6P-FAIR_B/4pass"
    assert authority["higher_static_margin_candidate"] == "8P-FAIR_B/4pass"
    assert authority["assumptions"]["deposition_efficiency"] == 0.85
    assert authority["results"]["required_allowable_mpa"] == six_p["required_allowable_mpa"]
    assert authority["results"]["fallback_required_allowable_mpa"] == eight_p["required_allowable_mpa"]
    assert authority["endpoints"]["current_efficiency_0_85_required_allowable_mpa"] == six_p["required_allowable_mpa"]


def test_report_contains_single_decision_rule():
    root = Path(__file__).parents[1]
    report = (root / "deliverables/report/technical-report-v4-unified.md").read_text(encoding="utf-8")
    # 章节号随内容增减而漂移，这里锚定标题本身，并确认全篇只保留一处决策表。
    assert report.count("评委快速决策表") == 1
    assert report.count("52.17 MPa") >= 4
    assert "56.59 MPa" not in report
    assert "Monte Carlo 代理通过率" not in report


def test_current_process_source_matches_design_authority():
    root = Path(__file__).parents[1]
    process = yaml.safe_load((root / "project/process.yaml").read_text(encoding="utf-8"))["process"]["nominal"]
    design = yaml.safe_load((root / "project/competition-design.yaml").read_text(encoding="utf-8"))["process"]
    assert process["pass_count"] == design["pass_count"] == 4
    assert process["sequence"] == design["sequence"] == [1, 4, 3, 6, 2, 5]
    assert process["filler_diameter_mm"] == design["wire_diameter_mm"] == 1.6
    assert process["filler_feed_rate_mm_s"] == 1.343967
    assert process["current_a"] == 75.0
    assert process["voltage_v"] == 12.0
    assert process["travel_speed_mm_s"] == 1.5


def test_selection_uses_pareto_front_not_weighted_score():
    root = Path(__file__).parents[1]
    selection = json.loads((root / "studies/COMPETITION-DESIGN/results/robust-selection.json").read_text(encoding="utf-8"))
    assert "score" not in selection
    assert all("score" not in row for row in selection["candidates"])
    assert set(selection["pareto_front"]) == {
        "Continuous/4pass", "6P-FAIR_B/4pass", "8P-FAIR_B/4pass"
    }
    assert selection["digital_baseline"] == "6P-FAIR_B/4pass"
