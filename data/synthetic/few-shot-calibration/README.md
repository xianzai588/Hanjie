# 合成校准演示

本目录只保存由 `studies/FEW-SHOT-CALIBRATION/run_calibration_study.py` 生成的合成输入和结果：

- `trials.json`：合成温度、硬度和位置度数组，不是仪器原始数据；
- `calibration_summary.json`：合成温度拟合、固定刚度下的组合响应系数、训练残差和合成留一误差。

硬度数组不参加拟合。相同工况的位置度样本不能独立辨识刚度与收缩，因此不得从该结果声称物理后验、校准不确定度缩减或独立验证。
