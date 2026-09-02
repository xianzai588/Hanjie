# 最终提交物清单（WP8）

01 **技术说明书.pdf**

02 **焊接工艺文件**
   - 工艺选型
   - 工艺参数
   - 工艺卡

03 **工程设计**
   - 接头图
   - 焊缝布置图
   - 夹具总装
   - 零件图

04 **仿真**
   - 温度场
   - 变形
   - 应力
   - 优化前后对比

05 **实验**
   - 原始数据
   - 照片
   - 金相
   - 硬度
   - 测量结果

06 **自动化**
   - 源代码
   - 系统架构
   - 视觉定位
   - 监测程序
   - 数据分析

07 **展示**
   - 演示视频
   - 技术路线图
   - 答辩材料

> 说明：实施方案未规定格式与篇幅，最终作品允许项目研究报告、设计图或研究实物等形式。
> 产物归档至 `deliverables/{report,drawings,presentation,video}`。

## V2 证据写法约束

- 降阶结果统一写作 `P_sim`，引用 `simulation/results/summary-r1.md` 和 `simulation/results/monte-carlo/`，不得写成 CMM 位置度。
- 二维热—结构代理结果统一写作 `P_FE`，引用 `simulation/fe/results/fe-summary.md` 和对应 `simulation/cases/FE-00x/bore-nodes.csv`；必须注明等效焊桥、弹簧夹具、峰值温度未达到熔化温度，以及未包含的熔池/熔合、三维/塑性/相变边界。
- FE-001/002 连续座体刚性基准与 FE-003 柔顺方案并列呈现；由于 FE-003 指标较高，V2 不得把柔顺结构表述为已被完整焊接 FE 证明的唯一最优结构，其作用仅为独立结构反例检查。
- 视觉章节以误差预算和工程判定为主指标；“检测返回率”只表示算法返回结果，必须同时报告径向 MAE、角度 MAE 和 PASS/FAIL。
- 工程基准统一为 A=壳体安装基准平面、B=壳体理论中心轴、C=独立周向定位特征；Ø40 孔轴线位置度统一写作 `Ø0.05 | A | B`。
- 自动化章节引用 `automation/vision/results/difficult-summary.md` 和 `automation/anomaly-detection/results/benchmark/summary.md`；所有样本均标记为数字渲染或仿真注入。
- 工程图引用 `cad/generated/engineering-drawings/drawing-manifest.json`，状态写作 `design-review`，不得冒充制造发布图、合格 WPS 或实测记录。
