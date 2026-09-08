# Elmer 独立热参考

本目录实现 THERMAL-REF：使用本机 Elmer 原生 `HeatSolve/HeatSolver` 计算三维局部焊接热循环。安装包名为 26.1，实际求解器报告 **9.0，2026-01-20 编译，单进程无 MPI**。不通过 ElmerGUI 自动点击运行，网格和 SIF 由脚本生成，便于重放与核查。

这是**数值诊断参考**，不是已校准热模型，也不是获准的 STRUCT-0 热载荷。`assessment.json` 区分程序执行、部件验证、能量审计和整模型准入；不会自动修改 THERMAL-1 或结构准入标志。

2026-09-08 已执行 `REF-C`：22,421 节点、18,240 个 Hex8、0.1 秒步长、完整 60 秒；600 步非线性迭代全部收敛，运行约 834 秒。三个实际 Elmer 解析对照通过。总输入 19,800 J，填丝体积 90.477868 mm³；终值能量缺陷 4.2293 J（0.02136%），最大瞬态相对缺陷 0.35435%，未通过 0.02% 审计限值。

与 NEST-VF 对比：焊缝中心 RMS 16.96°C、峰温差 51.27°C；QT 近界面 RMS 22.77°C、峰温差 71.44°C；Q235B 近界面 RMS 3.98°C、峰温差 4.69°C。完整曲线和冷却指标见 `results/REF-C/assessment.json` 与 `comparison.png`。粗网格及出生接触近似尚未独立收敛，不能把这些差值归因为 FVM 错误。下一步先处理参考模型的能量与出生表示，再决定细化，而非直接切换正式计算。

## 运行

在仓库根目录运行。需要项目已有的 Python、NumPy、SciPy、PyYAML、matplotlib，以及 Elmer 安装包自带的 Fortran 编译器。无需安装额外求解器。

```powershell
python simulation/thermal-ref/verify_elmer.py --output-dir output/elmer-verification
python simulation/thermal-ref/elmer_reference.py --case REF-C --output-dir output/elmer-ref-c
python simulation/thermal-ref/assess_reference.py output/elmer-ref-c --verification output/elmer-verification
```

`--elmer-home` 指向包含 `bin`、`share`、`stripped_gfortran` 的安装根目录，也可设置 `ELMER_HOME`。默认使用本次提供的 `E:/OpenSource/ElmerFEM-26.1/ElmerFEM-gui-nompi-Windows-AMD64`。输出目录已存在时拒绝覆盖。`--prepare-only` 只生成模型；`--smoke` 仅运行三步，不能成为完整热历史。

`REF-C` 是首轮粗网格诊断。Plan 7 已把 `REF-M` 改为条件入口：生成网格前检查当前插件的 birth-only 与 40 s 严格审计证据，缺失、失败或失效均拒绝；`REF-F/VF` 在本计划内禁止。

## 相同物理输入与独立实现

共同输入冻结在 `project/thermal-reference-elmer.yaml` 引用的 YAML 中：局部窗口 s=±70 mm、n=-36…5 mm、z=±12 mm；QT450-10/Q235B/ERNiFe-CI；0.02 mm 间隙；六条带面积精确截面；495 W；1.5 mm/s；150°C 母材预热；20°C 冷填丝；12 W/(m²·K) 对流及 0.75 发射率；40 秒移动热源和 20 秒冷却；五个固定物理测点。填丝截面积约 1.507964 mm²，等效焊脚约 1.736643 mm，不能标成设计 3.5 mm 已实现。

生成器独立读取这些输入，构建 Hex8 网格、射线首交面、双高斯解析面积积分和分段线性热物性。**不导入 FVM 的几何生成、源分配、材料函数、矩阵、时间积分或 WLS 重构。** 仅评估脚本读取历史 FVM 结果作对照。Elmer 负责有限元积分、装配、线性与非线性解；Fortran 插件负责物性、出生与边界数据，以及独立能量记录。

内部使用 mm、s、kg、W、°C：k 从 W/(m·K) 转为 W/(mm·K)，密度转为 kg/mm³，对流和 Stefan–Boltzmann 常数转为 mm² 面积基准。热源按每面 W 除实际面面积得到 W/mm²；不在活动域重归一化。对流、辐射和导热系数取旧温度，源中心取时间步中点，与冻结 FVM 的时间取值一致。

