# SCHAEFFLER-MAP：Schaeffler 相图组织映射与铸铁冷焊热制度计算

**执行**：`python studies/SCHAEFFLER-MAP/run.py`
**产物**：`results/schaeffler-mapping.json`、`results/schaeffler-mapping.csv`、
`results/thermal-regime.csv`、`results/schaeffler-map.svg`、`results/cold-weld-regime.svg`，
以及报告用图件 `docs/report/figures/schaeffler-map.png`、`docs/report/figures/cold-weld-regime.png`。

## 计算内容

1. **当量计算**：Cr_eq = Cr + Mo + 1.5 Si + 0.5 Nb；Ni_eq = Ni + 30 C + 0.5 Mn；
   Ms = 561 − 474C − 33Mn − 17Ni − 17Cr − 21Mo。
2. **成分输入**：Q235B（GB/T 700）、QT450-10（GB/T 1348）、NiFe-55（供方技术数据表，
   AWS A5.15 E NiFe-CI / EN ISO 1071 S C NiFe-2）。
3. **球墨铸铁石墨化修正**：11 vol% 球状石墨对应石墨碳 3.49 wt%，给出基体口径当量点。
4. **稀释率扫描**：D = 10%～50%，铸铁侧份额 r = 0.40（设计）与 r = 0.30（保守）。
5. **冷焊热制度**：座体蓄热、组件温升、自由径向收缩协调量与温度—位置度换算。

## 关键结论

- 焊缝金属全稀释域 Ni_eq 46.18～56.61、Cr_eq 0.32～1.18，稳居单相奥氏体区，
  相对 A+M 边界（Ni_eq 12～16）余量 ≥ 30 个当量单位；全部算例 Ms ≤ −217 ℃。
- Q235B 碳当量 0.263% < 0.40%，钢侧免预热。
- 铸铁淬硬倾向来自基体当量点 (3.95, 5.18)、Ms +468 ℃，与冷却速度无关，
  必须由填充金属从外部引入镍。
- 冷焊（不预热、层间 ≤ 100 ℃）相对预热 150 ℃ 少预置 40.94 kJ 蓄热，
  自由径向收缩协调量由 0.1024 mm 降至 0.0630 mm。
- 孔区与焊道之间 31.7 K 温差即产生 0.025 mm 径向漂移，等于 Ø0.05 mm 位置度径向限值。
