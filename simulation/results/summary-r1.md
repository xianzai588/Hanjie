# 第一轮数字仿真结果（R1）

> 结果来自降阶热—结构代理模型；不是有限元或实物测量。

| 算例 | 结构 | 夹具 | 点数 | 顺序 | P_sim (mm) | 相对同点数 S1 降低 (%) | 模型内判定 |
| --- | --- | --- | ---: | --- | ---: | ---: | --- |
| BASELINE-RIGID-4P-S1 | baseline | rigid | 4 | S1 | 0.039049 | 0.000 | True |
| BASELINE-RIGID-4P-S2 | baseline | rigid | 4 | S2 | 0.019524 | 50.001 | True |
| BASELINE-RIGID-4P-S3 | baseline | rigid | 4 | S3 | 0.019524 | 50.001 | True |
| BASELINE-RIGID-6P-S1 | baseline | rigid | 6 | S1 | 0.049701 | 0.000 | True |
| BASELINE-RIGID-6P-S2 | baseline | rigid | 6 | S2 | 0.016567 | 66.667 | True |
| BASELINE-RIGID-6P-S3 | baseline | rigid | 6 | S3 | 0.016567 | 66.667 | True |
| BASELINE-RIGID-8P-S1 | baseline | rigid | 8 | S1 | 0.061845 | 0.000 | False |
| BASELINE-RIGID-8P-S2 | baseline | rigid | 8 | S2 | 0.015461 | 75.000 | True |
| BASELINE-RIGID-8P-S3 | baseline | rigid | 8 | S3 | 0.015461 | 75.000 | True |
| FLEX-COMPLIANT-4P-S2 | flex | compliant | 4 | S2 | 0.010356 | 73.479 | True |
| FLEX-COMPLIANT-4P-S3 | flex | compliant | 4 | S3 | 0.010356 | 73.479 | True |
| FLEX-COMPLIANT-6P-S2 | flex | compliant | 6 | S2 | 0.008787 | 82.320 | True |
| FLEX-COMPLIANT-6P-S3 | flex | compliant | 6 | S3 | 0.008787 | 82.320 | True |
| FLEX-COMPLIANT-8P-S2 | flex | compliant | 8 | S2 | 0.008201 | 86.739 | True |
| FLEX-COMPLIANT-8P-S3 | flex | compliant | 8 | S3 | 0.008201 | 86.739 | True |

## 解释

基准参照为相同连接单元数、刚性基准结构、刚性夹具和 S1 顺序；`P_sim` 是按内孔轴线构造的数值评价指标。
当前代理模型中 S2 与 S3 对称性完全相同，因此不能据此宣称二者存在性能差异；S3 仅作为路径生成的代表顺序。
8 点柔顺方案的 `P_sim` 最小，但 6 点方案在模型内仍低于限值且总焊段更少、总热输入更低，因此 V1 将 6 点作为主方案、8 点作为对照；最终取舍待 FE/物理验证。
