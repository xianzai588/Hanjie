# 数据规范

## 样件唯一编号

所有样件使用 `W2026-XXX` 编号（从 W2026-001 起）。电流、温度、照片、金相、硬度、CMM 报告一律挂同一编号。数字样本使用相同编号规则，但 `meta.source_type` 必须写为 `simulated`。

## 原始数据铁律

- `experiments/raw-data/` 只增不改、不覆盖、不"美化"。
- 清洗/计算/统计结果放 `experiments/processed-data/`，并注明来源编号与处理脚本。
- 仿真和数字样本可以放在 `data/samples/` 或对应模块的 `results/`，文件名和元数据必须包含 `simulated` 或等价字段。

## 数据模式

焊接过程采集数据结构见 [schemas/weld-session.schema.json](schemas/weld-session.schema.json)（WP6 模块三）。

## 目录约定

```
data/
├─ schemas/      JSON Schema 等数据定义
└─ samples/      样例数据（演示用，非实验原始数据）
```
