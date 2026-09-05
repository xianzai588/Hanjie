> 2026-09-05 纠偏：src/hanjie/simulation/fe3d.py 是经验代理，旧 Gate B.1 通过声明撤销。下列真实求解工作仍待完成。当前报告源为 technical-report-v4-unified.md。

# FE3D-BASE 实施状态追踪

**版本**：V1.1-V4.2
**日期**：2026-09-05
**模型代号**：FE3D-BASE  

---

## 实施检查清单

### Phase 0: 准备与纠偏（已完成）

- [x] 设计输入冻结（`design-inputs-frozen-v4.md`）
- [x] 验证协议编写（`FE3D-BASE-verification-protocol.md`）
- [x] 当前技术报告源冻结（`deliverables/report/technical-report-v4-unified.md`）
- [x] 模型目录创建（`simulation/fe3d/models/FE3D-BASE/`）

### Phase 1: 几何建模

- [ ] 壳体几何（Ø160×200×5 mm）
- [ ] 轴承座几何（连续环形座体）
- [ ] 焊缝区几何（角焊缝 3.5 mm 腿长）
- [ ] 装配配合（径向间隙 0.02 mm）
- [ ] 几何检查（干涉检查、尺寸验证）

**输出文件**：
- `models/FE3D-BASE/geometry/shell.step`
- `models/FE3D-BASE/geometry/bearing-seat.step`
- `models/FE3D-BASE/geometry/assembly.step`

### Phase 2: 网格划分

#### G61 基准网格

- [ ] 焊缝区网格（0.5 mm）
- [ ] 轴承座网格（1.0 mm）
- [ ] 壳体网格（2.0 mm）
- [ ] 网格质量检查（畸变 < 0.7，长宽比 < 5:1）
- [ ] 单元类型选择（C3D8/C3D20）

#### 收敛验证网格

- [ ] G51 粗化网格（1.2×）
- [ ] G71 加密网格（0.8×）
- [ ] G81 加密网格（0.6×）

**输出文件**：
- `models/FE3D-BASE/mesh/G51.inp`
- `models/FE3D-BASE/mesh/G61.inp`
- `models/FE3D-BASE/mesh/G71.inp`
- `models/FE3D-BASE/mesh/G81.inp`

### Phase 3: 材料定义

- [ ] QT450-10 温度相关参数（E, α, σ_y, k, c_p）
- [ ] Q235B 温度相关参数
- [ ] ERNiFe-CI 焊缝参数
- [ ] 塑性本构（各温度点）
- [ ] 参数来源标注

**输出文件**：
- `models/FE3D-BASE/materials/QT450-10.inp`
- `models/FE3D-BASE/materials/Q235B.inp`
- `models/FE3D-BASE/materials/ERNiFe-CI.inp`

### Phase 4: 边界条件与载荷

#### 热边界条件

- [ ] 初始温度场（150°C 预热）
- [ ] Goldak 双椭球热源（参数：a_f=3, a_r=6, b=2, c=2.5 mm）
- [ ] 热源移动路径（S3 顺序：1→4→3→6→2→5）
- [ ] 对流换热（h=10 W/m²·K）
- [ ] 辐射换热（ε=0.8）
- [ ] 层间温度控制（≤200°C）

#### 结构边界条件

- [ ] 壳体底面固定支撑
- [ ] 轴承座孔径向约束（焊前+焊中）
- [ ] 约束释放时机（T=50°C）
- [ ] 热应变加载
- [ ] 重力载荷

**输出文件**：
- `models/FE3D-BASE/bc/thermal-bc.inp`
- `models/FE3D-BASE/bc/structural-bc.inp`
- `models/FE3D-BASE/bc/heat-source-S3.inp`

### Phase 5: 求解设置

#### 热分析步

- [ ] Step 1: 预热至 150°C
- [ ] Step 2-7: 六段焊接（S3 顺序）
- [ ] Step 8-13: 层间冷却（至 ≤200°C）
- [ ] Step 14: 完全冷却至 50°C

#### 结构分析步

- [ ] 耦合热应变场
- [ ] 夹具约束保持至 50°C
- [ ] 约束释放
- [ ] 继续冷却至 20°C

**输出文件**：
- `models/FE3D-BASE/analysis/thermal-steps.inp`
- `models/FE3D-BASE/analysis/structural-steps.inp`

### Phase 6: 求解运行

#### G61 基准求解

- [ ] 热分析求解
- [ ] 结构分析求解
- [ ] 收敛性检查
- [ ] 结果文件完整性

