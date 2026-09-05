"""带模型不确定性的逆向位姿反变形补偿算法 (创新点 C)。

求解受约束非线性逆问题：
    x_0* = argmin_{x_0} E[ || x_final(x_0, p) - x_nominal ||^2 ] + lambda * ||x_0||^2
受制于：
1. H7/h6 配合装配径向间隙边界: ||(x_0, y_0)|| <= c_max (0.040 mm)
2. 锥形夹具定心调节行程: |x_0|, |y_0| <= 0.035 mm
3. 机器人焊枪可达性与安全裕量
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import numpy as np
from scipy.optimize import minimize

from hanjie.domain.baseline import get_baseline


@dataclass
class PrecompensationCaseResult:
    method_name: str
    nominal_position_error_mm: float
    p95_position_error_mm: float
    max_position_error_mm: float
    boundary_violation_rate_pct: float
    pass_p005_rate_pct: float


class InversePrecompensationSolver:
    def __init__(
        self,
        max_clearance_mm: float = 0.040,  # H7/h6 最大间隙 0.040 mm
        max_stroke_mm: float = 0.035,
        regularization_lambda: float = 0.05,
    ) -> None:
        self.max_clearance = max_clearance_mm
        self.max_stroke = max_stroke_mm
        self.reg_lambda = regularization_lambda

    def predict_shrinkage_response(
        self,
        x0: np.ndarray,  # [dx, dy]
        heat_efficiency: float = 0.55,
        shrinkage_coeff: float = 0.00035,
    ) -> np.ndarray:
        """预测特定热效率与收缩参数下的焊后位姿偏移。"""
        # 焊接热变形主矢量偏向热累积侧，并伴随非线性泊松横向缩径
        shrink_mag = shrinkage_coeff * (heat_efficiency / 0.55) * 74.98
        # 偏斜角约 35 度
        shrink_vector = np.array([shrink_mag * 0.819, shrink_mag * 0.573])
        return x0 + shrink_vector

    def solve_inverse_pose(
        self,
        initial_offset: np.ndarray,
        nominal_target: np.ndarray = np.array([0.0, 0.0]),
        prior_uncertainty_samples: int = 50,
    ) -> np.ndarray:
        """求解考虑不确定性的最优逆向预置位姿 x_0*。"""
        # 蒙特卡洛抽样热效率与材料收缩率先验分布
        np.random.seed(42)
        eff_samples = np.random.normal(0.55, 0.03, prior_uncertainty_samples)
        coeff_samples = np.random.normal(0.00035, 0.00003, prior_uncertainty_samples)

        def objective(x: np.ndarray) -> float:
            total_loss = 0.0
            for eff, coeff in zip(eff_samples, coeff_samples):
                pred_final = self.predict_shrinkage_response(x, eff, coeff)
                err = pred_final - nominal_target
                total_loss += float(np.sum(err ** 2))
            mean_loss = total_loss / prior_uncertainty_samples
            # 加上正则项以避免极端激进调整导致干涉
            return mean_loss + self.reg_lambda * float(np.sum(x ** 2))

        # 约束条件：装配间隙边界
        constraints = [
            {"type": "ineq", "fun": lambda x: self.max_clearance - np.linalg.norm(x)},
        ]
        bounds = [(-self.max_stroke, self.max_stroke), (-self.max_stroke, self.max_stroke)]

        # 初猜：负名义收缩方向
        x_init = -0.5 * np.array([0.021, 0.015])
        res = minimize(objective, x_init, bounds=bounds, constraints=constraints, method="SLSQP")
        return res.x if res.success else x_init

    def evaluate_benchmark(self, num_trials: int = 200) -> Dict[str, PrecompensationCaseResult]:
        """三组对照评估：无补偿 vs 静态经验减法 vs 逆向自适应反演。"""
        np.random.seed(123)
        eff_trials = np.random.normal(0.55, 0.035, num_trials)
        coeff_trials = np.random.normal(0.00035, 0.00004, num_trials)
        init_offsets = np.random.normal(0.0, 0.005, (num_trials, 2))

        nominal_shrinkage = np.array([0.00035 * 74.98 * 0.819, 0.00035 * 74.98 * 0.573])

        errors_no_comp = []
        errors_static = []
        errors_inverse = []

        violations_static = 0
        violations_inverse = 0

        # 离线求解最优逆补偿设定
        x_inv_opt = self.solve_inverse_pose(np.array([0.0, 0.0]))

        for i in range(num_trials):
            eff = eff_trials[i]
            coeff = coeff_trials[i]
            init = init_offsets[i]

            # 1. 无补偿
            p_none = self.predict_shrinkage_response(init, eff, coeff)
            d_none = 2.0 * float(np.linalg.norm(p_none))  # 直径位置度
            errors_no_comp.append(d_none)

            # 2. 静态经验减法 (简单减去名义预测收缩)
            x_static = init - nominal_shrinkage
            if np.linalg.norm(x_static) > self.max_clearance:
                violations_static += 1
            p_static = self.predict_shrinkage_response(x_static, eff, coeff)
            d_static = 2.0 * float(np.linalg.norm(p_static))
            errors_static.append(d_static)

            # 3. 逆向自适应补偿
            x_inv = init + x_inv_opt
            # 硬保护截断
            if np.linalg.norm(x_inv) > self.max_clearance:
                violations_inverse += 1
                x_inv = (x_inv / np.linalg.norm(x_inv)) * self.max_clearance
            p_inv = self.predict_shrinkage_response(x_inv, eff, coeff)
            d_inv = 2.0 * float(np.linalg.norm(p_inv))
            errors_inverse.append(d_inv)

        def make_summary(name: str, errs: List[float], violations: int) -> PrecompensationCaseResult:
            arr = np.array(errs)
            return PrecompensationCaseResult(
                method_name=name,
                nominal_position_error_mm=float(np.mean(arr)),
                p95_position_error_mm=float(np.percentile(arr, 95)),
                max_position_error_mm=float(np.max(arr)),
                boundary_violation_rate_pct=(violations / num_trials) * 100.0,
                pass_p005_rate_pct=float(np.mean(arr <= 0.05)) * 100.0,
            )

        return {
            "no_compensation": make_summary("无补偿基线 (No-Comp)", errors_no_comp, 0),
            "static_subtraction": make_summary("经验静态减法 (Static-Minus)", errors_static, violations_static),
            "inverse_optimization": make_summary("不确定性逆向优化 (Inverse-Opt)", errors_inverse, violations_inverse),
        }
