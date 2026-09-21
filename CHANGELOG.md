# Changelog

## COMPETITION-R1-RC4 - 2026-09-20

本批次是两条并行 RC3 工作线（远端按官方五维度重组、本地落实指导教师评审意见）合并后的封版。两条工作线均自称 RC3 且各自重建过产物，因此合并后重新封版为 RC4，RC3 记录保留为历史。

**落实指导教师 2026-09-04 评审意见**

- 说明书新增 §2.4「焊缝组织预估与接头性能推测」，回应意见①（按母材、焊接材料及焊接工艺预估焊缝组织、推测性能）：给出输入三要素表、名义稀释成分区间（Ni 19.74～26.55 wt%、C 1.26～1.79 wt%）、五区分区组织预估表（焊缝区镍基奥氏体／富镍熔合线／铸铁侧半熔化区白口带／铸铁侧针状马氏体热影响区／Q235B 侧粗晶—细晶区）与四项性能推测（强度匹配方向、硬度梯度、疲劳萌生位置、组织—变形耦合），并注明全部为机理预估、不含实测金相与显微硬度数据。
- 说明书新增 §6.3「焊后变形量的软件预算方案」，回应意见②（根据线膨胀系数、焊接参数及约束条件用相关软件预算变形量）：给出 Sysweld／Simufact 与 Abaqus＋DFLUX 两套方案、三类冻结输入清单、四项输出回填路径与三因素敏感性交叉校核。线膨胀系数按 `project/materials.yaml` 权威口径取值（Q235B 12.0、QT450-10 10.5、ERNiFe-CI 11.0，单位 10⁻⁶/K），未沿用历史草稿中与配置分叉的 13.0/11.0；不引用已撤回的 V4.0 热源、对流与辐射手工值。本节只交付方法与输入，不输出计算变形量数值。

**固定题目合规修正**

- §8 五维表「质量检测与评价」行删除对包外证据的引用（原“困难视觉和异常信号基准”位于 `automation/vision`、`automation/anomaly-detection`，不在 21 项交付包内），改为包内 11～16 号可核对项；「自动化焊接方案」行删除“视觉基准、异常检测基准、端到端演示”，改为包内 06/07 号工艺卡与设计参数冻结表；「材料选配与连接」行补入分区组织预估与稀释成分区间。
- §7.1 新增「无损检测方法」：PT／MT／UT 按缺陷类型分工，明确 UT 需以同批材料确认探头与对比试块、5 mm 壁厚下 RT 不作主手段、金相与宏观截面为交叉验证而非替代。
- §9.2 新增 L11（组织与性能推测未实测回填）、L12（变形量软件预算未执行求解）两行未闭合项，使新增两节的证据边界进入统一台账。

**脚本与依赖**

- `studies/COMPETITION-DESIGN/run.py` 合并后同时保留两项改动：CSV 定点输出 `fixed()`（15 位有效数字，清除 `0.04360000000000001`、`330.00000000000006`、`142559.99999999983` 一类浮点表示噪声）与 STEP 头部 `FILE_NAME` 时间戳归一化 `normalize_step_timestamp()`。
- `requirements.txt` 补声明 `pandas>=2.0`（`robust_selection.py`）与 `pymupdf>=1.24`（`build_submission.py`、`competition_submission_lint.py`、`export_drawing_pdfs.py`），此前缺失会导致构建链在缺依赖环境中断。

**验证**

- `python deliverables/build_submission.py` → 重建技术包并通过 `scripts/competition_submission_lint.py`：`{"status": "PASS", "files": 19, "report_pages": 25, "drawing_pages": 6}`。
- `python -m pytest -q` → 216 passed、1 failed（Python 3.11.9）。唯一失败项 `test_thermal_plan7::test_native_components_require_nonlinear_convergence` 的成因是本机 `core.autocrlf=true` 把 `simulation/thermal-ref/ReferenceCallbacks.F90` 检出为 CRLF，而该测试比对的 sha256 按 LF 内容记录；该目录在两条工作线上均未被修改，属检出环境差异而非本批次回归。
- 页数口径：说明书 22 页（RC3）→ 25 页（RC4），图集 6 页；同步更新 `10-复现与版本冻结记录.md`、`submission-checklist.md`、`registration-description.md` 三处声明，页数门禁通过。
- 重新封版为 RC4，新增 `deliverables/COMPETITION-R1-RC4-SHA256.txt`；RC1～RC3 哈希记录保留为历史，可用 `python scripts/verify_release_hashes.py --record <记录文件>` 复核。

