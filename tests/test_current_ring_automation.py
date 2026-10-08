"""当前圆环自动化的工艺错配、波形语义与追溯反例。"""
from __future__ import annotations

import copy
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
for directory in ("automation/path-planning", "automation/anomaly-detection", "automation/traceability", "automation/app"):
    sys.path.insert(0, str(ROOT / directory))

from anomaly_detector import detect
from database import ingest
from generate_weld_path import generate_path
from run_demo import execute_complete_virtual_plan, execute_virtual_plan, synthetic_interlock_readings
from signal_simulator import simulate_complete_weld, simulate_trial
from hanjie.domain.submission import read_submission, ring_cycle_permission


def clean():
    return simulate_trial("RING-001", False, 45, duration_s=2.0, noise_scale=0)


def test_current_path_uses_actual_length_two_passes_and_product_frame():
    spec = read_submission()
    result = generate_path()
    assert result["process_version"] == spec["version"]
    assert result["sequence_segment_ids"] == [1, 5, 3, 7, 2, 6, 4, 8]
    assert result["pass_count"] == 2 and result["total_arc_length_mm"] == 320
    assert len(result["arc_commands"]) == 16
    for segment in result["segments"]:
        assert segment["actual_arc_length_mm"] == 20
        assert segment["effective_connection_length_mm"] == 18
        assert segment["radius_mm"] * segment["sweep_angle_rad"] == pytest.approx(20)
        assert segment["start_local_mm"][2] == 0
        assert segment["start_product_mm"][2] == 115
        assert segment["start_local_mm"][:2] == segment["start_product_mm"][:2]
    assert result["coordinate_frames"]["robot"]["tcp_calibrated"] is False


def test_legal_instantaneous_pulse_is_not_misread_as_75A_window():
    result = detect(clean())
    assert result["events"] == []
    assert result["calibration"]["current"]["peak_nominal_A"] == 100
    assert result["calibration"]["current"]["base_nominal_A"] == 50


def test_cycle_average_requires_explicit_semantics_and_unshifted_window():
    data = clean()
    data["meta"]["current_definition"] = "cycle_mean_A"
    data["current"] = [75 if p == "arc_on" else 0 for p in data["phase"]]
    assert not detect(data)["events"]
    data["current"] = [82 if p == "arc_on" else 0 for p in data["phase"]]
    result = detect(data)
    assert any(e["signal"] == "current" for e in result["events"])
    assert result["calibration"]["current"]["adjusted_window"] == [70, 80]
    assert result["calibration"]["current"]["estimated_bias"] == 0


@pytest.mark.parametrize("value", [1.69, 1.95])
def test_sustained_speed_offset_cannot_shift_monitoring_window(value):
    data = clean()
    data["speed"] = [value if p == "arc_on" else 0 for p in data["phase"]]
    result = detect(data)
    assert any(e["signal"] == "speed" for e in result["events"])
    assert result["calibration"]["speed"]["nominal_window"] == pytest.approx([1.617, 1.683])
    assert result["calibration"]["speed"]["adjusted_window"] == pytest.approx([1.617, 1.683])
    assert result["calibration"]["speed"]["estimated_bias"] == 0


def test_sustained_peak_offset_cannot_hide_between_legal_base_intervals():
    data = clean()
    data["current"] = [110 if v == 100 else v for v in data["current"]]
    assert any(e["signal"] == "current" for e in detect(data)["events"])


def test_instantaneous_waveform_rejects_aliasing_and_constant_mean():
    data = clean()
    undersampled = copy.deepcopy(data)
    for key in ("timestamp", "current", "voltage", "speed", "wire_feed", "temperature", "phase"):
        undersampled[key] = undersampled[key][::20]
    with pytest.raises(ValueError, match="采样不足"):
        detect(undersampled)
    data["current"] = [75 if p == "arc_on" else 0 for p in data["phase"]]
    assert any(e["signal"] == "current" for e in detect(data)["events"])