## 必须保留的离散差异

- Elmer 使用 Hex8 连续温度插值与原生集中质量；FVM 使用单元中心温度及串联面热阻。网格序列和观测重构并不相同。
- 连续出生在固定 FE 网格内以体积分数缩放密度和各向同性导热系数。部分出生单元的接触被平均化，**没有严格移动网格重建**；与 FVM 的活动面面积、半单元距离表示有差异，需要单独的沿焊道分辨率/出生验证。
- 未出生单元保留记录的极小密度与导热比例；只属于未出生材料的节点固定为 20°C。虚材料比例的敏感性尚需审计。
- 温度相关显热和潜热合并为比焓，以割线热容输入 Elmer。出生载荷做 Hex8 一致载荷逆映射，使积分后的冷质量扣焓与节点集中质量对应，防止将高温节点的扣焓错误传到相邻冷节点。
- 原生集中质量对变热容的积分仍可能与独立节点比焓积分有偏差。该偏差写入能量账本，终值和每步相对累计输入的缺陷分别检查，**不得用终值抵消掩盖瞬态偏差**。

因此单个粗网格与 FVM 不一致，不能裁决哪一个求解器正确，也不能据此宣称已完成成熟求解器交叉验证。

## 验证和输出

`verify_elmer.py` 实际调用同一 Elmer 内核及物性/出生回调，执行三项解析对照：不同材料与厚度的串联导热（界面 70°C）；完整跨越相变区的均匀加热（1/2/3 秒为 110/160/220°C）；低导热、非均匀温度下连续加入冷质量的能量守恒与温度下界。它们验证部件，不替代焊接模型的网格与出生验证。

正式结果目录包含 `case.sif`、`run-inputs.json`、`solver.log`、`execution.json`、`history.csv`、`sensors.dat`、`assessment.json`、`comparison.png` 和 `temperature-field.npz`。可重建的原始网格、面数据、插件二进制和中间场不进入 Git；评估脚本生成的 `temperature.vtu` 可用于 VTK 后处理。不得从 `field-00003.dat` 等中间场冒充完整结果。

比较五个固定测点的同时间 RMS、峰温、峰值时刻与 t8/5。焊丝测点出生前不参与比较；60 秒内未完成 800→500°C 冷却时报告截尾，不外推冷却时间。节点历史峰值的空间插值仅为**峰值上包络几何代理**，不等于同一时刻熔池、真实熔合区或 HAZ。

