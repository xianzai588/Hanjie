# V4 修正执行清单

**基于二次深度评审的关键修正**  
**日期**：2026-09-03 下午

---

## 核心判断修正

### 评分重新校准

| 状态 | 评分 | 说明 |
| --- | ---: | --- |
| 项目架构/规划成熟度 | 85 | ✅ README、计划文档已 V4 |
| **当前真正 PDF 提交态** | **81-83** | ⚠️ 技术报告仍 V2 |
| 修正报告一致性 + 误差预算 | 84-85 | ⏳ 本轮目标 |
| 完成可信 3D FE + 公平结构比较 | 86-88 | ⏳ 下一轮 |
| 温度门控得到有效对照结果 | 87-89 | ⏳ 第三轮 |
| 再有少量真实实验 | 89-91+ | 🎯 最终目标 |

**关键认识**：比赛是盲审无答辩，评委不会听你解释 README，最终 PDF 自己必须完全站得住。

---

## P0 级立即修正（今天必须完成）

### P0-1：纠正 H7/h6 表述 ⚠️

**当前错误**：
- 总结里写"H7/h6 过渡配合"
- 实际上 H7/h6 属于**定位间隙配合**（locational clearance fit）
- H7/k6、H7/m6 才是过渡配合

**geometry.json 实际参数**：
- 翼端 R74.98 mm
- 壳体内半径 R75 mm
- 名义径向间隙约 0.02 mm
- 本质是**小间隙精密定心设计**

**修正为**：
> 采用小间隙精密定心设计；若最终按 ISO 公差带表达，H7/h6 为定位间隙配合，实际极限间隙需结合 Ø150 名义尺寸重新计算并落实到制造图。

**修改文件**：
- [ ] docs/EXECUTIVE_SUMMARY.md
- [ ] docs/daily-summary-2026-09-03.md
- [ ] docs/response-to-deep-review.md
- [ ] docs/05-design-assumptions.md
- [ ] README.md（如果提到）

---

### P0-2：修正误差预算"未闭合"事实 ⚠️

**当前问题**：
V3 误差预算装配链合计：**0.035 mm > 0.025 mm**（目标）

| 项目 | 径向预算 (mm) |
| --- | ---: |
| A 基准 | 0.005 |
| B 轴线 | 0.003 |
| 心轴重复性 | 0.008 |
| 初始偏心 | 0.005 |
| 焊接变形 | 0.012 |
| 松夹回弹 | 0.002 |
| **合计** | **0.035** |

**不能说**："误差预算硬伤已修复" ❌

**应该说**：
> 误差预算口径已修正（装配链/自动化链分离），但当前最坏情况预算尚未闭合（0.035 > 0.025），成为 V4 重点优化约束。

**V4 目标分配**（设计指标）：

| 项目 | V4 目标 (mm) | 依据 |
| --- | ---: | --- |
| A/B 基准建立 | ≤0.004 | 精密装夹基准 |
| 定位夹具 | ≤0.004 | 锥形心轴自动找正 |
| 初始装配 | ≤0.003 | 小间隙精密定心 |
| 焊接变形 | ≤0.011 | 柔顺结构+自适应跳焊 |
| 松夹回弹 | ≤0.003 | 可释放夹具 |
| **合计** | **≤0.025** | |

**关键**：这些是设计指标，随后必须回答：
- 为什么夹具能做到 0.004？→ 精密夹具设计
- 为什么焊接变形允许 0.011？→ 热结构优化 + 自适应跳焊

**误差预算反而成为四个创新点的顶层约束。**

**修改文件**：
- [ ] docs/validation/position-error-budget-v3.md
- [ ] docs/EXECUTIVE_SUMMARY.md
- [ ] docs/daily-summary-2026-09-03.md
- [ ] docs/v3-progress-report.md

---

### P0-3：建立 technical-report-v4.md，冻结 V2 ⚠️

**当前问题**：
```
README = V4
开发计划 = V4
但技术报告 = V2
```

**立即行动**：
1. 冻结 `technical-report-v2.md`（历史版本）
2. 创建 `technical-report-v4.md`（新主稿）
3. 创建 `build_technical_report_v4.py`
4. 全面同步 V4 参数：
   - R74.98 小间隙精密定心
   - 锥形心轴 1:50
   - V3 误差预算（未闭合但方向正确）
   - V4 主叙事和四个创新点
5. 所有"尚未实现的创新"标为 `proposed / to-be-verified`

**新目录结构**：
```
deliverables/report/
├─ technical-report-v2.md       # 冻结历史
├─ technical-report-v4.md       # 新主稿
├─ build_technical_report_v4.py # 新生成器
└─ figures-v4/                  # 新图集
```

**修改文件**：
- [ ] deliverables/report/technical-report-v4.md（新建）
- [ ] deliverables/report/build_technical_report_v4.py（新建）

---

### P0-4：建立 evidence/claims.yaml ⚠️

**立即建立证据清单系统**，不要等到 P2。

**示例**：

