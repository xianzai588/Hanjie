from pathlib import Path
import yaml


def test_competition_authority_uses_conservative_endpoint():
    root = Path(__file__).parents[1]
    authority = yaml.safe_load((root / "project/competition-authority.yaml").read_text(encoding="utf-8"))
    assert authority["selected_candidate"] == "6P-FAIR_B/4pass"
    assert authority["assumptions"]["deposition_efficiency"] == 0.85
    assert authority["results"]["required_allowable_mpa"] == 56.58977732333571
    assert authority["endpoints"]["optimistic_efficiency_1_required_allowable_mpa"] == 52.17319678607985


def test_report_contains_single_decision_rule():
    root = Path(__file__).parents[1]
    report = (root / "deliverables/report/technical-report-v4-unified.md").read_text(encoding="utf-8")
    assert "2.2 评委快速决策表" in report
    assert report.count("56.59 MPa") >= 3
    assert "52.17 MPa，仅作为乐观上限对照" in report
