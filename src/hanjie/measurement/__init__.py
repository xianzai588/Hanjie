"""测量、CMM 与少样本物理标定模块。"""

from .few_shot_calibration import (
    FewShotCalibrator,
    CalibrationReport,
    PhysicalTrialData,
)

__all__ = [
    "FewShotCalibrator",
    "CalibrationReport",
    "PhysicalTrialData",
]
