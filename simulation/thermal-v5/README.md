# THERMAL-0 / G-THERMAL

本目录执行 V5.2 计划一的三维瞬态热历史基线。模型采用 R74.98 mm 接口的周期展开坐标、温度相关热物性和离散 Goldak 双椭球；结果证据等级固定为 `solver_result_unvalidated`，不代表商业求解器或实验校准。

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

当前审计结论：热源归一化和累计输入能量通过；时间步通过；medium→fine 峰值温度变化约 7.07%，参数敏感性仍需复核，因此 G-THERMAL 保持 `review_required`。
