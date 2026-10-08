# 关键设计数字与计算来源索引

完整圆环为基础方案，八翼开口为创新候选。索引按物理对象列出数字；“设计输入”“守恒核算”“已有数值结果”“规划情景”“试制方法目标”分别标识。路径以仓库根目录为起点，详细输出保留在计算依据和可编辑源文件中。

## 1 决定结构与工艺的数字

| 编号 | 物理对象与状态 | 关键数字 | 用途及采用结论 |
| --- | --- | --- | --- |
| C01 | 完整圆环名义几何，设计输入 | QT厚15 mm、R20～74.98、z100～115；壳R75～80、z0～200；径向间隙0.02 mm | 定义完整传力基准和名义装配；其预制覆盖、热史与孔轴按圆环实体分别评价。来源HJ-S01 |
| C02 | 旧版冷态结构比较，等效弹性接口 | 八翼/圆环质量0.997/1.772 kg；受载孔轴弹性偏移直径19.218/11.821 μm；应变能310.79/201.63 N·mm | 说明开口构型减重约43.7%的同时降低刚度；采用圆环为基础方案。来源旧版上传论文第8页，恢复原表而非本轮新求解 |
| C03 | 圆环HJ-W-S01最终组焊，路径及守恒核算 | 有效8×18＝144 mm；每段两端各加1 mm，两道实际320 mm；300 J/mm、96.0 kJ、193.939 s | 完整记入端区热量与时间。旧八翼18 mm路径JSON保留288 mm、86.4 kJ、174.545 s；两种实体温度与孔轴分别评价 |
| C04 | 圆环最终送丝与稳定区成形，守恒核算 | 送丝3.50±0.05 mm/s、Ø1.60±0.01 mm；圆环耗丝678.788 mm，加15%备料780.606 mm；稳定区截面积7.326～8.760 mm² | 320 mm实际路径承担耗材；旧八翼耗丝610.909 mm保留原对象。端区、双侧熔合及有效喉部以试样评价 |
| C05 | 八翼CI-A1首层完整热史，已有数值结果 | 15.329235 g；184.675927 kJ；全部1051.200939 mm²界面达到模型逐面液化判据；首道至入炉1694.302 s | 记录该实体在给定热源下的热连接响应，支持八翼首层及工位占用；不是圆环结果或实测稀释 |
| C06 | 八翼整件首层炉冷，已有数值结果 | 入炉至冷态24300 s＝6.75 h；首道至冷态25994.302 s＝7.22064 h；温度20.04873～20.04998℃ | 计算缓冷库存与交接时刻；热冷态与机械残余状态分别标识 |
| C07 | 八翼真实预制槽公差族，几何及供料核算 | 最大槽176.157710 mm³/翼；设计密度需1.566042 g/翼；0.15 g/s下100/120 mm/min余量+0.124682/−0.164543 g | 保持100 mm/min设计基线；120的减热不能补偿公差下欠填。八翼公差STEP对应该槽 |
| C08 | 八翼平直连接区，层厚和质量混合情景 | 总层1.40～1.60 mm；首层法向0.65～0.75 mm；第二层≥0.65 mm；累计重熔≤0.40 mm时第二层≥0.25 mm、总残层≥1.00 mm | 解释两层分工与最终重熔限制；圆角、混合带及局部成分按同截面检查 |
| C09 | 同一材料链的分道均匀混合诊断情景 | 最终C为0.03055～0.07160 wt%；首层入第二层≤15%对应条件重熔深度≤0.1745 mm | 用于检查成分敏感性及截面评价重点；稀释率为输入情景，不是测量或实际输运结果 |
| C10 | 旧八翼完全卸夹制造家族，已有数值结果 | 热残余孔轴最不利15.584 μm；总预算52.084 μm；细时间孔径极差约25.961 μm | 超过50 μm目标2.084 μm，说明为何采用分工序制造及恢复圆环基准；结果保留其原材料与网格身份 |
| C11 | 共用孔轴设计分配，直径值 | 28＋2＋6.5＋13.5＝50 μm为允许上限；热残余内部目标12 μm给出48.5 μm，总裕量1.5 μm | 13.5是热残余上限而非内部目标；后列6.5是有限精整轴线变化直径。工装6.5径向已含在28非热直径项内 |
| C12 | 圆环短闭框架冷态截面核算 | L120、b80、h120 mm、E206 GPa、ν0.30；5 kN/170 kN·mm，轴线杠杆100 mm；含平移、转角和剪切5.053 μm，距6.5 μm径向夹紧分配余1.447 μm | 采用短受力闭环为基础站，剩余额度分配给接触/连接/基座/热态；6.5径向已在28非热直径项内。原重门架5.602 μm保留八翼历史对象 |
| C13 | 原八翼铜屏障热容量与退出，设计核算 | 净铜≥67.60 g；总水流≥0.60 L/min；铜≤45℃、下座≤48℃；铜瓣退位1.10±0.05 mm | 定义屏障制造和联锁窗口；圆环核对装配净隙及热边界后使用 |
| C14 | 后序隔离液路，几何及流阻核算 | 微珩液154.510 mL/min、供液≤60；下杯容量20.957 mL/故障需求18.803 mL；PT/UT盘47.733/21.203 mL | 支撑局部封闭回收；流阻结果仅适用于规定黏度牛顿液，UT凝胶另确认 |
| C15 | 孔壁、孔径及有限精整，方法设计目标 | 径向去除≤3 μm；直径增量≤6 μm；孔径方法U≤0.5 μm；40.000～40.025 mm为项目H7窗 | 孔轴、尺寸、表面缺陷分别检查，精整前后复检并保持封闭回收 |
| C16 | 圆环小批资源，规划情景 | 8件/8 h、3600 s间隔；每层10 h，各10位，延迟24位，共44位；PT每阶段2停留位；最终焊站900 s预留 | 解释单头与跨日库存。10 h按5.6 h缓降＋2 h保温＋2.4 h升温/转运/热滞后预留，属于容位规划。八翼41位/143.58元费用保持原口径 |
| C17 | PT/UT及洁净检验，试制方法目标 | PT15～35℃、渗透15～30 min、显像10～30 min；UT专用对比块；牺牲件残留＋U≤0.50 mg | 交付可执行的质量评价方案；方法目标和实际检测值分别填报 |
| C18 | 圆环八个局部预制窗口，名义实体与供料核算 | 窗长24±0.5、宽6±0.1、深1.50±0.10 mm；17有效实体；首层75 mm/min＋两端各0.5 s补弧；最短弧/速度+2%低供料2.869706 g/窗，对含保护带目标2.603046 g保留0.266660 g（10.24%） | 75 mm/min主弧及两端补弧统一提供保护带覆盖；与80比较采用同样补弧制度。首层/第二层弧燃161.6/288 s、净热322.2208/142.560 kJ；80在同样补弧条件下仅3.61%供料裕量。首件/每批冷态称量确认供料资格，逐窗检查余高与周界覆盖 |

