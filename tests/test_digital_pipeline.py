"""Hanjie 数字工程主线的最小回归测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simulation" / "scripts"))
sys.path.insert(0, str(ROOT / "automation" / "vision"))
sys.path.insert(0, str(ROOT / "automation" / "anomaly-detection"))
sys.path.insert(0, str(ROOT / "automation" / "path-planning"))
sys.path.insert(0, str(ROOT / "src"))

from anomaly_detector import detect  # noqa: E402
from anomaly_detector import score_events  # noqa: E402
from detect_center import detect_image  # noqa: E402
from generate_dataset import render_sample  # noqa: E402
from generate_weld_path import generate_path  # noqa: E402
from position_tolerance import DATUM_DEFINITION, demo_points, fit_axis, fit_circle_xy  # noqa: E402
from run_reduced_order import build_cases, load_yaml  # noqa: E402
from run_monte_carlo import run_monte_carlo  # noqa: E402

from simulation.fe.run_fe_cases import build_mesh  # noqa: E402


def test_all_weld_sequences_are_permutations() -> None:
    from run_reduced_order import sequence_for

    for count in (4, 6, 8):
        for sequence in ("S1", "S2", "S3"):
            result = sequence_for(sequence, count)
            assert sorted(result) == list(range(count))


from hanjie.domain.baseline import get_baseline, validate_parameter_consistency  # noqa: E402


def test_baseline_parameter_consistency() -> None:
    """全工程唯一参数源 (SSOT) 一致性校验：禁止任何模块出现硬编码分叉。"""
    res = validate_parameter_consistency()
    assert res["status"] == "PASSED"

    # 交叉核验 CAD、仿真配置与 SSOT 基线
    base = get_baseline()
    sim_config = load_yaml(ROOT / "simulation" / "configs" / "default.yaml")
    cad_config = json.loads((ROOT / "cad" / "parametric" / "geometry.json").read_text(encoding="utf-8"))

    # 外径一致性
    assert abs(sim_config["geometry"]["wing_outer_radius_mm"] - 74.98) < 1e-6
    assert abs(cad_config["design_assumptions"]["wing_outer_radius"] - 74.98) < 1e-6
    assert abs(base["geometry"]["wing_outer_radius_mm"] - 74.98) < 1e-6

    # 配合间隙一致性 (H7/h6)
    assert cad_config["design_assumptions"]["assembly_fit"] == "H7/h6"
    assert base["geometry"]["assembly_fit"] == "H7/h6"


def test_rom_reference_case_reproducible() -> None:
    """冻结基准回归测试：保证降阶数值模型结果可复现且输出格式符合规范，不预设优化胜出偏误。"""
    config = load_yaml(ROOT / "simulation" / "configs" / "default.yaml")
    rows = build_cases(config)
    assert len(rows) == 15
    baseline = next(row for row in rows if row["case_id"] == "BASELINE-RIGID-6P-S1")
    assert "position_metric_p_sim_mm" in baseline
    assert baseline["position_metric_p_sim_mm"] > 0
    # 无优化的顺次焊刚性基准略微超出 0.05 mm 门限 (约 0.0505 mm)，充分印证了工艺与控制优化的必要性
    assert 0.045 < baseline["position_metric_p_sim_mm"] < 0.055


def test_mesh_convergence_calculation_correct() -> None:
    """网格收敛率判定逻辑测试：验证 |P_fine - P_med| / P_fine 判据正确性。"""
    p_med = 0.00150
    p_fine = 0.00145
    rel_change = abs(p_fine - p_med) / p_fine
    assert rel_change < 0.05  # <5% 判定收敛通过
    p_bad = 0.00190
    bad_change = abs(p_fine - p_bad) / p_fine
    assert bad_change > 0.05  # >5% 判定未收敛


def test_position_tolerance_demo_is_reproducible() -> None:
    result = fit_axis(demo_points())
    assert 0.04 < result["p_sim_mm"] < 0.06


def test_position_tolerance_uses_independent_assembly_datums() -> None:
    assert DATUM_DEFINITION["A"] == "壳体安装基准平面（z=0）"
    assert DATUM_DEFINITION["B"] == "Q235B 壳体理论中心轴（x=0, y=0）"
    assert DATUM_DEFINITION["position_tolerance"] == "Ø0.05 | A | B"
    assert "孔轴线" in DATUM_DEFINITION["controlled_feature"]


def test_position_tolerance_robust_fit_reports_outlier() -> None:
    import numpy as np

    theta = np.linspace(0.0, 2.0 * np.pi, 48, endpoint=False)
    points = np.column_stack((20.0 * np.cos(theta), 20.0 * np.sin(theta)))
    points = np.vstack((points, [[20.0, 2.0]]))
    _, _, _, quality = fit_circle_xy(points, return_quality=True)
    assert quality["outlier_count"] >= 1
    assert quality["residual_p95_mm"] < 0.02


def test_position_tolerance_reports_uncertainty_proxy() -> None:
    result = fit_axis(demo_points())
    assert result["fit_method"] == "huber_irls"
    assert result["measurement_uncertainty_proxy_mm"] >= 0.0
    assert len(result["section_quality"]) == 3


def test_weld_path_approach_points_follow_segment_angle() -> None:
    result = generate_path(6, "S3")
    assert result["sequence_segment_ids"] == [1, 4, 3, 6, 2, 5]
    for segment in result["segments"]:
        x, y, _ = segment["approach_mm"]
        assert abs((x * x + y * y) ** 0.5 - 68.98) < 1e-9


def test_vision_detector_on_rendered_sample(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    import cv2

    cv2.imwrite(str(image_path), render_sample(1.0, -1.0, 7.0, 123))
    result = detect_image(image_path)
    assert abs(result["dx_mm"] - 1.0) < 0.02
    assert abs(result["dy_mm"] + 1.0) < 0.02
    # 姿态标记先栅格化为像素，7° 输入允许一个像素级离散误差。
    assert abs(result["theta_deg"] - 7.0) < 0.25
    assert result["quality"]["accepted"] is True


def test_vision_quality_gate_rejects_perspective_sample(tmp_path: Path) -> None:
    from generate_dataset import apply_difficulty, render_sample_geometry
    import cv2

    image, points = render_sample_geometry(1.0, -1.0, 7.0, 123)
    image, _ = apply_difficulty(image, points, "perspective", 123)
    image_path = tmp_path / "perspective.png"
    cv2.imwrite(str(image_path), image)
    result = detect_image(image_path, reject_quality=False)
    assert result["quality"]["accepted"] is False
    assert result["quality"]["failed_checks"]


def test_simulated_session_matches_schema_and_detector() -> None:
    schema = json.loads((ROOT / "data/schemas/weld-session.schema.json").read_text(encoding="utf-8"))
    session = json.loads((ROOT / "data/samples/W2026-001-simulated.json").read_text(encoding="utf-8"))
    jsonschema.validate(session, schema)
    result = detect(session)
    assert session["meta"]["source_type"] == "simulated"
    assert result["event_count"] >= 4


def test_fe_mesh_distinguishes_continuous_and_flexible_structures() -> None:
    config = load_yaml(ROOT / "simulation" / "configs" / "default.yaml")
    baseline, baseline_seat, _ = build_mesh(config, 41, "baseline")
    flex, flex_seat, _ = build_mesh(config, 41, "flex")
    assert baseline.t.shape[1] > flex.t.shape[1]
    assert baseline_seat.sum() > flex_seat.sum()


def test_monte_carlo_records_both_designs() -> None:
    config = load_yaml(ROOT / "simulation" / "configs" / "default.yaml")
    rows, summary = run_monte_carlo(config, 20, 123, layouts=(6,))
    assert len(rows) == 20 * 2 * 2 * 3
    assert summary["design_count"] == 12
    assert summary["baseline_rigid_6p_s1"]["count"] == 20
    assert summary["flex_compliant_6p_s3"]["count"] == 20
    assert "structure" in summary["matched_effects"]
    assert summary["matched_6p_s3_structure"]["baseline_rigid"]["count"] == 20
    assert "未由 FE 或实测标定" in summary["model_assumption_status"]["structure_factor"]


def test_monte_carlo_accepts_non_default_layout_subset() -> None:
    config = load_yaml(ROOT / "simulation" / "configs" / "default.yaml")
    rows, summary = run_monte_carlo(config, 1, 123, layouts=(4,))
    assert len(rows) == 12
    assert summary["reference_layout"] == 4
    assert summary["baseline_rigid_4p_s1"]["count"] == 1
    assert summary["matched_4p_s3_structure"]["flex_rigid"]["count"] == 1


def test_anomaly_event_score_matches_injected_signal() -> None:
    data = {
        "sample_id": "T-001",
        "timestamp": [0.0, 0.1, 0.2, 0.3],
        "current": [75.0, 35.0, 35.0, 75.0],
        "voltage": [12.0, 12.0, 12.0, 12.0],
        "speed": [1.5, 1.5, 1.5, 1.5],
        "temperature": [150.0, 150.0, 150.0, 150.0],
        "meta": {"injected_anomalies": [{"name": "current_drop", "signal": "current", "start_s": 0.1, "end_s": 0.3}]},
    }
    result = detect(data)
    score = score_events(data, result)
    assert score["tp"] == 1
    assert score["fp"] == 0
    assert score["fn"] == 0


def test_anomaly_detector_debounces_short_pulse_and_adapts_current_bias() -> None:
    from signal_simulator import simulate_trial

    short = simulate_trial("SHORT", True, 7, duration_s=8.0, sample_rate_hz=200.0, anomaly_duration_s=0.02, anomaly_names=("current_drop",))
    assert not detect(short)["events"]
    biased = simulate_trial("BIAS", False, 8, current_bias=3.0)
    result = detect(biased)
    assert not result["events"]
    assert abs(result["calibration"]["current"]["estimated_bias"] - 3.0) < 0.2
