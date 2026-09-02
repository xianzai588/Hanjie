# 参数化 CAD 数字样机

- `parametric/geometry.json`：官方尺寸、设计假设和 V1 参数入口；
- `parametric/hanjie_model.scad`：可在 OpenSCAD 中渲染壳体、柔顺轴承座、夹具或总装；
- `generated/layout-v1.svg`：由脚本生成的俯视工程布局图。

当前环境没有 FreeCAD/OpenSCAD，因此仓库提交的是可复用 CAD 源文件和 SVG 预览，不虚构 STEP/STL 导出。获得 CAD 软件后，应从同一 JSON 参数生成正式零件/装配文件，并对翼端间隙、焊缝可达性和夹具干涉做工程复核。
