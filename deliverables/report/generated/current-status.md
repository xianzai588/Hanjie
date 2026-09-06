# 自动生成的当前证据摘要

当前权威配置与已执行结果；非实测证据仍保留原等级

## 阶段状态

| 阶段 | 执行状态 | 验收结果 | 允许用途 |
| --- | --- | --- | --- |
| G-INPUTS | controlled_inputs_and_volume_closed_candidate_defined | not_closed | 受控设计输入；接头承载依据和成形关系仍待闭合 |
| THERMAL-0.4R1 | ten_case_run_and_audit_completed | failed_spatial_convergence | 未校准局部热诊断；禁止正式整件性能结论 |
| METALLURGY-0 | executor_and_historical_diagnostics_completed | current_joint_not_physically_validated | 风险识别；禁止宣称当前接头组织或连接质量已验证 |
| EXP-THERMAL | protocol_completed_experiment_not_run | not_executed | 试验准备 |
| THERMAL-1 | blocked | not_admitted | 不允许正式结构耦合 |
| STRUCT-0-PREP | partial_with_1d_constitutive_baselines_verified | not_ready | 独立组件验证；不得冒充实际焊接残余位置度 |
| STRUCT-0 | not_executed | blocked_by_thermal_and_prep | 无 |
| STRUCT-1 | static_screening_only | formal_comparison_not_executed | 当前载荷和支承下的静力筛查 |
| SERVICE | load_builder_unit_verified_results_not_computed | not_executed | 载荷构造验证；无整件性能结论 |
| PROCESS-CONTROL | surrogate_prototypes_completed | formal_study_not_executed | 算法演示和拒绝逻辑验证 |
| EXP-FINAL | not_executed | not_executed | 无 |
| DECISION | candidate_retention_decisions_only | final_decision_not_available | 阶段设计评审 |

## 公差与接头闭合状态

| 项目 | 当前值 |
| --- | ---: |
| 产品几何链径向限值 | 0.025 mm |
| 产品链最坏情况设计和 | 0.035 mm |
| 预算状态 | not_closed |
| 测量扩展不确定度 | 待实测评定 |
| 设计角焊缝截面积 | 6.125 mm² |
| 名义送丝新增截面积 | 1.508 mm² |
| 名义送丝等效焊脚 | 1.737 mm |

## 三维静力筛查

| 排名 | 候选 | 细网格平均轴线偏移直径 (mm) | P95 应力 (MPa) |
| ---: | --- | ---: | ---: |
| 1 | Continuous | 0.000304 | 0.632 |
| 2 | 8P-FAIR_B | 0.000570 | 0.972 |
| 3 | 8P-FAIR_A | 0.000696 | 1.226 |
| 4 | 6P-FAIR_A | 0.000750 | 1.281 |
| 5 | 6P-FAIR_B | 0.000750 | 1.281 |
| 6 | 4P-FAIR_A | 0.000898 | 1.409 |
| 7 | 4P-FAIR_B | 0.001247 | 1.919 |

静力筛查门：通过；完整热—结构门：未通过。

## THERMAL-0.4R1 名义工况

| 材料 | 峰温 (°C) | 越固相线体积 (mm³) | 越液相线体积 (mm³) |
| --- | ---: | ---: | ---: |
| Q235B | 1015.79 | 0.000000 | 0.000000 |
| QT450-10 | 1088.14 | 0.000000 | 0.000000 |
| ERNiFe-CI | 1520.82 | 26.389378 | 9.424778 |

名义能量残差：2.568e-08%；空间网格收敛：未通过；时间步收敛：通过。
条件数值收敛：未通过；实物校准：未完成；允许进入正式结构耦合：否。

相对历史 0.4R 的峰温差：Q235B -2.55 °C、QT450-10 +0.88 °C、ERNiFe-CI +3.55 °C。该差值只表示离散修正影响。
