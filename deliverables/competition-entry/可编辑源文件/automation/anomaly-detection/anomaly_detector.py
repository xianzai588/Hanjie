"""用工艺窗口与连续采样规则识别仿真过程异常。"""

from __future__ import annotations

import argparse
import json
import hashlib
import math
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from hanjie.domain.submission import read_submission, session_identity

DEFAULT_INPUT = ROOT / "automation/anomaly-detection/results/W2026-001-signals.json"
DEFAULT_OUTPUT = ROOT / "automation" / "anomaly-detection" / "results" / "W2026-001-anomalies.json"


WINDOWS = {
    "current": (70.0, 80.0, "A"),
    "voltage": (11.0, 13.0, "V"),
    "speed": (1.2, 1.8, "mm/s"),
    "temperature": (0.0, 200.0, "°C"),
}

# 仅对有稳定工艺中心的连续过程量做在线偏置估计；温度保留绝对上限，避免把真实升温趋势抵消。
ADAPTIVE_BIAS_SIGNALS = {"current", "voltage", "speed"}
DEFAULT_MIN_DURATION_S = 0.05
DEFAULT_HYSTERESIS_FRACTION = 0.10


def score_events(data: dict[str, object], detection: dict[str, object], tolerance_s: float = 0.2) -> dict[str, object]:
    """按信号和区间匹配注入事件，输出TP/FP/FN与离线事件起点偏差，非在线触发延迟。"""
    meta = data.get("meta", {})
    truth = list(meta.get("injected_anomalies", [])) if isinstance(meta, dict) else []
    predicted = list(detection.get("events", []))
    matched_prediction: set[int] = set()
    delays: list[float] = []
    tp = 0
    for expected in truth:
        candidates = []
        for index, event in enumerate(predicted):
            if index in matched_prediction or event.get("signal") != expected.get("signal"):
                continue
            start_gap = float(event["start_s"]) - float(expected["end_s"])
            end_gap = float(expected["start_s"]) - float(event["end_s"])
            if start_gap <= tolerance_s and end_gap <= tolerance_s:
                candidates.append(index)
        if candidates:
            index = min(candidates, key=lambda item: abs(float(predicted[item]["start_s"]) - float(expected["start_s"])))
            matched_prediction.add(index)
            tp += 1
            delays.append(max(0.0, float(predicted[index]["start_s"]) - float(expected["start_s"])))
    fp = len(predicted) - len(matched_prediction)
    fn = len(truth) - tp
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "delays_s": delays,
        "truth_count": len(truth),
        "predicted_count": len(predicted),
    }


def _sample_period(timestamp: np.ndarray) -> float:
    if timestamp.size < 2:
        return 0.0
    return float(np.median(np.diff(timestamp)))


def _adaptive_window(signal: str, values: np.ndarray, low: float, high: float) -> tuple[float, float, float]:
    """估计传感器静态偏置，并将窗口整体平移；偏移量限制在窗口宽度的 40%。"""
    if signal not in ADAPTIVE_BIAS_SIGNALS or values.size == 0:
        return low, high, 0.0
    center = (low + high) / 2.0
    offset = float(np.median(values) - center)
    max_offset = 0.4 * (high - low)
    offset = float(np.clip(offset, -max_offset, max_offset))
    return low + offset, high + offset, offset


def _hysteresis_mask(values: np.ndarray, low: float, high: float, hysteresis: float) -> np.ndarray:
    """滞回状态机，过滤阈值边缘噪声并保留真实越界段。"""
    active = False
    mask = np.zeros(values.size, dtype=bool)
    release_low = low + hysteresis
    release_high = high - hysteresis
    for index, value in enumerate(values):
        if not active and (value < low or value > high):
            active = True
        elif active and release_low <= value <= release_high:
            active = False
        mask[index] = active
    return mask


def _events_from_mask(mask: np.ndarray, timestamp: np.ndarray, values: np.ndarray, min_duration_s: float) -> list[dict[str, float]]:
    starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
    ends = np.flatnonzero(mask & ~np.r_[mask[1:], False])
    dt = _sample_period(timestamp)
    events = []
    for start, end in zip(starts, ends):
        duration = float(timestamp[end] - timestamp[start] + dt)
        if duration + 1e-9 < min_duration_s:
            continue
        events.append({
            "start_s": float(timestamp[start]),
            "end_s": float(timestamp[end] + dt),
            "duration_s": duration,
            "min": float(values[start:end + 1].min()),
            "max": float(values[start:end + 1].max()),
        })
    return events


