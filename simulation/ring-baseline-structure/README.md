# 完整圆环冷态结构计算

## 决策问题及计算预算

完整QT450-10圆环在八个有效连接区建立后的孔区刚度和接头附近应力分布如何？计算采用3.5 mm最小焊脚，径向5000 N、轴向5000 N、倾覆力矩250 kN·mm分别加载及同向叠加。荷载为本设计采用的参考包络，题面未给出压缩机实际工作载荷。

计算预算为两档实体网格、四种线弹性荷载；若孔轴、孔形或应变能变化超过5%，再增加一档，达到基本工程精度即停止。焊趾和材料分界保留CAD尖边，原始单元应力峰值单列，不用节点平均或剔除峰值取得强度通过。

## 实体、连接与边界

- 导入`cad/generated/ring-baseline/ring-precoat-eight-windows-17solids.step`：完整圆环本体，以及8个CI-A1首层和8个Ni99第二层保留实体。保留内角曲面与端壁层厚。
- 显式建立Q235B壳体（R75～80 mm，高200 mm）和8个NiFe55等效最终焊缝。焊缝有效弧长18 mm/段、角间距45°，最小等脚三角断面3.5 mm。热过程20 mm实际路径的起停过渡不纳入有效承载长度。
- 共形四面体网格仅在所建材料共享面传递载荷。未焊位置的0.02 mm径向间隙保持分离，没有整圈绑定、径向弹簧或辅助工装支承。初始间隙不闭合时的接触承载未计入。
- 壳体下端完整环面三向位移固定，壳体上端自由。圆环孔面施加均布径向/轴向面力；倾覆由仿射轴向面力产生，按实际离散表面积分给出零合力、250 kN·mm力矩。固定底环是参考支承边界，实际压缩机安装柔度另据整机接口定义。
- 3D小变形各向同性线弹性；QT为E=169 GPa、ν=0.27，Q235B为E=206 GPa、ν=0.30，镍层及最终焊缝为E=200 GPa、ν=0.30。这些是可重算设计弹性输入，镍层未赋予未经核实的强度许用值。

## 证据含义

接头材料在有效区域按连续连接处理，是冷态承载计算的明确前提。该模型不计算熔合、界面冶金或残余应力，不把几何接触视为工艺已实现。首次预制及最终组焊状态的有效界面必须由其工艺资格证据对应。

孔轴以固定下端壳体的初始名义轴线为参考，拟合孔面径向位移中的平移、倾斜及平均半径变化。受载位移不是焊后完全卸夹的位置度；弹性卸载回到本模型的初始冷态参考，也不代表已消除制造残余变形。

## 重算

