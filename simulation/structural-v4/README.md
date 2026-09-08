# P1A README

**任务**：Gate C-pre / 三维结构静刚度公平筛选  
**版本**：V4-P1A  
**状态**：P1A Phase 1 - 接口修正完成，七个实体通过独立几何审查

---

## 目标

无预设结论地筛选进入后续三维焊接热—结构 FE 的结构候选：
- 连续环形座体（Continuous）
- 四点离散连接（4P）
- 六点离散连接（6P）
- 八点离散连接（8P）

**最终输出**：Continuous + 最多两个离散候选 → 进入 Gate B/C 焊接 FE

---

## 目录结构

```
simulation/structural-v4/
├── P1A-design-inputs.md           # 设计输入冻结文档
├── P1A-status.md                  # 执行状态追踪
├── README.md                      # 本文件
├── configs/                       # 模型配置文件
│   ├── continuous.json
│   ├── 4p-fair-a.json
│   ├── 4p-fair-b.json
│   ├── 6p-fair-a.json
│   ├── 6p-fair-b.json
│   ├── 8p-fair-a.json
│   └── 8p-fair-b.json
├── models/                        # 每个目录含 STEP/BREP/geometry-manifest.json
│   ├── continuous/
│   ├── 4p-fair-a/
│   ├── 4p-fair-b/
│   ├── 6p-fair-a/
│   ├── 6p-fair-b/
│   ├── 8p-fair-a/
│   └── 8p-fair-b/
├── common/                        # 独立壳体实体（Ø160×H200×t5）
│   ├── shell.brep
│   └── shell.step
├── meshes/                        # 网格文件（coarse/medium/fine）
├── results/static-screening/      # 本地三维线弹性静力筛查结果
│   ├── static-screening-raw.json  # 294 个方向/边界原始结果
│   ├── static-screening.csv       # 汇总主表
│   ├── static-screening-analysis.json
│   └── static-screening-analysis.md
├── figures/                       # 图表
│   ├── polar-radial-compliance.svg
│   └── pareto-stiffness-stress-mass.svg
└── stiffness-screening-v4.md      # 筛选技术报告
```

---

## 两套公平设计族

### FAIR-A：固定 R74.98 圆柱接口总弧长 108 mm
- 回答："拓扑本身哪个好？"
- 4P: 27 mm/段 × 4 = 108 mm
- 6P: 18 mm/段 × 6 = 108 mm
- 8P: 13.5 mm/段 × 8 = 108 mm

### FAIR-B：固定每段 R74.98 圆柱接口弧长 18 mm
- 回答："实际工程方案哪个好？"
- 4P: 18 mm/段 × 4 = 72 mm
- 6P: 18 mm/段 × 6 = 108 mm
- 8P: 18 mm/段 × 8 = 144 mm

**不要混淆 FAIR-A 和 FAIR-B 的结论。**

---

## 主要指标

| 指标 | 符号 | 单位 |
| --- | --- | --- |
| 最大径向柔度 | $C_{r,\max}$ | mm/kN |
| 径向各向异性 | $A_r$ | - |
| 轴向柔度 | $C_z$ | mm/kN |
| 倾覆柔度 | $C_\theta$ | rad/(N·m) |
| 槽根区域应力 | $\sigma_{\text{slot}}/F$ | MPa/kN |
| 材料体积/质量 | $V, m$ | mm³, kg |

---

## Gate C-pre 通过条件

1. 四种结构均完成统一条件 3D 静力比较
2. FAIR-A / FAIR-B 明确分离
3. 径向方向扫描完成（7 个方向）
4. 网格收敛通过（位移 <3%, 应力 <10%）
5. 边界敏感性完成（2 种边界）
6. 输出机器可读结果（CSV/JSON）
7. 输出技术报告（stiffness-screening-v4.md）
8. 生成径向柔度极坐标图
9. 生成 Pareto 图
10. 无预设地选出候选

---

## 禁止项

- ❌ 预设"六点最优"
- ❌ 为了理想结果修改判据
- ❌ 做温度门控/预偏置/焊接 FE
- ❌ 只给云图不提供收敛表

---

## 参考文档

