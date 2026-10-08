# Hanjie · 焊接固定题工艺设计

本项目围绕 QT450-10 主轴承座与 Q235B 壳体连接，提交完整的工艺设计、工艺卡和工程图。**完整圆环是参赛基准，八翼开口座体是结构创新候选。** 圆环保留环向承载通道；八段对称短焊降低最终组焊热量，独立高镍预制处理铸铁首次连接工序，铜环屏障管理内腔颗粒。

## 阅读入口

| 文件 | 内容 |
| --- | --- |
| [正文 PDF](output/pdf/焊接工艺设计论文-正文.pdf) | 设计任务、选型理由、五维技术方案与计算依据 |
| [说明书与工程图合订本](deliverables/competition-entry/01-工艺设计说明书与工程图.pdf) | 正文、工艺卡、圆环基准图与创新候选图 |
| [工艺规程与检验卡](deliverables/competition-entry/02-工艺规程与检验卡.pdf) | 分工序参数、检查频次、判据与处置 |
| [工程图集](deliverables/competition-entry/03-工程图集.pdf) | 完整圆环 HJ-S01/S02、圆环紧凑工装 HJ-F-S 系列及 HJ-001～021 历史候选详图 |
| [参赛设计报告包 ZIP](deliverables/焊接固定题-参赛设计报告包.zip) | PDF、图纸、STEP、计算附件及可编辑源文件 |
| [本次封版校验清单](deliverables/COMPETITION-R4-DESIGN-SHA256.txt) | 核对 ZIP 与全部包内文件，防止版本混用 |
| [本次材料清单](deliverables/competition-entry/验证与交付状态.json) | 实际页数、收录文件和设计计算状态 |

## 方案为何这样安排

壳外预制允许使用高镍药皮焊条和独立预热、缓冷。首层修整、第二层、轴承孔最终加工与清洗在入壳前完成，把清渣和切削污染留在开放工位。最终入壳采用 NiFe55 填充的脉冲 GTAW，每段保留 18 mm 有效连接，两端各加 1 mm 起止过渡，实际 20 mm；两道累计弧长 320 mm。名义净线能量 300 J/mm 对应净热 96.0 kJ、弧燃约 193.9 s、耗丝 678.8 mm。装卸、转位和温控等待另行安排。

圆环外缘设置八处局部预制窗，中心半径 71.98 mm、弧长 24±0.5 mm、径向宽 6±0.1 mm、深 1.5±0.1 mm。首层按 75 mm/min 主弧和两端各 0.5 s 保护弧设计，以低供料、槽尺寸上限及临时镍保护带核算余量；第二层采用三条同角度轨迹覆盖浅槽。

孔轴精度由短受力闭环、胀套背承、对称焊序和热量控制承担，按完全卸夹后的独立基准测量；洁净设计覆盖起弧、冷却、撤夹和转运全过程。正文说明每项设计的作用，工艺卡规定试制时应确认的接头、孔形、颗粒和承载项目。

## 源文件与参数

- [正文 Markdown](deliverables/report/technical-report-v4-unified.md)：论文版式的工程设计正文。
- [圆环参赛基准参数](project/submission-baseline.yaml)：主对象、八段焊布局、材料链、精度预算和交付路径。
- [圆环基准总装 STEP](cad/generated/ring-baseline/ring-assembly-QT450-10-Q235B.step)、[几何与质量记录](cad/generated/ring-baseline/geometry-quality-and-mass.json)和[HJ-S01](cad/generated/ring-baseline/HJ-S01-ring-baseline.svg)：完整环形母件总装；局部过渡层按断面与工艺卡表达。
- [基础站短受力闭环计算](studies/COMPETITION-DESIGN/results/ring-fixture-feasibility.json)：按真实分段背承、锥面、底座连接及上桥计算；附专属CAD、BOM和退出路径。
- [工艺卡源文件](deliverables/process)：独立首层、第二层、最终组焊、夹具、洁净、检测和生产组织。
- [八翼计算参数](project/competition-design.yaml)与[原计算选型记录](project/competition-authority.yaml)：保留 8P-R2-t15 模型身份，支持创新候选分析。
- [比赛内容与完善顺序](deliverables/competition-route.md)、[提交核对清单](deliverables/submission-checklist.md)：技术阅读和校方提交导航。

圆环实际路径按 320 mm 计热量和用量；旧八翼 288 mm/86.4 kJ/174.5 s 保留原计算身份。焊长、送丝和净热使用相同守恒方法；八翼专属的温度历程、残余孔形、槽根应力和热工位容量仍属于八翼实体。报告按其实际对象引用，圆环计算单独登记。

## 重新生成

当前版本为 `SUBMISSION-RING-20261008-R2`。安装项目Python依赖、Gmsh系统库（Linux libXft、libGLU）、Inkscape和Poppler（提供`pdftoppm`），准备Git LFS实体附件后，在仓库根目录执行：

```bash
python scripts/build_ring_delivery.py
```

该入口检查圆环结构与制造计算版本，再生成CAD、工艺卡、完整数字回放、正文、图集和ZIP。已有计算可以直接构建材料；需要重算时按 [圆环承载](simulation/ring-baseline-structure/README.md) 和 [圆环制造分析](simulation/ring-baseline-manufacturing/README.md) 的命令执行。缓存有输入身份检查，不允许静默把改参数前的网格/结果算作新版本。

本轮补充圆环自身冷态承载FE、最终两道热过程及固有应变条件响应窗口。固有应变范围为显式设计输入，完整制造位置度没有实测或全历史热塑性通过记录；图纸、计算和pWPS作为工程设计材料交付，生产放行状态单独保留。

各 PDF 的页数以本次生成文件与材料清单为准。本轮基于远端工程基线和恢复附件重新生成，新版本记录见[完整圆环修复与交付记录](docs/review/ring-delivery-repair-20261008.md)，前轮附件恢复见[重建与审核记录](docs/review/recovery-rebuild-20261008.md)。`deliverables/submission` 和既有研究目录保留历史资料；正式参赛入口为上方报告包。

## 校方提交

比赛原件规定焊接赛道 **2026 年 10 月 20 日前报名、10 月 25 日（含当日）提交**。校方负责报名、预选、审核推荐及盖章汇总；具体校内节点按学校最新通知办理。技术包与报名身份材料分别整理，原件及逐项核对见[提交清单](deliverables/submission-checklist.md)。

完整ZIP在Git仓库中按8 MiB分卷保存，以适配接口单次上传限制。拉取后运行`python deliverables/package_volumes.py`还原`deliverables/焊接固定题-参赛设计报告包.zip`；程序核每卷及完整文件SHA256，再核ZIP CRC。`python scripts/build_ring_delivery.py`也会生成完整ZIP和最新分卷。直接下载交付ZIP时无需还原。
