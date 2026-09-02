# FE 三案例复核结果

> 这是高分辨率二维 FE 热—结构复核，不是完整三维焊接仿真或 CMM 结果。

| Case | 方案 | 顺序 | 网格节点 | 网格单元 | P_FE (mm) | 模型内判定 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| FE-001 | baseline/rigid | S1 | 2800 | 5312 | 0.001449982 | True |
| FE-002 | baseline/rigid | S2 | 2800 | 5312 | 0.001466765 | True |
| FE-003 | flex/compliant | S3 | 1678 | 2632 | 0.002599523 | True |

## 排序

当前 FE 案例排序：FE-001 → FE-002 → FE-003。排序只对这三个二维模型成立。

FE 内孔节点已经写入各 Case 的 `bore-nodes.csv`，并由 `position_tolerance.fit_axis` 分层拟合圆和轴线。二维模型沿 z 复制截面，因此不提供真实三维倾斜证据。