## 2 文件路径与数据身份

- C01：`deliverables/process/ring-baseline-design-card.md`；名义实体与检验接口以该卡所列路径为准。
- C02：`deliverables/recovered-20261007/焊接工艺设计论文-正文.pdf`，第8页。原表使用壳底固定、孔40.008 mm、8×18 mm连接、同等效弹性接口，以及Fr/Fa各5000 N、Mx250 kN·mm；绝对响应尚未全部满足5%离散目标，取结构趋势及刚度代价作为设计依据。原始该比较JSON未随恢复附件取得，保留PDF来源。
- C03、C04：`deliverables/process/ring-final-welding-card.json`及HJ-W-S01。旧八翼`deliverables/process/joint-process-card.json`、`project/process-r3.yaml`保留原路径和数值，圆环新增20 mm/段实际路径独立记账。
- C05：`simulation/competition-r4/results/mma-eight-wing-phase-front-t4-end80-r12-20261007/actual-eight-wing-thermal-audit.json`；温度判据与热源适用域保留在该记录中。
- C06：`simulation/competition-r4/results/mma-eight-wing-furnace-phase-front-20261007/cold-thermal-handoff-audit.json`。
- C07：`deliverables/process/precoat-tolerance-and-feed-card.md`、`cad/generated/precoat-tolerance-family-20261007/`；提速供料比较`output/review/first-precoat-speed120-20261007/speed120-supply-window.json`。
- C08、C09：`studies/COMPETITION-DESIGN/results/current-section-interface.json`；八翼平直接触宽度及均匀混合情景。
- C10：`simulation/competition-r4/results/verification.json`、`deliverables/competition-entry/计算依据/历史八翼制造复核.json`；保留旧制造家族结果与离散差。
- C11、C15：`deliverables/process/bore-compensation-and-finish-card.md`及`project/competition-design.yaml`。40.006～40.008 mm在旧八翼为补偿输入，在圆环HJ-W-S01为自身试制起始加工设定，各自记录其孔径响应。
- C12：圆环`studies/COMPETITION-DESIGN/results/ring-fixture-feasibility.json`、计算脚本`studies/COMPETITION-DESIGN/ring-fixture-feasibility.py`。八翼原工装另见`simulation/competition-r4/results/fixture-axis-solid-core-h2/result.json`、`simulation/competition-r4/results/fixture-axis-solid-core-h1.5/result.json`及HJ-F-01，分别保留局部压缩与整体轴移口径。
- C13：`studies/COMPETITION-DESIGN/results/engineering-checks-r3.json`、`deliverables/process/copper-shield-card.md`、`deliverables/process/clean-shield-engineering-detail.md`。
- C14：`studies/COMPETITION-DESIGN/results/postweld-isolation.json`及`project/competition-design.yaml`的`postweld_drain`；下杯容量采用16 mm深现行边界，不采用历史10 mm名义深度字段。
- C16：圆环`deliverables/process/ring-final-welding-card.json`及`cad/generated/ring-baseline/ring-precoat-design.json`的资源规划。八翼费用/库存另见`project/pilot-production-design.yaml`、`studies/COMPETITION-DESIGN/results/pilot-production-20261007.json`及HJ-P-01。
- C17：`deliverables/process/NDT-inspection-card.md`、`deliverables/process/cleanliness-inspection-card.md`及`deliverables/process/manufacturing-and-inspection-card.md`。
- C18：`cad/generated/ring-baseline/ring-precoat-design.json`、`cad/generated/ring-baseline/ring-precoat-eight-windows-17solids.step`及HJ-S01；供料关系和温度效率为设计输入，几何重读与质量/热量积分单独记录。

## 3 提交时的引用规则

正文和图表使用上述编号或工艺卡号连接到同一来源。新圆环名义几何、共用守恒式、八翼已算结果和试制目标各保留对象与条件；受载弹性偏移、焊后残余位置度、精整轴线变化分别报告。比赛论证围绕结构选择、材料分工、制造顺序、工位可实施性和质量评价展开。