```yaml
CLAIM-001:
  claim: "QT450-10/Q235B 可采用镍基填充 TIG 焊接"
  status: "supported"
  evidence:
    - LIT-005
    - LIT-012
  confidence: "high"

CLAIM-017:
  claim: "六点低拘束结构降低位置度漂移"
  status: "unresolved"
  supporting_evidence:
    - ROM-006  # 降阶模型支持
  conflicting_evidence:
    - FE2D-003  # 二维 FE 反例
  required_evidence:
    - FE3D-BASE  # 3D Baseline
    - FE3D-6P    # 3D 六点
  confidence: "low"
  publication_status: "hypothesis"
  allowed_wording: "候选结构之一"

CLAIM-025:
  claim: "温度门控自适应跳焊优于固定 S3"
  status: "untested"
  required_evidence:
    - SIM-adaptive-vs-S3
  confidence: "hypothesis"
  publication_status: "proposed"

CLAIM-030:
  claim: "焊前反变形补偿降低最终位置度"
  status: "untested"
  required_evidence:
    - SIM-compensation
  confidence: "hypothesis"
  publication_status: "proposed"
```

**修改文件**：
- [ ] evidence/claims.yaml（新建）
- [ ] evidence/assumptions.yaml（新建）
- [ ] evidence/verification.csv（新建）

---

## 执行时间表（修正后）

### 9 月 3-5 日：提交基线清洗 ⏳

**Gate A：不存在一个设计参数在两个文档里给出两个值**

- [ ] H7/h6 表述纠正
- [ ] 误差预算改为"未闭合但方向正确"
- [ ] V2/V4 参数一致性扫描
- [ ] `technical-report-v4.md` 建立
- [ ] `claims.yaml` 建立
- [ ] 最终论文新目录（8 章结构）

---

### 9 月 5-10 日：3D FE Baseline ⏳

**只完成**：Continuous + rigid fixture + baseline process

**Gate B：模型自己先站得住**

- [ ] 真正 3D 壳体 + 轴承座
- [ ] 温度相关材料参数
- [ ] 移动热源（Goldak/高斯）
- [ ] 热-弹塑性顺序耦合
- [ ] 完全冷却后松夹
- [ ] 拟合 Ø40 孔轴线 → 位置度
- [ ] 网格收敛性验证（变化 < 5%）

**不追求**：熔池 CFD（资源有限）

---

### 9 月 10-14 日：公平结构比较 ⏳

**Gate C：六点到底是不是值得继续**

统一边界，只改变结构变量：
- [ ] Continuous（Baseline）
- [ ] 4-point
- [ ] 6-point
- [ ] 8-point

比较指标：
- P（位置度）
- 最大变形
- 热峰值
- 热梯度
- 焊缝热点应力
- 周期时间
- 制造复杂度

**关键**：如果六点输，换方案，不要保六点。

---

### 9 月 14-18 日：自适应跳焊 ⏳

**Gate D：必须比固定 baseline 有可解释改善**

对比方案：
- S1 顺序
- S2 对称
- S3 固定跳焊
- Thermal Gate（温度阈值门控）
- Dynamic（预测式动态顺序）

第一版：规则控制，不上 MPC/AI

---

### 9 月 18-22 日：多目标优化 ⏳

这时再产生 Pareto front

设计变量：
- N（连接点数）
- L_w（焊段长度）
- W_s（槽宽）
- K_f（夹具刚度）
- q（线能量）

目标：min(P, σ_hotspot, Q, t_cycle)

---

### 9 月 22-26 日：反变形补偿 ⏳

用已经可信的模型测试：
- 不补偿
- 静态补偿
- 根据初始装配偏差自适应补偿

---

### 9 月底：V4 技术报告第一完整稿 ⏳

论文从"V4 规划稿"变成"V4 结果稿"

---

## 最终提交前的 5 个"高奖门"

| Gate | 必须满足 |
| --- | --- |
| G1 题目响应 | 五个比赛维度都明确回答 |
| G2 主创新 | 至少 2 个创新有定量 baseline 对照 |
| G3 数值可信 | 核心 FE 收敛、BC、材料、热源清晰 |
| G4 证据完整 | 每个强结论都有 evidence ID |
| G5 盲审表现 | 3 分钟能看懂"问题—创新—结果—可信度" |

**五个都过，再谈 88-90。**

---

## 当前最值得做的第一件事

**不是写温度门控代码**

而是：

> 建立 `technical-report-v4.md` + `claims.yaml`，全面同步 R74.98、锥形心轴、V3 误差预算和 V4 主叙事，并把所有"尚未实现的创新"统一标为 `proposed / to-be-verified`。

完成这一步后，再正式进入 **3D FE 技术攻坚**。

---

## 核心原则（修正后）

1. ✅ 冻结 V4 主张
2. ✅ 先修提交物一致性和误差预算
3. ✅ 再建立一个可信的 3D baseline
4. ✅ 模型通过收敛和物理检查后，统一边界比较连续/4/6/8 结构
5. ✅ 只有得到结果以后，才允许更新论文中的创新结论

**不要让论文提前写"已经验证的成果"，而实际上还是"计划中的创新"。**
