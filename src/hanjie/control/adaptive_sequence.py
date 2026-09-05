"""温度状态驱动的受约束在线自适应跳焊控制引擎 (创新点 B)。

区别于固定的 S1/S2/S3 焊序，本算法实时获取各段当前温度场反馈，
在满足道温上限 (T < 200°C) 与邻段热阻隔门限的前提下，
通过多目标加权在线决策选取下一最佳施焊段，
动态平衡周向温度梯度并维持几何热对称性。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


@dataclass
class WeldingSegmentState:
    segment_id: int
    angle_deg: float
    is_welded: bool = False
    current_temp_c: float = 150.0  # 初始预热 150°C
    heat_input_j: float = 0.0


@dataclass
class SequenceDecisionStep:
    step_index: int
    selected_segment_id: int
    waiting_time_s: float
    temp_before_c: float
    temp_after_c: float
    max_circumferential_delta_t_c: float
    predicted_position_p_mm: float
    thermal_asymmetry_metric: float


@dataclass
class AdaptiveSequenceResult:
    strategy_name: str
    execution_order: List[int]
    total_cycle_time_s: float
    final_position_p_mm: float
    max_delta_t_observed_c: float
    steps: List[SequenceDecisionStep]
    cooling_waiting_time_total_s: float
    evidence_level: str = "surrogate_result"
    plant_model: str = "shared_segment_thermal_v1"
    position_predictor: str = "shared_surrogate_position_v1"
    evaluation_model: str = "shared_thermal_position_v1"
    initial_perturbation_c: Tuple[float, ...] = ()


class AdaptiveSequenceController:
    PLANT_MODEL = "shared_segment_thermal_v1"
    POSITION_PREDICTOR = "shared_surrogate_position_v1"
    EVALUATION_MODEL = "shared_thermal_position_v1"

    def __init__(
        self,
        num_segments: int = 6,
        preheat_c: float = 150.0,
        interpass_gate_c: float = 200.0,
        w_position: float = 0.40,
        w_delta_t: float = 0.30,
        w_heat: float = 0.15,
        w_wait: float = 0.15,
        cooling_rate_per_s: float = 0.045,
    ) -> None:
        self.num_segments = num_segments
        self.preheat_c = preheat_c
        self.interpass_gate_c = interpass_gate_c
        self.weights = (w_position, w_delta_t, w_heat, w_wait)
        self.cooling_rate = cooling_rate_per_s
        if num_segments < 3 or interpass_gate_c <= 20 or cooling_rate_per_s <= 0:
            raise ValueError("焊段数须至少为 3，道温门限须高于环境温度，冷却率须为正")

    @staticmethod
    def _predict_position(delta_t: float, asymmetry: float) -> float:
        """统一代理评价函数，策略名称不得改变评价系数；尚未经物理校准。"""
        return 0.015 + 0.00015 * delta_t + 0.028 * asymmetry

    def _init_segments(self, initial_temp_perturbation: Optional[np.ndarray] = None) -> List[WeldingSegmentState]:
        if initial_temp_perturbation is not None:
            initial_temp_perturbation = np.asarray(initial_temp_perturbation, dtype=float)
            if initial_temp_perturbation.shape != (self.num_segments,) or not np.all(np.isfinite(initial_temp_perturbation)):
                raise ValueError("初始温度扰动须为每段一个有限数值")
        segments = []
        for i in range(self.num_segments):
            angle = (360.0 / self.num_segments) * i
            t0 = self.preheat_c
            if initial_temp_perturbation is not None:
                t0 += float(initial_temp_perturbation[i])
            segments.append(WeldingSegmentState(segment_id=i + 1, angle_deg=angle, current_temp_c=t0))
        return segments

    def _update_temperatures(
        self,
        segments: List[WeldingSegmentState],
        active_id: int,
        weld_duration_s: float = 12.0,
        wait_s: float = 0.0,
    ) -> None:
        """更新传热与冷却过程中的各段温度。"""
        dt_total = weld_duration_s + wait_s
        for seg in segments:
            # 自然对流冷却
            seg.current_temp_c = 20.0 + (seg.current_temp_c - 20.0) * math.exp(-self.cooling_rate * dt_total)

        # 施焊段注入热量，局部升高约 280°C
        active_seg = segments[active_id - 1]
        active_seg.current_temp_c += 280.0
        active_seg.heat_input_j += 5940.0  # 495 W * 12s

        # 热传导至相邻段
        left_id = (active_id - 2) % self.num_segments
        right_id = active_id % self.num_segments
        segments[left_id].current_temp_c += 45.0
        segments[right_id].current_temp_c += 45.0

    def _calculate_thermal_asymmetry(self, segments: List[WeldingSegmentState]) -> float:
        """计算当前热力学质心相对于中心轴的偏离矢量模长。"""
        x_cm = 0.0
        y_cm = 0.0
        total_delta_t = 0.0
        for seg in segments:
            rad = math.radians(seg.angle_deg)
            dt = max(0.0, seg.current_temp_c - self.preheat_c)
            x_cm += dt * math.cos(rad)
            y_cm += dt * math.sin(rad)
            total_delta_t += dt
        if total_delta_t < 1e-4:
            return 0.0
        return math.sqrt(x_cm ** 2 + y_cm ** 2) / total_delta_t

    def solve_adaptive_sequence(
        self,
        initial_perturbation: Optional[np.ndarray] = None,
    ) -> AdaptiveSequenceResult:
        """执行闭环温度门控自适应决策流程。"""
        segments = self._init_segments(initial_perturbation)
        steps = []
        welded_ids = []
        total_time = 0.0
        total_wait = 0.0

        for step in range(self.num_segments):
            candidates = [s for s in segments if not s.is_welded]
            best_cand = None
            best_score = float("inf")
            best_wait = 0.0

            for cand in candidates:
                # 检查道温约束：若候选段当前温度 >= interpass_gate_c，则需要等待降温
                wait_needed = 0.0
                if cand.current_temp_c > self.interpass_gate_c:
                    # 计算降温至门限所需时间
                    dt_cool = -math.log((self.interpass_gate_c - 20.0) / (cand.current_temp_c - 20.0)) / self.cooling_rate
                    wait_needed = max(0.0, dt_cool)

                # 预测施焊后的热质心不对称度
                sim_segs = [WeldingSegmentState(s.segment_id, s.angle_deg, s.is_welded, s.current_temp_c) for s in segments]
                # 虚拟试算
                self._update_temperatures(sim_segs, cand.segment_id, wait_s=wait_needed)
                asym = self._calculate_thermal_asymmetry(sim_segs)

                # 周向温差
                temps = [s.current_temp_c for s in sim_segs]
                delta_t = max(temps) - min(temps)

                # 预测位置度贡献
                pred_p = self._predict_position(delta_t, asym)

                # 多目标评分函数: S = w1*P + w2*ΔT + w3*Q + w4*wait
                score = (
                    self.weights[0] * (pred_p / 0.05)
                    + self.weights[1] * (delta_t / 100.0)
                    + self.weights[2] * (cand.heat_input_j / 10000.0)
                    + self.weights[3] * (wait_needed / 30.0)
                )

                if score < best_score:
                    best_score = score
                    best_cand = cand
                    best_wait = wait_needed

            assert best_cand is not None
            # 执行施焊
            t_before = 20.0 + (best_cand.current_temp_c - 20.0) * math.exp(-self.cooling_rate * best_wait)
            self._update_temperatures(segments, best_cand.segment_id, weld_duration_s=12.0, wait_s=best_wait)
            t_after = best_cand.current_temp_c
            best_cand.is_welded = True
            welded_ids.append(best_cand.segment_id)

            temps = [s.current_temp_c for s in segments]
            delta_t_now = max(temps) - min(temps)
            asym_now = self._calculate_thermal_asymmetry(segments)
            p_step = self._predict_position(delta_t_now, asym_now)

            steps.append(SequenceDecisionStep(
                step_index=step + 1,
                selected_segment_id=best_cand.segment_id,
                waiting_time_s=best_wait,
                temp_before_c=t_before,
                temp_after_c=t_after,
                max_circumferential_delta_t_c=delta_t_now,
                predicted_position_p_mm=p_step,
                thermal_asymmetry_metric=asym_now,
            ))
            total_time += 12.0 + best_wait
            total_wait += best_wait

        final_delta_t = max(s.max_circumferential_delta_t_c for s in steps)
        final_p = steps[-1].predicted_position_p_mm

        return AdaptiveSequenceResult(
            strategy_name="ADAPTIVE-TEMPERATURE-DRIVEN",
            execution_order=welded_ids,
            total_cycle_time_s=total_time,
            final_position_p_mm=final_p,
            max_delta_t_observed_c=final_delta_t,
            steps=steps,
            cooling_waiting_time_total_s=total_wait,
            plant_model=self.PLANT_MODEL,
            position_predictor=self.POSITION_PREDICTOR,
            evaluation_model=self.EVALUATION_MODEL,
            initial_perturbation_c=tuple(
                np.asarray(initial_perturbation, dtype=float).tolist()
                if initial_perturbation is not None else []
            ),
        )

    def evaluate_fixed_sequence(self, sequence_name: str, order: List[int], initial_perturbation: Optional[np.ndarray] = None) -> AdaptiveSequenceResult:
        """评估固定时序方案 (S1, S2, S3) 以形成对照基线。"""
        if sorted(order) != list(range(1, self.num_segments + 1)):
            raise ValueError("固定焊序必须恰好包含每个焊段一次")
        segments = self._init_segments(initial_perturbation)
        steps = []
        total_time = 0.0
        total_wait = 0.0

        for step, seg_id in enumerate(order):
            target = segments[seg_id - 1]
            wait_needed = 0.0
            if target.current_temp_c > self.interpass_gate_c:
                wait_needed = max(0.0, -math.log((self.interpass_gate_c - 20.0) / (target.current_temp_c - 20.0)) / self.cooling_rate)

            t_before = 20.0 + (target.current_temp_c - 20.0) * math.exp(-self.cooling_rate * wait_needed)
            self._update_temperatures(segments, target.segment_id, weld_duration_s=12.0, wait_s=wait_needed)
            t_after = target.current_temp_c
            target.is_welded = True

            temps = [s.current_temp_c for s in segments]
            delta_t_now = max(temps) - min(temps)
            asym_now = self._calculate_thermal_asymmetry(segments)
            p_step = self._predict_position(delta_t_now, asym_now)

            steps.append(SequenceDecisionStep(
                step_index=step + 1,
                selected_segment_id=seg_id,
                waiting_time_s=wait_needed,
                temp_before_c=t_before,
                temp_after_c=t_after,
                max_circumferential_delta_t_c=delta_t_now,
                predicted_position_p_mm=p_step,
                thermal_asymmetry_metric=asym_now,
            ))
            total_time += 12.0 + wait_needed
            total_wait += wait_needed

        return AdaptiveSequenceResult(
            strategy_name=sequence_name,
            execution_order=order,
            total_cycle_time_s=total_time,
            final_position_p_mm=steps[-1].predicted_position_p_mm,
            max_delta_t_observed_c=max(s.max_circumferential_delta_t_c for s in steps),
            steps=steps,
            cooling_waiting_time_total_s=total_wait,
            plant_model=self.PLANT_MODEL,
            position_predictor=self.POSITION_PREDICTOR,
            evaluation_model=self.EVALUATION_MODEL,
            initial_perturbation_c=tuple(
                np.asarray(initial_perturbation, dtype=float).tolist()
                if initial_perturbation is not None else []
            ),
        )
