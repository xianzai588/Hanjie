"""ADAPTIVE-SEQUENCE 自适应跳焊与固定序列 (S1/S2/S3) 对照研究。

对比四组策略：
1. S1: 顺次连续施焊 (1->2->3->4->5->6)
2. S2: 对角跳焊 (1->4->2->5->3->6)
3. S3: 固定分段跳焊 (1->4->3->6->2->5)
4. ADAPTIVE: 在线温度状态驱动自适应跳焊
并在工件存在初始预热温差扰动时，展示自适应策略的鲁棒抗扰调整能力。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hanjie.control.adaptive_sequence import AdaptiveSequenceController


def result_row(result) -> dict:
    """统一记录控制结果，避免报告脚本重新拼接或改写数值。"""
    return {
        "name": result.strategy_name,
        "order": result.execution_order,
        "time_s": result.total_cycle_time_s,
        "max_delta_t": result.max_delta_t_observed_c,
        "p_mm": result.final_position_p_mm,
        "plant_model": result.plant_model,
        "position_predictor": result.position_predictor,
        "evaluation_model": result.evaluation_model,
        "initial_perturbation_c": list(result.initial_perturbation_c),
        "evidence_level": result.evidence_level,
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("=" * 85)
    print("运行 ADAPTIVE-SEQUENCE 自适应跳焊策略与固定焊序对照研究...")
    print("=" * 85)

    controller = AdaptiveSequenceController(num_segments=6)

    # 1. 理想均匀初始预热工况
    res_s1 = controller.evaluate_fixed_sequence("S1-SEQUENTIAL", [1, 2, 3, 4, 5, 6])
    res_s2 = controller.evaluate_fixed_sequence("S2-DIAGONAL", [1, 4, 2, 5, 3, 6])
    res_s3 = controller.evaluate_fixed_sequence("S3-FIXED-SKIP", [1, 4, 3, 6, 2, 5])
    res_adapt = controller.solve_adaptive_sequence()

    print(f"\n【工况一：标准均匀预热 (150°C)】")
    print(f"{'焊序方案':<20}{'实际执行序列':<22}{'周期时间(s)':<14}{'最大周向温差(°C)':<18}{'最终位置度 P (mm)':<16}")
    print("-" * 88)
    for r in [res_s1, res_s2, res_s3, res_adapt]:
        order_str = "->".join(str(x) for x in r.execution_order)
        print(f"{r.strategy_name:<20}{order_str:<22}{r.total_cycle_time_s:<14.1f}{r.max_delta_t_observed_c:<18.1f}{r.final_position_p_mm:<16.5f}")

    # 2. 存在预热局部温差梯度扰动工况 (如区域 3 因加热器边缘效应温度高出 25°C)
    perturbation = np.array([0.0, 0.0, 25.0, 5.0, -10.0, 0.0])
    res_s3_disturbed = controller.evaluate_fixed_sequence("S3-DISTURBED", [1, 4, 3, 6, 2, 5], initial_perturbation=perturbation)
    res_adapt_disturbed = controller.solve_adaptive_sequence(initial_perturbation=perturbation)
    res_s1_disturbed = controller.evaluate_fixed_sequence("S1-DISTURBED", [1, 2, 3, 4, 5, 6], initial_perturbation=perturbation)
    res_s2_disturbed = controller.evaluate_fixed_sequence("S2-DISTURBED", [1, 4, 2, 5, 3, 6], initial_perturbation=perturbation)

    print(f"\n【工况二：存在初始预热扰动 (3号区偏高 +25°C)】")
    print(f"{'焊序方案':<20}{'实际执行序列':<22}{'周期时间(s)':<14}{'最大周向温差(°C)':<18}{'最终位置度 P (mm)':<16}")
    print("-" * 88)
    for r in [res_s1_disturbed, res_s2_disturbed, res_s3_disturbed, res_adapt_disturbed]:
        order_str = "->".join(str(x) for x in r.execution_order)
        print(f"{r.strategy_name:<20}{order_str:<22}{r.total_cycle_time_s:<14.1f}{r.max_delta_t_observed_c:<18.1f}{r.final_position_p_mm:<16.5f}")

    print("-" * 88)
    difference = res_adapt_disturbed.final_position_p_mm - res_s3_disturbed.final_position_p_mm
    print(f"相同扰动/评价模型下 Adaptive - S3 位置度差值：{difference:+.6f} mm")
    print("仅为未经校准的代理结果，不能证明实物达标或稳定优于固定焊序。")

    # 用 Adaptive 实际选出的同一序列回放，检查 plant、预测器、评价函数和扰动完全一致。
    replay = controller.evaluate_fixed_sequence(
        "ADAPTIVE-REPLAY",
        res_adapt_disturbed.execution_order,
        initial_perturbation=perturbation,
    )
    fairness_check = {
        "same_execution_order": replay.execution_order == res_adapt_disturbed.execution_order,
        "same_initial_perturbation": replay.initial_perturbation_c == res_adapt_disturbed.initial_perturbation_c,
        "same_plant_model": replay.plant_model == res_adapt_disturbed.plant_model,
        "same_position_predictor": replay.position_predictor == res_adapt_disturbed.position_predictor,
        "same_evaluation_model": replay.evaluation_model == res_adapt_disturbed.evaluation_model,
        "exact_final_position_match": replay.final_position_p_mm == res_adapt_disturbed.final_position_p_mm,
        "exact_cycle_time_match": replay.total_cycle_time_s == res_adapt_disturbed.total_cycle_time_s,
    }
    if not all(fairness_check.values()):
        raise RuntimeError(f"Adaptive 同序列回放公平性检查失败: {fairness_check}")
    print(f"同序列回放公平性检查：PASS（{res_adapt_disturbed.execution_order}，不含优越性门槛）")

    out_dir = ROOT / "studies" / "ADAPTIVE-SEQUENCE" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "evidence_level": "surrogate_result",
        "evaluation_model": "shared_thermal_position_v1",
        "plant_model": res_adapt_disturbed.plant_model,
        "position_predictor": res_adapt_disturbed.position_predictor,
        "fairness_check": fairness_check,
        "initial_perturbation_c": perturbation.tolist(),
        "uniform_condition": [result_row(r) for r in [res_s1, res_s2, res_s3, res_adapt]],
        "disturbed_condition": [result_row(r) for r in [res_s1_disturbed, res_s2_disturbed, res_s3_disturbed, res_adapt_disturbed]],
        "replay_condition": result_row(replay),
    }
    (out_dir / "adaptive_sequence_study.json").write_text(json.dumps(summary_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n报告已保存至: {out_dir / 'adaptive_sequence_study.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
