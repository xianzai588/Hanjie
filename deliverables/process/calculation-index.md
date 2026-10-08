# 关键设计数字与计算来源索引

现行主设计为8P-R2-t15八翼径向柔顺槽座体，采用壳外CI-A1高镍首层、低碳Ni99第二层、NiFe55两道最终连接及真实门架/内锥胀套/铜环。统一参数源为project/submission-baseline.yaml。以下按物理对象标明设计输入、守恒核算、已算数值、历史比较及方法目标，路径以仓库根目录为起点。

## 1 关键数字和用途

| 编号 | 对象及状态 | 关键数字 | 设计用途及边界 |
| --- | --- | --- | --- |
| C01 | 8P-R2-t15及壳体，名义设计几何 | QT厚15 mm、孔Ø40、外R74.98、z100～115；八槽宽4、槽端R2、最深R39；壳R75～80、z0～200 | 定义柔顺结构、装配和真实外缘可用行程；名义径向间隙0.02 mm，生产装配0.01～0.04 mm |
| C02 | 历史冷态构型比较，8×18 mm等效弹性接口 | 八翼/圆环质量0.997/1.772 kg；受载孔轴弹性偏移直径19.218/11.821 μm；应变能310.79/201.63 N·mm | 用于解释开口结构减重及刚性代价；该旧接口与现行稳定16 mm接口分别记录，构型趋势不替代制造残余 |
| C03 | 最终HJ-W-01路径及能量守恒 | 每翼实际18 mm，端部各1 mm过渡，稳定16 mm；八段稳定128 mm，两道实际288 mm；300 J/mm、86.4 kJ、174.545 s | 承载按128 mm、供料和热量按288 mm；两道共同形成一个最终喉部，不重复增加承载长度 |
| C04 | 最终分道供丝及几何包络 | 根3.42/盖3.78±0.05 mm/s、Ø1.60±0.01；耗丝628.364 mm，15%备料722.618 mm；截面积7.538777～9.007008 mm²，等效焊脚3.882983～4.244292 mm | 稳定区两脚≥3.80、喉厚≥2.687006、完整自由面在4.30三角包络；理想喉厚余58.677 μm，实际局部分布、双侧熔合分别确认 |
| C05 | CI-A1首层连续热史，既有模型结果 | 100 mm/min、末1.2 s从110→80 A；沉积15.329235 g、净热184.675927 kJ、电弧92.552 s；逐面液化判据累计1051.200939 mm²；首道至入炉1694.302 s | 保留给定热源下逐面同时液化判据及真实翼间时序；液化累计面积与接头容量、实际输运稀释分别评价 |
| C06 | 首层八翼炉冷，已算温度过程 | 入炉至室温24300 s=6.75 h；首道至室温25994.302 s=7.22064 h；末态20.04873～20.04998℃ | 计算首层缓冷库存及交接时刻，温度已降至室温与机械残余状态分开标识 |
| C07 | 真实槽公差族及首层供料 | 最大槽176.157710 mm³/翼；设计密度8.89 mg/mm³需1.566042 g；0.15 g/s情景下100/120 mm/min余量+0.124682/−0.164543 g | 保持100 mm/min基线；100速度+2%仍余0.090656 g，120在0.17 g/s、速度+2%时欠0.009813 g，故不采用提速候选 |
| C08 | 法向分层、加工及重熔尺寸链 | 首层0.70±0.05 mm；槽R1.50±0.10，R修整=R槽−留层；第二层料高≥1.75、齐平总层1.40～1.60；第二层≥0.65 mm | 累计重熔≤0.40时总残层≥1.00、第二层≥0.25 mm；圆角、混合带与实际传力范围同截面检查 |
| C09 | 第二层双轨，设计供料及热量 | R70.48/R73.48双轨；总308.508351 mm、154.254176 s、76.355817 kJ；DMNA099 Ø1.143±0.020、8.00±0.20；新增体积131.441733～167.961640 mm³/翼 | 两轨同一定长棒；采购两根914.4 mm；局部覆盖、连续熔合及材料区组织分别评价，C28 |
| C10 | 逐层均匀混合条件情景 | 首层C1.265～1.530、第二层C0.1355～0.2380、最终C0.03055～0.07160 wt%；首层入第二层15%对应条件重熔约0.1745 mm | 稀释比例为诊断输入；Fe–Ni–C筛查结合Si/Mn和冷却，不能反向证明实际稀释窗口 |
| C11 | 历史八翼完全卸夹制造家族 | 热残余孔轴基准/空间/时间13.003/15.584/13.741 μm；总预算49.503/52.084/50.241 μm；孔径极差约25.961 μm | 最不利超50 μm目标2.084 μm，空间/时间差16.56%/5.38%；用于修订制造继承、热源/接触及释放边界 |
| C12 | 位置度设计预算，直径值 | 28+2+6.5+13.5=50 μm；热内部目标12 μm时48.5 μm，余1.5 μm；无去料且孔径直接合格时热分支20 μm | 工装6.5 μm径向夹紧已含在28 μm非热直径项，与后列6.5 μm微珩轴线变化不同 |
| C13 | 真实反锥/胀套/门架，实体工装有限元 | 5 kN侧向、170 kN·mm及两头各200 N轻击容量包络；h2/h1.5轴移3.695/3.750 μm，差1.46%；峰应力26.64/30.79 MPa、峰差约13.5%；串联包络5.602 μm | 使用HJ-003/006/012/013详细力链；螺栓、法兰及界面柔度另串联；重复定位与热态接触按工装卡确认 |
| C14 | 铜屏障和退出，热/流/包络核算 | 净铜≥67.60 g；八路水总≥0.60 L/min；铜≤45℃、下座≤48℃；铜瓣退1.10±0.05 mm；制造全周通止净隙≥0.10 mm | 维持连续阻粒、冷却和朝上回收；气幕10～15 L/min辅助输运，不能代替实体屏障 |
| C15 | 后序液路，几何及流阻计算 | 微珩液排量154.510、供液≤60 mL/min；下杯20.957/故障需求18.803 mL；PT/UT盘47.733/21.203 mL | 规定黏度牛顿液的排液能力与UT凝胶流变分别评价；微珩与PT/UT回收分工序装入 |
| C16 | 孔径、孔壁和有限微珩，方法目标 | 成品40.000～40.025 mm；焊前40.006～40.008为补偿核验输入；方法U≤0.5 μm；径向去除≤3、直径增加≤6 μm | 位置度先检查，微珩只恢复欠尺寸孔；前后复检孔轴、孔径及孔壁，封闭回收磨屑 |
| C17 | 小批资源及费用，规划情景 | 8件/8 h、3600 s间隔；首层8位、第二层9预留位、延迟24位，共41位；PT每阶段2位、最终焊接子程序462.5 s | 首层热史已算、第二层30960 s资源预留；PT/转运/环境冷却另配，热过程及延迟小计40.42 h，跨日组织；完整夹具循环最低702.5 s另加退出/温控延长，80%工时下≤4.10件/h |
| C18 | 现行128 mm焊缝组容量需求，新计算 | 最低焊脚3.80、喉厚2.687006、面积343.936738 mm²；静载需求42.249313 MPa；30 MPa@2×10⁶、m3目标下条件D0.672182，需参考范围26.279490 MPa | 正应力σ=Fa/A+M·r/I最小，剪应力τ=Fr/A；旧3.50 mm需求45.870683、D0.860268，修订3.80在既有供丝包络内；目标曲线与实测性能分别记录 |
| C19 | 历史冷态实体构件需求，旧8×18接口 | QT/NiFe/Q235组合VM189.42/112.74/58.13 MPa，两网格差0.60%/0.22%/0.41% | 保留旧构件应力分布；现行稳定长度和制造残余状态进入同状态加载/卸载，局部槽根、PMZ及永久孔形另评价 |
| C20 | PT/UT及洁净，试制方法目标 | PT15～35℃、渗透15～30 min、显像10～30 min；UT同曲率对比块、SNR≥12 dB；牺牲件残留+U≤0.50 mg、定量限≤0.10 mg | 工艺硬颗粒检出即拒收；正常产品干态检查，牺牲件提取仅用于屏障方法资格 |
| C21 | 本轮表面源/出生域修复，有界诊断 | dt0.125/0.0625 s均在0.5 s停止，峰2810.303/2823.076℃；共同0.375 s峰温差8.67%；载荷组装误差≤2.27×10⁻¹³ W | 源仅加载中点实际自由面及内部前沿；功率、供料、宽度、物性不变。越无蒸发域且时间精度未通过，不推进机械或用终点0.45%授予资格 |
| C22 | 壳体制造与独立CMM，设计及方法资格目标 | A平面度2 μm；B1/B2 z20～30/170～180、各10 mm；圆度3、按A定向共圆柱4 μm；孔5截面z100.5/104/107.5/111/114.5；方法k2设计U1.64 μm | U资格≤2 μm，工件测区/参考器残余温差≤±0.2℃；设计预算不能冒充实测校准结果 |
| C23 | 气水与抽吸接口及故障保持，工程指令 | 4抽口R78/z210、45°起等分；转运前退15至R93；前吹/后吹、独立水支路与阀态按HJ-C-03 | 抽口全退位才允许上提；失泵不宣称铜环仍保持45℃，漏水/失气/失电按实际屏障保持和隔离动作 |
| C24 | 副压环外驱动与真实工具扫掠，局部接口设计 | 压环ID74/OD104/t12、三足R37；三缸146.45/207.11/146.45 N；枪丝转位升150 mm；192个限定姿态及完整竖直扫掠最小名义净隙0.915611 mm，扣0.65 mm公差取≥0.25 mm | 臂内细端3×20、球座Ø14；手算校核轴向压紧、退位和止动选型，保持原5 kN径向力链；不代替整工装热态资格或实物装机校验 |
| C25 | 局部不等腿、凹陷与空间成形包络 | 以原3.50±0.05供丝、真实公差实体和4.30三角禁入包络计算；喉部≥2.687006 mm、两侧焊脚均≥3.80 mm | 将等面积余量落实到局部几何；单个3.68±0.05供丝对照未采用，不授予熔合资格 |
| C26 | 当前04名义装配实际覆盖 | 13个导入根、33实体，几何有效；已移出停用轻击器 | 既有名义力链、固定铜盘和根道枪丝包络；禁入体及见证片占位也计数，HJ-022/023新增接口未建成04实体 |
| C27 | 原始证据迁移及宏观制造表示 | 首次界面、PMZ/HAZ、重熔存留、容量四类问题逐项组包；原料/沉积态/工序身份分列 | 公开证据可组合，完整同件PQR不是唯一来源；输入不足的制造性能链停止，几何/容量/接口设计可继续 |
| C28 | 第二层同材料目录供货与定长棒供料 | DMNA099 Ø1.143×914.4 mm；采购验收±0.020；8.00±0.20 mm/s；180 mm/翼×8段，整棒2根 | 最大槽面补高需求、公差反算、质量/焓及实际备料；不将设计公差写成供方保证 |
| C29 | 一次根/盖分道成形修订 | 根3.42/盖3.78±0.05；原公差下S7.538777～9.007008 mm²，名义耗丝628.364 mm | 联合轮廓界，额外进入焓0.322～0.351 kJ计入原86.4 kJ；实际熔合/留层/残余尚未资格 |
| C30 | 原生塑性历史复用及冷态去料接口 | 旧实际删除/再加入320点PEEQ差0；新增原生重启/变形A/B/整单元删除准备 | 非真实重熔参考验证，尚无本件有效冷态/后续装配网格；未执行切削再平衡 |