def _detect_historical(data: dict[str, object], min_duration_s: float = DEFAULT_MIN_DURATION_S,
           hysteresis_fraction: float = DEFAULT_HYSTERESIS_FRACTION,
           filter_window_samples: int = 5) -> dict[str, object]:
    if min_duration_s < 0.0:
        raise ValueError("min_duration_s 必须非负")
    if not 0.0 <= hysteresis_fraction < 0.5:
        raise ValueError("hysteresis_fraction 必须位于 [0, 0.5)")
    if filter_window_samples < 1 or filter_window_samples % 2 == 0:
        raise ValueError("filter_window_samples 必须为正奇数")
    timestamp = np.asarray(data["timestamp"], dtype=float)
    if timestamp.ndim != 1 or timestamp.size < 2 or not np.all(np.isfinite(timestamp)):
        raise ValueError("timestamp 必须包含至少两个有限采样点")
    if np.any(np.diff(timestamp) <= 0.0):
        raise ValueError("timestamp 必须严格递增")
    events = []
    calibration = {}

    for signal, (low, high, unit) in WINDOWS.items():
        values = np.asarray(data[signal], dtype=float)
        if values.size != timestamp.size:
            raise ValueError(f"{signal} 与 timestamp 长度不一致")
        if values.ndim != 1 or not np.all(np.isfinite(values)):
            raise ValueError(f"{signal} 必须是一维有限数值序列")
        adjusted_low, adjusted_high, offset = _adaptive_window(signal, values, low, high)
        calibration[signal] = {
            "nominal_window": [low, high],
            "adjusted_window": [adjusted_low, adjusted_high],
            "estimated_bias": offset,
        }
        hysteresis = (high - low) * hysteresis_fraction
        # 短测试片段不足一个滤波窗口时保留原始序列，避免边界复制掩盖整个异常段。
        filtered_values = values if values.size < filter_window_samples * 2 else median_filter(values, size=filter_window_samples, mode="nearest")
        mask = _hysteresis_mask(filtered_values, adjusted_low, adjusted_high, hysteresis)
        for event in _events_from_mask(mask, timestamp, values, min_duration_s):
            events.append({
                "signal": signal,
                "type": "out_of_window",
                **event,
                "window": [adjusted_low, adjusted_high],
                "unit": unit,
            })
    events.sort(key=lambda item: (item["start_s"], item["signal"]))
    return {
        "sample_id": data["sample_id"],
        "scope": "historical_unversioned_window_replay",
        "event_count": len(events),
        "events": events,
        "min_duration_s": min_duration_s,
        "hysteresis_fraction": hysteresis_fraction,
        "filter_window_samples": filter_window_samples,
        "calibration": calibration,
        "statement": "历史75A/1.5mm/s/200℃窗口及旧偏置规则的离线回放；不参与当前圆环控制或当前追溯入库。",
    }


