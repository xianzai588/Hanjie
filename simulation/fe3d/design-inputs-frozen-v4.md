# V4.3 热—结构设计输入索引

**日期**：2026-09-06
**状态**：当前入口；原 V4.0 手工参数表因与权威配置分叉而撤回，历史内容由 Git 保存。

本文件不再复制材料、工艺、公差或接头数字。完整工件热—结构模型建立时必须从以下权威源读取，并先运行 `validate_parameter_consistency()`：

| 输入域 | 唯一当前来源 | 证据边界 |
| --- | --- | --- |
| 官方尺寸、设计几何、夹具 | `project/baseline.yaml` | 设计假设；松夹温度 50±5 °C 待实物确认 |
| 名义工艺、窗口、送丝 | `project/process.yaml` | 候选工艺；未完成 WPS/PQR |
| 材料与温度相关物性 | `project/materials.yaml`、`project/thermal-physics-v5.3.yaml` | 非本批次实测，高温段含工程假设 |
| 产品/路径/测量三条公差链 | `project/tolerance.yaml` | 产品链 0.035 mm 径向，尚未闭合 |
| 局部热模型 | `project/thermal-mass-closed-v5.4r1.yaml` | 串联热阻修正版，未校准 |
| 结构候选与静力证据 | `simulation/structural-v4/results/static-screening/` | 仅三维线弹性受载筛查 |

## 当前冻结边界

- 工艺候选：自动 TIG，75 A、12 V、1.5 mm/s、η=0.55、150 °C 预热、≤200 °C 层间温度。
- 接头：3.5 mm 为设计焊脚目标；当前名义送丝只形成 1.508 mm² 新增截面积（约 1.737 mm 等效理想焊脚），二者未闭合。
- 结构：Continuous、6P、8P-FAIR_B 三个候选进入后续热—结构比较；静力排序不等于焊后位置度排序。
- 后处理：必须在松夹、热平衡并重新建立壳体 A/B 基准后拟合整个 Ø40 孔轴。

任何消费者若仍引用原 V4.0 表中的 169/206/180 GPa、旧 Goldak 尺度、10 W/(m²·K) 或 ε=0.8 等手工值，应视为配置错误，不得进入当前提交结果。