## 2 对应文件和结果路径

- C01：`project/submission-baseline.yaml`；`simulation/competition-r4/geometry/8P-R2-t15-manifest.json`；`cad/generated/competition-design/competition-assembly-r4.step`；HJ-001及HJ-021。
- C02：`deliverables/recovered-20261007/焊接工艺设计论文-正文.pdf`第8页，旧构型比较采用壳底固定、孔40.008 mm、8×18 mm等效弹性接口、Fr/Fa各5000 N及Mx250 kN·mm；绝对响应尚未全部满足5%离散目标，作为趋势来源。
- C03、C04：`project/submission-baseline.yaml`；`deliverables/process/joint-process-card.md`及`deliverables/process/joint-process-card.json`；`studies/COMPETITION-DESIGN/results/delivery-joint-capacity-20261008.json`。实际路径、稳定长度及供丝分账以现行源为准，旧名义布局评估按18 mm有效长度的容量排序另存历史。
- C05：`simulation/competition-r4/results/mma-eight-wing-phase-front-t4-end80-r12-20261007/actual-eight-wing-thermal-audit.json`，首层23 V、MMA效率0.8及末端降流情景保留原方法输入。
- C06：`simulation/competition-r4/results/mma-eight-wing-furnace-phase-front-20261007/cold-thermal-handoff-audit.json`。
- C07：`deliverables/process/precoat-tolerance-and-feed-card.md`；`cad/generated/precoat-tolerance-family-20261007/`；提速供料比较`output/review/first-precoat-speed120-20261007/speed120-supply-window.json`。
- C08：`deliverables/process/independent-precoat-design-card.md`；`cad/generated/independent-precoat-curved/precoat-stack-R15-R08.step`；HJ-017/019及真实法向公差族。
- C09：`project/precoat-process-design.yaml`及`project/submission-baseline.yaml`的`precoat_ledger`；`deliverables/process/first-layer-input-card.md`，第二层双轨实际长度与热功率积分分别核算。
- C10：`studies/COMPETITION-DESIGN/results/current-section-interface.json`；`project/materials.yaml`；正文引用的Oikawa/Ueshima公开Fe–Ni–C数据库及相平衡结果。
- C11：`simulation/competition-r4/results/verification.json`；`studies/COMPETITION-DESIGN/results/independent-revision-audit.json`。保存旧材料接口、原网格及时间条件。
- C12、C16：`deliverables/process/bore-compensation-and-finish-card.md`；`project/competition-design.yaml`及`project/submission-baseline.yaml`。孔径补偿输入、尺寸判定、热残余及微珩分配分别使用。
- C13：`simulation/competition-r4/results/fixture-axis-solid-core-h2/result.json`和`simulation/competition-r4/results/fixture-axis-solid-core-h1.5/result.json`；`deliverables/process/fixture-load-and-transfer-card.md`。局部均匀压缩、整体轴移与接口串联按原分项保存。
- C14：`studies/COMPETITION-DESIGN/results/engineering-checks-r3.json`；`deliverables/process/copper-shield-card.md`及`deliverables/process/clean-shield-engineering-detail.md`；HJ-009～014。
- C15：`studies/COMPETITION-DESIGN/results/postweld-isolation.json`；`project/competition-design.yaml`的`postweld_drain`；HJ-015/016/018。下杯使用16 mm深现行边界。
- C17：`project/pilot-production-design.yaml`；`studies/COMPETITION-DESIGN/results/pilot-production-20261007.json`；`deliverables/process/pilot-production-and-resource-card.md`。共享实际作业直接运行费144.97元/件，4人专线整班口径215.58元/件，设备及资格试验另计。
- C18：`studies/COMPETITION-DESIGN/delivery_joint_capacity.py`及`studies/COMPETITION-DESIGN/results/delivery-joint-capacity-20261008.json`；设定载荷来源`project/load-basis-v1.yaml`。同最低焊脚3.80 mm下，6P静载56.332418 MPa、条件D1.593321、需35.039320 MPa；全周11.479007 MPa、D0.013482、需7.140056 MPa。
- C19：`simulation/competition-r4/results/service-t15-affine-h2-rootlocal0.35/service-area-result.json`和`simulation/competition-r4/results/service-t15-affine-h2-rootlocal0.25/service-area-result.json`；`simulation/competition-r4/postprocess_service.py`。
- C20：`deliverables/process/NDT-inspection-card.md`；`deliverables/process/cleanliness-inspection-card.md`；`deliverables/process/manufacturing-and-inspection-card.md`；HJ-020同曲率UT对比块及声路覆盖。

