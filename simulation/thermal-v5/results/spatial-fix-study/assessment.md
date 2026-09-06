# THERMAL-0.4R2-A 固定几何场网格对照

> 六条带解析边界、物理输入和 dt=0.1 s 固定；以下为实际重算结果，不是真值误差。

| 网格对 | 材料 | 共同控制体峰温 P95差 (°C) | 最大差 (°C) | 固相线翻转体积 (mm³) | 原登记指标集合 |
| --- | --- | ---: | ---: | ---: | --- |
| A-field-coarse-fixed6_to_A-field-medium-fixed6 | q235b | 8.614 | 44.008 | 0.000 | 未通过 |
| A-field-coarse-fixed6_to_A-field-medium-fixed6 | qt450_10 | 4.288 | 62.674 | 0.000 | 未通过 |
| A-field-coarse-fixed6_to_A-field-medium-fixed6 | ernife_ci | 25.087 | 47.442 | 1.508 | 未通过 |
| A-field-medium-fixed6_to_A-field-fine-fixed6 | q235b | 6.968 | 66.991 | 0.000 | 未通过 |
| A-field-medium-fixed6_to_A-field-fine-fixed6 | qt450_10 | 3.273 | 67.260 | 14.637 | 未通过 |
| A-field-medium-fixed6_to_A-field-fine-fixed6 | ernife_ci | 16.682 | 25.167 | 1.634 | 未通过 |

## 原混合序列中的几何影响

同名义场间距下，把旧 3/4 条带换为固定 6 条带时，焊材共同控制体 P95 差分别为 54.166/59.708 °C。由于边界锚点也改变局部分区，这不是严格几何极限，但足以证明旧序列混入了显著几何影响。

固定六条带后 medium→fine 的焊材热区 P95 差降至约16.7°C，说明旧混合序列的74.554°C含显著几何变化贡献；但仍高于10°C且QT固相线翻转仍存在，场离散也尚未收敛。

## 方向控制变量

保持截面为 medium、只把沿焊道细化到 fine 后，距完整 fine 的焊材 P95 差为 18.714 °C；保持沿焊道为 medium、只细化截面后的对应差为 3.834 °C。截面细化的剩余影响更大。

状态：A 固定几何控制变量计算已完成；`spatial_gate_pass=false`、`thermal_1_allowed=false`。下一步先针对焊材/界面高梯度做局部场细化，再决定是否需要 xfine；随后在新细网格复查时间步。
