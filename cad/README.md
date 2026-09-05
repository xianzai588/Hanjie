# 参数化 CAD 数字样机

- `parametric/geometry.json`：官方尺寸、设计假设和 V1 参数入口；
- `parametric/hanjie_model.scad`：可在 OpenSCAD 中渲染壳体、柔顺轴承座、夹具或总装；
- `generated/layout-v1.svg`：由脚本生成的俯视工程布局图。
- `generated/engineering-drawings/`：由 `parametric/generate_engineering_drawings.py` 生成的 7 张工程表达图，覆盖座、壳体、接头、焊缝布置、夹具总装/零件和焊接总装。
- `simulation/structural-v4/generate_seat_geometry.py`：P1A 七个公平比较实体的唯一 OCC 生成入口；输出在 `simulation/structural-v4/models/`。

工程图包已经显式包含 A/B/C 基准、Ø0.05 位置度框、焊缝符号、槽宽、夹具自由度、材料和未注公差，但当前状态仍是 `design-review`，不是制造发布图：图纸中的座厚、翼宽、装配间隙、焊缝尺寸和夹具等效刚度属于设计假设。

P1A 实体已由 OpenCascade（OCP）直接导出 STEP/BREP；这些文件只证明参数化实体和导出链路已生成，仍需独立几何审查后才能进入结构求解。当前没有把 SCAD 渲染图当作 P1A 权威实体，也没有把导出文件当作制造发布图；仍需完成三维关联、公差叠加、焊缝可达性、夹具干涉和企业制图标准复核。