def test_temperature_gate_is_immediate_and_separate_from_arc_peak():
    data = clean()
    data["temperature"] = [150 if p == "arc_on" else 25 for p in data["phase"]]
    assert not detect(data)["events"]  # 弧燃读数不被误当起弧前层间温度。
    data["phase"][100] = "interpass_start"
    data["current"][100] = data["voltage"][100] = data["speed"][100] = 0
    events = detect(data)["events"]
    assert any(e["type"] == "interpass_start_temperature_block" for e in events)
    assert ring_cycle_permission("weld", synthetic_interlock_readings(150)) is False
    assert ring_cycle_permission("weld", synthetic_interlock_readings(85)) is True
    missing = synthetic_interlock_readings(25)
    missing.pop("water_leak_free")
    assert ring_cycle_permission("weld", missing) is False
    string_feedback = synthetic_interlock_readings(25)
    string_feedback["fixture_locked"] = "false"
    assert ring_cycle_permission("weld", string_feedback) is False


def test_non_arc_values_do_not_leak_hysteresis_into_next_arc():
    data = clean()
    data["meta"]["current_definition"] = "cycle_mean_A"
    # 重启时的值在合法边缘，仍须从本弧重新判定，不能继承停弧时0值的报警状态。
    data["current"] = [70.2 if p == "arc_on" else 0 for p in data["phase"]]
    data["speed"] = [1.618 if p == "arc_on" else 0 for p in data["phase"]]
    data["voltage"] = [11.02 if p == "arc_on" else 0 for p in data["phase"]]
    assert not detect(data)["events"]


def test_demo_interlock_suppresses_commands_after_fault_feedback():
    data = clean()
    assert execute_virtual_plan(generate_path(), data, detect(data))["suppressed_request_count"] == 0
    data["speed"] = [1.95 if p == "arc_on" else 0 for p in data["phase"]]
    plan = execute_virtual_plan(generate_path(), data, detect(data))
    assert plan["hardware_commands_sent"] == 0
    assert len(plan["virtual_requests_emitted"]) == 1
    assert plan["suppressed_request_count"] == 15
    assert plan["temperature_gate_examples"]["interpass_150C"] is False


def test_rejected_first_arc_cannot_skip_to_next_segment_or_use_forged_detection():
    data = clean()
    data["temperature"] = [150 if p == "first_start" else t for p, t in zip(data["phase"], data["temperature"])]
    result = detect(data)
    plan = execute_virtual_plan(generate_path(), data, result)
    assert plan["virtual_requests_emitted"] == [] and plan["suppressed_request_count"] == 16
    result["events"] = []
    result["event_count"] = 0
    with pytest.raises(ValueError, match="未绑定"):
        execute_virtual_plan(generate_path(), data, result)


def write_pair(tmp_path, data, anomaly):
    signal_path, anomaly_path = tmp_path / "signal.json", tmp_path / "anomaly.json"
    signal_path.write_text(json.dumps(data), encoding="utf-8")
    anomaly_path.write_text(json.dumps(anomaly), encoding="utf-8")
    return signal_path, anomaly_path


@pytest.mark.parametrize("field,value", [("sample_id", "OTHER"), ("session_id", "OTHER-RUN"),
    ("process_version", "OLD"), ("source_type", "physical"), ("operation", "first_layer")])
def test_traceability_rejects_mismatched_result_identity(tmp_path, field, value):
    data = clean()
    anomaly = detect(data)
    anomaly[field] = value
    signal_path, anomaly_path = write_pair(tmp_path, data, anomaly)
    with pytest.raises(ValueError, match="不一致"):
        ingest(signal_path, anomaly_path, tmp_path / "trace.db")
    assert not (tmp_path / "trace.db").exists()


def test_traceability_binds_result_to_input_and_keeps_correct_source(tmp_path):
    data = clean()
    anomaly = detect(data)
    altered = copy.deepcopy(data)
    altered["voltage"][100] = 12.1  # 身份相同、未改变报警数，仍不是该结果对应的原始输入。
    signal_path, anomaly_path = write_pair(tmp_path, altered, anomaly)
    with pytest.raises(ValueError, match="未绑定"):
        ingest(signal_path, anomaly_path, tmp_path / "trace.db")
    signal_path, anomaly_path = write_pair(tmp_path, data, anomaly)
    ingest(signal_path, anomaly_path, tmp_path / "trace.db")
    ingest(signal_path, anomaly_path, tmp_path / "trace.db")
    with sqlite3.connect(tmp_path / "trace.db") as db:
        assert db.execute("SELECT sample_id,source_type,process_version,current_definition FROM weld_sessions_v2").fetchall() == [
            (data["sample_id"], "simulated", read_submission()["version"], "instantaneous_pulsed_A")]
    altered["meta"]["session_id"] = data["meta"]["session_id"]
    signal_path, anomaly_path = write_pair(tmp_path, altered, detect(altered))
    with pytest.raises(ValueError, match="覆盖"):
        ingest(signal_path, anomaly_path, tmp_path / "trace.db")


