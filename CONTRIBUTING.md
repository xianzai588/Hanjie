# 协作规则

## 三条铁律

1. **原始实验数据永不覆盖** —— `experiments/raw-data/` 只增不改、不"美化"。处理结果放 `experiments/processed-data/`。
2. **每个试样唯一 ID** —— `W2026-001` 起编号。照片、电流、温度、金相、硬度、CMM 报告一律挂同一 ID。
3. **仿真结果不只给图** —— 每个 Case 必须包含 `config.yaml`（输入是什么）+ `README.md`（为什么这么设）+ `result.csv`（输出是什么）。

## 分支

```
main
├─ research/*      材料与焊接性
├─ simulation/*    仿真
├─ experiment/*    实验
├─ automation/*    软件与自动化
└─ docs/*          文档与报告
```

- main 永远保持可完整查看当前项目状态，成员改动走 PR 合并。
- 3~4 人团队不搞企业级 GitFlow，一层分支足够。

## Issue

- 所有任务先进 Issue，完成后在 PR 中关联（`Closes #N`）。
- 模拟评审中无法回答的问题也转 Issue 跟进。

## 大文件

- 仿真大文件（`*.odb` `*.rst` `*.rth` `*.cas` 等）禁止入库，见 `.gitignore`。
- CAD 源文件与视频走 Git LFS（见 `.gitattributes`）：`*.step` `*.stp` `*.sldprt` `*.sldasm` `*.dwg` `*.mp4`。