def _current_ring_detection(data: dict, min_duration_s: float, hysteresis_fraction: float,
                            filter_window_samples: int) -> dict:
    spec = read_submission()
    identity = session_identity(data, spec)
    process, monitoring = spec["final_GTAW"], spec["monitoring_design"]
    meta = data["meta"]
    timestamp = np.asarray(data["timestamp"], dtype=float)
    if timestamp.ndim != 1 or timestamp.size < 2 or not np.all(np.isfinite(timestamp)) or np.any(np.diff(timestamp) <= 0):
        raise ValueError("timestamp 必须是至少两个有限且严格递增的采样点")
    phase = np.asarray(data.get("phase", []))
    if phase.shape != timestamp.shape or not np.all(np.isin(phase, ["first_start", "interpass_start", "arc_on", "cooling"])):
        raise ValueError("当前信号必须逐点区分首段起弧、续焊起弧、弧燃与冷却工序")
    series = {}
    for name in (*WINDOWS, "wire_feed"):
        values = np.asarray(data[name], dtype=float)
        if values.shape != timestamp.shape or not np.all(np.isfinite(values)):
            raise ValueError(f"{name} 与timestamp长度不一致或有非法值")
        series[name] = values
    arc = phase == "arc_on"
    dt = _sample_period(timestamp)
    events = []
    calibration = {}

    def arc_hysteresis(values, low, high, hysteresis):
        mask = np.zeros(timestamp.size, dtype=bool)
        starts = np.flatnonzero(arc & ~np.r_[False, arc[:-1]])
        ends = np.flatnonzero(arc & ~np.r_[arc[1:], False])
        for start, end in zip(starts, ends):
            mask[start:end + 1] = _hysteresis_mask(values[start:end + 1], low, high, hysteresis)
        return mask

    def append(name, mask, low, high, unit, *, minimum=None, event_type="out_of_window"):
        for event in _events_from_mask(mask, timestamp, series[name], min_duration_s if minimum is None else minimum):
            events.append({"signal": name, "type": event_type, **event, "window": [low, high], "unit": unit})
        calibration[name] = {"nominal_window": [low, high], "adjusted_window": [low, high], "estimated_bias": 0.0,
                             "policy": "fixed_design_window_no_online_shift"}

    definition = meta["current_definition"]
    mean = process["peak_current_A"] * process["peak_duty_fraction"] + process["base_current_A"] * (1 - process["peak_duty_fraction"])
    if definition == "cycle_mean_A":
        tol = monitoring["current"]["cycle_mean_tolerance_A"]
        mask = arc_hysteresis(series["current"], mean - tol, mean + tol, tol * 2 * hysteresis_fraction)
        append("current", mask, mean - tol, mean + tol, "A")
    else:
        frequency, duty, origin = (meta.get(k) for k in ("pulse_frequency_Hz", "pulse_peak_duty_fraction", "pulse_phase_origin_s"))
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (frequency, duty, origin)):
            raise ValueError("瞬时电流缺少有限的脉冲频率、占空比或相位起点")
        if not math.isclose(frequency, process["frequency_Hz"]) or not math.isclose(duty, process["peak_duty_fraction"]):
            raise ValueError("瞬时信号脉冲频率/占空比与当前pWPS不一致")
        arc_steps = np.diff(timestamp)[arc[:-1] & arc[1:]]
        if arc_steps.size and np.max(arc_steps) * frequency > 1 / monitoring["current"]["minimum_samples_per_cycle"] + 1e-6:
            raise ValueError("瞬时脉冲采样不足每周期20点，应提供足够采样或明确周期平均值")
        cycle_ids = np.floor((timestamp - origin) * frequency + 1e-6).astype(int)
        peak = np.remainder((timestamp - origin) * frequency + 1e-9, 1.0) < duty
        tol = monitoring["current"]["plateau_tolerance_A"]
        bad = np.zeros(timestamp.size, dtype=bool)
        cycle_starts = np.r_[0, np.flatnonzero(np.diff(cycle_ids)) + 1]
        cycle_ends = np.r_[cycle_starts[1:], timestamp.size]
        for first, last in zip(cycle_starts, cycle_ends):
            cid = cycle_ids[first]
            active, peak_part = arc[first:last], peak[first:last]
            values = series["current"][first:last]
            high_values, low_values = values[active & peak_part], values[active & ~peak_part]
            begin, end = origin + cid / frequency, origin + (cid + 1) / frequency
            complete = (timestamp[first] <= begin + dt + 1e-8 and timestamp[last - 1] + dt >= end - 1e-8
                        and np.all(active))
            # 起停跨越周期时不判整周期；完整弧燃周期缺峰/谷采样则拒绝数据。
            if complete:
                minimum = monitoring["current"]["minimum_samples_per_cycle"]
                if high_values.size < math.floor(minimum * duty) or low_values.size < math.floor(minimum * (1 - duty)):
                    raise ValueError("完整弧燃周期缺少峰值或基值平台采样")
                fault = (abs(float(high_values.mean()) - process["peak_current_A"]) > tol
                         or abs(float(low_values.mean()) - process["base_current_A"]) > tol)
                bad[first:last] = fault
        minimum = max(min_duration_s, monitoring["current"]["minimum_bad_cycles"] / frequency)
        append("current", bad, process["base_current_A"] - tol, process["peak_current_A"] + tol, "A",
               minimum=minimum, event_type="pulse_plateau_out_of_window")
        calibration["current"].update({"definition": definition, "peak_nominal_A": process["peak_current_A"],
                                       "base_nominal_A": process["base_current_A"], "plateau_tolerance_A": tol,
                                       "minimum_consecutive_bad_cycles": monitoring["current"]["minimum_bad_cycles"]})

    lo, hi = monitoring["voltage_window_V"]
    speed, relative = process["travel_speed_mm_s"], monitoring["travel_speed_relative_tolerance"]
    feed, feed_tol = process["wire_feed_mm_s"], monitoring["wire_feed_tolerance_mm_s"]
    for name, low, high, unit in (("voltage", lo, hi, "V"), ("speed", speed * (1 - relative), speed * (1 + relative), "mm/s"),
                                ("wire_feed", feed - feed_tol, feed + feed_tol, "mm/s")):
        values = series[name]
        filtered = values if values.size < filter_window_samples * 2 else median_filter(values, size=filter_window_samples, mode="nearest")
        mask = arc_hysteresis(filtered, low, high, (high - low) * hysteresis_fraction)
        append(name, mask, low, high, unit)
    # 弧燃峰温不与层间温度混用；在起弧请求处立即禁止越界，不作50ms去抖。
    for gate, low, high in (("first_start", *process["start_temperature_C"]),
                            ("interpass_start", process["start_temperature_C"][0], process["interpass_limit_C"])):
        values = series["temperature"]
        mask = (phase == gate) & ((values < low) | (values > high))
        append("temperature", mask, low, high, "°C", minimum=0.0, event_type=f"{gate}_temperature_block")
    calibration["temperature"]["phase_gates"] = {"first_start": process["start_temperature_C"],
                                                  "interpass_start": [process["start_temperature_C"][0], process["interpass_limit_C"]]}
    segment_metrics = []
    if meta.get("record_scope") == "complete_final_weld_candidate_feedback":
        segment_metrics = evaluate_complete_segments(data, spec)
        for row in segment_metrics:
            if not row["energy_in_range"]:
                events.append({"signal": "net_energy", "type": "segment_net_energy_out_of_window", "start_s": row["start_s"],
                               "end_s": row["end_s"], "duration_s": row["arc_time_s"], "min": row["net_energy_J_mm"],
                               "max": row["net_energy_J_mm"], "window": row["energy_window_J_mm"], "unit": "J/mm"})
            if not row["path_in_range"]:
                events.append({"signal": "path_length", "type": "segment_path_length_out_of_window", "start_s": row["start_s"],
                               "end_s": row["end_s"], "duration_s": row["arc_time_s"], "min": row["actual_path_mm"],
                               "max": row["actual_path_mm"], "window": row["path_window_mm"], "unit": "mm"})
    events.sort(key=lambda e: (e["start_s"], e["signal"]))
    digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return {**identity, "detector_revision": "ring-fixed-window-v2", "scope": "current_ring_design_monitoring",
            "input_digest": digest, "event_count": len(events), "events": events,
            "min_duration_s": min_duration_s, "hysteresis_fraction": hysteresis_fraction,
            "filter_window_samples": filter_window_samples, "calibration": calibration,
            "segment_metrics": segment_metrics,
            "next_arc_permitted_by_monitor": not events,
            "statement": "当前圆环pWPS设计监测窗；固定阈值，峰/基值按周期独立评价，起弧温度门与弧燃温度分开。"}