def test_current_traceability_rejects_unversioned_historical_record(tmp_path):
    data = clean()
    data["meta"].pop("process_version")
    signal_path, anomaly_path = write_pair(tmp_path, data, {})
    with pytest.raises(ValueError, match="工艺版本"):
        ingest(signal_path, anomaly_path, tmp_path / "trace.db")


def test_complete_normal_cycle_integrates_16_arcs_with_exact_interval_edges():
    data = simulate_complete_weld()
    result = detect(data)
    assert not result["events"]
    rows = result["segment_metrics"]
    assert len(rows) == 16
    assert sum(r["actual_path_mm"] for r in rows) == pytest.approx(320, abs=1e-5)
    assert sum(r["arc_time_s"] for r in rows) == pytest.approx(320 / 1.65)
    assert max(abs(r["net_energy_J_mm"] / 300 - 1) for r in rows) < .002
    assert all(r["energy_in_range"] and r["path_in_range"] and r["wire_feed_in_range"] for r in rows)
    replay = execute_complete_virtual_plan(generate_path(), data, result)
    assert replay["feedback_consumed_arc_count"] == 16 and replay["suppressed_request_count"] == 0
    assert replay["hardware_commands_sent"] == 0 and replay["source_type"] == "simulated"


def test_in_window_voltage_drift_still_trips_integrated_energy_and_next_arc():
    data = simulate_complete_weld(fault="energy", fault_segment_index=3)
    result = detect(data)
    assert not any(e["signal"] == "voltage" for e in result["events"])
    assert any(e["signal"] == "net_energy" for e in result["events"])
    assert result["segment_metrics"][3]["net_energy_J_mm"] > 306
    replay = execute_complete_virtual_plan(generate_path(), data, result)
    assert replay["feedback_consumed_arc_count"] == 4 and replay["suppressed_request_count"] == 12
    assert replay["decisions"][4]["previous_segment_energy_in_range"] is False
    assert replay["decisions"][4]["action"] == "suppress_arc_request"


@pytest.mark.parametrize("fault", ["wire_feed", "speed"])
def test_complete_wire_feed_and_speed_drift_stop_after_observed_segment(fault):
    data = simulate_complete_weld(fault=fault, fault_segment_index=3)
    result = detect(data)
    assert any(e["signal"] == fault for e in result["events"])
    replay = execute_complete_virtual_plan(generate_path(), data, result)
    assert replay["feedback_consumed_arc_count"] == 4 and replay["suppressed_request_count"] == 12
    row = result["segment_metrics"][3]
    if fault == "wire_feed":
        assert row["wire_feed_in_range"] is False
    else:
        assert row["actual_path_mm"] == pytest.approx(20 * 1.95 / 1.65, abs=1e-6)
        assert row["energy_in_range"] is False and row["path_in_range"] is False


def test_complete_feedback_rejects_segment_identity_mismatch():
    data = simulate_complete_weld()
    index = data["phase"].index("arc_on")
    data["segment_id"][index] = 5
    with pytest.raises(ValueError, match="身份"):
        detect(data)


def test_complete_first_arc_temperature_block_stops_all_requests():
    data = simulate_complete_weld(fault="temperature", fault_segment_index=0)
    replay = execute_complete_virtual_plan(generate_path(), data, detect(data))
    assert replay["feedback_consumed_arc_count"] == 0
    assert replay["suppressed_request_count"] == 16 and replay["virtual_requests_emitted"] == []


def test_segment_energy_cannot_multiply_separately_averaged_current_and_voltage():
    data = simulate_complete_weld()
    data["meta"]["current_definition"] = "cycle_mean_A"
    data["current"] = [75 if p == "arc_on" else 0 for p in data["phase"]]
    with pytest.raises(ValueError, match="同步瞬时UI"):
        detect(data)


@pytest.mark.parametrize('scope', ['fragment', 'complete'])
def test_synthetic_control_entry_rejects_physical_source(scope):
    data = clean() if scope == 'fragment' else simulate_complete_weld()
    data['meta']['source_type'] = 'physical'
    result = detect(data)
    entry = execute_virtual_plan if scope == 'fragment' else execute_complete_virtual_plan
    with pytest.raises(ValueError, match='纯合成演示入口只接受simulated'):
        entry(generate_path(), data, result)
