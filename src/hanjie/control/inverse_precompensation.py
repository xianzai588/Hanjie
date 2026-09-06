"""带模型不确定性的逐件装配预偏置算法原型。

求解受约束非线性逆问题：
    delta* = argmin_delta E[||x_final(x_measured + delta, p)-x_target||^2]
受制于：
1. 实际装配位置 ``x_measured + delta`` 不超过径向间隙；
2. 相对调整量 ``delta`` 的每个轴不超过执行器行程；
3. 求解或约束失败时拒绝该件，不做静默截断。

当前收缩响应仍是未校准的合成代理，因此本模块只能验证变量、约束和拒绝
语义，不能证明实物自适应补偿有效。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List
import numpy as np
from scipy.optimize import minimize

@dataclass
class PrecompensationCaseResult:
    method_name: str
    nominal_position_error_mm: float
    p95_position_error_mm: float
    max_position_error_mm: float
    boundary_violation_rate_pct: float
    pass_p005_rate_pct: float
    accepted_count: int
    rejected_count: int
    overall_pass_rate_pct: float


class InversePrecompensationSolver:
    def __init__(
        self,
        max_clearance_mm: float = 0.040,  # 当前受控极限尺寸形成的最大径向间隙
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
        """由实际装配位置预测焊后位姿；当前仅为未校准代理。"""
        # 焊接热变形主矢量偏向热累积侧，并伴随非线性泊松横向缩径
        shrink_mag = shrinkage_coeff * (heat_efficiency / 0.55) * 74.98
        # 偏斜角约 35 度
        shrink_vector = np.array([shrink_mag * 0.819, shrink_mag * 0.573])
        return x0 + shrink_vector

    def solve_inverse_pose(
        self,
        initial_offset: np.ndarray,
        nominal_target: np.ndarray | None = None,
        prior_uncertainty_samples: int = 50,
    ) -> np.ndarray:
        """返回相对调整量 ``delta``，而不是绝对装配位置。"""
        initial_offset = np.asarray(initial_offset,dtype=float)
        nominal_target = np.zeros(2) if nominal_target is None else np.asarray(nominal_target,dtype=float)
        if initial_offset.shape!=(2,) or nominal_target.shape!=(2,) or not np.isfinite(initial_offset).all() or not np.isfinite(nominal_target).all():
            raise ValueError("初始偏心和目标必须是有限二维向量")
        if prior_uncertainty_samples<=0:
            raise ValueError("不确定性样本数必须为正")
        # 局部随机数生成器保证可复现，同时不污染调用方随机状态。
        rng = np.random.default_rng(42)
        eff_samples = rng.normal(0.55,0.03,prior_uncertainty_samples)
        coeff_samples = rng.normal(0.00035,0.00003,prior_uncertainty_samples)

        def objective(delta: np.ndarray) -> float:
            total_loss = 0.0
            for eff, coeff in zip(eff_samples, coeff_samples):
                actual_assembly = initial_offset+delta
                pred_final = self.predict_shrinkage_response(actual_assembly,eff,coeff)
                err = pred_final - nominal_target
                total_loss += float(np.sum(err ** 2))
            mean_loss = total_loss / prior_uncertainty_samples
            # 正则化作用于执行器实际调整量，避免无必要的大行程。
            return mean_loss+self.reg_lambda*float(np.sum(delta**2))

        # 径向间隙约束作用于真正执行后的装配位置。
        constraints = [
            {"type": "ineq", "fun": lambda delta: self.max_clearance-np.linalg.norm(initial_offset+delta)},
        ]
        bounds = [(-self.max_stroke, self.max_stroke), (-self.max_stroke, self.max_stroke)]

        nominal_shrinkage = np.array([0.00035*74.98*0.819,0.00035*74.98*0.573])
        delta_init = np.clip(nominal_target-initial_offset-nominal_shrinkage,-self.max_stroke,self.max_stroke)
        if np.linalg.norm(initial_offset+delta_init)>self.max_clearance:
            # 给求解器一个尽可能靠近允许圆域的初猜；最终仍由统一约束复核。
            assembly = initial_offset+delta_init
            assembly *= .95*self.max_clearance/np.linalg.norm(assembly)
            delta_init = np.clip(assembly-initial_offset,-self.max_stroke,self.max_stroke)
        result = minimize(objective,delta_init,bounds=bounds,constraints=constraints,method="SLSQP",
                          options={"ftol":1e-12,"maxiter":200})
        delta = np.asarray(result.x,dtype=float)
        if not result.success or not self.execution_is_feasible(initial_offset,delta):
            raise RuntimeError(f"预偏置求解失败或执行量越界：{result.message}")
        return delta

    def execution_is_feasible(self,initial_offset: np.ndarray,adjustment: np.ndarray) -> bool:
        """用同一口径检查相对行程与最终装配间隙。"""
        initial_offset = np.asarray(initial_offset,dtype=float)
        adjustment = np.asarray(adjustment,dtype=float)
        return bool(
            initial_offset.shape==(2,) and adjustment.shape==(2,)
            and np.isfinite(initial_offset).all() and np.isfinite(adjustment).all()
            and np.all(np.abs(adjustment)<=self.max_stroke+1e-9)
            and np.linalg.norm(initial_offset+adjustment)<=self.max_clearance+1e-9
        )

    def evaluate_benchmark(self, num_trials: int = 200) -> Dict[str, PrecompensationCaseResult]:
        """三组对照评估：无补偿 vs 静态经验减法 vs 逆向自适应反演。"""
        if num_trials<=0:
            raise ValueError("试次数必须为正")
        rng = np.random.default_rng(123)
        eff_trials = rng.normal(0.55,0.035,num_trials)
        coeff_trials = rng.normal(0.00035,0.00004,num_trials)
        init_offsets = rng.normal(0.0,0.005,(num_trials,2))

        nominal_shrinkage = np.array([0.00035 * 74.98 * 0.819, 0.00035 * 74.98 * 0.573])

        errors_no_comp = []
        errors_static = []
        errors_inverse = []

        violations_static = 0
        violations_inverse = 0

        for i in range(num_trials):
            eff = eff_trials[i]
            coeff = coeff_trials[i]
            init = init_offsets[i]

            # 三种方法共享同一执行器/间隙约束，越界样本均拒绝，不截断伪装为成功。
            no_adjustment = np.zeros(2)
            if self.execution_is_feasible(init,no_adjustment):
                p_none = self.predict_shrinkage_response(init,eff,coeff)
                errors_no_comp.append(2.0*float(np.linalg.norm(p_none)))

            static_adjustment = -nominal_shrinkage
            if not self.execution_is_feasible(init,static_adjustment):
                violations_static += 1
            else:
                p_static = self.predict_shrinkage_response(init+static_adjustment,eff,coeff)
                errors_static.append(2.0*float(np.linalg.norm(p_static)))

            try:
                inverse_adjustment = self.solve_inverse_pose(init)
            except RuntimeError:
                violations_inverse += 1
            else:
                p_inv = self.predict_shrinkage_response(init+inverse_adjustment,eff,coeff)
                errors_inverse.append(2.0*float(np.linalg.norm(p_inv)))

        def make_summary(name: str, errs: List[float], violations: int) -> PrecompensationCaseResult:
            arr = np.array(errs)
            if arr.size==0:
                return PrecompensationCaseResult(
                    method_name=name,nominal_position_error_mm=float("nan"),p95_position_error_mm=float("nan"),
                    max_position_error_mm=float("nan"),boundary_violation_rate_pct=100.0,
                    pass_p005_rate_pct=0.0,accepted_count=0,rejected_count=violations,overall_pass_rate_pct=0.0,
                )
            passed = int(np.sum(arr<=0.05))
            return PrecompensationCaseResult(
                method_name=name,
                nominal_position_error_mm=float(np.mean(arr)),
                p95_position_error_mm=float(np.percentile(arr, 95)),
                max_position_error_mm=float(np.max(arr)),
                boundary_violation_rate_pct=(violations / num_trials) * 100.0,
                pass_p005_rate_pct=passed/len(arr)*100.0,
                accepted_count=len(arr),
                rejected_count=violations,
                overall_pass_rate_pct=passed/num_trials*100.0,
            )

        return {
            "no_compensation": make_summary("无补偿基线 (No-Comp)",errors_no_comp,num_trials-len(errors_no_comp)),
            "static_subtraction": make_summary("经验静态减法 (Static-Minus)", errors_static, violations_static),
            "inverse_optimization": make_summary("不确定性逆向优化 (Inverse-Opt)", errors_inverse, violations_inverse),
        }
