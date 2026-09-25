"""从既有结构不确定度结果提取 6P/8P 热—结构对照证据。

本研究不重新包装未准入的热有限元，也不把代理结果当成产品验收；
只在同一组候选、同一夹具假设和同一不确定度范围内，量化两种布局
的端点偏移差、模型间差异和承载代价，供报告作条件性决策依据。
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASSESSMENT = ROOT / "simulation" / "structural-v4" / "results" / "struct-uncertainty" / "assessment.json"
DESIGN = ROOT / "studies" / "COMPETITION-DESIGN" / "results" / "assessment.json"
OUT = ROOT / "studies" / "THERMO-STRUCTURAL-6P-8P" / "results"


def main() -> int:
    source = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
    design = json.loads(DESIGN.read_text(encoding="utf-8"))
    envelopes = {
        (row["candidate"], row["source"]): row
        for row in source["envelopes"]
        if row["candidate"] in {"6P-FAIR_B", "8P-FAIR_B"}
    }
    six = [envelopes[("6P-FAIR_B", model)] for model in ("fvm", "elmer")]
    eight = [envelopes[("8P-FAIR_B", model)] for model in ("fvm", "elmer")]
    six_max = max(row["maximum_mm"] for row in six)
    eight_max = max(row["maximum_mm"] for row in eight)
    six_min = min(row["minimum_mm"] for row in six)
    eight_min = min(row["minimum_mm"] for row in eight)
    paired = next(
        row for row in source["pairs"]
        if {row["a"], row["b"]} == {"6P-FAIR_B", "8P-FAIR_B"}
    )
    result = {
        "study": "THERMO-STRUCTURAL-6P-8P",
        "evidence_level": source["evidence_level"],
        "model_status": "existing_3d_inherent_strain_proxy; full_thermoelastic_plastic_FE_not_executed",
        "source_assessment": str(ASSESSMENT.relative_to(ROOT)).replace("\\", "/"),
        "same_conditions": ["同一 3D 固有应变代理", "同一夹具/载荷假设", "FVM 与 Elmer 两条来源"],
        "comparison": {
            "6P_maximum_envelope_mm": six_max,
            "8P_maximum_envelope_mm": eight_max,
            "maximum_difference_6P_minus_8P_mm": six_max - eight_max,
            "maximum_difference_percent_of_8P": (six_max / eight_max - 1.0) * 100.0,
            "6P_minimum_envelope_mm": six_min,
            "8P_minimum_envelope_mm": eight_min,
            "paired_signed_difference_min_mm": paired["signed_a_minus_b_min_mm"],
            "paired_signed_difference_max_mm": paired["signed_a_minus_b_max_mm"],
            "paired_unresolved_cases": paired["unresolved"],
            "paired_total_cases": source["paired_scenarios"],
            "maximum_model_disagreement_span_mm": source["maximum_c_m_span_mm"],
        },
        "sensitivity_boundary": {
            "paired_unresolved_fraction": paired["unresolved"] / paired["paired_scenarios"] if "paired_scenarios" in paired else paired["unresolved"] / source["paired_scenarios"],
            "max_paired_source_change_mm": source["maximum_paired_thermal_source_change_mm"],
            "comparison_resolution_mm": source["maximum_c_m_span_mm"],
            "difference_is_resolvable": False,
            "hole_wall_envelope": "not_available_in_existing_proxy; requires released FE or post-weld section/envelope measurement",
        },
        "machining_check": {
            "selected_candidate": design["machining_allowance"]["selected_candidate"],
            "minimum_geometric_allowance_mm": next(row["geometric_min_radial_allowance_mm"] for row in design["machining_allowance"]["candidates"] if row["id"] == design["machining_allowance"]["selected_candidate"]),
            "required_radial_allowance_mm": design["machining_allowance"]["required_radial_allowance_mm"],
            "status": "pressure_screen_closed; hole_wall_shape_still_requires_check",
        },
        "mechanical_tradeoff": {
            "6P_required_allowable_mpa": 52.173,
            "8P_required_allowable_mpa": 39.12989758955982,
            "6P_to_8P_allowable_ratio": 52.173 / 39.12989758955982,
            "6P_net_heat_input_kj": 142.56,
            "8P_net_heat_input_kj": 190.08,
            "6P_heat_reduction_percent": 25.0,
        },
        "decision": "当前代理证据下6P与8P不可分辨；不输出布局胜负。6P仅因低热输入保留为条件性首选，8P因更高承载筛查余量保留为切换方案。",
        "limitations": source["limitations"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "comparison.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md = f"""# 6P/8P 热—结构对照（条件性）

数据源为 `simulation/structural-v4/results/struct-uncertainty/assessment.json`，沿用同一几何、夹具假设、载荷尺度和 FVM/Elmer 两条代理热源。当前没有完成完整三维瞬态热—弹塑性求解；本表是既有代理的成对复核，不用于产品位置度放行。

| 指标 | 6P-FAIR_B | 8P-FAIR_B | 解释 |
|---|---:|---:|---|
| 端点最大径向偏移包络 (mm) | {six_max:.9f} | {eight_max:.9f} | 8P 低 {abs(six_max-eight_max):.9f} mm，约 {abs((six_max/eight_max-1)*100):.2f}% |
| 端点最小径向偏移包络 (mm) | {six_min:.9f} | {eight_min:.9f} | 不代表概率区间 |
| 6P−8P 配对差值范围 (mm) | — | {paired['signed_a_minus_b_min_mm']:.9f} ～ {paired['signed_a_minus_b_max_mm']:.9f} | 72/72 组不可分辨 |
| 模型间最大差异 (mm) | — | {source['maximum_c_m_span_mm']:.9f} | 大于候选端点差异 |
| 所需许用应力 (MPa) | 52.173 | 39.1299 | 6P 约为 8P 的 {52.173/39.12989758955982:.3f} 倍 |
| 名义净热输入 (kJ) | 142.56 | 190.08 | 6P 少 25% |

## 敏感性边界

- 72/72 组6P/8P配对不可分辨；成对差值范围为 -0.000687915～0.000460309 mm。
- 最大模型间差异0.000167953 mm，大于端点最大差异0.000055858 mm，因此不输出“谁更低”的工程结论。
- 当前代理没有孔壁倾斜、椭圆化和局部最薄处包络；这些量必须由合格FE或焊后截面/包络测量补齐。
- A2的0.250 mm最小几何余量覆盖0.213299 mm压力情景，但该数字不替代焊后孔壁可加工性检查。

**结论。** 当前代理计算没有证明6P或8P在焊后孔轴偏移上更优；端点包络虽显示8P略低，但差异远小于模型不确定度。因此6P的依据只能写成“低热输入条件性首选”，不能写成“已由热—结构结果证明偏移更优”。若机械裕量优先或实测热残余/裂纹门失败，切换8P。
"""
    (OUT / "comparison.md").write_text(md, encoding="utf-8")
    print(json.dumps(result["comparison"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
