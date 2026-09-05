"""自适应跳焊控制、逆向反变形补偿与少样本标定的单元测试。"""

from __future__ import annotations

import numpy as np

from hanjie.control.adaptive_sequence import AdaptiveSequenceController
from hanjie.control.inverse_precompensation import InversePrecompensationSolver
from hanjie.measurement.few_shot_calibration import FewShotCalibrator
from hanjie.simulation.fe3d import run_mesh_convergence_study


def test_mesh_convergence_3d_passes_gate_b1() -> None:
    """3D 有限元网格收敛验证测试：变化率应严格 < 5% (Gate B.1)。"""
    study = run_mesh_convergence_study("continuous")
    assert study["gate_b1_passed"] is True
    assert study["p_change_fine_vs_med_pct"] < 5.0
    assert study["stress_change_pct"] < 15.0


def test_adaptive_sequence_controller_respects_constraints() -> None:
    """自适应跳焊控制测试：确保施焊顺序满足道温约束与扰动调整能力。"""
    controller = AdaptiveSequenceController(num_segments=6)
    res = controller.solve_adaptive_sequence()
    assert len(res.execution_order) == 6
    assert set(res.execution_order) == {1, 2, 3, 4, 5, 6}
    assert res.final_position_p_mm <= 0.050

    # 在 3 号区域高出 25°C 扰动下，自适应算法应调整施焊次序
    perturb = np.array([0.0, 0.0, 25.0, 5.0, -10.0, 0.0])
    res_disturbed = controller.solve_adaptive_sequence(initial_perturbation=perturb)
    assert res_disturbed.execution_order[0] != 3  # 绝不在最热的 3 号区起焊


def test_inverse_precompensation_respects_clearance_bound() -> None:
    """逆向反变形补偿测试：反演出的预置位姿必须严格处于 H7/h6 间隙裕量内。"""
    solver = InversePrecompensationSolver(max_clearance_mm=0.040)
    x_opt = solver.solve_inverse_pose(np.array([0.0, 0.0]))
    assert np.linalg.norm(x_opt) <= 0.040 + 1e-6

    bench = solver.evaluate_benchmark(num_trials=50)
    assert bench["inverse_optimization"].p95_position_error_mm < bench["no_compensation"].p95_position_error_mm
    assert bench["inverse_optimization"].pass_p005_rate_pct >= 98.0


def test_few_shot_calibration_reduces_uncertainty() -> None:
    """少样本物理试验校准测试：后验不确定度应显著低于先验。"""
    calibrator = FewShotCalibrator()
    trials = calibrator.generate_synthetic_physical_trials()
    report = calibrator.calibrate_from_trials(trials)

    assert 0.50 <= report.posterior_eta <= 0.60
    assert 1000.0 <= report.posterior_stiffness_n_mm <= 1400.0
    assert report.uncertainty_reduction_pct > 50.0  # 不确定度缩减率大于 50%
    assert report.post_calib_error_p95_mm < report.pre_calib_error_p95_mm
