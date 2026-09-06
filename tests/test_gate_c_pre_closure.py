"""P1A 三维线弹性静刚度公平筛选与 Gate C-pre 闭环测试套件。"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_stiffness_screening_report_exists_and_complete() -> None:
    """验证 stiffness-screening-v4.md 报告存在且包含全部必要章节与审查要素。"""
    report_path = ROOT / "simulation" / "structural-v4" / "stiffness-screening-v4.md"
    assert report_path.exists(), "stiffness-screening-v4.md 报告文件不存在"

    content = report_path.read_text(encoding="utf-8")
    assert "Gate C-pre" in content
    assert "FAIR-A" in content and "FAIR-B" in content
    assert "网格收敛性分析" in content
    assert "边界敏感性" in content
    assert "Pareto" in content
    assert "四大核心审查问题专项回复" in content
    assert "Continuous" in content
    assert "6P" in content
    assert "8P-FAIR_B" in content


def test_all_seven_models_pass_convergence_criteria() -> None:
    """验证 7 个模型在中→细网格加密下的位移变化率 < 3%、应力变化率 < 10% 且敏感性通过。"""
    json_path = ROOT / "simulation" / "structural-v4" / "results" / "static-screening" / "static-screening-analysis.json"
    assert json_path.exists(), "static-screening-analysis.json 不存在"

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("static_screening_pass") is True, "静力筛查总体判定未通过"

    convergences = data.get("convergence", [])
    assert len(convergences) == 14, f"应包含 7 模型 × 2 边界 = 14 组收敛性检验，实际为 {len(convergences)}"

    for c in convergences:
        assert c["pass"] is True, f"模型 {c['model_id']} 在 {c['boundary_condition']} 下收敛未通过"
        assert c["medium_to_fine_displacement_relative_change"] < 0.03, f"模型 {c['model_id']} 位移变化超标 3%"
        assert c["medium_to_fine_p95_stress_relative_change"] < 0.10, f"模型 {c['model_id']} 应力变化超标 10%"

    sensitivities = data.get("boundary_sensitivity", [])
    assert len(sensitivities) == 7, "应包含 7 个模型的边界敏感性分析"
    for s in sensitivities:
        assert s["pass"] is True, f"模型 {s['model_id']} 边界敏感性未通过"
        assert s["bc1_bc2_displacement_relative_change"] < 0.10, f"模型 {s['model_id']} 边界位移变化超标 10%"


def test_gate_c_pre_status_in_status_md() -> None:
    """验证 P1A-status.md 中 Gate C-pre 审查及 10 项条件全部闭环通过。"""
    status_path = ROOT / "simulation" / "structural-v4" / "P1A-status.md"
    assert status_path.exists(), "P1A-status.md 不存在"

    content = status_path.read_text(encoding="utf-8")
    assert "**Gate C-pre 通过**" in content
    assert "✅ 通过" in content

    # 验证 10 项通过条件均为 [x]
    for i in range(1, 11):
        assert f"- [x] {i}." in content, f"Gate C-pre 第 {i} 项条件未勾选闭环"


def test_structure_comparison_summary_matches_screening() -> None:
    """验证 STRUCTURE-4-6-8 结果汇总与三维实体有限元筛查结论一致。"""
    summary_path = ROOT / "studies" / "STRUCTURE-4-6-8" / "results" / "structure_comparison_summary.json"
    assert summary_path.exists(), "structure_comparison_summary.json 不存在"

    with summary_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    assert data.get("gate_c_pre_status") == "passed"
    recommended = data.get("recommended_candidates", [])
    assert "Continuous" in recommended
    assert any("6P" in c for c in recommended)
    assert any("8P" in c for c in recommended)

    comparison = data.get("comparison", [])
    assert len(comparison) >= 4
    # Continuous 刚度最高（位移最小）
    cont_entry = next((item for item in comparison if item["structure_type"] == "Continuous"), None)
    assert cont_entry is not None
    assert cont_entry["fine_average_displacement_diameter_mm"] < 0.0004