- 设计输入：`P1A-design-inputs.md`
- 执行状态：`P1A-status.md`
- V4 统一报告：`deliverables/report/technical-report-v4-unified.md`
- 几何参数：`cad/parametric/geometry.json`
- 实体生成：`generate_seat_geometry.py`
- 独立审查材料：`geometry-audit.md`
- 独立回读程序：`audit_geometry_independent.py`
- 机器可读审查结果：`geometry-independent-audit.json`

---

**当前状态**：七个真实 OCC 实体已生成，并通过 STEP/BREP 独立回读、壳体零穿透、接口弧长和局部退化审查。基于新 STEP 的 21 个 Gmsh 三维实体网格和 294 个线弹性静力方向/边界结果已完成，网格收敛与支承敏感性筛查通过；完整焊接热—结构 FE 仍需补充温度场、焊缝本构和显式壳体柔度后独立审查。

## Route B：非正式 STRUCT-UNCERTAINTY

计划 `project/struct-uncertainty-route-b.yaml`，结果 `results/struct-uncertainty/assessment.json`，图 `sensitivity-ranking.png`。当前无实物采集条件，不以热电偶、CMM、金相或实焊作为计划依赖；正式THERMAL-1/STRUCT-0门不变。

已执行432例：Continuous、6P-FAIR_B（同一6P几何）和8P-FAIR_B，各自C/M实体网格；FVM/Elmer两套实际QT局部热历史；3组α/屈服物性情景；均匀半约束、均匀全约束及四种方位的半圈强弱约束；按真实接口面积施加10⁴/10⁶ N/mm³弹性基础。扰动是预设确定性设计假设，不是校准材料范围，也不是概率或置信区间。

这是一条**固有应变敏感性链**。从s=0两侧相邻C单元提取共同P0截面热历史，15–26 s每0.1 s，其余每5 s；温度域覆盖现有QT机械物性曲线。材料点先从20°C升至150°C预热，经真实数值热历史，再作无物理时间含义的单调准静态冷却至20°C。既有3D J2在指定切向约束下生成残余塑性应变，将其铺展至候选实际座体并转成等效节点载荷，送入同一既有3D弹性链。未覆盖的内圈域显式置零固有应变，其体积记录在run-inputs中；不是温度外推。所有材料点塑性功非负、塑性应变迹小于10⁻¹⁰，432例线性平衡最大相对残差2.36×10⁻¹⁴。

壳体A平面/B圆柱作为理想刚性基准，使用实际变形内孔的圆柱及轴倾斜拟合位置度。**没有求解三材料整件瞬态热塑性、焊缝/壳体塑性、松夹接触或候选实际焊序**；局部热循环铺展也未证明整圈能量与热积累保守。因此输出名为`position_sensitivity_diameter_mm`，不能冒充最终焊接残余位置度。

跨全部情景的敏感性直径约为：Continuous 0.000023–0.009945 mm，6P 0.000013–0.009647 mm，8P 0.000013–0.009591 mm。这些小值受简化和对称性影响，**不表示产品满足Ø0.05 mm**。成对换热历史的最大变化为0.0000580 mm；C/M最大变化0.000168 mm，后者仅为观测跨度，未达到三网格GCI验证，不能当误差上界。

排序预设分辨尺度为0.001 mm，再加两候选各自C/M变化。在72组成对情景中，6P/8P全部无法分辨；Continuous相对6P有16组更低、56组无法分辨，相对8P有11组更低、61组无法分辨；原始带符号差值也随情景换向。**没有稳健优胜候选，保留三方案**。不能用最大值排序或未经分辨的百分比改善宣布6P胜出，也不能把局部热差异对这条简化链影响小推广为整件模型结论。

```powershell
python simulation/structural-v4/run_struct_uncertainty.py
python simulation/structural-v4/assess_struct_uncertainty.py
python simulation/thermal-ref/plot_route_b.py
```

归档的`thermal-drivers.npz`及来源记录支持不依赖未入库Elmer中间场重算结构；输入变更或检查点摘要不符会拒绝复用。驱动温度有来源，冷却补段与约束假设单列。原始`cases.csv`、`paired-rankings.csv`和`sensitivity-envelopes.csv`可重建评估与图。下一数字研究应优先候选尺度热历史映射和结构支承假设，不重开Plan9式局部热调参；当前仍为`solver_disagreement / physical_unvalidated`。
