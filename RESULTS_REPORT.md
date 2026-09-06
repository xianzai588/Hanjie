# V4.3 关键结果索引

更新时间：2026-09-06

本文件只登记已实际运行且当前有效的结果；完整边界见各结果文件。

| 工作包 | 结果 | 状态 | 证据 |
| --- | --- | --- | --- |
| 三维静力筛查 | Continuous、6P、8P-FAIR_B 保留；细网格平均受载轴线偏移直径分别为 0.000304、0.000750、0.000570 mm | solver_result_unvalidated；不代表焊后位置度 | `simulation/structural-v4/stiffness-screening-v4.md` |
| 局部热模型 | 0.4R1 名义峰温：Q235B 1015.79 °C、QT450-10 1088.14 °C、ERNiFe-CI 1520.82 °C | 能量/时间步通过，空间网格未收敛；未校准 | `simulation/thermal-v5/results/credibility04r1/assessment.json` |
| 接头一致性 | 3.5 mm 设计焊脚对应 6.125 mm²；当前送丝等效焊脚 1.737 mm，仅占设计面积 24.6% | not_closed；不得作为 WPS | `deliverables/process/joint-process-card.json` |
| 逐件预偏置 | 逆补偿合成代理均值 0.00647 mm、P95 0.01585 mm、总体通过率 100% | synthetic_demo；未做实物标定 | `studies/PRECOMPENSATION/results/precompensation_summary.json` |
| 误差预算 | 最坏径向 0.035 mm，对应 Ø0.070 mm | 未满足 Ø0.05 mm 目标 | `project/tolerance.yaml` |

热模型串联热阻修正相对历史名义峰温变化为 -2.55、+0.88、+3.55 °C；它只表示离散修正差异，不是真值误差。真实焊接、宏观截面、CMM、硬度、NDT、洁净度及 WPS/PQR 均未被这些数值结果替代。
