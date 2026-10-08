# 仿真目录与历史代理模型

当前设计与计算状态从 [competition-entry](../deliverables/competition-entry/00-提交与阅读说明.txt) 及 [current-status.json](../deliverables/report/generated/current-status.json) 阅读。计算按冻结的设计问题、有效输入及必要离散对照执行，服务于接头、制造残余与完全卸夹孔形等具体决策。失效热史保持停止继承；公开证据补强和独立设计核算可逐项推进。

## 历史代理模型（停用为当前运行入口）

以下脚本及输出保留为早期方案筛查记录；代理模型、二维交叉检查和1000次Monte Carlo不是当前必跑步骤，也不作为现行8P制造性能通过证据：

| 历史脚本 | 当时用途 |
| --- | --- |
| `scripts/run_reduced_order.py` | 等效收缩向量的降阶筛查 |
| `scripts/position_tolerance.py --demo` | 合成孔点位置度演示 |
| `fe/run_fe_cases.py` | 不依赖商用求解器的二维热—结构代理交叉检查 |
| `scripts/run_monte_carlo.py --count 1000` | 历史参数扰动统计 |

历史结果保存在 `simulation/results/`：

- `summary.csv`：不同连接单元数、焊接顺序、结构/夹具组合的可追溯结果；
- `summary.png` 与 `summary.svg`：位置度评价指标和椭圆度对比图；
- `run-metadata.json`：输入参数、脚本版本和模型声明。
- `monte-carlo/`：1000 次参数扰动及 P5/P50/P95、worst、超限比例。
- `../fe/results/`：FE-001..005 二维热—结构匹配复核、`fe-convergence.csv` 网格检查与结果图。

## 历史评价指标与适用范围

模型先计算每个焊段的等效收缩向量，再拟合孔中心在有效高度内的名义轴线：

$$P_{sim}=2\max_z\sqrt{x(z)^2+y(z)^2}$$

`P_sim` 与比赛位置度直径限值 Ø0.05 mm 使用相同的“直径”量纲，但它不是 CMM 结果。只有真实焊后完全冷却、解除夹具后测量内孔并完成基准建立，才能出具实测位置度。

## 模型分层

`P_sim` 是降阶代理模型指标；`P_FE` 是二维热—结构代理交叉检查指标。FE 案例输出的
`bore-nodes.csv` 直接送入 `position_tolerance.py`，但二维截面沿 z 方向复制，不能
证明真实三维倾斜。当前峰值温度远未达到钢/铸铁熔化温度，模型没有模拟熔池形成、
熔合、焊缝金属激活、温度相关塑性或相变。统一 S3 后，FE-003（柔顺/柔顺夹具）高于
FE-002，而 FE-005（柔顺/刚性夹具）略低于 FE-002；这说明“柔顺降低变形”不能仅凭
降阶模型成立。FE 的主要作用是提供结构和夹具边界的反例，正式结论必须等待三维 FE 或物理数据。
