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

### 需要使用CAD文件时检查真实内容

```powershell
Get-Content -LiteralPath 'cad/generated/competition-design/competition-assembly-r4.step' -TotalCount 1
```

判断指针与真内容：文件首行是 `version https://git-lfs.github.com/spec/v1` 即为未取回的指针；真实 STEP 首行为 `ISO-10303-21;`。仅在所需文件是指针时取回其内容；用于提交的STEP须实际打开，确认实体和工程覆盖范围。克隆、全库LFS检查与远端补传不是每轮设计整改的必做工作。

**2026-09-19 事故与修复记录**：服务端曾缺失 9 个 LFS 对象（2.0 MB，`cad/generated/tooling-access/`、`simulation/structural-v4/` 下的全部 `.step`），新克隆会报 `[404] Object does not exist on the server`。原因是这些指针来自历史提交，而 `git lfs push` 只扫描**本次新提交**涉及的对象，历史对象从未被校验上传。修复方式为按对象补传：

```powershell
git lfs ls-files --long                 # 取完整 oid
git lfs push --object-id origin <oid>   # 对每个服务端缺失的 oid 执行
```

当时已从新克隆检出11个真实STEP。该记录仅说明2026-09-19修复时的内容状态；当前交付按实际文件检查。远端对象缺失时再针对具体对象处理，不重复克隆或补传整库。

### 历史封版记录与当前收束

`COMPETITION-R1-*-SHA256.txt`、`scripts/verify_release_hashes.py`及旧导出时间戳归一化代码保留为R1封版历史。历史哈希对应当时产物，不能要求当前修订文件与旧快照逐字节一致；逐批SHA校验、确定性构建、固定PDF/ZIP时间戳均不再列为当前强制工作。

当前交付检查集中在说明书与WPS的一致性、匿名、图纸可读性、必要STEP真实实体及覆盖范围、关键设计数字与有效计算来源。只有能提高说明书质量或答辩说服力的检查才进入本轮工作；不扩展测试数量或重复整包重建。