- C21：`simulation/competition-r4/results/implementation-source-compatibility-20261008/summary.md`、`compatibility-and-domain-audit.json`及两组逐步源/质量/热账；批准预算见同目录`approved-run-plan.json`。
- C22：`deliverables/process/shell-datum-and-cmm-execution-card.md`；HJ-022及HJ-M-02。
- C23：`deliverables/process/gas-water-fault-execution-card.md`；HJ-009/023。
- C24：`docs/review/pressure-interface-design-20261008.md`；`cad/parametric/check_pressure_interfaces.py`；`cad/generated/engineering-supplements-20261007/pressure-interface-clearance.json`；HJ-023。
- C25：`studies/COMPETITION-DESIGN/delivery_section_envelope.py`及`studies/COMPETITION-DESIGN/results/section-forming-envelope-20261008.json/md`；分层图来自既有公差尺寸链，不画未经来源限定的PMZ宽度。
- C26：`cad/generated/competition-design/assembly-coverage-20261008.json`；`src/hanjie/domain/competition_design.py`的单装配出口；`studies/COMPETITION-DESIGN/export_current_assembly.py`。未重算原assessment或工装矩阵。
- C27：`docs/review/evidence-transfer-20261008.md`；`docs/review/macroscopic-manufacturing-plan-20261008.md`；`docs/review/macroscopic-input-independent-review-20261008.md`。第二层终端PT从缓冷至室温时起算≥24 h，为项目设计窗口；41位及40.42 h原预算不变。

