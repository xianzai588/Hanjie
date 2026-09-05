# V4.2 冻结状态核查

**日期**：2026-09-05
**状态**：G0 纠偏已完成；工程验证未完成

本文件只核查设计资料、代码边界和证据登记是否一致，不把文件存在、脚本可运行或代理数值当作 FE、实验或 Gate B 通过证据。旧版“全部通过”记录已被本页取代。

## 已核查的 G0 项

- [x] 当前报告源固定为 `deliverables/report/technical-report-v4-unified.md`。
- [x] `src/hanjie/simulation/fe3d.py` 明确标记为 `surrogate_result`，不执行真实热—结构求解。
- [x] FE3D-BASE 的 Gate B.1 通过声明撤销；代理相邻网格差值不再晋升为收敛证据。
- [x] FE3D 输出中的能量平衡误差保持空值，因为当前没有能量计算。
- [x] Adaptive 与固定序列共用 plant、位置度预测器、评价函数和初始扰动，并保存同序列回放检查。
- [x] Adaptive 在统一扰动下为 0.07220 mm，S3 为 0.06648 mm；不设置“必须优于”或“必须达标”门槛。
- [x] 4P/6P/8P/Continuous 结构标签代理结果全部超过 Ø0.05 mm；结构选择保持 `unresolved`。
- [x] 校准演示及结果位于 `data/synthetic/few-shot-calibration/`；硬度不参加拟合。
- [x] 固定刚度时只辨识组合响应系数，未写入物理后验或不确定度缩减声明。
- [x] 误差预算拆分为产品几何、自动化路径和测量三链；产品链 0.035 mm 为设计分配且未闭合，RSS/P95 保持空值。
- [x] 证据图校验拒绝低等级证据晋升为 verified/passed。

## 当前未完成且不得勾选

- [ ] Continuous、4/6/8P 七个真实 FAIR-A/B 几何实体、STEP/BREP 和 manifest。
- [ ] 真实热—结构求解：移动热源、温变材料、塑性、冷却、松夹和孔面节点轴线拟合。
- [ ] Gate B.1/B.2/B.3/B.4；当前只能记录“不适用/未执行”。
- [ ] 设备、材料批次、加工和 CMM 条件核实。
- [ ] 温度历史、PT/宏观、硬度和 CMM 实验数据。
- [ ] 三链灵敏度、相关性、RSS/P95 和 guard band 的数据闭合。

## 证据解释

| 对象 | 当前等级 | 当前允许表述 |
| --- | --- | --- |
| FE3D 代理响应 | `surrogate_result` | 经验代理演示；不能称 FE 收敛或 solver verified |
| 统一焊序对照 | `surrogate_result` | 同模型公平回放；不能称 Adaptive 优于 S3 |
| 七候选非支配筛选 | `surrogate_result` | 有限手选集合非支配子集；不能称全局 Pareto 或六点最优 |
| 校准演示 | `synthetic_demo` | 合成拟合与留一误差；不能称实测、校准后验或独立验证 |
| 产品误差预算 | `design_assumption` | 等效径向设计分配；未实测、未闭合 |

后续执行、时间和退出条件以 [`docs/V4.2-competition-roadmap.md`](../../docs/V4.2-competition-roadmap.md) 为准。
