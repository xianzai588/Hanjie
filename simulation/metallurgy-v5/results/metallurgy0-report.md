# METALLURGY-0 组织—性能风险预测

> 证据等级：`literature_supported_plus_solver_result_unvalidated`。本报告消费 THERMAL-0 热历史，未消费任何实测金相、硬度或化学成分数据。

## 结果摘要

- QT450-10 母材峰值温度：434.9 °C；最大离散冷却速率：115.3 °C/s；t8/5 中位数：无有效节点 s。
- Q235B 母材峰值温度：525.9 °C；最大离散冷却速率：125.0 °C/s；t8/5 中位数：无有效节点 s。
- ERNiFe-CI 代理焊缝峰值温度：897.0 °C；高温物性和相变模型补齐前不评分焊缝冶金风险。
- 母材热暴露宽度（Tpeak≥400 °C，排除 ±3 mm 代理焊缝带）：QT450-10=0.279 mm，Q235B=1.606 mm。

## 风险判定

| 材料侧 | 风险项 | 等级 |
| --- | --- | --- |
| qt450_10 | white_cast_iron_carbide_risk | **unresolved_due_to_non_fusing_thermal_baseline** |
| qt450_10 | martensite_high_hardening_risk | **unresolved_due_to_non_fusing_thermal_baseline** |
| qt450_10 | haz_embrittlement_risk | **unresolved_due_to_non_fusing_thermal_baseline** |
| qt450_10 | cold_crack_risk | **unresolved_due_to_non_fusing_thermal_baseline** |
| q235b | high_temperature_grain_coarsening_risk | **unresolved_due_to_non_fusing_thermal_baseline** |
| q235b | hardening_risk | **unresolved_due_to_non_fusing_thermal_baseline** |
| q235b | haz_embrittlement_risk | **unresolved_due_to_non_fusing_thermal_baseline** |

## 焊缝稀释—成分区间

- 名义焊缝金属截面积：6.125 mm²。
- 名义 QT450-10 熔入比例：35.3%；Q235B 熔入比例：23.5%。

- 保守单道等效敏感性：Ni 19.74–26.55 wt%；C 1.05–1.60 wt%。

| 口径 | 填充 | QT450-10 | Q235B | Ni wt% | C wt% |
| --- | ---: | ---: | ---: | ---: | ---: |
| 单道等效（保守下界） | 41.2% | 35.3% | 23.5% | 22.65 | 1.33 |
| 仅第一道熔入 1.5/1.0 | 58.3% | 25.0% | 16.7% | 32.08 | 0.95 |
| 仅第一道熔入 0.8/0.5 | 72.9% | 16.7% | 10.4% | 40.10 | 0.63 |
| 零稀释（纯焊材参考） | 100.0% | 0.0% | 0.0% | 55.00 | 0.01 |

- 逐道分支把母材熔入归于第一道，后三道只作上道表面重熔的名义比较；其填充等效面积采用 z² 口径，不等同于实测熔池截面。上述所有数值均待 §9.2 L7 的宏观截面与化学分析回填。
- 无论采用哪一口径，当前成分范围对应 Fe-Ni-C 奥氏体（Ni 约 20–40 wt%）；不得把它当作未稀释镍基固溶体，也不得把供方未稀释熔敷金属 Rm 450 MPa 直接当作本接头强度。

## Gate 边界

- G-METALLURGY：**未通过物理验证**；未热激活的母材标记 unresolved，不能把 Low 或未激活解释为方案安全。
- 下一步物理证据：宏观截面 → 金相（QT 母材—QT HAZ—熔合线—NiFe 焊缝—Q235B HAZ—母材）→ 显微硬度线扫。
