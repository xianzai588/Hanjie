# 数据规范

## 样件唯一编号

所有样件使用 `W2026-XXX` 编号（从 W2026-001 起）。电流、温度、照片、金相、硬度、CMM 报告一律挂同一编号。

## 原始数据铁律

- `experiments/raw-data/` 只增不改、不覆盖、不"美化"。
- 清洗/计算/统计结果放 `experiments/processed-data/`，并注明来源编号与处理脚本。

## 数据模式

焊接过程采集数据结构见 [schemas/weld-session.schema.json](schemas/weld-session.schema.json)（WP6 模块三）。

## 目录约定

```
data/
├─ schemas/      JSON Schema 等数据定义
└─ samples/      样例数据（演示用，非实验原始数据）
```
