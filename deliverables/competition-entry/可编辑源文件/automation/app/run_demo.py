"""运行一次端到端数字样机 Demo：视觉定位、路径规划、信号检测、追溯。"""

from __future__ import annotations

import json
import argparse
import subprocess
import sys
from pathlib import Path
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "automation/anomaly-detection"))
from hanjie.domain.submission import read_submission, ring_cycle_permission, session_identity
from anomaly_detector import detect
from signal_simulator import simulate_complete_weld


def synthetic_interlock_readings(temperature: float, *, monitor_ok: bool = True) -> dict:
    """合成输入，覆盖既有联锁需要的全部字段；不连接任何设备。"""
    return {"shield_present": True, "bottom_open": True, "fixture_locked": True, "path_checked": True,
            "temperature_min": temperature, "temperature_max": temperature, "gas_flow_l_min": 10.0,
            "curtain_flow_l_min": 12.0, "curtain_manifold_pressure_pa": 1000.0,
            "copper_temperature_c": 25.0, "lower_ring_temperature_c": 25.0, "seal_band_temperature_c": 25.0,
            "coolant_flow_l_min": .608, "coolant_branch_flows_l_min": [.076] * 8,
            "water_leak_free": True, "energy_in_range": monitor_ok, "guard_closed": True}


def execute_virtual_plan(path: dict, signals: dict, detection: dict) -> dict:
    """联锁允许才产生虚拟起弧请求；任一异常锁存后禁止后续请求。"""
    spec = read_submission()
    identity = session_identity(signals, spec)
    if identity["source_type"] != "simulated":
        raise ValueError("纯合成演示入口只接受simulated，不能用合成联锁替代physical反馈")
    if path.get("process_version") != identity["process_version"] or any(detection.get(k) != v for k, v in identity.items()):
        raise ValueError("路径、信号与检测结果工艺身份不一致")
    expected_order = [(p, segment) for p in (1, 2) for segment in spec["weld_layout"]["sequence"]]
    if [(item.get("pass_id"), item.get("segment_id")) for item in path.get("arc_commands", [])] != expected_order:
        raise ValueError("虚拟计划段序/道数与当前圆环基准不一致")
    if detection != detect(signals):
        raise ValueError("虚拟计划拒绝未绑定原始信号的异常结果")
    first = np.asarray(signals["phase"]) == "first_start"
    if not np.any(first):
        raise ValueError("缺少首段起弧检查，不能运行虚拟计划")
    temperature = float(np.max(np.asarray(signals["temperature"])[first]))
    fault_latched = False
    decisions, emitted = [], []
    for index, command in enumerate(path["arc_commands"]):
        stage = "first_weld" if index == 0 else "weld"
        readings = synthetic_interlock_readings(temperature, monitor_ok=not fault_latched)
        permitted = ring_cycle_permission(stage, readings, spec)
        decisions.append({**command, "stage": stage, "temperature_C": temperature,
                          "permitted": permitted, "monitor_fault_latched": fault_latched,
                          "action": "emit_virtual_arc_request" if permitted else "suppress_arc_request"})
        if permitted:
            emitted.append({"pass_id": command["pass_id"], "segment_id": command["segment_id"]})
            # 合成首段反馈存在异常时，由该反馈锁存故障；不以“Demo完成”继续发弧。
            fault_latched = detection["event_count"] > 0
        else:
            # 首弧被拒绝时同样停止计划，不自动改温度后跳到下一段。
            fault_latched = True
        temperature = 85.0
    return {"source_type": "simulated", "hardware_commands_sent": 0,
            "planned_arc_count": len(path["arc_commands"]), "virtual_requests_emitted": emitted,
            "suppressed_request_count": sum(not item["permitted"] for item in decisions),
            "decisions": decisions,
            "temperature_gate_examples": {
                "first_25C": ring_cycle_permission("first_weld", synthetic_interlock_readings(25), spec),
                "interpass_85C": ring_cycle_permission("weld", synthetic_interlock_readings(85), spec),
                "interpass_150C": ring_cycle_permission("weld", synthetic_interlock_readings(150), spec)},
            "statement": "合成控制回放：联锁实际决定虚拟请求是否产生，异常反馈锁存后停止后续起弧；无设备通信。"}