#### 收敛验证求解

- [ ] G51 求解
- [ ] G71 求解
- [ ] G81 求解

**输出文件**：
- `models/FE3D-BASE/results/G61/thermal.odb`
- `models/FE3D-BASE/results/G61/structural.odb`
- `models/FE3D-BASE/results/G51/*.odb`
- `models/FE3D-BASE/results/G71/*.odb`
- `models/FE3D-BASE/results/G81/*.odb`

### Phase 7: 后处理

#### 孔轴线位置度提取

- [ ] 提取 Ø40 孔内表面节点坐标（20°C，释放后）
- [ ] 最小二乘拟合轴线
- [ ] 计算位置度 P
- [ ] 倾斜角计算

#### 热场后处理

- [ ] 峰值温度分布
- [ ] HAZ 宽度测量（> 723°C）
- [ ] 温度历程曲线（特征点）
- [ ] 热源移动速度验证

#### 应力场后处理

- [ ] 等效应力云图
- [ ] 残余应力分布
- [ ] 变形场云图
- [ ] 约束释放位移跳变

**输出文件**：
- `models/FE3D-BASE/results/position-tolerance.csv`
- `models/FE3D-BASE/results/thermal-field.png`
- `models/FE3D-BASE/results/stress-field.png`
- `models/FE3D-BASE/results/deformation-field.png`

### Phase 8: Gate B 验证（当前不适用，待真实求解）

#### Gate B.1: 网格收敛

- [ ] 位置度变化率计算（G71 vs G61, G81 vs G71）
- [ ] 峰值温度变化率计算
- [ ] 最大应力变化率计算
- [ ] 通过/不通过判定（代理结果不得填写）

#### Gate B.2: 热场合理性

- [ ] 峰值温度范围检查（1300-1600°C）
- [ ] HAZ 宽度检查（3-10 mm）
- [ ] 热源移动速度验证（1.5 mm/s）
- [ ] 层间温度控制检查（≤200°C）

#### Gate B.3: 边界条件

- [ ] 夹具约束清单检查
- [ ] 释放时机验证（50±5°C）
- [ ] 热边界条件检查

#### Gate B.4: 材料参数

- [ ] 温度相关性检查（单调性）
- [ ] 塑性参数合理性
- [ ] 来源标注清晰性

**输出文件**：
- `simulation/fe3d/FE3D-BASE-verification-report.md`

### Phase 9: 文档更新

- [ ] 更新 `technical-report-v4-unified.md` §4 Gate B 状态
- [ ] 更新 `evidence/claims.yaml` CLAIM-052 状态
- [ ] 编写验证报告总结
- [ ] 归档模型文件

---

## 当前状态

**阶段**：G0 纠偏已完成，G1 真实几何与静刚度筛选待开始
**FE 状态**：`fe3d.py` 为 surrogate prototype；Gate B.1 已撤销且不适用，能量平衡未计算
**设备状态**：设备、材料和检测窗口待核实
**下一步**：先建立 Continuous、4/6/8P 的真实 FAIR-A/B 几何与 manifest

---

## 风险与依赖

### 软件依赖

- [ ] 有限元软件（Abaqus/ANSYS/LS-DYNA）
- [ ] Python 后处理脚本环境
- [ ] 网格生成工具

### 计算资源

- [ ] 求解器许可证
- [ ] 计算节点（估算：G61 单次求解 8-16 核，4-8 小时）
- [ ] 存储空间（估算：每网格级 5-10 GB）

### 关键风险

| 风险 | 影响 | 缓解措施 |
| --- | --- | --- |
| 网格收敛未达标 | Gate B.1 不通过 | 预留 G91 加密网格 |
| 峰值温度超范围 | Gate B.2 不通过 | 调整 Goldak 热源参数 |
| 求解不收敛 | 无法获得结果 | 调整时间步长、增量步 |
| 计算时间过长 | 进度延误 | 优化网格过渡、并行计算 |

---

## 禁止项（重申）

在真实 FE 的 Gate B 全部通过前，**严格禁止将以下结果写成工程结论**：

🚫 开始 4/6/8 点结构建模  
🚫 柔顺夹具对比  
🚫 Pareto 优化  
🚫 自适应跳焊  
🚫 反变形补偿  
🚫 修改验证协议判据（结果出来后）  

**理由**：Baseline 数值可信度未建立前，任何结构扩展都是过早优化。

---

**状态追踪**：每完成一个 Phase 更新此文件，记录实际输出文件路径和问题诊断。