## COMPETITION-R1-RC3 - 2026-09-20

按官方命题五个维度与考核要点逐条复核后，完成说明书内容补齐与叙事重组；本轮不新增未运行的数值声明，全部新增内容基于已有计算结果、真实几何与文献。

- 说明书新增五节：§2.1 异种材料界面设计与表面预处理（对应维度②的界面/过渡层/预处理/强韧匹配）、§3.2 应力释放与反变形与隔热结构（对应维度③）、§6.1 焊接变形精密测量、§6.2 焊缝疲劳与寿命评估（对应维度④的力学性能与疲劳试验方案）、§9.2 局限与验证路线。
- 恢复 v2 说明书被删除的疲劳章节并更新为 6P 四道口径：IIW 名义应力法 FAT 63～80 基线、参考包络角点名义应力 52.17 MPa、FAT 63 名义裕量 1.21、三级验证试验计划。
- 新增 §3.1，正面说明 6P 把焊缝压到整圈 22.9%、承载裕量由 5.0× 降至 1.15× 的代价，并给出 6P→8P 的自动切换边界。
- 新增预算反算：由 Ø0.05 上限反算热残余允许径向上限 0.0102 mm，使位置度由待验证项变为有数值门限的放行条件。该反算与 `studies/ROBUST-BOUNDARY` 输出一致。
- 叙事重组：摘要改为结论先行并新增「条件性达标判断」表；把分散全文的"未验证/不宣称"集中到 §9.2；局部热模型明确登记为热输入窗口依据并声明不作为位置度证据；432 例敏感性的"不可分辨"结论改写为设计依据。
- 工艺卡 `06-工艺提案.md` 增加界面与过渡层、稀释控制、表面预处理、反变形、应力释放与隔热、后热、疲劳基线七行。
- 修复边界图缺失中文字形：`studies/ROBUST-BOUNDARY/run.py` 新增 `configure_cjk_font()`，复用 `project/report.yaml` 的字体候选（本次解析为 DengXian），并设置 `svg.fonttype=path`，使两张随包交付的 SVG 在任何查看器下字形一致，构建警告由 60 余条归零。
- 页数口径同步：说明书由 14 页增至 22 页，图集 6 页；更新 `10-复现与版本冻结记录.md`、`submission-checklist.md`、`registration-description.md` 与 `00-评审导航.txt`。
- 新增 `docs/review/competition-r1-gap-analysis.md` 记录本轮诊断依据。
- 测试锚点收敛：`test_report_contains_single_decision_rule` 改为锚定标题文本并断言全篇仅一处决策表，避免章节号漂移导致假失败。
- 验证：`python -m pytest -q` → 217 passed；`scripts/competition_submission_lint.py` → PASS（19 文件、22/6 页）。
- LFS 校验：本轮改动了 `cad/generated/competition-design/competition-assembly.step`，已随提交推送；按 `CONTRIBUTING.md` 的规程在全新目录克隆复核，11 个 `.step` 全部还原为真实 STEP、0 个指针，`git lfs push --dry-run` 无残留待传对象。
- 重新封版为 RC3，新增 `deliverables/COMPETITION-R1-RC3-SHA256.txt`（技术包 ZIP、manifest、说明书/图集 PDF、STEP、计算记录与指标 CSV）；RC1、RC2 哈希记录保留为历史。
- 修正 `10-复现与版本冻结记录.md` 中残留的上一轮验证口径：原写 `py -3.11 -m pytest -q` → 214 passed，更正为本轮实测 `python -m pytest -q` → 217 passed（Python 3.12.10）。
- 构建确定性（SVG）：`studies/ROBUST-BOUNDARY/run.py` 固定 `svg.hashsalt` 并为 `savefig` 传入 `metadata={"Date": None}`。此前 matplotlib 每次重建都会改写元素 ID 与 `<dc:date>`，导致两张随包交付的边界图产生纯噪声差异；现连续多次重建逐字节一致。
- 构建确定性（STEP）：`studies/COMPETITION-DESIGN/run.py` 新增 `normalize_step_timestamp()`，把 OCC 写入 `FILE_NAME` 的导出时刻归一化为固定值。此前每次重建都生成仅差一行时间戳的新内容，等于每次都向 LFS 写入一个新的 427 KB 对象（几何零变化）；现几何不变时产物逐字节稳定。改动按字节替换，除该字段外零改动，并已用 OCC 回读校验（7 root、8 solid、非空）。
- 确定性验证：连续三次 `python deliverables/build_submission.py`，`competition-assembly.step`、`03-名义装配包络.step` 与两张边界 SVG 的 sha256 完全不变。
- 哈希记录可用化：`RC1/RC2/RC3` 记录的首行由裸标题改为 `#` 注释行，使文件可被标准校验工具消费；新增 `scripts/verify_release_hashes.py`，逐项校验记录值与实际产物并打印差异（退出码 0/1），Windows 下不依赖 coreutils。
- `CONTRIBUTING.md` 新增「封版哈希校验」与「构建确定性」两节，说明校验命令、历史记录为何只能对当时提交复验，以及哪些产物已逐字节稳定。
- 全新克隆复验（commit 1d50059）：11 个 `.step` 全部为真实内容、0 指针，`git lfs fsck OK`；克隆内 7 项产物 sha256 与 RC3 记录逐项一致；说明书 22 页且新增五节与关键数字齐备。

