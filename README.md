# Hanjie · 焊接固定题工艺设计

主方案：独立CI-A1高镍预制、低碳Ni99第二层、8P低热输入GTAW及铜环实体屏障。当前已整理完整参赛设计报告文件；有效接头、完整孔形及完整强度验证仍未全部通过，具体见正文0、4、5。

- [参赛设计报告包ZIP](deliverables/焊接固定题-参赛设计报告包.zip)
- [说明书与工程图合订本](deliverables/competition-entry/01-工艺设计说明书与工程图.pdf)
- [工艺规程与检验卡](deliverables/competition-entry/02-工艺规程与检验卡.pdf)
- [21张工程图](deliverables/competition-entry/03-工程图集.pdf)
- [正文源文件](deliverables/report/technical-report-v4-unified.md)
- [独立预制设计参数](project/precoat-process-design.yaml)
- [后续修复计划](deliverables/competition-route.md)

首层每翼单主轨迹：110 A、23 V参考、100 mm/min、名义熔敷率0.17 g/s；计入末段缓降后沉积15.329235 g/件。八个公差角点加名义实体已完成独立STEP重读，最大槽176.157710 mm³/翼；120 mm/min仍有供料不足情景，保留100基线。第二层75 A、11 V参考、2 mm/s、Ø1.20裸棒送丝7.20±0.20 mm/s。以上为设计pWPS，试制确认后冻结生产窗口。最终随动轻击作为选配，不计控形/强度收益。

本次新增HJ-019真实公差断面、HJ-020专用UT可达图及HJ-021关键零件明细；HJ-P-01按8件/8 h目标配置单头整线、8/9/24个首层/第二层预留/延迟PT位置。143.58元/件为直接运行费假设情景。首层冷态尚未取得，当前完整制造链、Ø0.05 mm及完整承载验证均未通过；历史52.084 μm超差保留。

重建参赛报告文件：

```powershell
python cad/parametric/build_precoat_tolerance_family.py
python cad/parametric/inspect_precoat_tolerance_steps.py
python studies/COMPETITION-DESIGN/pilot_production_resources.py
python cad/parametric/build_engineering_supplements.py
python cad/parametric/export_drawing_pdfs.py
python -c "import sys;from pathlib import Path;sys.path.insert(0,'src');from hanjie.reporting.current_status import write_status_artifacts;write_status_artifacts(Path.cwd())"
python deliverables/report/build_technical_report_pdf.py --competition-entry --with-drawings
python deliverables/build_competition_entry.py
```

文件齐备与工程性能分别记录。`python deliverables/build_submission.py`仍保留有效接头、完全卸夹精度与完整强度的工程发布检查，不用参赛报告打包结果替代其通过。`deliverables/submission`为历史技术包，勿与当前参赛设计报告包混用。

校方报名、身份信息及盖章材料单独办理；工具不发送邮件、不代签。技术文件中保留匿名。

## 历史研究记录（按原日期保留）

**2026-09-08 工装几何推进**：已读取既有 BREP 检查防护盘上/下退出、六种焊枪包络和锥面压入情景。三候选均排除整盘上撤；底口开放时下撤与所列实体无干涉。30°/45° 弯头后竖直枪体保留为几何候选；原心轴整段入孔会穿透，名义退让 5 mm 后为孔缘接触，已改为内置锥驱动开缝圆柱胀套并配置 1.00 mm 主动回退行程。入口 `python studies/TOOLING-ACCESS/run.py`。

**2026-09-06 V4.3**：修正非均匀异材公共面导热的串联热阻离散，并完成 THERMAL-0.4R1 全量重跑与审计；七个真实三维实体的静力筛查已完成，Continuous、6P、8P-FAIR_B 进入后续比较。

**2026-09-08 无实物条件选型**：新增六候选 108 组承载—沉积截面—名义净热输入核算及精度预算反算，按参考载荷与设计筛查许用值给出低热输入优先项与 6P/8P 自动切换边界。执行入口 `python studies/ROUTE-B-DESIGN/run.py`。


