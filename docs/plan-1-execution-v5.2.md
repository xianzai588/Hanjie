# 计划一执行记录：G-INPUTS → THERMAL-0 → METALLURGY-0

> 2026-09-06 封存：THERMAL0.2 为 numerically verified, physically uncalibrated baseline；当前推进 [计划二](plan-2-physics-v5.3.md)。本文件旧 Low/Medium/High 评分仅作历史记录，未热激活母材的当前结论为 unresolved；不进入 THERMAL-1 或正式 STRUCT-0。

**项目**：QT450-10 / Q235B 异种材料焊接工艺设计  
**路线版本**：V5.2-Roadmap-Freeze  
**执行日期**：2026-09-05  
**证据原则**：没有实测数据的结果均不升级为 calibrated、experiment_result 或 physical_validated。

## 1. 计划范围

冻结稿没有单独名为“计划一”的章节。按冻结稿第 22 节“阶段 A：立即执行”解释，计划一落地以下链路：

```text
G-INPUTS → THERMAL-0 → METALLURGY-0 → 既有三维静力初筛结果复核
```

本计划不提前执行 STRUCT-0/STRUCT-1、SERVICE、PROCESS/CONTROL 或 EXP-FINAL；这些阶段必须使用经过本计划审查的热历史，并按冻结稿规定的 Gate 继续推进。

## 2. 交付物与状态

| 工作项 | 交付物 | 状态 | 证据等级 |
| --- | --- | :---: | --- |
| G-INPUTS 冻结 | [`project/g-inputs-v5.2.yaml`](../project/g-inputs-v5.2.yaml) | 已完成 | design_assumption |
| THERMAL-0 执行器 | [`simulation/thermal-v5/run_thermal0.py`](../simulation/thermal-v5/run_thermal0.py) | 已完成 | solver_result_unvalidated |
| THERMAL-0 热场 | `thermal0-field.npz`、`thermal0-summary.json`、传感点历史 | 已生成 | solver_result_unvalidated |
| 热循环图 | `thermal0-peak-profile.svg/png` | 已生成 | solver_result_unvalidated |
| METALLURGY-0 执行器 | [`simulation/metallurgy-v5/run_metallurgy0.py`](../simulation/metallurgy-v5/run_metallurgy0.py) | 已完成 | literature_supported_plus_solver_result_unvalidated |
| 组织风险与稀释区间 | `metallurgy0-summary.json`、`metallurgy0-risk.csv`、报告 | 已生成 | literature_supported_plus_solver_result_unvalidated |
| 三维静力初筛复核 | [`simulation/structural-v4/results/static-screening/static-screening-analysis.json`](../simulation/structural-v4/results/static-screening/static-screening-analysis.json) | 已有结果复核通过 | solver_result_unvalidated |
| G-THERMAL 审计 | [`simulation/thermal-v5/results/g-thermal-audit/G-THERMAL-audit.md`](../simulation/thermal-v5/results/g-thermal-audit/G-THERMAL-audit.md) | 能量/时间步通过；网格与参数需复核 | solver_result_unvalidated |
| EXP-THERMAL 测点协议 | [`experiments/protocols/EXP-THERMAL-v1.yaml`](../experiments/protocols/EXP-THERMAL-v1.yaml) | 已冻结测点；实验待落实 | design_assumption |
| 物理验证 | 热电偶、金相、显微硬度、化学成分 | 未具备 | pending |

## 3. G-INPUTS 冻结内容

- 几何：Q235B 壳体 Ø160 × H200 × t5 mm；QT450-10 座体；Ø40 孔；R74.98/R75.00 接口；Continuous 作为 THERMAL-0 的基线焊道。
- 工艺：automatic TIG、ERNiFe-CI、75 A、12 V、1.5 mm/s、η=0.55、净功率 495 W、净线能量 330 J/mm、预热 150°C、层间上限 200°C。
- 热源：离散 Goldak 双椭球；参数和前后热源比例集中登记在 G-INPUTS，当前均为未校准设计假设。
- 夹具：1:50 锥形心轴、Ø39.90–40.10 mm、500 N 轴向预紧；冷却保持和释放条件已显式写入。
- 输出网格：周向 49 × 法向 17 × 轴向 13；时间步 0.05 s；持续计算至焊后冷却窗口。

