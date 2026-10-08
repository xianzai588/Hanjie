"""当前参赛圆环基准读取与自动化输入检查，无 CAD/求解器依赖。"""
from __future__ import annotations

import math
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "project/submission-baseline.yaml"


def read_submission(path: Path = SPEC) -> dict:
    """每次读取当前工艺版本，拒绝长度、顺序或能量互相矛盾的基准。"""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not str(data.get("version", "")).startswith("SUBMISSION-RING-"):
        raise ValueError("缺少当前圆环参赛版本身份")
    layout, process = data["weld_layout"], data["final_GTAW"]
    count, passes = layout["segment_count"], layout["pass_count"]
    if count != 8 or passes != 2 or layout["sequence"] != [1, 5, 3, 7, 2, 6, 4, 8]:
        raise ValueError("当前完整圆环须采用八段两道与规定的对称顺序")
    length = float(layout["segment_length_mm"])
    effective = float(layout["effective_segment_length_mm"])
    if not math.isclose(length, effective + layout["start_allowance_mm"] + layout["end_allowance_mm"]):
        raise ValueError("实际路径长度与有效连接及起止余量不一致")
    expected_length = count * length * passes
    if not math.isclose(layout["total_arc_length_mm"], expected_length):
        raise ValueError("焊接总路径与段长/道数不一致")
    current = process["peak_current_A"] * process["peak_duty_fraction"] + process["base_current_A"] * (1 - process["peak_duty_fraction"])
    energy = current * process["reference_voltage_V"] * process["model_arc_efficiency"] / process["travel_speed_mm_s"]
    if not math.isclose(energy, process["nominal_net_energy_J_mm"], rel_tol=1e-6):
        raise ValueError("脉冲平均电流与净线能量不一致")
    if not math.isclose(process["net_energy_kJ"] * 1000, energy * expected_length, rel_tol=1e-6):
        raise ValueError("总净热未按实际焊接路径计算")
    monitoring = data.get("monitoring_design", {})
    if monitoring.get("operation") != "final_GTAW" or not 0 < monitoring.get("travel_speed_relative_tolerance", 0) < 0.1:
        raise ValueError("缺少当前最终组焊的监测设计窗口")
    return data


def session_identity(data: dict, spec: dict | None = None) -> dict:
    """当前信号身份：允许合成/实采标识，禁止缺失版本和混用工序。"""
    spec = spec or read_submission()
    meta = data.get("meta", {})
    sample_id = data.get("sample_id")
    session_id = meta.get("session_id")
    if not isinstance(sample_id, str) or not sample_id.strip() or not isinstance(session_id, str) or not session_id.strip():
        raise ValueError("信号必须包含工件编号与焊接会话编号")
    if meta.get("process_version") != spec["version"] or meta.get("operation") != "final_GTAW":
        raise ValueError("信号工艺版本/工序与当前圆环基准不一致")
    if meta.get("source_type") not in {"simulated", "physical"}:
        raise ValueError("必须明确 simulated 或 physical 来源")
    if meta.get("sequence_segment_ids") != spec["weld_layout"]["sequence"]:
        raise ValueError("信号焊序与当前圆环基准不一致")
    if meta.get("current_definition") not in spec["monitoring_design"]["current"]["supported_definitions"]:
        raise ValueError("未定义电流是瞬时脉冲值还是周期平均值")
    if meta.get("temperature_definition") != spec["monitoring_design"]["temperature_definition"]:
        raise ValueError("温度必须明确为起弧前控制点读数")
    return {"sample_id": sample_id, "session_id": session_id,
            "process_version": meta["process_version"], "operation": meta["operation"],
            "source_type": meta["source_type"]}


def ring_cycle_permission(stage: str, readings: dict, spec: dict | None = None) -> bool:
    """现有工作站联锁与当前圆环温控门共同决定能否发出起弧请求。"""
    if stage not in {"first_weld", "weld"}:
        raise ValueError("本入口只处理首段起弧/续焊起弧")
    spec = spec or read_submission()
    process = spec["final_GTAW"]
    boolean_feedback = ("shield_present", "bottom_open", "fixture_locked", "path_checked", "water_leak_free", "guard_closed")
    if any(readings.get(name) is not True for name in boolean_feedback):
        return False
    low, high = process["start_temperature_C"] if stage == "first_weld" else (process["start_temperature_C"][0], process["interpass_limit_C"])
    tmin, tmax = readings.get("temperature_min"), readings.get("temperature_max")
    gas = readings.get("gas_flow_l_min")
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (tmin, tmax, gas)):
        return False
    if not (low <= tmin <= tmax <= high and process["shielding_flow_L_min"][0] <= gas <= process["shielding_flow_L_min"][1]):
        return False
    from hanjie.domain.competition_design import cycle_permission
    return cycle_permission(stage, **readings)
