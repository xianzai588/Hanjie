"""生成条件性接头承载影响系数与热量/节拍代价。"""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))

from hanjie.domain.joint_load import build_load_basis


def main() -> int:
    result = build_load_basis(ROOT)
    output = ROOT/"simulation/structural-v4/results/joint-load-basis"
    output.mkdir(parents=True,exist_ok=True)
    (output/"joint-load-basis.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    lines = ["# 条件性接头承载筛查","","> 题面没有真实整机载荷或载荷谱；以下为参考包络影响系数，不是服役安全认证。","",
             "| 布局 | 有效焊长 (mm) | 焊脚 (mm) | 参考包络角点所需许用 (MPa) | 单道净热输入 (kJ) | 四道净热输入 (kJ) |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name,layout in result["layouts"].items():
        costs=result["process_costs"][name]
        for row in layout["rows"]:
            lines.append(f"| {name} | {layout['effective_weld_length_mm']:.3f} | {row['fillet_leg_mm']:.3f} | {row['reference_envelope_corner_required_allowable_mpa']:.3f} | {costs['single_pass_net_heat_input_j']/1000:.3f} | {costs['four_pass_net_heat_input_j']/1000:.3f} |")
    lines += ["","## 结论","",result["decision"]["reason"],result["decision"]["current_1p737_limitation"],result["decision"]["four_pass_disposition"],"",
              "既有 1000 N 径向静力筛查仅作为座体孔轴位移影响系数引用；它没有显式焊缝，不能给 3.5 mm 焊脚背书。",
              "疲劳只登记焊趾、焊根、离散焊段端部和翼根圆角为风险位置；没有载荷谱时不计算或宣称寿命。"]
    (output/"joint-design-basis.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(output/"joint-load-basis.json")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
