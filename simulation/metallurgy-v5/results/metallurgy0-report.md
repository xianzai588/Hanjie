# METALLURGY-0 组织—性能风险预测

> 证据等级：`literature_supported_plus_solver_result_unvalidated`。本报告消费 THERMAL-0 热历史，未消费任何实测金相、硬度或化学成分数据。

## 结果摘要

- QT450-10 侧空间区域峰值温度：1009.7 °C；最大离散冷却速率：1452.8 °C/s；t8/5 中位数：1.9562516475713778 s。
- Q235B 侧空间区域峰值温度：627.1 °C；最大离散冷却速率：109.3 °C/s；t8/5 中位数：无有效节点 s。

## 风险判定

| 材料侧 | 风险项 | 等级 |
| --- | --- | --- |
| qt450_10 | white_cast_iron_carbide_risk | **Medium** |
| qt450_10 | martensite_high_hardening_risk | **High** |
| qt450_10 | haz_embrittlement_risk | **Medium** |
| qt450_10 | cold_crack_risk | **Medium** |
| q235b | high_temperature_grain_coarsening_risk | **Low** |
| q235b | hardening_risk | **Medium** |
| q235b | haz_embrittlement_risk | **Low** |

## 焊缝稀释—成分区间

- 名义焊缝金属截面积：6.125 mm²。
- 名义 QT450-10 熔入比例：35.3%；Q235B 熔入比例：23.5%。
- Ni 区间：19.74–26.55 wt%；C 区间：1.26–1.79 wt%。
- 上述成分为 geometry_based_nominal 稀释贡献的敏感性估计，不是焊缝化学分析结果；填充金属贡献约为 41.2%。

## Gate 边界

- G-METALLURGY：**未通过物理验证**；当前可作为 THERMAL-0 驱动的风险筛查。
- 下一步物理证据：宏观截面 → 金相（QT 母材—QT HAZ—熔合线—NiFe 焊缝—Q235B HAZ—母材）→ 显微硬度线扫。