## 仓库维护 - 2026-09-19

- 修复 Git LFS 服务端缺对象：全新克隆会报 `[404] Object does not exist on the server`，涉及 9 个 `.step`（共 2.0 MB，`cad/generated/tooling-access/` 与 `simulation/structural-v4/` 下全部模型，含 4P/6P/8P/Continuous 与壳体外壳）。本地缓存与工作树内容完好且 sha256 与指针一致，用 `git lfs push --object-id origin <oid>` 逐对象补传完成。
- 根因：`git lfs push` 只扫描本次新提交涉及的对象，历史提交里的 LFS 对象从未被校验上传；`git lfs push --dry-run` 在无新提交时无输出，不能作为"服务端齐备"的依据。判断服务端真实状态需在干净目录 `git lfs fetch` 实测。
- CONTRIBUTING.md 增加"克隆后必做的 LFS 校验"与本次事故记录，说明指针/真内容的判别方式与补传命令。
- 已用全新目录克隆并检出验证：11 个 `.step` 全部还原为真实 STEP，0 个残留指针。

## COMPETITION-R1-RC2 - 2026-09-19

- 修正交付文档页数口径漂移：以包内 manifest 实际计数（14页说明书、6页设计图集）为准，统一 `10-复现与版本冻结记录.md`、`submission-checklist.md`、`registration-description.md`、`technical-report-v4-unified.md` 中的过期表述，并移除 `stage-status.yaml`、`current_status.py` 里硬编码的图集页数。
- `scripts/competition_submission_lint.py` 增加页数声明门禁 `check_page_claims`：扫描交付文档与说明书 PDF 中“N页说明书/N页设计图/N页图集/N页图纸”声明，与 manifest 实际计数比对后不通过即失败。
- 新增 `tests/test_submission_page_claims.py`，覆盖阿拉伯数字与中文数字解析、过期页数识别与当前仓库一致性。
- 重新构建技术包：说明书页数仍为14页，PDF 文本差异仅“五页图纸→六页设计图集”一处；计算记录（assessment/robust-selection/boundary-summary/CSV）与工艺卡逐字节未变，STEP 体积不变。
- 重新封版为 RC2，更新 `deliverables/COMPETITION-R1-RC2-SHA256.txt`；RC1 哈希记录保留为历史。

## V4.3.0 - 2026-09-06

- 修正非均匀异材网格公共面的串联热阻离散，并新增解析、左右交换、部分出生和守恒测试；旧热结果保留，新建 0.4R1 证据目录重跑。
- 删除 `baseline.yaml` 中重复的工艺和旧混合公差链，建立几何/夹具、工艺、公差三链的跨文件一致性校验。
- 将预偏置变量统一为逐件相对调整量，约束实际装配位置，失败显式拒绝；重新生成合成对照。
- 生成接头—送丝—耗材一致性卡，明确 3.5 mm 设计目标与 1.737 mm 名义送丝等效焊脚尚未闭合。
- 更新 V4.3 工艺设计说明书、可移植字体配置、自动证据摘要，以及含防护罩安装/退出路径的工序总装图。

