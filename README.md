# Hanjie · 数字化异种材料焊接工艺设计 2026

> **2026-09-06 V4.3**：修正非均匀异材公共面导热的串联热阻离散，并完成 THERMAL-0.4R1 全量重跑与审计；能量和时间步门通过，空间网格门未通过，历史 0.4R 结果保留。七个真实三维实体的静力筛查已完成，Continuous、6P、8P-FAIR_B 进入后续热—结构比较。工艺扫描、正式整件热—结构耦合与性能放行仍未开放。
第一届辽宁省大学生材料焊接与铸造工艺设计大赛
“中铁山桥杯”焊接工艺设计赛——固定命题

> **面向 Ø0.05 mm 位置度的 QT450-10/Q235B 异种材料焊接热—结构协同优化与自适应数字质量控制**
>
> 以 Ø0.05 mm 位置度为设计目标，通过候选接头比较、逐件装配预偏置、温度门控、内腔防护和独立测量，形成 QT450-10/Q235B 异种焊接的可制造、可检查方案；实物性能仍待验证。

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
2. **控制焊后偏移** —— 以 Ø0.05 mm 位置度为设计目标，通过三候选结构比较、温度门控、逐件装配预偏置和精密夹具建立待验证的热—结构控制链。
3. **稳定焊** —— 焊前视觉定位、焊中温度状态反馈、过程异常检测、批量质量追溯，构建三闭环数字工艺体系。

## 当前阶段

**V4.3 阶段整改与评审材料已形成**（2026-09-06）：已修正界面导热离散、活动版本指针、视觉预算生成入口和逐件预偏置约束；接头 3.5 mm 设计目标与当前送丝形成的约 1.737 mm 等效焊脚仍未闭合，不能据此宣称完整技术路线完成。各阶段的执行、验收和允许用途见 [`project/stage-status.yaml`](project/stage-status.yaml)。

**V4.3 主线**：已完成七个真实三维实体的静力筛查，并修正局部热模型的非均匀异材界面导热；温度门控和逐件装配预偏置仍是待物理校准的控制候选。

**Plan 3 数值准入推进**：已实际完成固定六条带几何的 coarse/medium/fine 场网格及沿焊道/截面方向控制对照、条件性焊缝组承载筛查，以及三维 J2 和六四面体小网格验证。固定几何使 medium→fine 焊材热区 P95 差由旧混合序列的 74.554 °C 降至 16.682 °C，方向对照显示截面细化影响占主导；但仍未达到 10 °C 门且 QT 固相线翻转未消失，正式 THERMAL-1 与 STRUCT-0 继续冻结。

当前已完成：
- 15 组降阶方案筛选
- 5 组二维热—结构代理匹配对照
- 41/51/61/81 网格检查（注意：网格相邻变化29.224%，未通过5%参考门）
- 1000 次全析因蒙特卡洛（注意：structure_factor/fixture_factor未经FE或实验标定）
- 带运行时质量拒绝门的困难视觉基准
- 100+100 异常检测基准
- 8 张 SVG/PDF 工程表达图（含内腔防护安装与退出路径）

**证据边界**：三维静力筛查只回答当前载荷与支承下的刚度，不等于焊后残余位置度；局部热模型仍未校准，0.4R1 审计确认空间网格未收敛且未形成两侧母材熔合证据。真实焊接、CMM、金相、硬度、NDT、洁净度和 WPS/PQR 仍是物理验证门。

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
- [当前正式报告源 V4.3（工艺设计说明书）](deliverables/report/technical-report-v4-unified.md)
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
