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

from anomaly_detector import detect  # noqa: E402
from anomaly_detector import score_events  # noqa: E402
from detect_center import detect_image  # noqa: E402
from generate_dataset import render_sample  # noqa: E402
from generate_weld_path import generate_path  # noqa: E402
from position_tolerance import demo_points, fit_axis  # noqa: E402
from run_reduced_order import build_cases, load_yaml  # noqa: E402
from run_monte_carlo import run_monte_carlo  # noqa: E402

from simulation.fe.run_fe_cases import build_mesh  # noqa: E402


def test_all_weld_sequences_are_permutations() -> None:
    from run_reduced_order import sequence_for

    for count in (4, 6, 8):
        for sequence in ("S1", "S2", "S3"):
            result = sequence_for(sequence, count)
            assert sorted(result) == list(range(count))


def test_optimized_layout_is_lower_than_baseline() -> None:
    config = load_yaml(ROOT / "simulation" / "configs" / "default.yaml")
    rows = build_cases(config)
    baseline = next(row for row in rows if row["case_id"] == "BASELINE-RIGID-6P-S1")
    optimized = next(row for row in rows if row["case_id"] == "FLEX-COMPLIANT-6P-S3")
    assert optimized["position_metric_p_sim_mm"] < baseline["position_metric_p_sim_mm"]
    assert optimized["reduction_vs_baseline_s1_pct"] > 0


def test_position_tolerance_demo_is_reproducible() -> None:
    result = fit_axis(demo_points())
    assert 0.04 < result["p_sim_mm"] < 0.06


def test_weld_path_approach_points_follow_segment_angle() -> None:
    result = generate_path(6, "S3")
    assert result["sequence_segment_ids"] == [1, 4, 3, 6, 2, 5]
    for segment in result["segments"]:
        x, y, _ = segment["approach_mm"]
        assert abs((x * x + y * y) ** 0.5 - 67.8) < 1e-9


def test_vision_detector_on_rendered_sample(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    import cv2

    cv2.imwrite(str(image_path), render_sample(1.0, -1.0, 7.0, 123))
    result = detect_image(image_path)
    assert abs(result["dx_mm"] - 1.0) < 0.02
    assert abs(result["dy_mm"] + 1.0) < 0.02
    # 姿态标记先栅格化为像素，7° 输入允许一个像素级离散误差。
    assert abs(result["theta_deg"] - 7.0) < 0.25


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
    rows, summary = run_monte_carlo(config, 20, 123)
    assert len(rows) == 40
    assert summary["baseline_rigid_6p_s1"]["count"] == 20
    assert summary["flex_compliant_6p_s3"]["count"] == 20


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
