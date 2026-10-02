# Hanjie · 数字化异种材料焊接工艺设计 2026

**当前参赛版：COMPETITION-R3，焊接固定题。** 采用 8P 两道脉冲 TIG、QT侧Ni99预制隔离层＋NiFe55填充、Ø1.6 mm棒材鲁棒送丝、六指胀套机械止挡、分体式紫铜环独立气水路，并执行铸铁冷焊（不预热、层间≤100 ℃）与窗口受控热态轻击。数字结果区分全件热—结构计算、设计筛查和待实物评定项目。

- [工艺设计说明书](output/pdf/technical-report-v4.pdf)与[设计图集](cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf)（8张图）。
- [提交技术包](deliverables/submission/)；报名表、学校盖章和推荐由参赛方办理。
- 统一设计配置：`project/competition-design.yaml`（含 `thermal_regime` 与 `peening` 段）。
- 复现入口：`python deliverables/build_submission.py`；相图与热制度计算：`python studies/SCHAEFFLER-MAP/run.py`。

## 设计要点

**焊得住。** Ni99预制层降低QT侧直接碳稀释，NiFe55承担最终连接。Schaeffler只在原图域内读图，图外Ni-Fe-C点不做相区外推；文献支持奥氏体主枝晶但同时提示NiFe枝晶间渗碳体与HAZ马氏体风险。热态轻击只在焊道400～500℃窗口执行，不把锤击假定成全熔合线压应力。

**焊不歪。** 位置度预算保留0.002 mm测量扩展不确定度，热残余由全件模型实算并与0.0102 mm径向门比较；不再用均匀热胀直接代替孔轴偏移。A/B独立基准、冷却卸夹和微珩前测量写入pWPS。

**焊得干净。** 铜环静态密封和接料盘承担颗粒截留，气幕仅辅助输运；水气分路、流量/漏水/回缩互锁，不能用“低飞溅”作为洁净保证。

## 核心指标

| 项目 | 要求 |
| --- | --- |
| 壳体 | Q235B，壁厚 5 mm，Ø160 × 200 mm |
| 主轴承座 | QT450-10，环形盘状，轴承孔 Ø40 mm |
| 焊后位置度 | 轴承孔轴线位置度偏差 ≤ Ø0.05 mm（预算闭合，余 0.0044 mm） |
| 洁净度 | 不得产生可能落入压缩机内部的焊渣、飞溅物（四条件合取控制） |
| 焊缝组织 | NiFe高镍奥氏体倾向；QT侧PMZ/HAZ的马氏体、碳化物与裂纹须由首件金相/HV/PT确认 |

## 工程确认计划

试制阶段按说明书 §9.2 的 V1～V10 完成 A 类实物工程确认：小试金相与宏观截面 → 锤击层残余应力 → 同件测量与重复装夹 → 热残余 CMM 回填 → 铜衬环热接触与颗粒清点 → 自动化联调。设计指标的统一表述为：**经理论计算与数值仿真验证，在设定工况下满足设计指标要求；建议在后续试制阶段通过 A 类实物试验完成最终工程验证。**

## 工作包与分工

| WP | 模块 | 回答的问题 |
| --- | --- | --- |
| WP0 | 项目定义与资料管理 | 我们到底要解决什么 |
| WP1 | 材料与焊接性 | 为什么难焊 |
| WP2 | 焊接工艺选型 | 用什么方法焊 |
| WP3 | 接头结构与夹具 | 接头怎么设计 |
| WP4 | 热-结构仿真 | 为什么这样设计 |
| WP5 | 物理验证（可选） | 实物能不能焊好 |
| WP6 | 自动化与智能监测 | 怎么稳定重复 |
| WP7 | 检测评价与数值后处理 | 怎么证明真的好 |
| WP8 | 作品集成与答辩 | 怎么形成参赛作品 |

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
studies/       竞赛设计计算、相图映射、鲁棒边界
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
- [工艺设计说明书源文件](deliverables/report/technical-report-v4-unified.md)
- [Schaeffler 相图与冷焊冶金设计](docs/process/schaeffler-diagram-analysis.md)
- [协作规则](CONTRIBUTING.md)

## 复现入口

在仓库根目录执行：

```powershell
python -m pytest -q
python deliverables/build_submission.py
```

构建链依次重算竞赛设计、候选排序、鲁棒边界、Schaeffler 相图映射、工装可达性、Route B 条件选型、工艺卡与工程图，随后生成说明书 PDF、提交包与 ZIP，并通过 `scripts/competition_submission_lint.py` 质量门。输出分别位于 `cad/generated/`、`simulation/results/`、`studies/*/results/` 与 `deliverables/submission/`。

## 历史研究记录（按原日期保留）

**2026-09-08 工装几何推进**：已读取既有 BREP 检查防护盘上/下退出、六种焊枪包络和锥面压入情景。三候选均排除整盘上撤；底口开放时下撤与所列实体无干涉。30°/45° 弯头后竖直枪体保留为几何候选；原心轴整段入孔会穿透，名义退让 5 mm 后为孔缘接触，已改为内置锥驱动开缝圆柱胀套并配置 1.00 mm 主动回退行程。入口 `python studies/TOOLING-ACCESS/run.py`。

**2026-09-06 V4.3**：修正非均匀异材公共面导热的串联热阻离散，并完成 THERMAL-0.4R1 全量重跑与审计；七个真实三维实体的静力筛查已完成，Continuous、6P、8P-FAIR_B 进入后续比较。

**2026-09-08 无实物条件选型**：新增六候选 108 组承载—沉积截面—名义净热输入核算及精度预算反算，按参考载荷与设计筛查许用值给出低热输入优先项与 6P/8P 自动切换边界。执行入口 `python studies/ROUTE-B-DESIGN/run.py`。