Python依赖：`numpy scipy gmsh pyamg matplotlib pyyaml`。Gmsh需要系统`libXft`与`libGLU`。当前P2结果的完整复现命令（仓库/参赛包内保留历史P1结果JSON、CSV和热点图用于故障诊断，当前计算不依赖其原始NPZ）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python simulation/ring-baseline-structure/run_quadratic_check.py --rebuild --levels coarse medium
python simulation/ring-baseline-structure/sample_existing_fields.py --levels p2-linear-coarse p2-linear-medium
python simulation/ring-baseline-structure/summarize_quadratic.py
```

`sample_existing_fields.py`调用同目录`bore_sampling.py`，按真实面片射线交点和P2形函数重建128×11孔面CSV，必须先取得两个当前P2原始场。`summarize_quadratic.py`再生成当前assessment、报告和P2孔区云图/独立网格对比；参赛包已包含明确标注历史P1的原始应力图。没有静默借用缺失的历史原始场。

最终当前版本结论由`results/assessment.json`及`results/cold-structure-report.md`提供；`summarize_quadratic.py`验证实际P2原始结果、网格和孔面采样的身份，不把旧P1结果贴为当前工艺版本。当前P1三个快照缺少构建身份，仅保留历史诊断。只要已有当前P2原始场及孔面CSV，重跑最终汇总不要求旧P1重新求解。

最终assessment顶层`input_identity`保留实际P2-medium原始结果的身份，只有raw result、mesh-summary和virtual-bore-summary三者真实身份一致且等于当前模型输入才发布。交付准入可调用`model_inputs.current_publication_identity()`（只读取输入，不建网格/求解）：把返回的`process_version`和`input_identity`分别与assessment顶层字段直接比较。后者包含当前STEP DATA摘要、网格/连接尺寸、荷载、材料、边界和单元阶次；同版本改几何或材料不会仅靠版本号放行。STEP header时间不影响DATA摘要。

如需重新研究P1离散，可另运行`run_ring_structure.py --rebuild --levels coarse medium fine`及`sample_existing_fields.py --levels coarse medium fine`。`plot_and_report.py`只接受有当前身份的新P1结果，写入独立`assessment-p1.json`、`cold-structure-report-p1.md`及`figures/p1-diagnostic/`，不会覆盖当前P2结论或图。历史热点图的重画入口`plot_raw_stress.py`需要P1细档原始场，不是当前P2复现的必要步骤。

`results/<网格>/mesh.npz`保留节点、四面体、材料号和面片；`*-field.npz`保留位移、原始单元应力和主应力；`result.json`含荷载/反力平衡与孔形指标。原始场作为本地计算记录，不重复放入参赛包；图、JSON结果、孔面位移CSV和脚本提供设计证据与重算入口。重新画云图前须先重算取得原始场。

缓存读取先校对STEP的DATA实体摘要、焊脚、网格档位、实际尺寸场、网格算法/连接规则，以及结果的材料、荷载、支承和工艺版本。STEP导出日期/文件名变化不触发重网格；实体变化才改变几何身份。缺少身份的旧结果或不匹配的缓存明确拒绝，采用`--rebuild`重算，不能更改参数后静默返回旧结果。

首次网格采用HXT（算法10）因本几何的层间薄区与0.02 mm根部短边报`HXT 3D mesh failed`，随后采用Delaunay（算法1）并控制近间隙壳曲面弦误差。首档有Netgen优化，后续两档采用默认线性网格优化；几何、连接和有效长度保持原定义。未通过的生成尝试不作为结果网格。

旧P1首档中，壳内曲面面片边实际最低R74.96455 mm，低于座体外半径74.98 mm；只看曲面节点R75或面心会漏掉弦误差。该首档不作为有效几何模型，保留故障记录及608 MPa原始应力需求。当前生成器和最终P2汇总通过`geometry_audit.py`检查裁剪到座体高度范围内的完整面片边。P2两档最低R分别74.984410/74.992357 mm，座体与壳没有直接共享节点，几何间隙成立。该硬检查不能证明实际熔合或制造状态的接触间隙。

`build_support_mesh.py`在独立`results/p1-current-coarse-safe`建立当前有身份的完整环P1支持网格，供独立固有应变灵敏度分析；不覆盖旧coarse结果，也不自动给出结构载荷或残余应力资格结论。

## 弯曲离散复核

三档P1实体中，径向刚度变化减小，但轴向/倾覆弯曲能量仍随网格细化增加。`bending-discretization-diagnostic.json`给出R45 mm、θ22.5°竖直探线穿过15 mm圆环的实际单元区间。低阶常应变四面体用于弯曲时存在偏硬趋势，单看百万级单元数不足以判定精度。

因此增加两档P2二次四面体四分之一模型，保持同一材料链、最小焊脚及有效长度。径向和倾覆在x=0反对称、y=0对称；轴向在两平面对称。分别求解后按荷载奇偶性还原全环孔面及组合能量。最终两档采用直边几何、二次位移；`minDetJac`排除倒置单元，四点体积分对直边P2刚度为精确积分，孔面加载为七点三角积分。此前曲边粗档成功结果仅作几何灵敏度记录，曲边中档优化未成功，不能和最终直边族混判收敛。解析仿射能量与刚体转动检查针对二次单元公式，收敛检查针对实际圆环弯曲。

当前P2受载轴线和应变能两级变化分别不超过0.703%和0.217%，组合孔形变化不超过0.793%。倾覆单项约0.5 μm的圆柱径向峰谷仍变化8.69%（绝对0.044 μm），作为未达到5%的细小形状量单列。局部原始应力没有收敛资格，不签署强度通过。