## 4. THERMAL-0 实际结果

运行命令：

```powershell
python simulation/thermal-v5/run_thermal0.py
```

关键输出：

- 全场峰值温度约 **1009.7°C**，位于接口附近 `n=-0.125 mm`、`z=0 mm` 的网格点。
- 以 `Tpeak ≥ 400°C` 定义的热暴露离散宽度估计：QT450-10 侧约 **2.69 mm**，Q235B 侧达到当前外推范围 **5.0 mm**；这不是经过冶金验证的真实 HAZ 宽度，应在更大法向范围和实测宏观截面中复核。
- 有效 t8/5 节点 **49**；中位数约 **1.96 s**，范围约 **1.82–2.01 s**。该量只描述热循环，不作为 QT450-10 的独立相组成判据。
- 当前峰值低于 G-INPUTS 中的 1350°C 熔合阈值，因此本轮结果**没有证明形成真实熔池或达到可焊熔合状态**；Goldak 尺寸、边界换热和效率必须由热电偶、宏观熔合区或进一步数值验证约束后再进入 THERMAL-1。
- 能量审计显示每步热源体积分功率误差约 `10^-15`，连续焊段累计能量误差约 **0.0078%**；累计输入与 `ηUI·t_w` 一致。
- dt/2→dt/4 峰值变化约 **0.014%**，单步热源移动距离 **0.075 mm**，小于当前法向网格间距 **2.5625 mm**。
- medium→fine 峰值变化约 **7.07%**，超过拟定 5% 研究门槛；效率和热源尺寸敏感性也达到约 10%–16%，因此 G-THERMAL 总状态为 **review_required**，不能升级 THERMAL-1。

该失败信号是计划一的有效结果：它阻止后续将当前热场直接写成已校准焊接热模型。

## 5. METALLURGY-0 实际结果

运行命令：

```powershell
python simulation/metallurgy-v5/run_metallurgy0.py
```

当前结果仅给出风险级、趋势、位置和区间：

- QT450-10 侧空间区域（含熔合线邻近网格）峰值约 **1009.7°C**，白口/碳化物风险 **Medium**，马氏体/高硬化风险 **High**，HAZ 脆化和冷裂风险 **Medium**；该结论对网格分层和热源校准敏感，不能替代金相与硬度。
- Q235B 侧空间区域峰值约 **1009.7°C**，高温晶粒粗化和硬化风险暂评为 **Medium**；不能由此推断接头强度或疲劳寿命。
- 稀释支路：以 3.5 mm 焊脚、QT 熔入 1.5 mm、Q235B 熔入 1.0 mm 为设计假设，名义 QT450-10/Q235B/填充金属几何贡献约 **35.3% / 23.5% / 41.2%**；熔入深度 ±25% 敏感性下，Ni 约 **19.74–26.55 wt%**、C 约 **1.26–1.79 wt%**。

以上成分是几何稀释估计，不是焊缝化学分析；未输出伪精确相含量，也未把硬度趋势等价为拉伸、断裂韧性或疲劳性能。风险统计已区分“材料分区”和“接口两侧空间区域”，后者用于避免焊缝分类遮蔽熔合线邻近母材风险。

稀释字段已在结果中拆分为 `qt450_10_fraction`、`q235b_fraction` 和 `filler_fraction`，并固定 `thermal_fusion_validated=false`、`chemistry_validated=false`。因此这些数值只能称为 **geometry_based_nominal dilution contribution**。

## 6. 既有静力初筛复核

