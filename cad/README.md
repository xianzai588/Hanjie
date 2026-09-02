# 参数化 CAD 数字样机

- `parametric/geometry.json`：官方尺寸、设计假设和 V1 参数入口；
- `parametric/hanjie_model.scad`：可在 OpenSCAD 中渲染壳体、柔顺轴承座、夹具或总装；
- `generated/layout-v1.svg`：由脚本生成的俯视工程布局图。
- `generated/engineering-drawings/`：由 `parametric/generate_engineering_drawings.py` 生成的 7 张工程表达图，覆盖座、壳体、接头、焊缝布置、夹具总装/零件和焊接总装。

工程图包已经显式包含 A/B/C 基准、Ø0.05 位置度框、焊缝符号、槽宽、夹具自由度、材料和未注公差，但当前状态仍是 `design-review`，不是制造发布图：图纸中的座厚、翼宽、装配间隙、焊缝尺寸和夹具等效刚度属于设计假设。

当前环境没有 FreeCAD/OpenSCAD，因此仓库提交的是可复用 CAD 源文件和 SVG 工程表达图，不虚构 STEP/STL 导出。获得 CAD 软件后，应从同一 JSON 参数生成正式零件/装配文件，并完成三维关联、公差叠加、焊缝可达性、夹具干涉和企业制图标准复核。
