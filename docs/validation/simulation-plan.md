# 仿真计划（WP4）

> 版本：V1.0 · 2026-09-02。原则：**不做“为了有云图而仿真”**，只回答一个问题——怎样把焊接变形降到最低。
> 当前环境没有商用求解器，因此先运行 `simulation/scripts/run_reduced_order.py` 完成方案筛选；它是降阶代理模型，不是有限元替代品。

## 模型一：等效热输入代理

| 输入 | 输出 |
| --- | --- |
| `ηUI/v` 线热输入 | 有效峰值温度代理 |
| 预热温度、等效热容 | HAZ 宽度代理 |
| 焊缝数量与长度 | 总热输入与收缩向量 |
| 热效率、物性扰动 | 敏感性结果 |

## 模型二：收缩向量—轴线评价

输出：

- ΔX / ΔY / ΔZ
- 轴承孔轴线倾斜
- 壳体椭圆变形
- 残余应力（当前未计算，待 FE 求解器）

对焊后完全冷却、解除夹具后的 Ø40 内孔点云，按多个 z 截面拟合圆，再对圆心拟合轴线：

$$\mathbf p(z)=\mathbf p_0+\mathbf v z$$

在有效孔高范围计算：

$$P_{sim}=2\max_z\sqrt{x(z)^2+y(z)^2}$$

该量纲与比赛位置度直径限值一致，但必须在报告中注明：**数值评价指标，不是 CMM 认证结果。**

## 方案对比（核心产出）

| 方案 | 焊缝布局 | 顺序 | 热输入 | 位置偏差 |
| --- | --- | --- | ---: | ---: |
| V0 | 初始 | 顺序 | — | — |
| V1 | 优化 | 对称 | — | — |
| V2 | 优化 | 跳焊 | — | — |
| Final | 六点柔顺 | S2/S3 | 75 A / 12 V / 1.5 mm/s | 脚本输出 |

结论必须给出**相对基准方案的量化降低量**，不允许只写"效果显著"。

## 当前可运行内容

- 9 组基准：4/6/8 点 × S1/S2/S3；
- 6 组优化：4/6/8 点 × S2/S3，六点柔顺结构 + 柔顺夹具对照；
- 结果：`simulation/results/summary.csv`、`summary.png`、`summary.svg`；
- 参数扫描：`python simulation/scripts/run_sensitivity.py`，输出 `sensitivity.csv`；
- 输入：`simulation/configs/default.yaml`，设计假设见 [../05-design-assumptions.md](../05-design-assumptions.md)。

当前还没有 FE 求解器，因此不把解析/降阶离散精度扫描包装成网格收敛。获得 Abaqus/ANSYS/SYSWELD 等工具后，必须补做粗/中/细网格，并记录单元尺寸、单元数、孔轴线评价指标和相邻网格相对差异。

## Case 管理规范

每个算例一个目录 `simulation/cases/SIM-XXX/`：

```
SIM-XXX/
├─ config.yaml    输入参数（功率/速度/热效率/预热/布局/顺序）
├─ README.md      为什么这么设
├─ model/         模型文件（大文件不入库）
├─ raw/           求解器原始输出（大文件不入库）
└─ result.csv     提取后的关键结果
```

网格、材料参数等可复用资源放 `simulation/models/`、`simulation/materials/`。
