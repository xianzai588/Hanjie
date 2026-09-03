# V3 → V4 主线重构计划

**基于深度评审意见的关键升级**  
**日期**：2026-09-03  

---

## 核心判断

当前项目：**7/10 省赛竞争力**  
- 优势：工程化、证据分级、诚信度高
- 短板：主创新不够"尖"、仿真可信度低、缺实物

**V4 目标**：**8.5/10 高奖竞争力**  
- 不推翻重做，在当前基础上升级
- 从"数字内容多" → "机理驱动、自适应闭环、可验证"

---

## P0 级主线重构（必须立即完成）

### 1. 主标题和核心叙事修改 ⚠️ 最高优先级

**当前标题**：
> 基于六点柔顺连接结构的 QT450-10/Q235B 主轴承座低变形自动 TIG 异种焊接及数字化质量控制方案

**问题**：
- "六点柔顺"承担整个项目成败
- 但当前证据：降阶模型支持，二维FE不完全支持，网格未收敛，无实物
- FE-003（柔顺+柔顺夹具）反而最差

**V4 新标题**：
> **面向 Ø0.05 mm 位置度的 QT450-10/Q235B 异种材料焊接热—结构协同优化与自适应数字质量控制**

**核心一句话**（所有材料都围绕这句话）：
> 不是单纯"选一种低热输入TIG工艺"，而是以Ø0.05 mm位置度为直接设计目标，通过**参数化低拘束接头、热—结构鲁棒优化、焊前位姿补偿、焊中温度门控自适应跳焊和全过程质量追溯**，构建QT450-10/Q235B异种焊接的**三闭环数字工艺体系**。

**文件修改**：
- [ ] README.md 主标题和项目描述
- [ ] technical-report 题目和摘要
- [ ] 所有演示材料

---

### 2. 四个创新点重构 ⚠️

**不要列12个创新，只保留4个**：

#### 创新点 1：参数化低拘束接头与热—结构协同优化 ⭐⭐⭐
- 不说"六点最优"
- 说"参数化优化得到Pareto前沿，六点处于变形、疲劳和制造复杂度的折中区域"
- 关键：4/6/8/连续结构公平比较 + 多目标优化

#### 创新点 2：基于热状态反馈的自适应对称跳焊策略 ⭐⭐⭐
- 从固定S3升级成温度门控动态选择
- `next_segment = f(T1..T6, ΔT, P_predicted)`
- 这是最有价值的主创新

#### 创新点 3：焊前位姿—焊后变形联合预测的轨迹/反变形补偿 ⭐⭐
- 视觉测初始偏差 → 预测焊接收缩 → 反向补偿
- `x_cmd = x_nominal - predict_shrinkage(offset_initial)`

#### 创新点 4：基于过程数据和证据分级的一件一码数字质量闭环 ⭐
- I/U/v/T + anomaly + model state + inspection + traceability
- 数字化亮点收尾

---

## P0 级技术升级（必须完成）

### 3. 三维热—结构模型 ⚠️ 最大技术短板

**当前问题**：
- 二维FE峰值仅462-562℃，无熔池
- 网格变化29.224%，远未收敛
- FE-003柔顺反而最差

**V4 要求**：
- [ ] 真正3D壳体+轴承座几何
- [ ] 温度相关材料参数
- [ ] 移动焊接热源
- [ ] 真实焊段顺序
- [ ] 夹具边界/释放
- [ ] 热-弹塑性顺序耦合
- [ ] 完全冷却后拟合Ø40孔轴线
- [ ] 网格收敛性验证（变化<5%）

**不要求**：
- ❌ 熔池CFD（资源有限）
- ❌ 相变细节（可简化）

**结果**：
- Baseline vs 4-point vs 6-point vs 8-point
- 统一边界，公平比较
- 给出Pareto前沿

---

### 4. 温度门控自适应跳焊 ⚠️ 主创新

**当前问题**：
- S2/S3因模型对称性得到相同结果
- 不能证明S3更好

**V4 升级**：

```python
class AdaptiveSequenceStrategy:
    """温度状态驱动的动态焊接顺序"""
    
    def select_next_segment(self, state: WeldState) -> int:
        """基于实时状态选择下一焊段
        
        Args:
            state: {
                'T': [T1, T2, ..., T6],  # 当前六区域温度
                'delta_T_max': float,     # 最大温差
                'P_predicted': float,     # 预测位置度
                'Q_accumulated': float,   # 累积热输入
                'welded_mask': [bool],    # 已焊标记
            }
        
        Returns:
            next_segment: 下一个焊段编号
        """
        # 规则控制/MPC，不需要神经网络
        candidates = [i for i, welded in enumerate(state['welded_mask']) 
                      if not welded]
        
        scores = []
        for seg in candidates:
            # 预测焊后状态
            state_next = self.predict(state, seg)
            
            # 多目标评分
            score = (
                w1 * state_next['P_predicted'] +      # 位置度
                w2 * state_next['delta_T_max'] +      # 温差
                w3 * state_next['t_interpass_wait']   # 等待时间
            )
            scores.append(score)
        
        return candidates[np.argmin(scores)]
```

