# Hanjie · 焊接固定题工艺设计

当前开发线为COMPETITION-R4，产物为修订审阅稿。主线为Ni99两层预制、NiFe55两道脉冲GTAW、8P-R2-t15柔顺座体、实心反锥/门架夹具及铜环—静密封—接料盘的颗粒隔离。

- [说明书与14张工程图审阅稿](output/pdf/工艺设计说明书与工程图-修订审阅稿.pdf)
- [说明书正文](deliverables/report/technical-report-v4-unified.md)、[车间工艺卡及工程展开](deliverables/process/)
- [当前阶段账](project/stage-status.yaml)、[自动状态摘要](deliverables/report/generated/current-status.md)
- [实际计算入口与结果用途](simulation/competition-r4/README.md)、[内部修复记录](docs/review/2026-10-03-报告复核与修复.md)

完整工具热耦合四组正在计算，须完成冷却、完全卸夹、孔轴/孔径、空间时间精度、工具热域、支点差胀、段前温控及同源轻击核验。旧40.014 mm冷工具参考的空间差11.77%、孔径超限均真实保留；不作为当前达标证据。制造补偿核验窗口40.006～40.008 mm尚未冻结，配置中的旧40.010～40.014 mm须在有效结果通过后同步。服役参考目前也是40.014 mm，正式发布入口要求与接受的制造窗口统一。

推荐8P依据控形、冶金、洁净、静载和节拍的综合设计；6P为低热对照，全周焊为高承载参考。疲劳模型报告同谱资格需求，不以自设30 MPa曲线单独淘汰候选或证明寿命。Ø40 H7为压入式轴套座孔的装配设计输入，官方只给名义Ø40。

参数源为project/process-r3.yaml，project/process.yaml明确为historical_only。文件名R3为兼容已有入口，不意味着返回旧R3边界。修订审阅稿生成命令为：

```powershell
python deliverables/report/build_technical_report_pdf.py --review
```

正式构建使用python deliverables/build_submission.py；它要求完整R4核验通过，并阻止历史参数和未完成结果进入正式包。现有deliverables/submission中的历史文件不应直接用于本轮比赛提交，待正式构建通过后整体更新。固定焊接题未要求自编代码，报名和盖章材料按官方附件办理；报名10月20日、校方统一作品提交10月25日（含当日）。

## 历史研究记录（按原日期保留）

**2026-09-08 工装几何推进**：已读取既有 BREP 检查防护盘上/下退出、六种焊枪包络和锥面压入情景。三候选均排除整盘上撤；底口开放时下撤与所列实体无干涉。30°/45° 弯头后竖直枪体保留为几何候选；原心轴整段入孔会穿透，名义退让 5 mm 后为孔缘接触，已改为内置锥驱动开缝圆柱胀套并配置 1.00 mm 主动回退行程。入口 `python studies/TOOLING-ACCESS/run.py`。

**2026-09-06 V4.3**：修正非均匀异材公共面导热的串联热阻离散，并完成 THERMAL-0.4R1 全量重跑与审计；七个真实三维实体的静力筛查已完成，Continuous、6P、8P-FAIR_B 进入后续比较。

**2026-09-08 无实物条件选型**：新增六候选 108 组承载—沉积截面—名义净热输入核算及精度预算反算，按参考载荷与设计筛查许用值给出低热输入优先项与 6P/8P 自动切换边界。执行入口 `python studies/ROUTE-B-DESIGN/run.py`。


