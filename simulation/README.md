# 降阶热—结构仿真

本目录同时提供降阶方案筛选和不依赖商用求解器的二维 FE 热—结构复核。两条模型证据链均不是经过实验标定的温度场、残余应力或 CMM 结果。

## 运行

在仓库根目录执行：

```powershell
python simulation/scripts/run_reduced_order.py
python simulation/scripts/position_tolerance.py --demo
python simulation/fe/run_fe_cases.py
python simulation/scripts/run_monte_carlo.py --count 1000
```

结果写入 `simulation/results/`：

- `summary.csv`：不同连接单元数、焊接顺序、结构/夹具组合的可追溯结果；
- `summary.png` 与 `summary.svg`：位置度评价指标和椭圆度对比图；
- `run-metadata.json`：输入参数、脚本版本和模型声明。
- `monte-carlo/`：1000 次参数扰动及 P5/P50/P95、worst、超限比例。
- `../fe/results/`：FE-001/002/003 二维热—结构复核与结果图。

## 评价指标

模型先计算每个焊段的等效收缩向量，再拟合孔中心在有效高度内的名义轴线：

$$P_{sim}=2\max_z\sqrt{x(z)^2+y(z)^2}$$

`P_sim` 与比赛位置度直径限值 Ø0.05 mm 使用相同的“直径”量纲，但它不是 CMM 结果。只有真实焊后完全冷却、解除夹具后测量内孔并完成基准建立，才能出具实测位置度。

## 模型分层

`P_sim` 是降阶代理模型指标；`P_FE` 是高分辨率二维 FE 复核指标。FE 案例输出的
`bore-nodes.csv` 直接送入 `position_tolerance.py`，但二维截面沿 z 方向复制，不能
证明真实三维倾斜。FE-003 的柔顺结构结果高于 FE-001/002，说明“柔顺降低变形”
不能仅凭降阶模型成立；正式结论必须等待三维 FE 或物理数据。
