# Hanjie · 焊接固定题工艺设计说明书

本项目交付 QT450-10 主轴承座与 Q235B 壳体的工艺设计说明书，附 WPS 设计卡及工程图。主方案冻结为 **8P-R2-t15 八翼柔顺槽座体、壳外 CI-A1 高镍首层预制、低碳 Ni99 第二层、低热输入脉冲 GTAW 最终组焊**，采用已有详细设计的门架、内锥胀套、托环和铜环颗粒屏障。完整圆环及短梁截面计算保留为比较附件。

## 阅读入口

| 文件 | 内容 |
| --- | --- |
| [单一主PDF](deliverables/competition-entry/01-焊接工艺设计说明书与工程图.pdf) | 正文、工艺卡、5张按比例工程图与18张NTS工艺附图 |
| [完整参赛ZIP](deliverables/焊接固定题-参赛设计报告包.zip) | 主PDF、两份匿名STEP、阅读说明和材料清单 |
| [评委阅读说明](deliverables/competition-entry/00-提交与阅读说明.txt) | 章节与图纸阅读导航 |
| [材料清单](deliverables/competition-entry/材料清单.json) | 最终文件和页数组成 |

## 制造与控形

高温预制、清渣、层面修整及轴承孔预加工在壳外完成，随后清洗干燥并入壳。最终组焊采用八段对称跳焊，焊序为 1→5→3→7→2→6→4→8。每翼真实外缘路径为 **18 mm**，两端各 1 mm 分配给起止过渡，稳定有效连接按 **16 mm/翼、128 mm/道**核算。两道实际路径 288 mm；名义净线能量 300 J/mm 对应净热 86.4 kJ、弧燃 174.545 s、耗丝 628.364 mm。有效焊长用于接头容量，实际路径用于热量、时间和焊材。

本轮第二层采用DMNA099目录Ø1.143×914.4 mm直棒，采购验收±0.020、配套送进11.52±0.29 mm/s；每翼两轨用同一180±0.5 mm定长棒。最终一次分道修订为根3.42/盖3.78±0.05 mm/s，理想最差喉厚余58.677 μm，实际轮廓与连续熔合分别确认。

孔轴控形依靠径向柔顺槽、内锥胀套背承、门架拘束、对称焊序及逐段能量控制。位置度按完全冷却、孔内与壳底工装全部解除后的独立 A/B 基准评价。主路线预算28＋2＋0＋20＝50 μm，最终孔径在入壳装夹态一次成形；完全卸夹后零去料，独立A/B验收位置度。铜环、接料盘、向上气幕和顶部排烟覆盖组焊、冷却及受控撤工具过程。

## 定稿状态与下一步

主方案固定8P-R2-t15，2026年10月18日冻结技术文件。既有全件终焊—冷却—完全卸夹计算的热残余孔轴位置度直径为13.0／15.6／13.7 μm。本轮只补双网格Richardson/GCI估计和一个三级空间网格准备，将阶次假设与数值误差直接写入说明书。

最终孔径采用A托环保夹转运、闭底全收集工位一次成形、抽尽干燥与干态内窥，然后完全卸夹验收。完整位置度预算28+2+0+20=50 μm，成形导向与装夹综合变化纳入28 μm非热项，由首件校准。第二层85 A/14 V、2.88/11.52 mm/s同步pWPS。

Run B已完成按比例工程图和云图重画、主包清理及工艺路线同步。三级网格与单头对照由主控运行；本轮只读结果，待结果到位更新第5章。首件PQR与孔成形校准集中列于第9章。唯一进度入口为[定稿状态](deliverables/FINAL-ENTRY-STATUS.md)。

既有名义装配STEP覆盖原设计力链、固定铜盘及根道枪丝包络；HJ-022／023新增接口继续按已有图纸与净隙计算表达。历史结果与原始数据保留在仓库。

## 历史入口

[比赛交付旧目录](deliverables/比赛交付-20261008/00-历史快照说明.md)和[论文格式旧目录](deliverables/论文格式交付-20261008/00-历史快照说明.md)均为历史快照。前者保留11份STEP指针，后者保留11份完整旧STEP及旧版正文；本次提交入口为上表的competition-entry。

## 维护与重新生成

[参赛基准参数](project/submission-baseline.yaml)是本次对象、焊长和交付路径的机器输入；[说明书正文源稿](deliverables/report/technical-report-v4-unified.md)、[工艺卡目录](deliverables/process)及[比赛内容与完善顺序](deliverables/competition-route.md)是维护入口。PDF路径以[报告配置](project/report.yaml)为准，仓库根目录为维护源，附件中的源文件为导出快照，修改后统一重新构建：

```bash
python cad/parametric/final_entry_drawings.py
python cad/parametric/final_entry_illustrations.py
python docs/report/plot_final_entry_fields_readable.py
python deliverables/report/build_technical_report_pdf.py --competition-entry --with-drawings
python deliverables/build_competition_entry.py
```

主包只收当前方案，历史计算原件保留在仓库。Run A导出保存在competition-entry-runA-snapshot，旧可编辑附件为开发快照，提交使用上列参赛ZIP。各PDF页数以本次材料清单为准。

## 校方提交

原比赛文件的焊接赛道节点为 2026 年 10 月 20 日前报名、10 月 25 日（含当日）提交。报名、盖章、审核推荐及校内节点由团队与校方办理，见[提交核对清单](deliverables/submission-checklist.md)。身份文件与匿名技术作品分别整理。
