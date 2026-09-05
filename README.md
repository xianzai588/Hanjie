# Hanjie · 数字化异种材料焊接工艺设计 2026

> **2026-09-05 V4.2 纠偏**：FE3D 为 surrogate prototype，Gate B 未通过；设备尚未核实；所有新研究结果为代理/合成演示。拓扑与控制优越性 unresolved。正式报告源为 `deliverables/report/technical-report-v4-unified.md`，V2/V3 及旧提交包仅作历史归档。执行计划见 [V4.2 路线](docs/V4.2-competition-roadmap.md)。
第一届辽宁省大学生材料焊接与铸造工艺设计大赛
“中铁山桥杯”焊接工艺设计赛——固定命题

> **面向 Ø0.05 mm 位置度的 QT450-10/Q235B 异种材料焊接热—结构协同优化与自适应数字质量控制**
>
> 以 Ø0.05 mm 位置度为直接设计目标，通过参数化低拘束接头、热—结构鲁棒优化、焊前位姿补偿、焊中温度门控自适应跳焊和全过程质量追溯，构建 QT450-10/Q235B 异种焊接的三闭环数字工艺体系。

## 核心指标

| 项目 | 要求 |
| --- | --- |
| 壳体 | Q235B，壁厚 5 mm，Ø160 × 200 mm |
| 主轴承座 | QT450-10，环形盘状，轴承孔 Ø40 mm |
| 焊后位置度 | 轴承孔轴线位置度偏差 ≤ Ø0.05 mm |
| 洁净度 | 不得产生可能落入压缩机内部的焊渣、飞溅物 |

## 创新方向与研究路线

1. **公平拓扑—热工艺协同设计**：先做 FAIR-A/B 真实几何与静刚度筛选，再用可信热—结构模型裁决。当前没有六点最优结论。
2. **物理校准驱动的变形控制闭环**：热电偶/CMM → 模型校准 → 温度门控 → 焊前装配预偏置 → 独立检测。当前只有代理/合成原型，尚未物理验证；补偿对象是装配姿态。
3. **支撑方向：可审计数字证据链**：逐项标注证据等级，低等级演示不能自动晋升为工程验证。

七个手选点只在现有代理目标下筛选非支配子集。当前目标不含真实承载、疲劳和制造约束，不能称全局 Pareto 前沿。Adaptive 在统一预热扰动对照中反而弱于 S3，暂按候选安全门控策略研究。

执行顺序与验收条件见 [V4.2 计划](docs/V4.2-competition-roadmap.md)。

## 项目目标

1. **焊得住** —— QT450-10 / Q235B 异种材料可靠连接：白口与脆硬组织控制、裂纹防控、焊材与热输入选择、预热/后热制度。
2. **焊不歪** —— 以 Ø0.05 mm 位置度为直接设计目标，通过参数化接头优化、温度门控自适应跳焊、焊前反变形补偿和精密夹具，实现热—结构协同控制。
3. **稳定焊** —— 焊前视觉定位、焊中温度状态反馈、过程异常检测、批量质量追溯，构建三闭环数字工艺体系。

## 当前阶段

**V3 P0 修复已完成**（2026-09-03）：已消除接头几何矛盾（R73.8→74.98, H7/h6配合）、夹具定位矛盾（Ø39.96销→锥形心轴）、误差预算混淆（装配链/自动化链分离）。

**V4 主线重构进行中**：从"六点柔顺已成立"转向"面向Ø0.05 mm的参数化协同优化"，增加温度门控自适应跳焊、焊前反变形补偿两个核心创新。

当前已完成：
- 15 组降阶方案筛选
- 5 组二维热—结构代理匹配对照
- 41/51/61/81 网格检查（注意：网格相邻变化29.224%，未通过5%参考门）
- 1000 次全析因蒙特卡洛（注意：structure_factor/fixture_factor未经FE或实验标定）
- 带运行时质量拒绝门的困难视觉基准
- 100+100 异常检测基准
- 7 张 SVG 工程表达图

