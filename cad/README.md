# CAD 模型与图纸入口

参赛主方案采用完整圆环，输入来自 `project/submission-baseline.yaml`。`parametric/build_ring_baseline.py` 生成座体、总装和八个局部双层预制窗口的 STEP，以及 HJ-S01、HJ-S02 两张设计图，输出目录为 `generated/ring-baseline/`。

八翼开口方案作为结构候选保留。其输入为 `project/competition-design.yaml`，`parametric/competition_drawings.py` 读取对应的真实座体 BREP 并生成 HJ-001～HJ-021。`parametric/generate_engineering_drawings.py` 的命令入口已转到该生成器；文件内旧绘图函数仅供历史复查。八翼方案的应力、变形及热模型结果按原模型身份使用。

| 对象 | 输入与生成入口 | 文件用途 |
|---|---|---|
| 完整圆环参赛主方案 | `project/submission-baseline.yaml`、`parametric/build_ring_baseline.py` | 参赛几何、局部预制结构与工序接口 |
| 八翼结构候选 | `project/competition-design.yaml`、`parametric/competition_drawings.py` | 结构比较和原八翼计算的几何对象 |
| V1 六点、12 mm 座厚 | `parametric/geometry.json`、`parametric/hanjie_model.scad`、`parametric/generate_drawing.py --historical-v1` | 早期草图与历史算例复查 |
| P1A 公平比较实体 | `simulation/structural-v4/generate_seat_geometry.py` | 七个旧比较模型，输出位于 `simulation/structural-v4/models/` |

`parametric/geometry.json` 保留原有 V1-6P-t12 参数，并增加 `provenance` 标识。旧的领域一致性校验、ROUTE-B 与 TOOLING-ACCESS 仍读取其中的焊脚、配合或夹具字段；这些兼容读取不代表整份 V1 几何适用于当前圆环。复用历史脚本前，先核对其模型身份和所读取的字段。圆环输入与八翼输入分别维护，不以替换旧参数的方式继承旧计算结果。

STEP 实体检查用于确认几何、材料分区和工装接口。图中的焊接工艺和尺寸要求用于指导后续试制与检验，具体接头能力按对应工艺设计卡及正文的论证对象判定。
