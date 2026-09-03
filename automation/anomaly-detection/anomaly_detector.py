"""用工艺窗口与连续采样规则识别仿真过程异常。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import median_filter


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "samples" / "W2026-001-simulated.json"
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
    """按信号和时间重叠匹配注入事件，输出事件级 TP/FP/FN 与检测延迟。"""
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


def detect(data: dict[str, object], min_duration_s: float = DEFAULT_MIN_DURATION_S,
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
        "event_count": len(events),
        "events": events,
        "min_duration_s": min_duration_s,
        "hysteresis_fraction": hysteresis_fraction,
        "filter_window_samples": filter_window_samples,
        "calibration": calibration,
        "statement": "基于信号窗口、在线偏置估计、滞回和最小持续时间的规则检测结果；参数需由真实设备与工艺评定标定。",
    }


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
