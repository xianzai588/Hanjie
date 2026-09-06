# THERMAL-0 / G-THERMAL

本目录执行 V5.2 计划一的三维瞬态热历史基线。THERMAL0.2 在 R74.98 mm 接口附近采用固定局部展开窗口，母材、边界和测点保持固定，仅离散 Goldak 双椭球热源沿 `s` 移动；结果证据等级固定为 `solver_result_unvalidated`，不代表商业求解器或实验校准。模型包含热源尺度解析度、归一化前有限域捕获率、固定测点坐标、面面积边界热损失和全局热能账本审计。

当前生产入口为 **THERMAL-0.4R1**。它保留 0.4 的连续填丝质量闭合与投影表面热源，并将非均匀异材公共面导热修正为 `G=A/(d_if/k_i+d_jf/k_j)`。历史 `mass-closed04` 与 `credibility04r` 目录只作修正前对照，不得与 0.4R1 混用。

## 运行

在仓库根目录执行：

```powershell
python simulation/thermal-v5/run_thermal0.py
python simulation/thermal-v5/audit_thermal0.py
python simulation/metallurgy-v5/run_metallurgy0.py
python simulation/thermal-v5/run_credibility04r.py --case all
python simulation/thermal-v5/audit_credibility04r.py
```

## 结果

- `results/thermal0-field.npz`：三维最终温度、峰值温度、冷却速率、t8/5 和材料分区。
- `results/thermal0-t85-samples.csv`：逐节点 `Tmax`、800/500°C 下降交点、t8/5 和有效标记。
- `results/thermal0-summary.json`：输入哈希、环境、热源能量和全场摘要。
- `results/g-thermal-audit/G-THERMAL-audit.json`：能量、网格、时间步、效率/换热/热源尺寸审计矩阵。
- `results/g-thermal-audit/G-THERMAL-audit.md`：审计结论和待复核项。
- `results/credibility04r1/assessment.json`：串联热阻修正后的名义、源结构、物性端点、网格与时间步审计，以及相对历史 0.4R 的差异。

当前审计结论由 `G-THERMAL-audit.json` 记录；即使数值账本、热源域捕获和网格/时间步检查通过，也不等于热源已校准或可进入 THERMAL-1。焊缝金属暂采用 `pre-existing weld metal thermal surrogate`，逐段激活和相变焓模型留待后续阶段。
