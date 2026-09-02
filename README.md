# Hanjie · 数字化异种材料焊接工艺设计 2026

第一届辽宁省大学生材料焊接与铸造工艺设计大赛
“中铁山桥杯”焊接工艺设计赛——固定命题

> 面向 QT450-10 球墨铸铁主轴承座与 Q235B 压缩机壳体的异种材料连接，研究低热输入焊接工艺、精密变形控制与自动化质量监测，目标：**焊后轴承孔轴线位置度偏差 ≤ Ø0.05 mm**。

## 核心指标

| 项目 | 要求 |
| --- | --- |
| 壳体 | Q235B，壁厚 5 mm，Ø160 × 200 mm |
| 主轴承座 | QT450-10，环形盘状，轴承孔 Ø40 mm |
| 焊后位置度 | 轴承孔轴线位置度偏差 ≤ Ø0.05 mm |
| 洁净度 | 不得产生可能落入压缩机内部的焊渣、飞溅物 |

## 项目主方案

**基于六点柔顺连接结构的 QT450-10/Q235B 主轴承座低变形自动 TIG 异种焊接及数字化质量控制方案**。

主候选为自动 TIG + 镍铁基填充材料；CMT 与激光填丝保留为对比路线。这里的“主候选”是基于文献、设备可实现性和降阶仿真的工程假设，须在真实设备/小试可用时进行工艺评定。

## 项目目标

1. **焊得住** —— QT450-10 / Q235B 异种材料可靠连接：白口与脆硬组织控制、裂纹防控、焊材与热输入选择、预热/后热制度。
2. **焊不歪** —— 通过焊缝布局、焊接顺序、夹具与热管理，把轴承孔位置度控制在 Ø0.05 mm 内。
3. **稳定焊** —— 视觉定位、自动路径生成、过程数据采集与异常检测、批量质量追溯。

## 技术路线

```
官方约束与设计假设 → 文献证据矩阵 → 自动 TIG + 镍基候选
→ 六点柔顺连接与精密夹具数字样机 → 降阶热-结构方案筛选
→ 网格/参数/鲁棒性接口 → 视觉定位/路径/监测/追溯数字样机
→ 真实制造时的检测规程 → 作品集成与答辩
```

## 当前阶段

**P2 数字证据链已运行**（2026-09-02）：已冻结约束与设计假设，完成参数化 CAD 工程表达图、15 组降阶筛选、3 组二维 FE 复核、1000 次蒙特卡洛、困难视觉样本和 100+100 异常检测基准。真实焊接、CMM、金相、硬度、NDT 和 WPS/PQR 仍是可选物理验证。
后续节点见 [docs/01-roadmap.md](docs/01-roadmap.md)。

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
- [技术说明书 V1（数字工程评审稿）](deliverables/report/technical-report-v1.md)
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