**证据边界**：降阶模型支持柔顺结构，但二维 FE 中 FE-003（柔顺+柔顺夹具）反而最差。网格未收敛，无实物验证。**因此"六点柔顺"现为候选方案之一，不作为已验证结论。** 真实焊接、CMM、金相、硬度、NDT 和 WPS/PQR 仍保留为物理验证门。

后续节点见 [docs/01-roadmap.md](docs/01-roadmap.md)、[docs/v3-progress-report.md](docs/v3-progress-report.md)、[docs/v4-mainline-refactor.md](docs/v4-mainline-refactor.md)。

## 工作包与分工

| WP | 模块 | 回答的问题 | 负责人 |
| --- | --- | --- | --- |
| WP0 | 项目定义与资料管理 | 我们到底要解决什么 | 待定 |
| WP1 | 材料与焊接性 | 为什么难焊 | 待定 |
| WP2 | 焊接工艺选型 | 用什么方法焊 | 待定 |
| WP3 | 接头结构与夹具 | 接头怎么设计 | 待定 |
| WP4 | 热-结构仿真 | 为什么这样设计 | 待定 |
| WP5 | 物理验证（可选） | 实物能不能焊好 | 待定 |
| WP6 | 自动化与智能监测 | 怎么稳定重复 | 待定 |
| WP7 | 检测评价与数值后处理 | 怎么证明真的好 | 待定 |
| WP8 | 作品集成与答辩 | 怎么形成参赛作品 | 待定 |

## 里程碑

| 日期 | 节点 |
| --- | --- |
| 09-05 | 约束/假设/证据矩阵 + 材料参数基线 |
| 09-10 | CAD V1、工艺候选与接头方案冻结 |
| 09-18 | Process Freeze V1（基于文献与数字仿真） |
| 09-25 | ≥9 组方案比较 + 结构优化 |
| 10-02 | 网格/参数敏感性/鲁棒性 |
| 10-08 | 自动化软件 MVP |
| 10-13 | 技术说明书 V1 |
| 10-17 | 工程图、流程图、结果图 |
| 10-20 | 报名与内部技术审查截止 |
| 10-25 | 学校统一提交截止（官方） |

## 仓库结构

```
docs/          项目定义、路线图、研究、工艺、验证计划
competition/   比赛官方文件（只读存档）
cad/           壳体、轴承座、接头、夹具、总装
simulation/    有限元模型、算例与结果
experiments/   实验方案、原始数据、金相、硬度、测量
automation/    视觉定位、路径规划、仿真采集、异常检测、追溯
data/          数据模式与样例数据
deliverables/  最终提交物
```

## 文档索引

- [项目定义](docs/00-project-definition.md)
- [路线图](docs/01-roadmap.md)
- [团队分工](docs/02-team.md)
- [设备清单](docs/03-equipment-inventory.md)
- [当前正式报告源 V4.2（研究草稿）](deliverables/report/technical-report-v4-unified.md)
- [协作规则](CONTRIBUTING.md)

## 首版数字样机运行

在仓库根目录执行：

```powershell
python cad/parametric/generate_drawing.py
python cad/parametric/generate_engineering_drawings.py
python simulation/scripts/run_reduced_order.py
python simulation/fe/run_fe_cases.py
python simulation/scripts/run_monte_carlo.py --count 1000
python simulation/scripts/position_tolerance.py --demo
python automation/vision/run_benchmark.py --difficult --count-per-condition 100
python automation/anomaly-detection/run_benchmark.py --normal-count 100 --injected-count 100
python automation/app/run_demo.py
```

输出分别位于 `cad/generated/`、`simulation/results/` 和 `automation/*/results/`。所有仿真、视觉和过程信号结果都带有“数字样本/降阶模型”声明，不替代实物 CMM、金相、硬度或焊接工艺评定。
