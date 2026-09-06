"""自适应跳焊控制、逆向反变形补偿与少样本标定的单元测试。"""

from __future__ import annotations

import numpy as np

from hanjie.control.adaptive_sequence import AdaptiveSequenceController
from hanjie.control.inverse_precompensation import InversePrecompensationSolver
from hanjie.measurement.few_shot_calibration import FewShotCalibrator
from hanjie.simulation.fe3d import run_mesh_convergence_study


def test_surrogate_cannot_pass_gate_b1() -> None:
    study = run_mesh_convergence_study("continuous")
    assert study["gate_b1_passed"] is False
    assert study["solver_executed"] is False
    assert study["fine"].thermal_balance_error_pct is None


def test_adaptive_replay_uses_identical_plant_and_measurement() -> None:
    controller = AdaptiveSequenceController()
    for perturb in [np.zeros(6), np.array([0, 0, 25, 5, -10, 0]), np.full(6, 200)]:
        adaptive = controller.solve_adaptive_sequence(perturb)
        replay = controller.evaluate_fixed_sequence("replay", adaptive.execution_order, perturb)
        assert adaptive.steps == replay.steps
        assert adaptive.final_position_p_mm == replay.final_position_p_mm
        assert adaptive.total_cycle_time_s == replay.total_cycle_time_s
        assert adaptive.plant_model == replay.plant_model
        assert adaptive.position_predictor == replay.position_predictor
        assert adaptive.evaluation_model == replay.evaluation_model
        assert all(s.temp_before_c <= controller.interpass_gate_c + 1e-8 for s in adaptive.steps)
        assert sorted(adaptive.execution_order) == list(range(1, 7))


def test_fixed_sequence_rejects_duplicate_segments() -> None:
    import pytest
    with pytest.raises(ValueError):
        AdaptiveSequenceController().evaluate_fixed_sequence("invalid", [1, 1, 2, 3, 4, 5])


def test_inverse_precompensation_respects_clearance_bound() -> None:
    """相对调整量与最终装配位置分别满足行程和间隙约束。"""
    solver = InversePrecompensationSolver(max_clearance_mm=0.040)
    initial = np.array([0.006,-0.004])
    adjustment = solver.solve_inverse_pose(initial)
    assert np.all(np.abs(adjustment)<=solver.max_stroke+1e-9)
    assert np.linalg.norm(initial+adjustment)<=0.040+1e-9
    assert solver.execution_is_feasible(initial,adjustment)


def test_inverse_precompensation_uses_each_measured_initial_offset() -> None:
    solver = InversePrecompensationSolver()
    first = np.array([0.006,-0.004])
    second = np.array([-0.003,0.007])
    delta_first = solver.solve_inverse_pose(first)
    delta_second = solver.solve_inverse_pose(second)
    assert not np.allclose(delta_first,delta_second)
    # 正则化会保留少量初态影响，但补偿后两件差异应显著小于原始差异。
    assert np.linalg.norm((first+delta_first)-(second+delta_second))<0.1*np.linalg.norm(first-second)


def test_precompensation_benchmark_reports_rejections_without_clipping() -> None:
    result = InversePrecompensationSolver(max_clearance_mm=0.012,max_stroke_mm=0.010).evaluate_benchmark(30)
    for row in result.values():
        assert row.accepted_count+row.rejected_count==30
        assert row.boundary_violation_rate_pct==row.rejected_count/30*100
        assert row.overall_pass_rate_pct<=row.pass_p005_rate_pct+1e-12



def test_calibration_is_synthetic_and_data_driven() -> None:
    from dataclasses import asdict
    import json
    calibrator = FewShotCalibrator()
    trials = calibrator.generate_synthetic_physical_trials()
    report = calibrator.calibrate_from_trials(trials)
    assert report.evidence_level == "synthetic_demo"
    assert report.uncertainty_reduction_pct is None
    assert "measured_p_mm" not in json.dumps(asdict(report))
    assert report.fitted_trial_types == ["thermal", "cmm_position"]
    assert report.excluded_trial_types == ["hardness"]
    assert "组合响应系数" in report.identifiability_note
    values = np.array([t.synthetic_values[0] for t in trials if t.trial_type == "cmm_position"])
    for i, row in enumerate(report.sample_comparisons):
        assert np.isclose(row["leave_one_out_pred_mm"], np.delete(values, i).mean())
    for t in trials:
        if t.trial_type == "cmm_position":
            t.synthetic_values *= 1.2
    changed = calibrator.calibrate_from_trials(trials)
    assert np.isclose(changed.fitted_combined_response_coeff, report.fitted_combined_response_coeff * 1.2)


def test_synthetic_entry_rejects_measured_labels() -> None:
    import pytest
    calibrator = FewShotCalibrator()
    trials = calibrator.generate_synthetic_physical_trials()
    trials[0].evidence_level = "experiment_measured"
    with pytest.raises(ValueError):
        calibrator.calibrate_from_trials(trials)
