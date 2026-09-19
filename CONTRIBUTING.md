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
