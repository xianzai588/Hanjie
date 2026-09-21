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

### 克隆后必做的 LFS 校验

```powershell
git lfs install
git clone git@github.com:xianzai588/Hanjie.git   # 或先 clone 再 git lfs pull
cd Hanjie
git lfs pull
git lfs fsck                                      # 期望：Git LFS fsck OK
Select-String -Path (git ls-files '*.step') -Pattern '^version https://git-lfs' -List
# 上一行无输出 = 所有 .step 都是真实内容；有输出说明仍是未取回的指针
```

判断指针与真内容：文件首行是 `version https://git-lfs.github.com/spec/v1` 即为未取回的指针；真实 STEP 首行为 `ISO-10303-21;`。

**2026-09-19 事故与修复记录**：服务端曾缺失 9 个 LFS 对象（2.0 MB，`cad/generated/tooling-access/`、`simulation/structural-v4/` 下的全部 `.step`），新克隆会报 `[404] Object does not exist on the server`。原因是这些指针来自历史提交，而 `git lfs push` 只扫描**本次新提交**涉及的对象，历史对象从未被校验上传。修复方式为按对象补传：

```powershell
git lfs ls-files --long                 # 取完整 oid
git lfs push --object-id origin <oid>   # 对每个服务端缺失的 oid 执行
```

已从全新目录克隆检出验证：11 个 `.step` 全部还原为真实 STEP（0 个指针）。**改动 `.step` 后请补跑一次 `git lfs push origin main`；若历史对象疑似缺失，用上面的 `--object-id` 方式补传。**

### 封版哈希校验

每个封版批次在 `deliverables/` 下留一份 `COMPETITION-R1-<RC>-SHA256.txt`，逐行记录产物哈希，格式与 `sha256sum` 一致（`#` 为注释行），可直接被标准工具消费。用仓库自带脚本校验（Windows 下不依赖 coreutils）：

```powershell
python scripts/verify_release_hashes.py --list          # 列出全部封版记录
python scripts/verify_release_hashes.py                 # 校验最新一批（应对当前工作树全部通过）
python scripts/verify_release_hashes.py --record deliverables/COMPETITION-R1-RC2-SHA256.txt
```

退出码 0 表示全部一致，1 表示存在缺失或不一致并逐项打印记录值与实际值。

注意：**只有最新一批记录能对当前工作树通过**。ZIP、说明书/设计图集 PDF 内嵌生成时间戳，每次重建都会变，因此历史记录是当时的快照校验值，要复验必须先检出对应提交。`04-设计计算.json`、`05-设计指标.csv` 与 `03-名义装配包络.step` 已是确定性输出（见下），在结果未变时应与历史记录保持一致。

### 构建确定性

`python deliverables/build_submission.py` 重建时，以下产物在输入未变的情况下逐字节稳定，便于比对与冻结：

- `03-名义装配包络.step`：`studies/COMPETITION-DESIGN/run.py` 把 OCC 写入 `FILE_NAME` 的导出时刻归一化为固定值（`normalize_step_timestamp()`），否则每次都生成仅差时间戳的新 LFS 对象。
- `15-确定性边界图.svg`、`16-位置度边界图.svg`：`studies/ROBUST-BOUNDARY/run.py` 固定 `svg.hashsalt` 并传入 `metadata={"Date": None}`，否则 matplotlib 每次都会改写元素 ID 与 `<dc:date>`。

ZIP 与两份 PDF 仍含生成时间戳，尚未做确定性处理；如需把它们也纳入可复现范围，应在构建时固定 PDF 的 `CreationDate`/`ModDate` 并以固定时间写入 ZIP 条目。
