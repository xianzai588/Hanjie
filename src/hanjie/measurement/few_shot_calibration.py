"""合成数据校准演示；不提供真实物理试验或贝叶斯后验证据。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import numpy as np
from scipy.optimize import curve_fit


@dataclass
class PhysicalTrialData:
    sample_id: str
    trial_type: str
    synthetic_values: np.ndarray
    synthetic_noise_2sigma: float
    description: str
    evidence_level: str = "synthetic_demo"


@dataclass
class CalibrationReport:
    fitted_eta: float
    synthetic_eta_fit_standard_error: float
    fixed_stiffness_n_mm: float
    fitted_combined_response_coeff: float
    training_error_p95_mm: float
    leave_one_out_error_p95_mm: float
    sample_comparisons: list[dict[str, Any]]
    fitted_trial_types: list[str]
    excluded_trial_types: list[str]
    identifiability_note: str
    evidence_level: str = "synthetic_demo"
    validation_status: str = "synthetic_leave_one_out_only"
    uncertainty_reduction_pct: float | None = None


class FewShotCalibrator:
    def __init__(self) -> None:
        self.nominal_eta = 0.55
        self.nominal_stiffness = 1200.0
        self.fixed_stiffness_n_mm = self.nominal_stiffness

    def generate_synthetic_physical_trials(self) -> list[PhysicalTrialData]:
        """旧接口保留，所有样本均为合成演示，SYN 编号不得当作实测编号。"""
        rng = np.random.default_rng(101)
        times = np.linspace(10, 60, 26)
        temperatures = 20 + (0.535 / 0.55) * 820 * np.exp(-0.038 * (times - 10))
        distances = np.linspace(-3, 3, 13)
        trials = [
            PhysicalTrialData("SYN-001", "thermal", temperatures + rng.normal(0, 1.2, 26), 2.4, "合成降温曲线，时间网格 10~60 s"),
            PhysicalTrialData("SYN-002", "hardness", 180 + 150 / (1 + (distances / 0.7) ** 2), 0, "合成硬度曲线；未用于参数拟合"),
        ]
        for i, value in enumerate([0.0465, 0.0482, 0.0458], 3):
            trials.append(PhysicalTrialData(f"SYN-{i:03d}", "cmm_position", np.array([value]), 0.002, "合成位置度；不是 CMM 实测"))
        return trials

    def calibrate_from_trials(self, trials: list[PhysicalTrialData]) -> CalibrationReport:
        """对合成样本拟合并做留一验证；真实数据需另建含采样时间与来源的入口。"""
        if not trials or any(t.evidence_level != "synthetic_demo" for t in trials):
            raise ValueError("此入口仅支持 synthetic_demo，不得作为真实物理校准")
        if len({t.sample_id for t in trials}) != len(trials):
            raise ValueError("样本编号必须唯一")
        if any(not np.all(np.isfinite(t.synthetic_values)) for t in trials):
            raise ValueError("样本值必须有限")
        thermal = [t for t in trials if t.trial_type == "thermal"]
        cmm = [t for t in trials if t.trial_type == "cmm_position"]
        if len(thermal) != 1 or len(thermal[0].synthetic_values) < 3 or len(cmm) < 3:
            raise ValueError("至少需要一条温度曲线及三个位置度演示样本")
        if any(np.asarray(t.synthetic_values).shape != (1,) for t in cmm):
            raise ValueError("每个位置度样本须为单一数值")
        times = np.linspace(10, 60, len(thermal[0].synthetic_values))

        def temp_model(t, eta, cooling):
            return 20 + (eta / 0.55) * 820 * np.exp(-cooling * (t - 10))

        params, covariance = curve_fit(temp_model, times, thermal[0].synthetic_values,
                                       p0=[0.55, 0.04], bounds=([0.01, 0.0001], [1, 1]))
        values = np.array([float(t.synthetic_values[0]) for t in cmm])
        if np.any(values < 0):
            raise ValueError("位置度不能为负")
        # 同一工况的位置度只提供一个观测方向；刚度固定后只能辨识组合响应系数，
        # 不能把刚度和收缩拆成两个独立的物理后验参数。
        stiffness_factor = self.nominal_stiffness / self.fixed_stiffness_n_mm
        scale = 2 * 74.98 * (params[0] / self.nominal_eta) * stiffness_factor
        combined_response = float(values.mean() / scale)
        prediction = float(scale * combined_response)
        loo = np.array([
            float(scale * np.delete(values, i).mean() / scale)
            for i in range(len(values))
        ])
        comparisons = [dict(sample_id=t.sample_id, synthetic_p_mm=float(values[i]),
                            fitted_p_mm=prediction, leave_one_out_pred_mm=float(loo[i]))
                       for i, t in enumerate(cmm)]
        return CalibrationReport(
            fitted_eta=float(params[0]),
            synthetic_eta_fit_standard_error=float(np.sqrt(covariance[0, 0])),
            fixed_stiffness_n_mm=self.fixed_stiffness_n_mm,
            fitted_combined_response_coeff=combined_response,
            training_error_p95_mm=float(np.percentile(abs(values - prediction), 95)),
            leave_one_out_error_p95_mm=float(np.percentile(abs(values - loo), 95)),
            sample_comparisons=comparisons,
            fitted_trial_types=["thermal", "cmm_position"],
            excluded_trial_types=["hardness"],
            identifiability_note=(
                "同一工况位置度数据在固定刚度假设下仅辨识收缩-刚度组合响应系数；"
                "硬度演示未参加拟合，结果不构成物理后验或独立验证。"
            ),
        )
