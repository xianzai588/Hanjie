# P1A README

**任务**：Gate C-pre / 三维结构静刚度公平筛选  
**版本**：V4-P1A  
**状态**：P1A Phase 1 - 七个实体已生成，等待独立几何审查

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
├── meshes/                        # 网格文件（coarse/medium/fine）
├── raw/                           # 原始求解器输出
├── processed/                     # 处理后结果
│   ├── results.csv                # 主结果表
│   ├── convergence.csv            # 收敛表
│   └── screening-summary.json     # 筛选摘要
├── figures/                       # 图表
│   ├── polar-radial-compliance.svg
│   └── pareto-stiffness-stress-mass.svg
└── stiffness-screening-v4.md      # 筛选技术报告
```

---

## 两套公平设计族

### FAIR-A：固定总外缘有效连接宽度 108 mm
- 回答："拓扑本身哪个好？"
- 4P: 27 mm/段 × 4 = 108 mm
- 6P: 18 mm/段 × 6 = 108 mm
- 8P: 13.5 mm/段 × 8 = 108 mm

### FAIR-B：固定每段外缘有效连接宽度 18 mm
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

---

**当前状态**：七个真实 OCC 实体已生成并通过脚本自检；当前暂停等待独立几何审查。审查通过前不进入结构性能筛选。
