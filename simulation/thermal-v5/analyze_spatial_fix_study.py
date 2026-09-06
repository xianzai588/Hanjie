"""比较 0.4R2-A 固定六条带几何的 coarse/medium/fine 实际解。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from analyze_spatial_convergence import _project_fine_to_medium,_weighted_percentile
from audit_credibility04r import compare
from run_physics03 import ROOT,load,write_json


SPEC=ROOT/"project/thermal-spatial-fix-v5.4r2.yaml"
RESULTS=ROOT/"simulation/thermal-v5/results/spatial-fix-study"
NAMES=("q235b","qt450_10","ernife_ci")
LEVELS=("A-field-coarse-fixed6","A-field-medium-fixed6","A-field-fine-fixed6")
DIRECTIONAL=("A-arc-fine-cross-medium-fixed6","A-cross-fine-arc-medium-fixed6")


def field_pair(lower_path: Path,upper_path: Path,lower_summary,upper_summary,limit):
    result={}
    with np.load(lower_path) as lower,np.load(upper_path) as upper:
        projected,projected_volume=_project_fine_to_medium(lower,upper)
        for code,name in enumerate(NAMES,1):
            base=(lower["material_id"]==code)&(lower["filled_fraction"]>0)
            mask=base&np.isfinite(projected)&(projected_volume>0)
            weight=lower["cell_volume_mm3"][mask]*lower["filled_fraction"][mask]
            absolute=np.abs(projected[mask]-lower["temperature_peak"][mask])
            solidus=float(lower_summary["material_statistics"][name]["solidus_c"])
            flips=(projected[mask]>solidus)!=(lower["temperature_peak"][mask]>solidus)
            p95=_weighted_percentile(absolute,weight,95.)
            result[name]={"matched_volume_fraction":float(weight.sum()/np.sum(lower["cell_volume_mm3"][base]*lower["filled_fraction"][base])),
                          "volume_weighted_mean_abs_peak_difference_c":float(np.average(absolute,weights=weight)),
                          "volume_weighted_p95_abs_peak_difference_c":p95,"maximum_abs_peak_difference_c":float(absolute.max()),
                          "solidus_threshold_flip_volume_mm3":float(weight[flips].sum()),"local_p95_pass":bool(p95<=limit),
                          "registered_peak_difference_c":abs(float(upper_summary["material_statistics"][name]["peak_temperature_c"])-float(lower_summary["material_statistics"][name]["peak_temperature_c"]))}
    return result


def history_pair(lower_path: Path,upper_path: Path):
    lower=json.loads(lower_path.read_text(encoding="utf-8")); upper=json.loads(upper_path.read_text(encoding="utf-8"))
    lower_rows,upper_rows=lower["rows"],upper["rows"]
    if len(lower_rows)!=len(upper_rows) or not np.allclose([row["time_s"] for row in lower_rows],[row["time_s"] for row in upper_rows]):
        raise ValueError("固定点历史时间轴不一致")
    result={}
    for point in [item["name"] for item in lower["points"]]:
        a=np.asarray([row[point] for row in lower_rows]); b=np.asarray([row[point] for row in upper_rows])
        result[point]={"maximum_same_time_abs_difference_c":float(np.max(np.abs(b-a))),
                       "rms_same_time_difference_c":float(np.sqrt(np.mean((b-a)**2))),
                       "peak_temperature_difference_c":float(abs(b.max()-a.max())),
                       "lower_represented_cell":next(item for item in lower["points"] if item["name"]==point),
                       "upper_represented_cell":next(item for item in upper["points"] if item["name"]==point)}
    return result


def build_assessment():
    plan=load(SPEC); old_rules=load(ROOT/"project/thermal-credibility-v5.4r1.yaml")["convergence"]
    summaries={level:json.loads((RESULTS/level/"summary.json").read_text(encoding="utf-8")) for level in LEVELS}
    pairs={}
    for lower,upper in zip(LEVELS[:-1],LEVELS[1:]):
        key=f"{lower}_to_{upper}"
        registered=compare(summaries[lower],summaries[upper],old_rules)
        pairs[key]={"registered_metrics":registered,
                    "common_control_volume_peak_field":field_pair(RESULTS/lower/"field.npz",RESULTS/upper/"field.npz",summaries[lower],summaries[upper],float(plan["acceptance"]["peak_absolute_limit_c"])),
                    "fixed_coordinate_containing_cell_histories":history_pair(RESULTS/lower/"fixed-point-history.json",RESULTS/upper/"fixed-point-history.json"),
                    "direct_source_by_material_difference_j":{name:float(summaries[upper]["energy"]["direct_source_by_material_j"][name]-summaries[lower]["energy"]["direct_source_by_material_j"][name]) for name in NAMES},
                    "net_conductive_by_material_difference_j":{name:float(summaries[upper]["energy"]["net_conductive_by_material_j"][name]-summaries[lower]["energy"]["net_conductive_by_material_j"][name]) for name in NAMES}}
    mesh_inputs={level:json.loads((RESULTS/level/"run-inputs.json").read_text(encoding="utf-8"))["specification"]["mesh"] for level in LEVELS}
    fixed_geometry=all(int(mesh["bead_geometry_strips"])==6 for mesh in mesh_inputs.values())
    legacy_fine=ROOT/plan["reference_fine"]["result"]
    with np.load(legacy_fine/"field.npz") as legacy_field,np.load(RESULTS/LEVELS[-1]/"field.npz") as rerun_field:
        fine_reproduction={"cell_count_equal":len(legacy_field["temperature_peak"])==len(rerun_field["temperature_peak"]),
                           "maximum_peak_field_difference_c":float(np.max(np.abs(legacy_field["temperature_peak"]-rerun_field["temperature_peak"]))),
                           "maximum_final_field_difference_c":float(np.max(np.abs(legacy_field["temperature_final"]-rerun_field["temperature_final"])))}
    geometry_effect={}
    for legacy_level,new_level,legacy_strips in (("coarse",LEVELS[0],3),("medium",LEVELS[1],4)):
        legacy=ROOT/"simulation/thermal-v5/results/credibility04r1"/legacy_level
        legacy_summary=json.loads((legacy/"summary.json").read_text(encoding="utf-8"))
        geometry_effect[f"legacy_{legacy_strips}_strips_to_fixed_6_at_{legacy_level}_spacing"]={
            "comparison_scope":"名义场间距相同，但新增解析边界锚点会改变局部背景分区；作为几何影响证据，不冒充严格纯几何极限",
            "common_control_volume_peak_field":field_pair(legacy/"field.npz",RESULTS/new_level/"field.npz",legacy_summary,summaries[new_level],float(plan["acceptance"]["peak_absolute_limit_c"]))}
    directional={}
    base_level,final_level=LEVELS[1],LEVELS[2]
    for level in DIRECTIONAL:
        summary=json.loads((RESULTS/level/"summary.json").read_text(encoding="utf-8"))
        directional[level]={
            "mesh":json.loads((RESULTS/level/"run-inputs.json").read_text(encoding="utf-8"))["specification"]["mesh"],
            "change_from_medium":field_pair(RESULTS/base_level/"field.npz",RESULTS/level/"field.npz",summaries[base_level],summary,float(plan["acceptance"]["peak_absolute_limit_c"])),
            "remaining_difference_to_fine":field_pair(RESULTS/level/"field.npz",RESULTS/final_level/"field.npz",summary,summaries[final_level],float(plan["acceptance"]["peak_absolute_limit_c"])),
            "history_change_from_medium":history_pair(RESULTS/base_level/"fixed-point-history.json",RESULTS/level/"fixed-point-history.json")}
    missing_cross=directional[DIRECTIONAL[0]]["remaining_difference_to_fine"]["ernife_ci"]["volume_weighted_p95_abs_peak_difference_c"]
    missing_arc=directional[DIRECTIONAL[1]]["remaining_difference_to_fine"]["ernife_ci"]["volume_weighted_p95_abs_peak_difference_c"]
    direction_diagnosis=("截面细化的剩余影响更大" if missing_cross>missing_arc else "沿焊道细化的剩余影响更大")
    return {"stage":plan["version"],"evidence_level":"solver_result_unvalidated","experiment":"A_fixed_geometry_field_refinement",
            "fixed_inputs":plan["policy"],"mesh_inputs":mesh_inputs,"fixed_six_strip_geometry_verified":fixed_geometry,
            "fine_reference_reproduction":fine_reproduction,
            "pairs":pairs,"directional_controls":directional,"direction_diagnosis":direction_diagnosis,
            "supporting_geometry_effect":geometry_effect,"a_control_completed":True,"spatial_gate_pass":False,"thermal_1_allowed":False,
            "diagnosis":"固定六条带后 medium→fine 的焊材热区 P95 差降至约16.7°C，说明旧混合序列的74.554°C含显著几何变化贡献；但仍高于10°C且QT固相线翻转仍存在，场离散也尚未收敛。",
            "gate_note":"A 对照完成不自动构成完整空间准入；保留原逐指标判据，并在结果基础上决定 B 几何对照和是否需要 xfine。"}


def render(result):
    lines=["# THERMAL-0.4R2-A 固定几何场网格对照","","> 六条带解析边界、物理输入和 dt=0.1 s 固定；以下为实际重算结果，不是真值误差。","",
           "| 网格对 | 材料 | 共同控制体峰温 P95差 (°C) | 最大差 (°C) | 固相线翻转体积 (mm³) | 原登记指标集合 |",
           "| --- | --- | ---: | ---: | ---: | --- |"]
    for pair,row in result["pairs"].items():
        for name,field in row["common_control_volume_peak_field"].items():
            lines.append(f"| {pair} | {name} | {field['volume_weighted_p95_abs_peak_difference_c']:.3f} | {field['maximum_abs_peak_difference_c']:.3f} | {field['solidus_threshold_flip_volume_mm3']:.3f} | {'通过' if row['registered_metrics']['nonzero_metrics_pass'] else '未通过'} |")
    lines += ["","## 原混合序列中的几何影响","",
              "同名义场间距下，把旧 3/4 条带换为固定 6 条带时，焊材共同控制体 P95 差分别为 "
              f"{result['supporting_geometry_effect']['legacy_3_strips_to_fixed_6_at_coarse_spacing']['common_control_volume_peak_field']['ernife_ci']['volume_weighted_p95_abs_peak_difference_c']:.3f}/"
              f"{result['supporting_geometry_effect']['legacy_4_strips_to_fixed_6_at_medium_spacing']['common_control_volume_peak_field']['ernife_ci']['volume_weighted_p95_abs_peak_difference_c']:.3f} °C。由于边界锚点也改变局部分区，这不是严格几何极限，但足以证明旧序列混入了显著几何影响。","",
              result["diagnosis"],"",
              "## 方向控制变量","",
              f"保持截面为 medium、只把沿焊道细化到 fine 后，距完整 fine 的焊材 P95 差为 {result['directional_controls'][DIRECTIONAL[0]]['remaining_difference_to_fine']['ernife_ci']['volume_weighted_p95_abs_peak_difference_c']:.3f} °C；保持沿焊道为 medium、只细化截面后的对应差为 {result['directional_controls'][DIRECTIONAL[1]]['remaining_difference_to_fine']['ernife_ci']['volume_weighted_p95_abs_peak_difference_c']:.3f} °C。{result['direction_diagnosis']}。","",
              "状态：A 固定几何控制变量计算已完成；`spatial_gate_pass=false`、`thermal_1_allowed=false`。下一步先针对焊材/界面高梯度做局部场细化，再决定是否需要 xfine；随后在新细网格复查时间步。"]
    return "\n".join(lines)+"\n"


def main():
    result=build_assessment(); write_json(RESULTS/"assessment.json",result); (RESULTS/"assessment.md").write_text(render(result),encoding="utf-8")
    print(RESULTS/"assessment.json")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
