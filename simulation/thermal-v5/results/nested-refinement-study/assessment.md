# THERMAL-0.6 严格嵌套离散准入

> 比较对象为完全一致的物理坐标、材料界面与焊道外形；局部控制体按整数细分。

| 网格对 | NiFe P95 (°C) | QT solidus flip (mm³) | NiFe solidus flip (mm³) | 源共同体 L1 | 接口最大 L1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| NEST-M_to_NEST-F | 26.877 | 2.894 | 5.781 | 0.0000 | 0.0489 |
| NEST-F_to_NEST-VF | 10.923 | 0.905 | 0.754 | 0.0000 | 0.0271 |

## 裁决

`spatial_gate_pass=false`；`xfine_allowed=false`；`time_step_recheck_allowed=false`。
停止NEST-XF与时间步复查；累计界面热量和共同控制体源积分已通过，下一轮只处理边界源承载层、逐面峰值与固定点重构的h敏感性。

未通过项：连续峰温或相变阈值翻转未稳定；固定物理点完整热循环未稳定。