既有 P1A 三维线弹性静力筛查结果已满足其自身数值稳定性门槛：

- 7 个实体模型、3 级网格、2 档支承、7 个径向方向，共 294 个方向结果；
- medium→fine 轴线偏移直径变化小于 3%，p95 应力变化小于 10%；
- fine 网格 BC-1/BC-2 敏感性小于 10%；
- 孔轴指标来自轴线评价逻辑，不使用最大节点位移替代；
- `full_thermal_structural_gate_pass` 仍为 `false`，因此该结果不升级为焊接热—结构结论。

## 7. 计划一验收结论

**计划一数字执行：完成；G-INPUTS：通过数字基线冻结；THERMAL-0：已完成 THERMAL0.2 固定窗口与截断纠偏，但仍未通过物理校准 Gate；METALLURGY-0：已按母材区域语义重跑风险级输出，但未通过物理验证 Gate。**

## 8. V5.2-THERMAL0.1 历史状态（已被 THERMAL0.2 取代）

THERMAL0.1 建立的保守面通量、面积边界热损失、三线性采样和全局能量账本继续保留；其局部窗口坐标语义、热源末端截断、测点漂移及冶金侧区掩码已被判定无效。THERMAL0.1 的峰温、冶金风险和热暴露宽度不得继续引用，当前有效数字统一见下一节 THERMAL0.2 记录。

## 9. V5.2-THERMAL0.2 固定窗口与冶金区域纠偏记录

针对第二轮审查发现的坐标系混用、热源截断重归一化和母材风险掩码问题，已完成以下修正并重新运行：

- 坐标模式冻结为 `fixed_local_window_moving_source`：计算域 `s=-70~70 mm`，热源路径 `-30~30 mm`，持续时间由路径长度和 `1.5 mm/s` 自动得到 `40 s`；固定测点不再执行 `-v·t` 坐标漂移。
- 基准网格更新为 `72×52×30`，`ds=1.944 mm`、`dn=0.788 mm`、`dz=0.800 mm`；热源两端最小边界余量 `40 mm`，大于 `3×a_rear=30 mm`，热源中心出域步数为 0。
- 在离散功率归一化前增加连续 Goldak 源有限域解析捕获率 Gate；基准最小捕获率 `99.999952%`，审计矩阵最小值 `99.997772%`，均高于 `99.9%` 门槛。
- 修正后全场峰值为 `896.99 °C @ (s,n,z)=(26.25,-0.125,-0.400) mm`，不在人工 `s` 截断边界；旧 `1876.03 °C` 判定为 THERMAL0.1 截断重归一化伪峰，不再作为物理结果引用。
- 全局热能残差为 `0.00371%`；审计矩阵最大残差 `0.00406%`。G-THERMAL 总状态仍为 `review_required`，因为参数敏感性与实验校准尚未闭环。
- pure-mesh 比较统一采用 `dt=0.003 s`：medium→fine 峰值变化 `0.557%`；QT450-10/Q235B 母材热暴露宽度变化分别为 `4.56%/3.96%`。
- 冶金风险和热暴露宽度仅使用 `material_id==2/1` 的母材单元；`n=0` 更名为 `WELD_CENTER`，`n=±3 mm` 记录为未校准的 `SURROGATE_INTERFACE_REF`，不再称作 fusion line。
- 重算后 QT450-10/Q235B 母材峰值为 `434.88/525.87 °C`，`Tpeak≥400 °C` 的母材暴露宽度为 `0.279/1.606 mm`；ERNiFe-CI 代理焊缝峰值 `896.99 °C`，在补齐高温物性、相变焓与实验校准前不作焊缝冶金风险评分。

THERMAL0.2 未加入固相线、液相线、潜热和 ERNiFe-CI 高温物性；这些仍是 THERMAL-1 前置工作。当前峰温、母材风险与暴露宽度均保持 `solver_result_unvalidated` 证据等级。
