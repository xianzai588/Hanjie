# Hanjie · 焊接固定题工艺设计

本轮只推进一条工程路线：**独立高镍预制解决铸铁首次连接，8P低热输入GTAW解决最终控形，铜环实体屏障解决内腔洁净。** CI-A1高镍首层和低碳Ni99第二层在壳外完成，修整及最终孔加工后入壳组焊；铜环、静密封和接料盘保持至冷却及受控退工具完成。

当前工作顺序：关闭CI-A1一翼有效接头与保留层接口 → 验证8P完整制造精度和同状态承载 → 完成全周期屏障接口及说明书/WPS/工程图。CI-A2、6P及其他方法保留已有对照，停止并行研究。历史任务记录不作为当前待办。

- [主线整改计划](deliverables/competition-route.md)
- [统一接口与验证状态](deliverables/process/current-candidate-state.md)
- [说明书正文](deliverables/report/technical-report-v4-unified.md)
- [说明书与18张工程图审阅稿](output/pdf/工艺设计说明书与工程图-修订审阅稿.pdf)
- [独立预制卡HJ-W-00C](deliverables/process/independent-precoat-design-card.md)与[首层输入卡HJ-W-00D](deliverables/process/first-layer-input-card.md)
- [独立审核及修订记录](docs/review/2026-10-06-独立审核与整改结果.md)

新主线尚待首次连续连接与完整制造验证。旧制造家族约52.084 μm超过50 μm，保留为修订依据。位置度预算仍为28+2+6.5+13.5=50 μm，微珩径向去除上限3 μm，禁止焊后精镗修正轴线。

当前交付为修订审阅稿。生成命令：

```powershell
python deliverables/report/build_technical_report_pdf.py --review --with-drawings
```

正式构建入口为 `python deliverables/build_submission.py`，要求完整R4核验通过；旧submission目录不直接用于本轮提交。参数源project/process-r3.yaml保留兼容文件名，project/process.yaml为历史输入。

## 历史研究记录（按原日期保留）

**2026-09-08 工装几何推进**：已读取既有 BREP 检查防护盘上/下退出、六种焊枪包络和锥面压入情景。三候选均排除整盘上撤；底口开放时下撤与所列实体无干涉。30°/45° 弯头后竖直枪体保留为几何候选；原心轴整段入孔会穿透，名义退让 5 mm 后为孔缘接触，已改为内置锥驱动开缝圆柱胀套并配置 1.00 mm 主动回退行程。入口 `python studies/TOOLING-ACCESS/run.py`。

**2026-09-06 V4.3**：修正非均匀异材公共面导热的串联热阻离散，并完成 THERMAL-0.4R1 全量重跑与审计；七个真实三维实体的静力筛查已完成，Continuous、6P、8P-FAIR_B 进入后续比较。

**2026-09-08 无实物条件选型**：新增六候选 108 组承载—沉积截面—名义净热输入核算及精度预算反算，按参考载荷与设计筛查许用值给出低热输入优先项与 6P/8P 自动切换边界。执行入口 `python studies/ROUTE-B-DESIGN/run.py`。


