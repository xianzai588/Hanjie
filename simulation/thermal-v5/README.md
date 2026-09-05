# THERMAL-0 / G-THERMAL

本目录执行 V5.2 计划一的三维瞬态热历史基线。模型采用 R74.98 mm 接口的周期展开坐标、温度相关热物性和离散 Goldak 双椭球；结果证据等级固定为 `solver_result_unvalidated`，不代表商业求解器或实验校准。THERMAL0.1 增加热源尺度解析度审计、精确坐标三线性插值、面面积边界热损失和全局热能账本。

## 运行

在仓库根目录执行：

```powershell
python simulation/thermal-v5/run_thermal0.py
python simulation/thermal-v5/audit_thermal0.py
python simulation/metallurgy-v5/run_metallurgy0.py
```

## 结果

- `results/thermal0-field.npz`：三维最终温度、峰值温度、冷却速率、t8/5 和材料分区。
- `results/thermal0-t85-samples.csv`：逐节点 `Tmax`、800/500°C 下降交点、t8/5 和有效标记。
- `results/thermal0-summary.json`：输入哈希、环境、热源能量和全场摘要。
- `results/g-thermal-audit/G-THERMAL-audit.json`：能量、网格、时间步、效率/换热/热源尺寸审计矩阵。
- `results/g-thermal-audit/G-THERMAL-audit.md`：审计结论和待复核项。

当前审计结论由 `G-THERMAL-audit.json` 记录；即使数值账本通过，也不等于热源已校准或可进入 THERMAL-1。焊缝金属暂采用 `pre-existing weld metal thermal surrogate`，逐段激活留待后续阶段。
