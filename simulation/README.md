# 降阶热—结构仿真

本目录当前提供一个不依赖 Abaqus/ANSYS 的、用于方案筛选的降阶代理模型。它不是有限元求解器，也不输出经过实验标定的温度场或残余应力。

## 运行

在仓库根目录执行：

```powershell
python simulation/scripts/run_reduced_order.py
python simulation/scripts/position_tolerance.py --demo
```

结果写入 `simulation/results/`：

- `summary.csv`：不同连接单元数、焊接顺序、结构/夹具组合的可追溯结果；
- `summary.png` 与 `summary.svg`：位置度评价指标和椭圆度对比图；
- `run-metadata.json`：输入参数、脚本版本和模型声明。

## 评价指标

模型先计算每个焊段的等效收缩向量，再拟合孔中心在有效高度内的名义轴线：

$$P_{sim}=2\max_z\sqrt{x(z)^2+y(z)^2}$$

`P_sim` 与比赛位置度直径限值 Ø0.05 mm 使用相同的“直径”量纲，但它不是 CMM 结果。只有真实焊后完全冷却、解除夹具后测量内孔并完成基准建立，才能出具实测位置度。

