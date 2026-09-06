# V4.3 关键结果索引

更新时间：2026-09-06

本文件只登记已实际运行且当前有效的结果；完整边界见各结果文件。

| 工作包 | 结果 | 状态 | 证据 |
| --- | --- | --- | --- |
| 三维静力筛查 | Continuous、6P、8P-FAIR_B 保留；细网格平均受载轴线偏移直径分别为 0.000304、0.000750、0.000570 mm | solver_result_unvalidated；不代表焊后位置度 | `simulation/structural-v4/stiffness-screening-v4.md` |
| 局部热模型 | 0.4R1 名义峰温：Q235B 1015.79 °C、QT450-10 1088.14 °C、ERNiFe-CI 1520.82 °C；共同控制体诊断确认焊材热区 P95 差异仍为 74.554 °C | 能量/时间步通过，空间网格未收敛；未校准 | `simulation/thermal-v5/results/credibility04r1/assessment.json`、`simulation/thermal-v5/results/credibility04r1/spatial-convergence-diagnosis.json` |
| 固定几何场网格对照 | 0.4R2-A 实际重算 coarse/medium/fine 和两个方向控制；固定六条带后 medium→fine 焊材热区 P95 差降至 16.682 °C，QT 固相线翻转 14.637 mm³；方向对照显示截面细化影响占主导 | 较旧混合序列改善但仍未通过；THERMAL-1 继续冻结 | `simulation/thermal-v5/results/spatial-fix-study/assessment.json` |
| 局部截面三级细化 | XSEC-M/F/VF 实际重算；焊材 P95 差 9.60/18.26 °C，缩减比 1.903；VF 对 F 的 QT/NiFe solidus flip 为 0.86/2.93 mm³ | 非单调、未进入渐近区；停止 xfine 与新网格时间步复查 | `simulation/thermal-v5/results/xsec-refinement-study/assessment.json` |
| 接头一致性 | 当前单道等效焊脚 1.737 mm；另登记 3.5 mm 等面积四道候选，体积核算为 6.125 mm² | 候选仅体积自洽；承载、成形、热循环未闭合，不得作为 WPS | `deliverables/process/joint-process-card.json` |
| 条件性接头承载 | 参考包络下 6P 的 1.737/2.0/2.5/3.0/3.5 mm 所需许用为 105.149/91.303/73.042/60.869/52.173 MPa，并分列径向、轴向与倾覆贡献 | design_assumption_reference_envelope；不能证明实际服役安全或 3.5 mm 唯一必要 | `simulation/structural-v4/results/joint-load-basis/joint-load-basis.json` |
| STRUCT-0 全局求解准备 | 一致切线有限差分核对、硬化拉杆解析对照、约束升温—释放—冷却及高温应力自由出生全部通过；拉杆最终 300 MPa 步最多 6 次 Newton，释放步 3 次 | algorithm_and_small_mesh_verification；尚非整件焊接求解 | `simulation/structural-v4/results/struct0-prep/global-newton-benchmarks.json` |
| Continuous 统一预备网格 | Q235B/QT450-10/ERNiFe-CI 三材料共形网格 52,210 节点、176,524 四面体，焊接/间隙/夹具/基准/孔集合完整且无倒置单元 | 仍有 1,381 个 minSICN<0.1 单元；热映射和接触未执行，STRUCT-PREP Gate 不通过 | `simulation/structural-v4/results/struct0-prep/continuous-unified-mesh.json` |
| 严格嵌套热离散 | NEST-M/F/VF 为 111,440/199,080/458,360 控制体；F→VF 焊材 P95 10.923 °C、缩减比 0.406，QT/NiFe solidus flip 0.905/0.754 mm³；共同源积分 L1 约 4.2e-16，两侧接口累计热差 0.10%/0.17% | 已出现渐近趋势但温度场和固定点历史仍超门；禁止 xfine、dt/2 和正式结构输入 | `simulation/thermal-v5/results/nested-refinement-study/assessment.json` |
| STRUCT-0 Plan 5 准备 | 法向接触—分离—撤夹、局部材料安全保守映射、全局六四面体激活/应力自由出生均通过；压紧 penetration 6.99e-6 mm | 小模型/局部算法验证；不代表 Continuous 正式求解 | `simulation/structural-v4/results/struct0-prep/struct0-prep-plan5-assessment.json` |
| Continuous 网格质量定位 | 1,381 个差单元全部在焊缝并邻近两焊接界面；0.5 mm 局部细化变为 2,575 个，Delaunay+重定位仍 1,393 个 | 两次试验均拒绝；根因收敛到系统性环形接口三角化/四面体拓扑，STRUCT-0-PREP 不通过 | `simulation/structural-v4/results/struct0-prep/continuous-mesh-quality-diagnosis.json` |
| 逐件预偏置 | 逆补偿合成代理均值 0.00647 mm、P95 0.01585 mm、总体通过率 100% | synthetic_demo；未做实物标定 | `studies/PRECOMPENSATION/results/precompensation_summary.json` |
| 误差预算 | 最坏径向 0.035 mm，对应 Ø0.070 mm | 未满足 Ø0.05 mm 目标 | `project/tolerance.yaml` |

热模型串联热阻修正相对历史名义峰温变化为 -2.55、+0.88、+3.55 °C；它只表示离散修正差异，不是真值误差。真实焊接、宏观截面、CMM、硬度、NDT、洁净度及 WPS/PQR 均未被这些数值结果替代。
