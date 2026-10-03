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


def test_current_process_has_single_authority_and_legacy_source_is_historical():
    root = Path(__file__).parents[1]
    current = yaml.safe_load((root / "project/process-r3.yaml").read_text(encoding="utf-8"))
    legacy = yaml.safe_load((root / "project/process.yaml").read_text(encoding="utf-8"))
    design = yaml.safe_load((root / "project/competition-design.yaml").read_text(encoding="utf-8"))
    assert current["state"] == "current_frozen_design"
    assert current["authority"] == "current_competition_process_source"
    assert design["process_source"] == "project/process-r3.yaml"
    assert legacy["state"] == "historical_only"
    assert legacy["current_authority"] == "project/process-r3.yaml"
    assert legacy["authority"] != "焊接工艺与填丝参数的唯一权威配置"


def test_legacy_process_card_entrypoint_contains_no_current_6p_parameters():
    root = Path(__file__).parents[1]
    script = (root / "deliverables/process/generate_joint_process_card.py").read_text(encoding="utf-8")
    assert "6P-FAIR_B" not in script
    assert "1.343967" not in script
    assert "3.50±0.05" not in script
    assert "generate_process_r3" in script
