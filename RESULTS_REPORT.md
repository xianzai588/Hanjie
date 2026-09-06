# V4.3 关键结果索引

更新时间：2026-09-06

本文件只登记已实际运行且当前有效的结果；完整边界见各结果文件。

| 工作包 | 结果 | 状态 | 证据 |
| --- | --- | --- | --- |
| 三维静力筛查 | Continuous、6P、8P-FAIR_B 保留；细网格平均受载轴线偏移直径分别为 0.000304、0.000750、0.000570 mm | solver_result_unvalidated；不代表焊后位置度 | `simulation/structural-v4/stiffness-screening-v4.md` |
| 局部热模型 | 0.4R1 名义峰温：Q235B 1015.79 °C、QT450-10 1088.14 °C、ERNiFe-CI 1520.82 °C；共同控制体诊断确认焊材热区 P95 差异仍为 74.554 °C | 能量/时间步通过，空间网格未收敛；未校准 | `simulation/thermal-v5/results/credibility04r1/assessment.json`、`simulation/thermal-v5/results/credibility04r1/spatial-convergence-diagnosis.json` |
| 固定几何场网格对照 | 0.4R2-A 实际重算 coarse/medium/fine 和两个方向控制；固定六条带后 medium→fine 焊材热区 P95 差降至 16.682 °C，QT 固相线翻转 14.637 mm³；方向对照显示截面细化影响占主导 | 较旧混合序列改善但仍未通过；THERMAL-1 继续冻结 | `simulation/thermal-v5/results/spatial-fix-study/assessment.json` |
| 接头一致性 | 当前单道等效焊脚 1.737 mm；另登记 3.5 mm 等面积四道候选，体积核算为 6.125 mm² | 候选仅体积自洽；承载、成形、热循环未闭合，不得作为 WPS | `deliverables/process/joint-process-card.json` |
| 条件性接头承载 | 参考包络下 6P 的 1.737/3.5 mm 焊脚所需许用分别约 105.149/52.173 MPa；同时登记各布局单位载荷影响系数和热量/节拍 | design_assumption_reference_envelope；不能证明实际服役安全或 3.5 mm 唯一必要 | `simulation/structural-v4/results/joint-load-basis/joint-load-basis.json` |
| STRUCT-0 准备 | 三维 J2 覆盖单轴/纯剪/静水/组合/卸载/旋转一致性；六四面体小网格完成自由与约束热膨胀、塑性加载和支承释放平衡检查 | algorithm_and_small_mesh_verification；任意边界全局 Newton、焊材、接触和统一整件网格仍未完成 | `simulation/structural-v4/results/struct0-prep/constitutive-3d-small-mesh.json` |
| 逐件预偏置 | 逆补偿合成代理均值 0.00647 mm、P95 0.01585 mm、总体通过率 100% | synthetic_demo；未做实物标定 | `studies/PRECOMPENSATION/results/precompensation_summary.json` |
| 误差预算 | 最坏径向 0.035 mm，对应 Ø0.070 mm | 未满足 Ø0.05 mm 目标 | `project/tolerance.yaml` |

热模型串联热阻修正相对历史名义峰温变化为 -2.55、+0.88、+3.55 °C；它只表示离散修正差异，不是真值误差。真实焊接、宏观截面、CMM、硬度、NDT、洁净度及 WPS/PQR 均未被这些数值结果替代。