**对比**：

| 方法 | P_sim P95 | 最大温差 | 峰值温度 | 周期时间 |
| --- | ---: | ---: | ---: | ---: |
| S1 固定顺序 | TBD | TBD | TBD | TBD |
| S2 对称 | TBD | TBD | TBD | TBD |
| S3 固定跳焊 | TBD | TBD | TBD | TBD |
| **温度门控S3** | TBD | TBD | TBD | TBD |
| **预测式动态** | TBD | TBD | TBD | TBD |

---

### 5. 焊前反变形补偿 ⚠️

**当前视觉**：
- 只是测ΔX/ΔY/Δθ → 路径变换
- 比较普通

**V4 升级**：

```python
class PreweldCompensation:
    """焊前位姿—焊后变形联合预测补偿"""
    
    def compute_compensation(self, 
                            offset_measured: np.ndarray,
                            weld_params: dict) -> np.ndarray:
        """
        Args:
            offset_measured: 视觉测得的初始装配偏差 [ΔX, ΔY, Δθ]
            weld_params: 焊接参数 {I, v, sequence, ...}
        
        Returns:
            compensation: 预补偿量 [ΔXc, ΔYc, Δθc]
        """
        # 热结构模型预测焊后收缩
        shrinkage_predicted = self.thermal_model.predict(
            offset_initial=offset_measured,
            **weld_params
        )
        
        # 反向补偿
        compensation = -shrinkage_predicted
        
        # 考虑可调节范围
        compensation = np.clip(compensation, -self.max_adjust, self.max_adjust)
        
        return compensation
    
    def apply_compensation(self, 
                          robot_path: Path,
                          compensation: np.ndarray) -> Path:
        """应用补偿到机器人轨迹"""
        # 调整装配姿态或机器人轨迹
        path_compensated = robot_path.transform(compensation)
        return path_compensated
```

**闭环**：
```
焊前视觉测量
    ↓
预测焊后收缩方向
    ↓
计算预补偿量
    ↓
调整轨迹/装配
    ↓
焊接
    ↓
焊后CMM验证
    ↓
反馈校准模型
```

---

## P1 级架构升级

### 6. 参数化多目标优化

**从离散挑选 → 真正优化**：

```python
# 设计变量
x = [N, Lw, Ws, Wa, R, K_fixture, I, v, T_preheat, sequence_type]

# 目标函数
objectives = [
    P_95,           # 位置度P95
    σ_hotspot,      # 槽根应力
    Q_total,        # 总热输入
    t_cycle,        # 周期时间
]

# 约束
constraints = [
    P_model <= 0.025,           # 位置度
    σ_max <= σ_yield / SF,      # 强度
    accessibility == True,      # 焊枪可达
    t_slot >= t_min,           # 最小壁厚
    FAT_check == True,         # 疲劳
]

# 多目标优化（NSGA-II / MOEA）
pareto_front = optimize(objectives, x, constraints)
```

**结果呈现**：
- Pareto前沿图
- 六点方案在前沿上的位置
- 不说"最优"，说"折中区域"

---

### 7. 可校准数字孪生

**当前问题**：
- `structure_factor`/`fixture_factor` 无标定
- 继续跑10万次Monte Carlo没意义

**V4 升级**：

```python
class CalibratableDigitalTwin:
    """可校准数字孪生"""
    
    def calibrate(self, experiments: List[Experiment]):
        """从少量实验数据反演模型参数
        
        Args:
            experiments: [
                {
                    'T_measured': [...],  # 温度曲线
                    'P_measured': float,  # CMM测量位置度
                    'params': {...},      # 工艺参数
                },
                ...
            ]
        """
        # 反演优化
        def objective(theta):
            # theta = [η, structure_factor, fixture_factor, ...]
            error = 0
            for exp in experiments:
                P_sim = self.model.predict(exp['params'], theta)
                error += (P_sim - exp['P_measured'])**2
            return error
        
        theta_optimal = minimize(objective, theta_init)
        
        # 更新模型参数
        self.model.update_parameters(theta_optimal)
        
        return theta_optimal
    
    def uncertainty_quantification(self):
        """量化模型不确定性"""
        # 基于标定数据集的残差
        residuals = [...]
        uncertainty = {
            'bias': np.mean(residuals),
            'std': np.std(residuals),
            'p95': np.percentile(np.abs(residuals), 95),
        }
        return uncertainty
```

**价值**：
- 哪怕1-3条数据都能校准
- 给出模型不确定性
- 真正叫"数字孪生"

---

### 8. 证据清单系统

**当前问题**：
- 测试里有 `test_optimized_is_lower_than_baseline`
- 存在确认偏误风险

**V4 升级**：

创建 `evidence/` 目录：

