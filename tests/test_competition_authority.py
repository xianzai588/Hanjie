from pathlib import Path
import json
import yaml


def test_competition_authority_uses_conservative_endpoint():
    root = Path(__file__).parents[1]
    authority = yaml.safe_load((root / "project/competition-authority.yaml").read_text(encoding="utf-8"))
    assessment = json.loads((root / "studies/COMPETITION-DESIGN/results/assessment.json").read_text(encoding="utf-8"))
    six_p = next(row for row in assessment["four_pass_comparison"] if row["layout"] == "6P-FAIR_B")
    eight_p = next(row for row in assessment["four_pass_comparison"] if row["layout"] == "8P-FAIR_B")
    assert authority["selected_candidate"] == "8P-FAIR_B/2pass"
    assert authority["assumptions"]["deposition_efficiency"] == 0.90
    assert authority["results"]["required_allowable_mpa"] == eight_p["required_allowable_mpa"]
    assert authority["results"]["fallback_required_allowable_mpa"] == six_p["required_allowable_mpa"]
    assert authority["endpoints"]["current_efficiency_0_90_required_allowable_mpa"] == eight_p["required_allowable_mpa"]


def test_report_contains_single_decision_rule():
    root = Path(__file__).parents[1]
    report = (root / "deliverables/report/technical-report-v4-unified.md").read_text(encoding="utf-8")
    # 章节号随内容增减而漂移，这里锚定标题本身，并确认全篇只保留一处决策表。
    assert report.count("8P-FAIR_B、两道脉冲 TIG") == 1
    assert report.count("52.17 MPa") >= 1
    assert report.count("39.13 MPa") >= 1
    assert "56.59 MPa" not in report
    assert "Monte Carlo 代理通过率" not in report
