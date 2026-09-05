"""ROBUST-OPT 鲁棒热—结构多目标协同优化研究。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hanjie.optimization.robust_pareto import RobustCoDesignOptimizer


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 105)
    print("运行 ROBUST-OPT 考虑材料/装配不确定性的有限候选代理非支配筛选...")
    print("=" * 105)

    optimizer = RobustCoDesignOptimizer(monte_carlo_samples=200)
    all_candidates = optimizer.evaluate_handpicked_candidates()
    pareto_front = optimizer.generate_pareto_front()
    pareto_ids = {cand.design_id for cand in pareto_front}

    print(f"{'方案 ID':<20}{'连接点':<6}{'焊长(mm)':<9}{'E(P)(mm)':<12}{'P95(mm)':<12}{'CVaR95(mm)':<12}{'最大应力(MPa)':<14}{'总热输入(kJ)':<14}{'周期(s)':<8}")
    print("-" * 105)

    rows = []
    for cand in all_candidates:
        print(f"{cand.design_id:<20}{cand.num_points:<6}{cand.weld_length_mm:<9.1f}{cand.mean_p_mm:<12.5f}{cand.p95_p_mm:<12.5f}{cand.cvar95_p_mm:<12.5f}{cand.max_stress_mpa:<14.1f}{cand.heat_input_kj:<14.2f}{cand.cycle_time_s:<8.1f}")
        rows.append({
            "design_id": cand.design_id,
            "num_points": cand.num_points,
            "weld_length_mm": cand.weld_length_mm,
            "slot_width_mm": cand.slot_width_mm,
            "current_a": cand.current_a,
            "mean_p_mm": cand.mean_p_mm,
            "p95_p_mm": cand.p95_p_mm,
            "cvar95_p_mm": cand.cvar95_p_mm,
            "max_stress_mpa": cand.max_stress_mpa,
            "heat_input_kj": cand.heat_input_kj,
            "cycle_time_s": cand.cycle_time_s,
            "is_pareto_optimal": cand.design_id in pareto_ids,
            "evidence_level": cand.evidence_level,
        })

    print("-" * 105)
    print("结果仅供代理/合成演示；不支持六点最优、疲劳承载或实物补偿达标结论。")

    out_dir = ROOT / "studies" / "ROBUST-OPT" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "robust_pareto_summary.json").write_text(json.dumps({
        "evidence_level": "surrogate_result",
        "validation_status": "unvalidated",
        "search_scope": "seven_handpicked_candidates",
        "search_scope_note": "有限候选非支配筛选，不是全设计域全局 Pareto 前沿",
        "candidate_count": len(rows),
        "objectives_minimized": ["p95_p_mm", "max_stress_mpa", "heat_input_kj", "cycle_time_s"],
        "non_dominated_ids": sorted(pareto_ids),
        "evaluated_candidates": rows,
        "pareto_candidates": [row for row in rows if row["is_pareto_optimal"]],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nPareto 解集已保存至: {out_dir / 'robust_pareto_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