def execute_complete_virtual_plan(path: dict, signals: dict, detection: dict) -> dict:
    """逐段消费合成候选反馈，实际积分得到的上一段能量决定下一段起弧。"""
    spec = read_submission()
    identity = session_identity(signals, spec)
    if identity["source_type"] != "simulated":
        raise ValueError("纯合成演示入口只接受simulated，不能用合成联锁替代physical反馈")
    if path.get("process_version") != identity["process_version"] or detection != detect(signals):
        raise ValueError("整件虚拟计划的路径/检测未绑定当前原始信号")
    metrics = detection["segment_metrics"]
    commands = path["arc_commands"]
    if not metrics or [(r["pass_id"], r["segment_id"]) for r in metrics] != [(c["pass_id"], c["segment_id"]) for c in commands]:
        raise ValueError("整件虚拟计划的反馈段身份与执行计划不一致")
    timestamp, phase, temperature = (np.asarray(signals[k]) for k in ("timestamp", "phase", "temperature"))
    previous_end, previous_energy_ok, fault_latched = float(timestamp[0]), True, False
    decisions, emitted, consumed = [], [], []
    for index, (command, row) in enumerate(zip(commands, metrics)):
        before = (timestamp >= previous_end - 1e-8) & (timestamp < row["start_s"] - 1e-8)
        gate = "first_start" if index == 0 else "interpass_start"
        if not np.any(before) or not np.all(phase[before] == gate):
            raise ValueError("虚拟计划缺少本段起弧前检查")
        readings = synthetic_interlock_readings(float(np.max(temperature[before])), monitor_ok=previous_energy_ok)
        readings["temperature_min"] = float(np.min(temperature[before]))
        stage = "first_weld" if index == 0 else "weld"
        allowed = ring_cycle_permission(stage, readings, spec) and not fault_latched
        decision = {"pass_id": command["pass_id"], "segment_id": command["segment_id"], "stage": stage,
                    "temperature_before_arc_C": readings["temperature_max"], "previous_segment_energy_in_range": previous_energy_ok,
                    "monitor_fault_latched_before_request": fault_latched, "permitted": allowed,
                    "action": "emit_virtual_arc_request" if allowed else "suppress_arc_request", "feedback_consumed": False}
        if allowed:
            emitted.append({"pass_id": command["pass_id"], "segment_id": command["segment_id"]})
            consumed.append(row)
            arc_events = [e for e in detection["events"] if e["start_s"] < row["end_s"] - 1e-8 and e["end_s"] > row["start_s"] + 1e-8]
            feedback_ok = row["energy_in_range"] and row["path_in_range"] and row["wire_feed_in_range"] and not arc_events
            previous_energy_ok = row["energy_in_range"]
            fault_latched = not feedback_ok
            decision.update({"feedback_consumed": True, "segment_net_energy_J_mm": row["net_energy_J_mm"],
                             "energy_in_range": row["energy_in_range"], "wire_feed_in_range": row["wire_feed_in_range"],
                             "path_in_range": row["path_in_range"], "feedback_in_range": feedback_ok})
        else:
            fault_latched = True
        decisions.append(decision)
        previous_end = row["end_s"]
    return {**identity, "record_scope": "complete_final_weld_simulated_control_replay", "hardware_commands_sent": 0,
            "candidate_arc_count": len(metrics), "candidate_arc_time_s": sum(r["arc_time_s"] for r in metrics),
            "candidate_path_mm": sum(r["actual_path_mm"] for r in metrics),
            "candidate_net_heat_J": sum(r["net_arc_energy_J"] for r in metrics),
            "candidate_segment_metrics": metrics, "virtual_requests_emitted": emitted,
            "feedback_consumed_arc_count": len(consumed), "suppressed_request_count": sum(not d["permitted"] for d in decisions),
            "consumed_virtual_arc_time_s": sum(r["arc_time_s"] for r in consumed),
            "consumed_virtual_net_heat_J": sum(r["net_arc_energy_J"] for r in consumed), "decisions": decisions,
            "statement": "16段次候选反馈均为合成输入；同步UI和速度积分评价逐段能量/路径，许可后才消费反馈，异常锁存后停止请求。未许可段的候选波形不计执行；无真实设备日志。"}


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000, help="视觉数字样本数量")
    args = parser.parse_args()
    python = sys.executable
    run([python, "automation/vision/run_benchmark.py", "--count", str(args.count)])
    run([python, "automation/path-planning/generate_weld_path.py"])
    run([python, "automation/anomaly-detection/signal_simulator.py"])
    run([python, "automation/anomaly-detection/anomaly_detector.py"])
    run([python, "automation/traceability/database.py"])
    vision_summary = json.loads((ROOT / "automation/vision/results/summary.json").read_text(encoding="utf-8"))
    anomaly_summary = json.loads((ROOT / "automation/anomaly-detection/results/W2026-001-anomalies.json").read_text(encoding="utf-8"))
    path = json.loads((ROOT / "automation/path-planning/results/weld-path.json").read_text(encoding="utf-8"))
    signals = json.loads((ROOT / "automation/anomaly-detection/results/W2026-001-signals.json").read_text(encoding="utf-8"))
    demo = {
        "process_version": read_submission()["version"],
        "source_type": "simulated",
        "vision": vision_summary,
        "path": "automation/path-planning/results/weld-path.json",
        "anomaly_event_count": anomaly_summary["event_count"],
        "traceability_db": "automation/traceability/results/traceability.db",
        "interlocked_virtual_plan": execute_virtual_plan(path, signals, anomaly_summary),
        "statement": "端到端结果包含数字样本和仿真过程信号，不代表实物焊接采集。",
    }
    full_replays = {}
    for scenario, fault in (("normal", None), ("energy_offset", "energy"), ("wire_feed_offset", "wire_feed")):
        full_signals = simulate_complete_weld(f"RING-FULL-{scenario}", fault=fault)
        full_replays[scenario] = execute_complete_virtual_plan(path, full_signals, detect(full_signals))
    replay_output = ROOT / "automation/app/results/complete-weld-replay-summary.json"
    replay_output.parent.mkdir(parents=True, exist_ok=True)
    replay_output.write_text(json.dumps(full_replays, ensure_ascii=False, indent=2), encoding="utf-8")
    demo["complete_weld_replay_summary"] = str(replay_output.relative_to(ROOT))
    demo["complete_weld_scenarios"] = {name: {"feedback_consumed_arc_count": value["feedback_consumed_arc_count"],
                                            "suppressed_request_count": value["suppressed_request_count"],
                                            "hardware_commands_sent": 0} for name, value in full_replays.items()}
    output = ROOT / "automation/app/results/demo-summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(demo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"数字样机 Demo 完成: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