def evaluate_complete_segments(data: dict, spec: dict | None = None) -> list[dict]:
    """同步左端采样积分：时间间隔由相邻时间戳给出，段末间隔精确截至实际段末。"""
    spec = spec or read_submission()
    if data.get("meta", {}).get("current_definition") != "instantaneous_pulsed_A":
        raise ValueError("完整段能量积分需要同步瞬时UI，不能以独立周期平均电流替代瞬时乘积")
    layout, process, monitoring = spec["weld_layout"], spec["final_GTAW"], spec["monitoring_design"]
    intervals = data.get("arc_intervals", [])
    expected = [(p, segment) for p in range(1, layout["pass_count"] + 1) for segment in layout["sequence"]]
    if [(row.get("pass_id"), row.get("segment_id")) for row in intervals] != expected:
        raise ValueError("整件候选反馈必须按当前圆环段序包含16段次")
    timestamp = np.asarray(data["timestamp"], dtype=float)
    phase = np.asarray(data["phase"])
    ids = {}
    for name in ("pass_id", "segment_id"):
        values = np.asarray(data.get(name, []), dtype=float)
        if values.shape != timestamp.shape or not np.all(np.isfinite(values)) or not np.all(values == np.round(values)):
            raise ValueError("整件反馈必须逐点保存整数pass_id与segment_id")
        ids[name] = values.astype(int)
    widths = np.r_[np.diff(timestamp), 0.0]
    current, voltage, speed, feed = (np.asarray(data[name], dtype=float) for name in ("current", "voltage", "speed", "wire_feed"))
    energy_target, energy_tol = process["nominal_net_energy_J_mm"], monitoring["segment_energy_relative_tolerance"]
    path_target, path_tol = layout["segment_length_mm"], monitoring["segment_path_relative_tolerance"]
    rows, previous_end, covered_arc = [], float(timestamp[0]), np.zeros(timestamp.size, dtype=bool)
    for index, item in enumerate(intervals):
        start, end = item.get("start_s"), item.get("end_s")
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, end)) or not previous_end <= start < end:
            raise ValueError("整件弧燃区间边界非法、逆序或重叠")
        mask = (timestamp >= start - 1e-8) & (timestamp < end - 1e-8) & (phase == "arc_on")
        before = (timestamp >= previous_end - 1e-8) & (timestamp < start - 1e-8)
        gate = "first_start" if index == 0 else "interpass_start"
        if not np.any(before) or not np.all(phase[before] == gate):
            raise ValueError("整件反馈缺少逐段起弧前检查阶段")
        for name, expected_id in (("pass_id", item["pass_id"]), ("segment_id", item["segment_id"])):
            if not np.all(ids[name][mask | before] == expected_id):
                raise ValueError("整件反馈逐点pass/segment身份与段区间不一致")
        if not np.any(mask) or abs(float(timestamp[mask][0]) - start) > 1e-8:
            raise ValueError("整件段反馈未从实际起弧边界开始采样")
        weights = np.minimum(widths[mask], end - timestamp[mask])
        if abs(float(weights.sum()) - (end - start)) > 1e-7:
            raise ValueError("整件段反馈时间覆盖不完整")
        length = float(np.sum(speed[mask] * weights))
        gross = float(np.sum(current[mask] * voltage[mask] * weights))
        net = gross * process["model_arc_efficiency"]
        if length <= 0 or not math.isfinite(length):
            raise ValueError("整件段反馈实际速度路径必须为正")
        q = net / length
        energy_window = [energy_target * (1 - energy_tol), energy_target * (1 + energy_tol)]
        path_window = [path_target * (1 - path_tol), path_target * (1 + path_tol)]
        feed_min, feed_max = float(feed[mask].min()), float(feed[mask].max())
        feed_tol = monitoring["wire_feed_tolerance_mm_s"]
        rows.append({"pass_id": item["pass_id"], "segment_id": item["segment_id"], "start_s": start, "end_s": end,
                     "arc_time_s": end - start, "actual_path_mm": length, "gross_arc_energy_J": gross,
                     "net_arc_energy_J": net, "net_energy_J_mm": q, "energy_window_J_mm": energy_window,
                     "path_window_mm": path_window, "energy_in_range": energy_window[0] <= q <= energy_window[1],
                     "path_in_range": path_window[0] <= length <= path_window[1],
                     "wire_feed_min_mm_s": feed_min, "wire_feed_max_mm_s": feed_max,
                     "wire_feed_in_range": process["wire_feed_mm_s"] - feed_tol <= feed_min <= feed_max <= process["wire_feed_mm_s"] + feed_tol})
        previous_end = end
        covered_arc |= mask
    if not np.array_equal(covered_arc, phase == "arc_on"):
        raise ValueError("整件反馈存在段区间以外的弧燃样本")
    return rows


def detect(data: dict[str, object], min_duration_s: float = DEFAULT_MIN_DURATION_S,
           hysteresis_fraction: float = DEFAULT_HYSTERESIS_FRACTION, filter_window_samples: int = 5) -> dict[str, object]:
    if min_duration_s < 0 or not 0 <= hysteresis_fraction < .5 or filter_window_samples < 1 or filter_window_samples % 2 == 0:
        raise ValueError("检测持续时间、滞回或滤波窗口非法")
    meta = data.get("meta", {})
    if isinstance(meta, dict) and "process_version" in meta:
        return _current_ring_detection(data, min_duration_s, hysteresis_fraction, filter_window_samples)
    return _detect_historical(data, min_duration_s, hysteresis_fraction, filter_window_samples)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    result = detect(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
