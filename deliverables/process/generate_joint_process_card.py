"""生成接头—送丝—耗材一致性卡；不把设计假设升级为 WPS/PQR。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))

from hanjie.domain.joint import joint_design_metrics


def main() -> int:
    metrics = joint_design_metrics()
    output = ROOT/"deliverables/process"
    output.mkdir(parents=True,exist_ok=True)
    (output/"joint-process-card.json").write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding="utf-8")
    target = metrics["design_target"]
    deposit = metrics["nominal_wire_deposition"]
    layout = metrics["primary_6p_layout"]
    diagnostic = metrics["diagnostic_only_feed_for_target"]
    scenarios = metrics["design_scenarios"]
    candidate = scenarios["target_3p5_four_pass_candidate"]
    markdown = f"""# 接头—送丝—耗材一致性卡

状态：`{metrics['closure_status']}`；证据等级：`{metrics['evidence_level']}`。本卡不是 WPS/PQR。

| 项目 | 当前值 |
| --- | ---: |
| 设计等脚焊脚 | {target['fillet_leg_mm']:.3f} mm |
| 设计理想三角截面积 | {target['ideal_triangular_area_mm2']:.3f} mm² |
| 名义送丝新增截面积 | {deposit['area_per_weld_length_mm2']:.3f} mm² |
| 名义送丝等效理想焊脚 | {deposit['equivalent_ideal_fillet_leg_mm']:.3f} mm |
| 新增截面积/设计面积 | {deposit['target_area_fraction']:.1%} |
| 6×18 mm 名义保留填丝质量 | {layout['nominal_retained_filler_mass_g']:.3f} g |
| 3.5 mm 设计截面等效质量 | {layout['design_target_filler_equivalent_mass_g']:.3f} g |

若仅按体积倒算，100%/最低声明沉积效率对应送丝速度分别为
{diagnostic['at_100pct_efficiency_mm_s']:.3f}/{diagnostic['at_min_declared_efficiency_mm_s']:.3f} mm/s。
这些数值只用于显示缺口，不能据此直接提高送丝量；必须由承载依据、宏观截面、
耗丝/增重、单道或多道安排及热输入共同冻结最终接头。

## 分离的设计情景

| 情景 | 道数 | 总沉积面积 | 等效理想焊脚 | 送丝范围 | 总弧能/焊长 | 用途 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 当前单道诊断基线 | 1 | {scenarios['current_single_pass_diagnostic']['total_deposited_area_mm2']:.3f} mm² | {scenarios['current_single_pass_diagnostic']['equivalent_ideal_fillet_leg_mm']:.3f} mm | 2.000 mm/s | {scenarios['current_single_pass_diagnostic']['total_arc_energy_per_weld_length_j_mm']:.1f} J/mm | 局部热诊断 |
| 3.5 mm 四道候选 | {candidate['pass_count']} | {candidate['total_deposited_area_mm2']:.3f} mm² | {candidate['equivalent_ideal_fillet_leg_mm']:.3f} mm | {candidate['wire_feed_range_mm_s'][0]:.3f}~{candidate['wire_feed_range_mm_s'][1]:.3f} mm/s | {candidate['total_arc_energy_per_weld_length_j_mm']:.1f} J/mm | 待承载、成形和热循环验证 |

四道候选只完成体积核算自洽，不是 WPS/PQR。其分层几何、层间温度和累计热输入必须建立新版本验证，不能继承当前单道 0.4R1 的结论。
"""
    (output/"joint-process-card.md").write_text(markdown,encoding="utf-8")
    print(output/"joint-process-card.json")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
