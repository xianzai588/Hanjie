# 工装空间与锥面约束检查

运行 `python studies/TOOLING-ACCESS/run.py`。`config.yaml` 明确新增工装包络假设，引用既有三候选BREP和官方壳体尺寸；不覆盖热场或结构材料输入。

`results/result.csv` 保存上/下退出的扫掠体求交结果，`assessment.json` 保存焊枪姿态、保守全路径包络与锥面载荷分析，`run-inputs.json` 保存输入及实体来源。`cad/generated/tooling-access/` 导出一个Continuous名义情景的STEP和同参数剖面SVG。

上撤是失败对照。下撤只适用于底口开放阶段；即便所列实体无干涉，截留盘壁隙仍可能漏接异物。焊枪只比较明确的刚性包络，不含整机腕部、管线或送丝机构。锥面按库仑摩擦力平衡分析，不计算接触应力、孔扩张或重复性。所有物理放行标记保持false。
