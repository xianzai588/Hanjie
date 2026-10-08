"""生成当前圆环pWPS的合成波形和起弧检查片段，明确 simulated 来源。"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from hanjie.domain.submission import read_submission

DEFAULT_OUTPUT = ROOT / "automation/anomaly-detection/results/W2026-001-signals.json"


def simulate_trial(trial_id: str, injected: bool, seed: int, duration_s: float = 20.0, sample_rate_hz: float = 400.0,
                   noise_scale: float = 1.0, current_bias: float = 0.0,
                   anomaly_duration_s: float | None = None,
                   anomaly_names: tuple[str, ...] | None = None) -> dict[str, object]:
    spec = read_submission()
    process, monitoring = spec["final_GTAW"], spec["monitoring_design"]
    if duration_s <= .1 or sample_rate_hz < process["frequency_Hz"] * monitoring["current"]["minimum_samples_per_cycle"]:
        raise ValueError("瞬时脉冲信号至少每周期20点，且片段长度大于0.1s")
    if noise_scale < 0 or not np.isfinite(noise_scale) or not np.isfinite(current_bias):
        raise ValueError("噪声/电流偏移输入非法")
    rng = np.random.default_rng(seed)
    timestamp = np.arange(0.0, duration_s, 1.0 / sample_rate_hz)
    pulse = np.remainder(timestamp * process["frequency_Hz"] + 1e-9, 1.0) < process["peak_duty_fraction"]
    current = np.where(pulse, process["peak_current_A"], process["base_current_A"]) + current_bias + rng.normal(0, .5 * noise_scale, timestamp.size)
    voltage = process["reference_voltage_V"] + rng.normal(0, .08 * noise_scale, timestamp.size)
    speed = process["travel_speed_mm_s"] + rng.normal(0, .002 * noise_scale, timestamp.size)
    wire_feed = process["wire_feed_mm_s"] + rng.normal(0, .003 * noise_scale, timestamp.size)
    temperature = 25.0 + 55 * (1 - np.exp(-timestamp / 8)) + rng.normal(0, .2 * noise_scale, timestamp.size)
    phase = np.full(timestamp.size, "arc_on", dtype=object)
    first_start = timestamp < .05
    phase[first_start] = "first_start"
    temperature[first_start] = 25.0
    current[first_start] = voltage[first_start] = speed[first_start] = wire_feed[first_start] = 0.0
    anomalies: list[dict[str, object]] = []

    def inject(name: str, signal: str, start: float, end: float, value: float) -> None:
        mask = (timestamp >= start) & (timestamp < end)
        if not np.any(mask):
            return
        if signal == "temperature":
            phase[mask] = "interpass_start"
            current[mask] = voltage[mask] = speed[mask] = wire_feed[mask] = 0.0
        {"current": current, "voltage": voltage, "speed": speed, "temperature": temperature}[signal][mask] = value
        anomalies.append({"name": name, "signal": signal, "start_s": start, "end_s": min(end, duration_s)})

    if injected:
        names = ("current_drop", "voltage_spike", "speed_deviation", "temperature_overrun", "arc_interruption")
        selected = list(anomaly_names) if anomaly_names is not None else list(rng.choice(names, size=int(rng.integers(1, 4)), replace=False))
        for index, name in enumerate(selected):
            start = 3.0 + 4.5 * index
            end = start + (anomaly_duration_s if anomaly_duration_s is not None else .8)
            if name == "current_drop":
                inject(name, "current", start, end, 35.0)
            elif name == "voltage_spike":
                inject(name, "voltage", start, end, 16.2)
            elif name == "speed_deviation":
                inject(name, "speed", start, end, 1.95)
            elif name == "temperature_overrun":
                inject(name, "temperature", start, end, 150.0)
            elif name == "arc_interruption":
                inject(name, "current", start, end, 0.0)
                inject(name, "voltage", start, end, 0.0)
            else:
                raise ValueError(f"未知注入异常: {name}")

    return {
        "sample_id": trial_id, "timestamp": np.round(timestamp, 6).tolist(),
        "current": np.round(current, 4).tolist(), "voltage": np.round(voltage, 4).tolist(),
        "speed": np.round(speed, 4).tolist(), "temperature": np.round(temperature, 4).tolist(),
        "wire_feed": np.round(wire_feed, 4).tolist(),
        "phase": phase.tolist(),
        "meta": {
            "session_id": f"{trial_id}-{spec['version']}-PULSE-FEED-V2-SIM-{seed}", "process_version": spec["version"],
            "record_scope": "monitoring_fragment",
            "operation": "final_GTAW", "process": "pulsed-GTAW-design-pWPS",
            "sequence": "S3", "sequence_segment_ids": spec["weld_layout"]["sequence"],
            "source_type": "simulated", "current_definition": "instantaneous_pulsed_A",
            "temperature_definition": monitoring["temperature_definition"],
            "pulse_frequency_Hz": process["frequency_Hz"], "pulse_peak_duty_fraction": process["peak_duty_fraction"],
            "pulse_phase_origin_s": 0.0, "operator": "simulation", "preheat_c": 25.0,
            "injected": injected, "injected_anomalies": anomalies,
            "notes": "合成波形与起弧检查片段；片段时长不是整件制造节拍，未连接焊机。",
        },
    }


def simulate(duration_s: float = 20.0, sample_rate_hz: float = 400.0, seed: int = 20260902) -> dict[str, object]:
    return simulate_trial("W2026-001", True, seed, duration_s, sample_rate_hz,
                          anomaly_names=("current_drop", "voltage_spike", "speed_deviation", "temperature_overrun"))


def simulate_complete_weld(trial_id: str = "RING-FULL-NORMAL", *, fault: str | None = None,
                           fault_segment_index: int = 3, sample_rate_hz: float = 400.0) -> dict:
    """整件16段次候选反馈，仅在内存保存；控制器许可后才消费该段合成反馈。"""
    if fault not in {None, "energy", "speed", "wire_feed", "temperature"} or not 0 <= fault_segment_index < 16:
        raise ValueError("整件合成故障类型/段次非法")
    base = simulate_trial(trial_id, False, 20261008, duration_s=.2, sample_rate_hz=sample_rate_hz, noise_scale=0)
    spec = read_submission()
    process, layout = spec["final_GTAW"], spec["weld_layout"]
    dt = 1 / sample_rate_hz
    duration = layout["segment_length_mm"] / process["travel_speed_mm_s"]
    series = {key: [] for key in ("timestamp", "current", "voltage", "speed", "wire_feed", "temperature", "phase", "pass_id", "segment_id")}
    intervals, clock = [], 0.0
    commands = [(p, sid) for p in range(1, layout["pass_count"] + 1) for sid in layout["sequence"]]

    def append_block(times, phase_name, pass_id, segment_id, *, arc=False, index=0):
        n = times.size
        peak = np.remainder(times * process["frequency_Hz"] + 1e-9, 1.0) < process["peak_duty_fraction"]
        current = np.where(peak, process["peak_current_A"], process["base_current_A"]) if arc else np.zeros(n)
        voltage = np.full(n, process["reference_voltage_V"] if arc else 0.0)
        speed = np.full(n, process["travel_speed_mm_s"] if arc else 0.0)
        feed = np.full(n, process["wire_feed_mm_s"] if arc else 0.0)
        temperature = np.full(n, 25.0 if index == 0 else 85.0)
        if index == fault_segment_index:
            if arc and fault == "energy":
                voltage[:] = 12.6  # 在弧压设计窗内，仍使逐段净能量超过+2%。
            if arc and fault == "speed":
                speed[:] = 1.95
            if arc and fault == "wire_feed":
                feed[:] = 4.0
            if not arc and fault == "temperature":
                temperature[:] = 150.0
        for key, values in (("timestamp", times), ("current", current), ("voltage", voltage), ("speed", speed),
                            ("wire_feed", feed), ("temperature", temperature),
                            ("phase", np.full(n, phase_name)), ("pass_id", np.full(n, pass_id)), ("segment_id", np.full(n, segment_id))):
            series[key].append(values)

    for index, (pass_id, segment_id) in enumerate(commands):
        check_duration = .05
        pre = clock + np.arange(math.ceil(check_duration / dt)) * dt
        append_block(pre[pre < clock + check_duration], "first_start" if index == 0 else "interpass_start", pass_id, segment_id, index=index)
        start = clock + check_duration
        end = start + duration
        times = start + np.arange(math.ceil(duration / dt)) * dt
        append_block(times[times < end], "arc_on", pass_id, segment_id, arc=True, index=index)
        intervals.append({"pass_id": pass_id, "segment_id": segment_id, "start_s": start, "end_s": end,
                          "nominal_length_mm": layout["segment_length_mm"], "nominal_duration_s": duration})
        clock = end
    append_block(np.array([clock, clock + .05]), "cooling", 2, commands[-1][1], index=16)
    for key in series:
        values = np.concatenate(series[key])
        base[key] = values.tolist() if key in {"phase", "pass_id", "segment_id"} else np.round(values, 9).tolist()
    base["arc_intervals"] = intervals
    base["meta"].update({"record_scope": "complete_final_weld_candidate_feedback",
                          "session_id": f"{trial_id}-{spec['version']}-FULL-{fault or 'normal'}-{fault_segment_index}",
                          "fault": fault, "fault_segment_index": fault_segment_index,
                          "notes": "整件16段次合成候选反馈；每段20/1.65秒弧燃，0.05秒起弧检查，25/85℃为指定合成测点输入；未许可段不计实际执行，无设备通信。"})
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(simulate(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成当前圆环合成信号: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
