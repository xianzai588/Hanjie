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
OUT = ROOT / "studies" / "THERMO-STRUCTURAL-6P-8P" / "results"


def main() -> int:
    source = json.loads(ASSESSMENT.read_text(encoding="utf-8"))
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
        "mechanical_tradeoff": {
            "6P_required_allowable_mpa": 52.173,
            "8P_required_allowable_mpa": 39.12989758955982,
            "6P_to_8P_allowable_ratio": 52.173 / 39.12989758955982,
            "6P_net_heat_input_kj": 142.56,
            "8P_net_heat_input_kj": 190.08,
            "6P_heat_reduction_percent": 25.0,
        },
        "decision": "当前代理证据不支持把 6P 宣称为偏移更优；6P 仅因低热输入保留为条件性首选，8P 因更高承载筛查余量保留为稳健方案。",
        "limitations": source["limitations"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "comparison.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md = f"""# 6P/8P 热—结构对照（条件性）

数据源为 `simulation/structural-v4/results/struct-uncertainty/assessment.json`，沿用同一几何、夹具假设、载荷尺度和 FVM/Elmer 两条代理热源。该结果不是完整三维焊接热塑性求解，也不用于产品位置度放行。

| 指标 | 6P-FAIR_B | 8P-FAIR_B | 解释 |
|---|---:|---:|---|
| 端点最大径向偏移包络 (mm) | {six_max:.9f} | {eight_max:.9f} | 8P 低 {abs(six_max-eight_max):.9f} mm，约 {abs((six_max/eight_max-1)*100):.2f}% |
| 端点最小径向偏移包络 (mm) | {six_min:.9f} | {eight_min:.9f} | 不代表概率区间 |
| 6P−8P 配对差值范围 (mm) | — | {paired['signed_a_minus_b_min_mm']:.9f} ～ {paired['signed_a_minus_b_max_mm']:.9f} | 72/72 组不可分辨 |
| 模型间最大差异 (mm) | — | {source['maximum_c_m_span_mm']:.9f} | 大于候选端点差异 |
| 所需许用应力 (MPa) | 52.173 | 39.1299 | 6P 约为 8P 的 {52.173/39.12989758955982:.3f} 倍 |
| 名义净热输入 (kJ) | 142.56 | 190.08 | 6P 少 25% |

**结论。** 当前代理计算没有证明 6P 能减少焊后孔轴偏移；端点包络甚至显示 8P 略低，但差异远小于模型不确定度。因此 6P 的依据只能写成“低热输入条件性首选”，不能写成“已由热—结构结果证明偏移更优”。若机械裕量优先或实测热残余/裂纹门失败，切换 8P。
"""
    (OUT / "comparison.md").write_text(md, encoding="utf-8")
    print(json.dumps(result["comparison"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