```yaml
# evidence/claims.yaml

CLAIM-001:
  claim: "QT450-10/Q235B可采用镍基填充TIG焊接"
  status: "supported"
  evidence:
    - LIT-005  # 文献
    - LIT-012
    - LIT-023
  confidence: "high"
  
CLAIM-017:
  claim: "六点柔顺结构降低焊后位置度漂移"
  status: "hypothesis"  # 不是 "proven"
  supporting_evidence:
    - ROM-006   # 降阶模型
  conflicting_evidence:
    - FE-003    # 二维FE反例
  missing_evidence:
    - 3D-FE     # 待完成
    - CMM-001   # 待实物
  confidence: "low-medium"
  next_gate: "3D-FE + 实物验证"
  
CLAIM-025:
  claim: "温度门控自适应跳焊优于固定S3"
  status: "to-be-verified"
  required_evidence:
    - SIM-adaptive-vs-fixed
  confidence: "hypothesis"
```

**测试改名**：

```python
# 不要
def test_optimized_layout_is_lower_than_baseline():
    assert optimized < baseline  # 确认偏误

# 改成
def test_reduced_order_reference_case_matches_frozen_result():
    """回归测试：代码未意外改变基准结果"""
    assert np.isclose(result, FROZEN_REFERENCE, rtol=0.01)
```

---

## 实物证据优先级

**如果能争取到设备/经费**：

### 优先级1：最小物理证据链

不需要几十件，**3个小试就够**：

1. **QT450-10/Q235B 小试焊缝** × 3
   - 不同热输入/预热
   - 宏观截面
   - 熔合情况拍照

2. **显微硬度** × 1条曲线
   - 母材 → HAZ → 焊缝 → HAZ → 母材
   - HV0.2 或 HV0.5

3. **PT检查** × 3件
   - 裂纹检查
   - 拍照记录

4. **温度历史** × 1条曲线
   - 热电偶 或 红外测温
   - 用于模型校准

5. **简单变形测量** × 1件
   - 焊前焊后对比
   - 哪怕只是卡尺/千分尺

**价值**：
- 这5项完成后，可信度跳一级
- 可以做模型校准
- 可以更新 evidence/claims.yaml

### 优先级2：完整验证链（如果时间充足）

- CMM 测量位置度
- 金相组织
- 拉伸/弯曲试验
- 疲劳试样

---

## 软件架构重构（可选，不阻塞比赛）

```
Hanjie/
├─ evidence/
│  ├─ claims.yaml          # 主张清单
│  ├─ assumptions.yaml     # 假设清单
│  └─ verification.csv     # 验证矩阵
│
├─ src/hanjie/
│  ├─ optimization/
│  │  ├─ multi_objective.py
│  │  └─ pareto.py
│  │
│  ├─ control/
│  │  ├─ adaptive_sequence.py    # 温度门控跳焊
│  │  └─ preweld_compensation.py # 反变形补偿
│  │
│  ├─ calibration/
│  │  ├─ parameter_identification.py
│  │  └─ uncertainty_quantification.py
│  │
│  └─ digital_twin/
│     └─ calibratable_model.py
│
└─ pipelines/
   ├─ run_adaptive_sequence_comparison.py
   ├─ run_pareto_optimization.py
   └─ run_model_calibration.py
```

---

## 时间节点（调整）

| 日期 | V3计划 | V4调整 | 状态 |
| --- | --- | --- | --- |
| 09-03 | P0三项修复完成 | ✅ 已完成 | ✅ |
| 09-04 | - | **主线重构**（标题/创新点） | ⏳ |
| 09-10 | 技术报告关键章节 | 3D FE模型建立 | ⏳ |
| 09-17 | 论文8章重构 | **温度门控跳焊** + FE结果 | ⏳ |
| 09-24 | 制造级工程图 | **反变形补偿** + Pareto优化 | ⏳ |
| 10-01 | V3全部完成 | **实物小试**（如果可能） | ⏳ |
| 10-08 | 内部评审 | 模型校准 + 证据清单 | ⏳ |
| 10-20 | 学校报名 | 🎯 | 🎯 |
| 10-25 | 作品提交 | 🎯 | 🎯 |

---

## 不要继续投入的地方 ❌

1. ❌ 更复杂的神经网络分类
2. ❌ 大模型/RAG
3. ❌ "AI自动生成WPS"
4. ❌ 追求合成数据99.99%
5. ❌ 再加十几个dashboard
6. ❌ 1000次→10万次Monte Carlo（参数未标定）
7. ❌ 继续二维FE算例（应升级3D）

---

## 评分预期

| 阶段 | 分数 | 判断 |
| --- | ---: | --- |
| V2当前 | 78 | 省赛中上档 |
| V3 P0修复后 | 83 | 省赛有竞争力 |
| **V4完成后** | **85-88** | **高奖竞争力** |
| V4+实物证据 | **88-92** | **高奖强竞争力** |

---

## 下一步立即行动

1. ✅ 修改 README/报告主标题
2. ✅ 重构四个创新点
3. ⏳ 建立3D FE模型
4. ⏳ 实现温度门控自适应跳焊
5. ⏳ 实现焊前反变形补偿
6. ⏳ 参数化多目标优化
7. ⏳ 争取最小物理证据链

**核心原则**：
- 不推翻重做
- 在当前基础上升级
- 做强证据、凝聚创新
- 从"数字内容多" → "机理驱动、可验证"
