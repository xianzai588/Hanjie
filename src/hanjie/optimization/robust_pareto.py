"""面向 Ø0.05 mm 可靠性的鲁棒热—结构多目标协同优化 (创新点 A)。

将传统均值优化升级为考虑制造公差、材料散差与装配偏心的鲁棒设计：
目标向量:
    min [ E(P), P_95, CVaR_95(P), sigma_hotspot, Q_total, t_cycle ]
决策变量:
    N: 连接单元数 (4, 6, 8)
    L_w: 焊段长度 (12~24 mm)
    W_s: 柔顺槽宽 (2~6 mm)
    I: 焊接电流 (65~85 A)
    T_pre: 预热温度 (130~180 °C)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import numpy as np


@dataclass
class RobustDesignCandidate:
    design_id: str
    num_points: int
    weld_length_mm: float
    slot_width_mm: float
    current_a: float
    preheat_c: float
    mean_p_mm: float
    p95_p_mm: float
    cvar95_p_mm: float
    max_stress_mpa: float
    heat_input_kj: float
    cycle_time_s: float
    is_pareto_optimal: bool = False
    evidence_level: str = "surrogate_result"


class RobustCoDesignOptimizer:
    def __init__(self, monte_carlo_samples: int = 150) -> None:
        self.mc_samples = monte_carlo_samples

    def evaluate_candidate(
        self,
        design_id: str,
        n_points: int,
        weld_len_mm: float,
        slot_w_mm: float,
        current_a: float,
        preheat_c: float,
        seed: int = 42,
    ) -> RobustDesignCandidate:
        """评估给定候选方案在不确定性扰动下的鲁棒目标值。"""
        rng = np.random.RandomState(seed)

        # 抽样制造与材料不确定性
        delta_fit = rng.normal(0.0, 0.005, self.mc_samples)       # 间隙偏心
        eta_samples = rng.normal(0.55, 0.025, self.mc_samples)     # 热效率扰动
        alpha_factor = rng.normal(1.0, 0.04, self.mc_samples)      # 膨胀系数散差

        # 热输入与几何物理关联
        voltage = 12.0
        speed = 1.5
        heat_per_mm = (eta_samples * voltage * current_a) / speed
        total_weld_len = n_points * weld_len_mm

        # 柔顺槽弱化系数 (槽宽越宽，热收缩对中心的拉力越小)
        compliance_ratio = slot_w_mm / 4.0
        struct_factor = (1.0 - 0.12 * compliance_ratio) * (0.65 + 0.05 * n_points)

        # 预测位置度分布
        p_samples = []
        for i in range(self.mc_samples):
            # 基准热变形响应 + 间隙随机偏心
            base_drift = 0.000135 * heat_per_mm[i] * struct_factor * alpha_factor[i]
            total_r = base_drift + abs(delta_fit[i])
            p_val = 2.0 * total_r
            p_samples.append(p_val)

        p_arr = np.array(p_samples)
        mean_p = float(np.mean(p_arr))
        p95 = float(np.percentile(p_arr, 95))

        # CVaR_95: 超过 95% 分位数的那部分最恶劣情况的条件期望
        tail = p_arr[p_arr >= p95]
        cvar95 = float(np.mean(tail)) if len(tail) > 0 else p95

        # 峰值残余应力 (MPa): 与电流正相关，与柔顺槽宽负相关
        max_stress = float((195.0 + 1.2 * (current_a - 75.0)) / (0.85 + 0.05 * compliance_ratio))

        # 总热输入 (kJ)
        heat_kj = float(np.mean(heat_per_mm) * total_weld_len / 1000.0)

        # 工艺周期时间 (焊弧时间 + 层间等待)
        weld_time = total_weld_len / speed
        cycle_time = weld_time + (n_points - 1) * 8.0

        return RobustDesignCandidate(
            design_id=design_id,
            num_points=n_points,
            weld_length_mm=weld_len_mm,
            slot_width_mm=slot_w_mm,
            current_a=current_a,
            preheat_c=preheat_c,
            mean_p_mm=mean_p,
            p95_p_mm=p95,
            cvar95_p_mm=cvar95,
            max_stress_mpa=max_stress,
            heat_input_kj=heat_kj,
            cycle_time_s=cycle_time,
        )

    def generate_pareto_front(self) -> List[RobustDesignCandidate]:
        """筛选七个手选候选中的非支配子集；并非全设计域 Pareto 前沿。"""
        results = self.evaluate_handpicked_candidates()
        # 当前只有这些代理目标；不包含刚度、疲劳或真实制造约束。
        objectives = np.array([[r.p95_p_mm, r.max_stress_mpa, r.heat_input_kj, r.cycle_time_s] for r in results])
        front = [r for i, r in enumerate(results)
                if not any(np.all(objectives[j] <= objectives[i]) and np.any(objectives[j] < objectives[i])
                           for j in range(len(results)) if j != i)]
        for result in results:
            result.is_pareto_optimal = result in front
        return front

    def evaluate_handpicked_candidates(self) -> List[RobustDesignCandidate]:
        """返回七个预先指定候选的完整代理评价集，供审计和有限集合筛选使用。"""
        candidates = [
            ("OPT-4P-MIN-HEAT", 4, 15.0, 5.0, 70.0, 150.0),
            ("OPT-4P-BALANCED", 4, 18.0, 4.0, 75.0, 150.0),
            ("OPT-6P-ROBUST-BASE", 6, 18.0, 4.0, 75.0, 150.0),  # 仅为待比较候选
            ("OPT-6P-LOW-STRESS", 6, 16.0, 5.0, 72.0, 160.0),
            ("OPT-6P-HIGH-FATIGUE", 6, 20.0, 3.5, 78.0, 150.0),
            ("OPT-8P-STIFF", 8, 16.0, 3.5, 75.0, 150.0),
            ("OPT-8P-HIGH-CAPACITY", 8, 18.0, 3.0, 80.0, 140.0),
        ]

        results = []
        for cid, n, l, w, i_a, t_pre in candidates:
            res = self.evaluate_candidate(cid, n, l, w, i_a, t_pre)
            results.append(res)
        return results