- C28：`studies/COMPETITION-DESIGN/second_layer_supply_decision_20261008.py`及`results/second-layer-supply-decision-20261008.json/md`；供方原TDS及HJ-W-00C/00D。
- C29：`studies/COMPETITION-DESIGN/final_pass_forming_revision_20261008.py`及`results/final-pass-forming-revision-20261008.json/md`；HJ-W-01和HJ-002；不重跑旧C25。
- C30：`simulation/competition-r4/prepare_native_cold_cut.py`、`results/native-interface-adaptation-20261008/interface-readback.json`、`docs/review/native-interface-adaptation-20261008.md`；旧实际功能源为`results/calculix-plastic-deposition-cut-benchmark-restartfix-20261007/reactivated-substrate-history/`。本轮开算前独立输入审查见`docs/review/second-round-input-independent-audit-20261008.md`。

## 3 制造验证状态和引用规则

现行材料链已有几何、公差、供料、热史、相平衡条件计算及工装/屏障工程依据；首层尚未形成可继承冷态机械状态，首次及最终有效接头、实际切削存留应力、完全卸夹孔轴/孔径和同状态承载按同一制造链继续闭合。历史超差和未收敛场保留原输入身份，当前名义焊缝组容量需求不代替局部槽根、PMZ及制造残余评价。数值工作不以实物为开始条件，试制记录按HJ-M-01完成工程确认。

正文及图表引用同一编号或工艺卡号。热残余位置度、受载弹性孔轴、卸载永久变化和精整轴线变化分别报告；供料体积、模型液化面积、实际连续接头和容量需求分别评价。现行提交只使用8P主链，历史圆环、短梁及其他方案保留在另册比较资料。
