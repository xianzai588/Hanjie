"""评估局部截面三级细化，决定是否进入 xfine 与新网格时间步复查。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from analyze_spatial_convergence import _project_fine_to_medium,_weighted_percentile
from audit_credibility04r import compare
from run_physics03 import ROOT,load,write_json


SPEC=ROOT/"project/thermal-xsec-refinement-v5.5.yaml"
RESULTS=ROOT/"simulation/thermal-v5/results/xsec-refinement-study"
LEVELS=("XSEC-M","XSEC-F","XSEC-VF")
NAMES=("q235b","qt450_10","ernife_ci")


def _relative_difference(a,b):
    scale=max(abs(float(a)),abs(float(b)),1e-12)
    return abs(float(b)-float(a))/scale


def field_pair(lower_path: Path,upper_path: Path,lower_summary,upper_summary,rules):
    result={}
    with np.load(lower_path) as lower,np.load(upper_path) as upper:
        projected,projected_volume=_project_fine_to_medium(lower,upper)
        for code,name in enumerate(NAMES,1):
            base=(lower["material_id"]==code)&(lower["filled_fraction"]>0)
            mask=base&np.isfinite(projected)&(projected_volume>0)
            weight=lower["cell_volume_mm3"][mask]*lower["filled_fraction"][mask]
            absolute=np.abs(projected[mask]-lower["temperature_peak"][mask])
            statistics=lower_summary["material_statistics"][name]
            thresholds={key:float(statistics[f"{key}_c"]) for key in ("solidus","liquidus")}
            flips={key:float(weight[((projected[mask]>value)!=(lower["temperature_peak"][mask]>value))].sum()) for key,value in thresholds.items()}
            mae=float(np.average(absolute,weights=weight))
            p95=_weighted_percentile(absolute,weight,95.)
            maximum=float(absolute.max())
            result[name]={
                "matched_volume_fraction":float(weight.sum()/np.sum(lower["cell_volume_mm3"][base]*lower["filled_fraction"][base])),
                "volume_weighted_mean_abs_peak_difference_c":mae,
                "volume_weighted_p95_abs_peak_difference_c":p95,
                "maximum_abs_peak_difference_c":maximum,
                "threshold_flip_volume_mm3":flips,
                "registered_peak_difference_c":abs(float(upper_summary["material_statistics"][name]["peak_temperature_c"])-float(statistics["peak_temperature_c"])),
                "checks":{
                    "mae":mae<=float(rules["field_volume_weighted_mae_limit_c"]),
                    "p95":p95<=float(rules["field_volume_weighted_p95_limit_c"]),
                    "maximum":maximum<=float(rules["field_maximum_limit_c"]),
                    "threshold_flips":all(value<=float(rules["threshold_flip_volume_limit_mm3"]) for value in flips.values()),
                },
            }
    return result


def history_pair(lower_path: Path,upper_path: Path,rules):
    lower=json.loads(lower_path.read_text(encoding="utf-8")); upper=json.loads(upper_path.read_text(encoding="utf-8"))
    a_rows,b_rows=lower["rows"],upper["rows"]
    if len(a_rows)!=len(b_rows) or not np.allclose([row["time_s"] for row in a_rows],[row["time_s"] for row in b_rows]):
        raise ValueError("固定点历史时间轴不一致")
    result={}
    for point in [item["name"] for item in lower["points"]]:
        a=np.asarray([row[point] for row in a_rows]); b=np.asarray([row[point] for row in b_rows])
        rms=float(np.sqrt(np.mean((b-a)**2))); peak=float(abs(b.max()-a.max()))
        result[point]={
            "maximum_same_time_abs_difference_c":float(np.max(np.abs(b-a))),
            "rms_same_time_difference_c":rms,
            "peak_temperature_difference_c":peak,
            "checks":{"rms":rms<=float(rules["fixed_point_rms_limit_c"]),"peak":peak<=float(rules["fixed_point_peak_limit_c"])},
            "lower_represented_cell":next(item for item in lower["points"] if item["name"]==point),
            "upper_represented_cell":next(item for item in upper["points"] if item["name"]==point),
        }
    return result


def integral_pair(lower,upper,rules):
    rows={}
    for name in NAMES:
        low=lower["material_statistics"][name]; high=upper["material_statistics"][name]
        metrics={
            "direct_source_j":(lower["energy"]["direct_source_by_material_j"][name],upper["energy"]["direct_source_by_material_j"][name]),
            "cumulative_net_conduction_j":(lower["energy"]["net_conductive_by_material_j"][name],upper["energy"]["net_conductive_by_material_j"][name]),
            "exposure_above_400c_volume_mm3":(low["exposure_above_400c_volume_mm3"],high["exposure_above_400c_volume_mm3"]),
            "t8_5_valid_volume_mm3":(low["t8_5_valid_volume_mm3"],high["t8_5_valid_volume_mm3"]),
            "t8_5_volume_weighted_mean_s":(low["t8_5_volume_weighted_mean_s"],high["t8_5_volume_weighted_mean_s"]),
        }
        rows[name]={key:{"lower":a,"upper":b,"absolute_difference":None if a is None or b is None else abs(float(b)-float(a)),
                          "relative_difference":None if a is None or b is None else _relative_difference(a,b)} for key,(a,b) in metrics.items()}
        rows[name]["integral_relative_check"] = all(item["relative_difference"] is None or item["relative_difference"]<=float(rules["integral_relative_limit"]) for item in rows[name].values() if isinstance(item,dict))
    return rows


def geometry_pair(lower,upper,rules):
    result={}
    for name in NAMES[:2]:
        a=lower["material_statistics"][name]; b=upper["material_statistics"][name]
        result[name]={}
        for metric in ("maximum_section_solidus_width_mm","maximum_section_solidus_depth_mm"):
            difference=abs(float(b[metric])-float(a[metric]))
            result[name][metric]={"lower":a[metric],"upper":b[metric],"absolute_difference_mm":difference,
                                  "pass":difference<=float(rules["exposure_geometry_limit_mm"])}
    return result


def _background_frozen():
    plan=load(SPEC); radial=plan["frozen_mesh"]["radial_local_zone_mm"]; axial=plan["frozen_mesh"]["axial_local_zone_mm"]
    edges={}
    for level in LEVELS:
        with np.load(RESULTS/level/"field.npz") as field:
            edges[level]={"n":field["n_edges"].copy(),"z":field["z_edges"].copy(),"s":field["s_edges"].copy()}
    def outer(values,bounds):
        return values[(values<bounds[0])|(values>bounds[1])]
    return {
        "arc_edges_identical":all(np.array_equal(edges[LEVELS[0]]["s"],edges[level]["s"]) for level in LEVELS[1:]),
        "radial_background_edges_identical":all(np.array_equal(outer(edges[LEVELS[0]]["n"],radial),outer(edges[level]["n"],radial)) for level in LEVELS[1:]),
        "axial_background_edges_identical":all(np.array_equal(outer(edges[LEVELS[0]]["z"],axial),outer(edges[level]["z"],axial)) for level in LEVELS[1:]),
    }


def _second_layer_diagnosis(summaries,pairs):
    """用现有账本区分整体能量稳定与局部峰值不稳定，不臆造唯一根因。"""
    source_spread={}; conduction_spread={}
    for name in NAMES:
        source=[summaries[level]["energy"]["direct_source_by_material_j"][name] for level in LEVELS]
        conduction=[summaries[level]["energy"]["net_conductive_by_material_j"][name] for level in LEVELS]
        source_spread[name]=max(source)-min(source)
        conduction_spread[name]=(max(conduction)-min(conduction))/max(max(abs(value) for value in conduction),1e-12)
    nesting={}
    for lower,upper in zip(LEVELS[:-1],LEVELS[1:]):
        with np.load(RESULTS/lower/"field.npz") as a,np.load(RESULTS/upper/"field.npz") as b:
            nesting[f"{lower}_to_{upper}"]={axis:float(np.mean([np.any(np.isclose(value,b[f"{axis}_edges"],atol=1e-12)) for value in a[f"{axis}_edges"]])) for axis in ("n","z")}
    with np.load(RESULTS/"XSEC-F/field.npz") as lower,np.load(RESULTS/"XSEC-VF/field.npz") as upper:
        projected,_=_project_fine_to_medium(lower,upper)
        difference=np.abs(projected-lower["temperature_peak"])
        valid=np.isfinite(difference)&(lower["filled_fraction"]>0)
        selected=np.flatnonzero(valid)[np.argsort(difference[valid])[-10:]][::-1]
        hotspots=[{"material":NAMES[int(lower["material_id"][index])-1],"s_n_z_mm":[float(lower[key][index]) for key in ("s","n","z")],
                   "absolute_peak_difference_c":float(difference[index])} for index in selected]
    histories=pairs["XSEC-F_to_XSEC-VF"]["fixed_physical_point_histories"]
    point_center_shifts={name:{level:float(np.linalg.norm(np.asarray(row[f"{which}_represented_cell"]["represented_cell_center_s_n_z_mm"])-np.asarray(row[f"{which}_represented_cell"]["requested_coordinate_s_n_z_mm"])))
                               for level,which in (("XSEC-F","lower"),("XSEC-VF","upper"))} for name,row in histories.items()}
    return {
        "direct_source_partition_spread_j":source_spread,
        "cumulative_net_conduction_relative_spread":conduction_spread,
        "local_edge_nesting_fraction":nesting,
        "fixed_point_to_represented_cell_center_distance_mm":point_center_shifts,
        "largest_f_to_vf_peak_difference_cells":hotspots,
        "findings":[
            "三档各材料直接吸收能量在浮点精度内一致，可排除总量归一化或材料源分配漂移为主因。",
            "六条带边界、焊材面积、沿焊道和背景边界均冻结，可排除上一轮那种几何档位变化。",
            "材料累计净导热和400℃以上暴露体积整体变化小，但局部峰值与包含固定点的控制体历史明显不稳，问题集中在局部离散而非总体能量账本。",
            "0.4/0.3/0.2mm局部边并非严格嵌套，固定坐标所落控制体中心也随档位移动；当前非单调结果不能直接归因于单一物理项。",
            "下一诊断应记录公共面逐面累计通量和瞬时表面源密度，并使用接口/阶梯边界完全对齐的嵌套局部网格；在该诊断前停止xfine。",
        ],
        "ruled_out_at_integral_level":["总吸收功率","按材料直接源分配","焊材质量与六条带几何"],
        "still_open":["局部表面热源投影密度","非嵌套控制体采样","异材界面逐面通量","阶梯拐角附近单元几何"],
    }


def build_assessment():
    plan=load(SPEC); rules=plan["acceptance"]
    old_rules=load(ROOT/"project/thermal-credibility-v5.4r1.yaml")["convergence"]
    summaries={level:json.loads((RESULTS/level/"summary.json").read_text(encoding="utf-8")) for level in LEVELS}
    pairs={}
    for lower,upper in zip(LEVELS[:-1],LEVELS[1:]):
        key=f"{lower}_to_{upper}"
        pairs[key]={
            "registered_metrics":compare(summaries[lower],summaries[upper],old_rules),
            "continuous_peak_field":field_pair(RESULTS/lower/"field.npz",RESULTS/upper/"field.npz",summaries[lower],summaries[upper],rules),
            "fixed_physical_point_histories":history_pair(RESULTS/lower/"fixed-point-history.json",RESULTS/upper/"fixed-point-history.json",rules),
            "integral_quantities":integral_pair(summaries[lower],summaries[upper],rules),
            "exposure_geometry":geometry_pair(summaries[lower],summaries[upper],rules),
        }
    first=pairs["XSEC-M_to_XSEC-F"]["continuous_peak_field"]["ernife_ci"]
    last=pairs["XSEC-F_to_XSEC-VF"]["continuous_peak_field"]["ernife_ci"]
    reduction=last["volume_weighted_p95_abs_peak_difference_c"]/max(first["volume_weighted_p95_abs_peak_difference_c"],1e-12)
    flips_stable=all(value<=float(rules["threshold_flip_volume_limit_mm3"]) for name in ("qt450_10","ernife_ci") for value in last["threshold_flip_volume_mm3"].values())
    all_last_checks=all(value for material in pairs["XSEC-F_to_XSEC-VF"]["continuous_peak_field"].values() for value in material["checks"].values())
    all_last_checks &= all(value for point in pairs["XSEC-F_to_XSEC-VF"]["fixed_physical_point_histories"].values() for value in point["checks"].values())
    background=_background_frozen()
    asymptotic=bool(reduction<=float(rules["asymptotic_reduction_ratio_max"]) and flips_stable)
    spatial_pass=bool(asymptotic and all_last_checks and all(background.values()))
    return {
        "stage":plan["version"],"evidence_level":plan["evidence_level"],"experiment":"local_cross_section_refinement",
        "fixed_inputs":plan["policy"],"pre_registered_acceptance":rules,"levels":LEVELS,
        "mesh_isolation_checks":background,"pairs":pairs,
        "second_layer_diagnosis":_second_layer_diagnosis(summaries,pairs),
        "asymptotic_diagnosis":{"ernife_p95_reduction_ratio":reduction,"required_maximum":rules["asymptotic_reduction_ratio_max"],"qt_and_ernife_flips_stable":flips_stable,"entered_asymptotic_region":asymptotic},
        "spatial_gate_pass":spatial_pass,"time_step_recheck_allowed":spatial_pass,"xfine_allowed":spatial_pass,
        "thermal_1_allowed":False,
        "decision":"若三级局部细化未进入渐近区或阈值翻转未稳定，则按预登记规则停止暴力xfine，转入热源投影/阶梯边界/界面通量/局部单元几何诊断。" if not spatial_pass else "局部截面空间序列满足预登记门；下一步只在XSEC-VF上执行dt/dt2，必要时dt/4。",
    }


def render(result):
    lines=["# THERMAL-0.5 局部截面空间细化","","> 六条带几何、沿焊道和背景网格冻结；仅改变预登记 n-z 高梯度区。结果是未校准求解器证据。","",
           "| 网格对 | 材料 | MAE (°C) | P95 (°C) | 最大差 (°C) | solidus flip (mm³) | liquidus flip (mm³) |",
           "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for pair,row in result["pairs"].items():
        for name,field in row["continuous_peak_field"].items():
            flip=field["threshold_flip_volume_mm3"]
            lines.append(f"| {pair} | {name} | {field['volume_weighted_mean_abs_peak_difference_c']:.3f} | {field['volume_weighted_p95_abs_peak_difference_c']:.3f} | {field['maximum_abs_peak_difference_c']:.3f} | {flip['solidus']:.3f} | {flip['liquidus']:.3f} |")
    diagnosis=result["asymptotic_diagnosis"]
    lines += ["","## 裁决","",f"焊材 P95 的后一级/前一级缩减比为 {diagnosis['ernife_p95_reduction_ratio']:.3f}（预登记要求 ≤ {diagnosis['required_maximum']:.3f}）；QT/NiFe 阈值翻转稳定：{diagnosis['qt_and_ernife_flips_stable']}。",
              f"`spatial_gate_pass={str(result['spatial_gate_pass']).lower()}`，`time_step_recheck_allowed={str(result['time_step_recheck_allowed']).lower()}`。{result['decision']}"]
    return "\n".join(lines)+"\n"


def main() -> int:
    result=build_assessment()
    write_json(RESULTS/"assessment.json",result)
    (RESULTS/"assessment.md").write_text(render(result),encoding="utf-8")
    print(RESULTS/"assessment.json")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