原生热方程与材料接口依据：[Elmer 官方 HeatSolve 源码](https://github.com/ElmerCSC/elmerfem/blob/devel/fem/src/modules/HeatSolve.F90)、[官方 Models Manual](https://www.nic.funet.fi/pub/sci/physics/elmer/doc/ElmerModelsManual.pdf)。接口细节以本机实际运行的解析对照为准，不能把上游开发分支等同于本机二进制。

## Plan 7：机制隔离

计划冻结在 `project/thermal-mechanism-plan7.yaml`，结果见 `results/plan7/assessment.json`。只做出生守恒、35–45 s 重放、C/C 动态与预出生对照、条件化 C→M；495 W、η、源参数和散热参数保持不变。最多两轮有针对性的诊断，不能用持续加密代替准入。

```powershell
python simulation/thermal-ref/run_plan7.py birth
python simulation/thermal-ref/run_plan7.py source-off
python simulation/thermal-ref/run_plan7.py preborn-elmer
python simulation/thermal-ref/run_plan7_fvm.py dynamic
python simulation/thermal-ref/run_plan7_fvm.py preborn
python simulation/thermal-ref/verify_elmer.py --output-dir simulation/thermal-ref/results/plan7/components
python simulation/thermal-ref/assess_plan7.py
```

默认路径已经保存本轮证据，重跑时各命令需指定新的 `--output-dir`；评估器指向含同名子目录的新批次。重放优先取原 REF-C 的 35 s 场，否则读取版本库中的 `restart-state.npz`，并核对网格。额外诊断开关只由 `mechanism.dat` 启用；FVM 对照执行器独立调用既有 FVM 内核，不被 Elmer 生成器或回调导入。

**40 s 定位。** 最后一个有源、有出生步是 39.9→40.0 s，积分 49.5 J；40.0→40.1 s 两者均为零。重放五点温度与原历史最大差约 1.65×10⁻¹²°C。40.1 s 的实测单步缺陷为 0.397794724 J，独立八点 Gauss 质量积分预测 0.397795327 J。原生集中质量先取一致质量的对角，再按总质量缩放，导致节点割线热容发生空间混合，与逐节点 Δh 不完全一致。推导参照[官方 SolverBasics 的集中质量实现](https://github.com/ElmerCSC/elmerfem/blob/devel/fem/src/SolverBasics.F90)，以本机重放和独立积分吻合为实际证据。

这已定位跃迁的主机制，但没有修复能量账：35–45 s 最大未解释余量在 36.0 s，为 1.0883×10⁻⁵ J，仍略超冻结的 10⁻⁵ J 限值。因此 `source_off_mechanism_identified=true`，严格的 `source_off_explained=false`；不通过扣除预测缺陷制造 PASS。

**birth-only。** 两个共享界面节点的 Hex8，一块已知温度母材与一块连续加入的 20°C 焊材；k、热源、对流和辐射全部为零。共享 FE 节点仍共享温度，这个极简试验审计全局焓守恒，不声称模拟物理混合过程。`birth-audit.csv` 逐步输出真实/有效出生质量、理论出生焓、独立场积分 ΔH、期望变化、单步及累计缺陷。有效质量另扣初始虚质量，防止混淆 epsilon 与真实送丝量。

常 cp 对照最大单步误差 2.22×10⁻¹⁶ J；冻结温变物性、150°C 母材时为 6.7271×10⁻⁶ J，累计相对缺陷 0.04958%，未通过。1500°C 压力测试仅完成前 10 步，第 11 步非线性不收敛，失败前最大单步缺陷 0.008310 J。把焓零点平移 12,345 J/kg 后，出生焓非零，缺陷仍一致；这排除了仅因 h(20)=0 导致的空洞测试。三项原解析对照也在新插件下重新通过；相变对照保留 10⁻¹⁰ 容限及失败中止，仅把迭代预算从 80 增至 160，弥补旧结果仅核对温度误差而未严格中止的验证缺口。

**预出生定义。** 双方都使用相同 C 级网格边界，路径内焊材从 t=0 全部存在，与母材一同初始化为 150°C；所有源参数、材料和散热条件保留。该反事实改变初始焊材热库存和可见表面，不能把它与原动态 FVM 直接配对，也不能将消融变化单独解释成接触几何贡献。五点 RMS、共同有效时间窗口 RMS、峰温、峰值时刻、t8/5、输入热量、焊材质量及终值/瞬态焓缺陷统一保存在批次评估中。

双方完整 600 步执行结束，结果如下；RMS 使用相同有效窗口（焊缝中心 20–60 s，其余 0.1–60 s）：

| 测点 | 动态 C/C 峰值差 °C | 预出生 C/C 峰值差 °C | 动态/预出生 RMS °C |
| --- | ---: | ---: | ---: |
| weld center | 71.11 | 68.53 | 26.16 / 23.53 |
| QT near | 113.52 | 108.76 | 33.69 / 32.59 |
| QT far | 68.08 | 65.22 | 20.59 / 19.52 |
| Q235B near | 29.21 | 26.49 | 8.88 / 7.72 |
| Q235B far | 3.64 | 2.10 | 2.03 / 2.56 |

焊缝/QT 近场峰值差仅减少约 3.6%/4.2%，不支持“出生是当前 C 级近场温差的主要来源”。它也不能单独区分异材界面、源的空间承载、FE 插值及粗网格误差。历史 C/VF 的 51/71°C 包含网格分辨率差异，不与此表混用。

四组焊接历史均积分 19,800 J，最终焊材质量约 0.741919 g；预出生组新增质量为零。Elmer 预出生终值焓缺陷仍为 6.2606 J（0.03162%），最大瞬态相对缺陷 0.35381%；能量问题没有随出生消失。两个 FVM C 组终值缺陷绝对值均小于 3×10⁻⁶ J，但守恒本身不证明近场温度正确。

本轮为第 1 次机制隔离，`REF-M` 前置未通过，未运行 M/F/VF；`THERMAL-NUMERICAL-GATE / THERMAL-1 / STRUCT-0` 保持关闭。最多剩一次针对性的焓一致性修正或界面/插值隔离；若仍有数十度冲突，转由真实热电偶数据裁决。图见 `results/plan7/mechanism-diagnostics.png`。