## v0.3.1 — 2026-09-02

- 技术说明书 V2 口径调整为参赛提交版：页眉/封面改为“参赛评审版/参赛提交版”，正文保留一次性证据分级声明，去除反复自贬式表述。
- 新增 §1.1 命题响应对照表、§3.1 候选工艺对比矩阵（自动 TIG vs CMT-MAG vs 激光填丝 vs 熔化极钎焊）。
- 新增 §5 焊缝疲劳与寿命评估：疲劳热点、IIW 名义应力法 FAT 63–80 设计基线、接头/部件/整机三级验证试验计划。
- 新增附录 A：WPS V1 工艺卡（设计态）及放行前必须补齐清单；FAQ 增补疲劳条目，参考文献增补 IIW 疲劳推荐。
- requirements.txt 补入 reportlab；PDF 构建脚本同步更新并重建。
- 新增 cad/parametric/export_drawing_pdfs.py：7 张 SVG 工程图忠实导出为 A4 矢量 PDF（单图 + HJ-DRW-drawing-set.pdf 合集），附 pdf-exports.json；不改几何与 design-review 状态。
- 封面标注“固定命题”赛道信息；PDF 元数据去识别化；新增 deliverables/submission-checklist.md 对照实施方案的提交核对清单（10-20 报名 / 10-25 提交 / 匿名要求）。
- 生成最终提交包 output/submission/：项目研究报告（15 页）、设计图集（7 页）、22 页合并版及提交说明；13 项终检（页数/内容标记/匿名/元数据）全部通过。

## v0.3.0 — 2026-09-02

- 形成技术说明书 V2：统一 A/B/C 装配基准与 `Ø0.05 | A | B` 位置度定义；将二维 FE 明确降级为热—结构代理交叉检查；补入熔化温度限制、未标定结构/夹具因子说明、视觉误差预算及参赛提交/制造放行分层。
- 修正二维 FE 网格域与元素筛选，正式运行 FE-001/002/003，并把内孔节点接入位置度后处理。
- 新增 1000 次降阶蒙特卡洛，输出 P5/P50/P95、worst、超限比例和配对比较。
- 新增噪声/模糊/光照/透视/遮挡/缺边/低对比度/畸变/大偏移视觉困难集与 100+100 异常检测基准。
- 新增 7 张带 A/B/C 基准、位置度框、焊缝符号和夹具 DOF 的 SVG 工程表达图。
- 更新证据矩阵、仿真计划、技术说明书边界和关键 GitHub Issue 正文；明确 `P_sim`/`P_FE` 均不是 CMM 结果。

## v0.2.0 — 2026-09-02

- 将项目主线切换为“自动 TIG + 镍基候选、六点柔顺连接、数字工程验证”。
- 新增官方条件/设计假设分层、文献证据矩阵和数值结果边界。
- 新增参数化 CAD 源文件与 SVG 工程草图。
- 新增降阶热—结构方案筛选、位置度后处理和 15 组算例输出。
- 新增视觉定位数字样本基准、焊接路径生成、仿真过程信号、异常检测和 SQLite 追溯 Demo。
- 将真实焊接、金相、硬度和 CMM 从关键路径调整为可选物理验证。

## v0.1.1 — 2026-08-30

- 技术预研初稿（31de8bc，#2~#5）：**仅作技术预研，不可直接作为最终工艺/报名依据**
- 设备调查表升级为可执行版：调查路线、逐设备问题清单、选型决策规则、9/1 验收标准
- 焊接性分析 / 工艺选型 / 焊材 / 热管理 V0.1 初稿，全部标注待验证项
- 技术纠错：删除绝对化表述（零塑性/必裂/唯一手段），过共晶结论以质保书为准，焊条与丝材牌号按方法分开管理，温度窗口按路线独立定义，禁用石棉，强冷降级为待验证的设计倾向

## v0.1.0 — 2026-08-30

- 初始化仓库：九大工作包目录骨架
- 项目定义、路线图、团队分工、设备清单模板
- 焊接性分析 / 工艺选型 / 仿真 / 实验 / 检测计划骨架
- 协作规则（CONTRIBUTING）与数据规范（data/README）
- 导入比赛官方文件至 competition/original-files/
- 创建 12 个启动 Issue
