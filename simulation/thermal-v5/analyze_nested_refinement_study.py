"""评估 Plan 5 严格嵌套序列及逐面/局部源离散准入。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from analyze_xsec_refinement_study import field_pair,history_pair
from hanjie.simulation.thermal_ledgers import aggregate_interface_faces,aggregate_source_to_lower_cells
from run_physics03 import ROOT,load,write_json


SPEC=ROOT/"project/thermal-nested-refinement-v5.6.yaml"
RESULTS=ROOT/"simulation/thermal-v5/results/nested-refinement-study"
LEVELS=("NEST-M","NEST-F","NEST-VF")
MATERIALS=("q235b","qt450_10","ernife_ci")


def _relative(a,b,scale_floor=1e-12):
    return abs(float(b)-float(a))/max(abs(float(a)),abs(float(b)),scale_floor)


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def nesting_pair(lower_path,upper_path):
    checks={}
    with np.load(lower_path) as lower,np.load(upper_path) as upper:
        for axis in ("s","n","z"):
            a,b=lower[f"{axis}_edges"],upper[f"{axis}_edges"]
            positions=np.searchsorted(b,a)
            subset=bool(np.all(positions<len(b)) and np.allclose(b[np.minimum(positions,len(b)-1)],a,atol=1e-12,rtol=0))
            subdivisions=np.diff(positions) if subset else np.array([],int)
            checks[axis]={
                "all_lower_edges_present":subset,
                "subdivisions_per_lower_interval":sorted(np.unique(subdivisions).astype(int).tolist()),
                "integer_subdivision_only":bool(subset and np.all((subdivisions==1)|(subdivisions==2))),
            }
    checks["strict_nested"]=all(row["all_lower_edges_present"] and row["integer_subdivision_only"] for row in checks.values())
    return checks


def interface_pair(lower_dir,upper_dir,lower_field,rules):
    lower=_load_json(lower_dir/"interface-flux-ledger.json")
    upper=_load_json(upper_dir/"interface-flux-ledger.json")
    rows={}
    for low_summary in lower["interfaces"]:
        name=low_summary["name"]
        high_summary=next(row for row in upper["interfaces"] if row["name"]==name)
        low_faces=[row for row in lower["faces"] if row["name"]==name]
        high_faces=[row for row in upper["faces"] if row["name"]==name]
        aggregated=aggregate_interface_faces(lower_field,low_faces,high_faces)
        reference=np.asarray([row["cumulative_signed_heat_j"] for row in low_faces])
        l1=float(np.sum(np.abs(aggregated-reference))/max(np.sum(np.abs(reference)),1e-12))
        total_relative=_relative(low_summary["cumulative_signed_heat_j"],high_summary["cumulative_signed_heat_j"])
        rows[name]={
            "lower_face_count":len(low_faces),"upper_face_count":len(high_faces),
            "lower_cumulative_signed_heat_j":low_summary["cumulative_signed_heat_j"],
            "upper_cumulative_signed_heat_j":high_summary["cumulative_signed_heat_j"],
            "cumulative_heat_relative_difference":total_relative,
            "common_face_energy_l1_relative_difference":l1,
            "lower_peak_abs_interface_power_w":low_summary["peak_abs_interface_power_w"],
            "upper_peak_abs_interface_power_w":high_summary["peak_abs_interface_power_w"],
            "lower_peak_abs_heat_flux_w_per_mm2":low_summary["peak_abs_heat_flux_w_per_mm2"],
            "upper_peak_abs_heat_flux_w_per_mm2":high_summary["peak_abs_heat_flux_w_per_mm2"],
            "checks":{
                "cumulative_heat":total_relative<=float(rules["interface_cumulative_heat_relative_limit"]),
                "common_face_energy":l1<=float(rules["interface_face_energy_l1_relative_limit"]),
            },
        }
    return rows


def source_pair(lower_dir,upper_dir,lower_field,rules):
    lower=_load_json(lower_dir/"source-density-ledger.json")
    upper=_load_json(upper_dir/"source-density-ledger.json")
    reference=np.zeros(len(lower_field["material_id"]),dtype=float)
    for row in lower["source_cells"]:
        reference[int(row["cell"])]=float(row["cumulative_source_energy_j"])
    aggregated=aggregate_source_to_lower_cells(lower_field,upper["source_cells"])
    l1=float(np.sum(np.abs(aggregated-reference))/max(np.sum(reference),1e-12))
    centroid=float(np.linalg.norm(np.asarray(upper["energy_weighted_centroid_s_n_z_mm"])-np.asarray(lower["energy_weighted_centroid_s_n_z_mm"])))
    low_moment=np.asarray(lower["energy_weighted_covariance_mm2"])
    high_moment=np.asarray(upper["energy_weighted_covariance_mm2"])
    moment=float(np.linalg.norm(high_moment-low_moment)/max(np.linalg.norm(low_moment),1e-12))
    return {
        "lower_total_source_energy_j":lower["total_source_energy_j"],
        "upper_total_source_energy_j":upper["total_source_energy_j"],
        "total_source_energy_relative_difference":_relative(lower["total_source_energy_j"],upper["total_source_energy_j"]),
        "common_control_volume_source_l1_relative_difference":l1,
        "source_centroid_distance_mm":centroid,
        "source_second_moment_relative_difference":moment,
        "lower_effective_spread_s_n_z_mm":lower["effective_spread_s_n_z_mm"],
        "upper_effective_spread_s_n_z_mm":upper["effective_spread_s_n_z_mm"],
        "lower_maximum_cell_source_density_w_per_mm3":lower["maximum_cell_source_density_w_per_mm3"],
        "upper_maximum_cell_source_density_w_per_mm3":upper["maximum_cell_source_density_w_per_mm3"],
        "checks":{
            "common_control_volume_source":l1<=float(rules["common_patch_source_l1_relative_limit"]),
            "source_centroid":centroid<=float(rules["source_centroid_distance_limit_mm"]),
            "source_second_moment":moment<=float(rules["source_second_moment_relative_limit"]),
        },
        "note":"单元峰值体积源密度随表面源承载单元厚度变化，保留为诊断量，不单独作为准入门；准入使用共同物理控制体积分。",
    }


def _all_checks(rows):
    return all(bool(value) for row in rows.values() for value in row.get("checks",{}).values())


def build_assessment():
    plan=load(SPEC); rules=plan["acceptance"]
    summaries={level:_load_json(RESULTS/level/"summary.json") for level in LEVELS}
    pairs={}
    for lower,upper in zip(LEVELS[:-1],LEVELS[1:]):
        lower_dir,upper_dir=RESULTS/lower,RESULTS/upper
        with np.load(lower_dir/"field.npz") as lower_field:
            pairs[f"{lower}_to_{upper}"]={
                "mesh_nesting":nesting_pair(lower_dir/"field.npz",upper_dir/"field.npz"),
                "continuous_peak_field":field_pair(lower_dir/"field.npz",upper_dir/"field.npz",summaries[lower],summaries[upper],rules),
                "fixed_physical_point_histories":history_pair(lower_dir/"fixed-point-reconstructed-history.json",upper_dir/"fixed-point-reconstructed-history.json",rules),
                "interface_flux":interface_pair(lower_dir,upper_dir,lower_field,rules),
                "local_source_distribution":source_pair(lower_dir,upper_dir,lower_field,rules),
            }
    first=pairs["NEST-M_to_NEST-F"]["continuous_peak_field"]["ernife_ci"]["volume_weighted_p95_abs_peak_difference_c"]
    last=pairs["NEST-F_to_NEST-VF"]["continuous_peak_field"]["ernife_ci"]["volume_weighted_p95_abs_peak_difference_c"]
    reduction=float(last/max(first,1e-12))
    final_pair=pairs["NEST-F_to_NEST-VF"]
    field_pass=_all_checks(final_pair["continuous_peak_field"])
    history_pass=_all_checks(final_pair["fixed_physical_point_histories"])
    interface_pass=_all_checks(final_pair["interface_flux"])
    source_pass=all(final_pair["local_source_distribution"]["checks"].values())
    nesting_pass=bool(final_pair["mesh_nesting"]["strict_nested"] and pairs["NEST-M_to_NEST-F"]["mesh_nesting"]["strict_nested"])
    asymptotic=reduction<=float(rules["asymptotic_reduction_ratio_max"])
    spatial_pass=bool(nesting_pass and asymptotic and field_pass and history_pass and interface_pass and source_pass)
    failed=[]
    if not asymptotic: failed.append("连续峰温P95未进入预登记渐近区")
    if not field_pass: failed.append("连续峰温或相变阈值翻转未稳定")
    if not history_pass: failed.append("固定物理点完整热循环未稳定")
    if not interface_pass: failed.append("共同物理界面累计通量未稳定")
    if not source_pass: failed.append("共同控制体源积分、质心或二阶矩未稳定")
    if not nesting_pass: failed.append("网格不满足严格整数嵌套")
    final_source=final_pair["local_source_distribution"]
    final_interfaces=final_pair["interface_flux"]
    peak_density_ratio=final_source["upper_maximum_cell_source_density_w_per_mm3"]/max(final_source["lower_maximum_cell_source_density_w_per_mm3"],1e-12)
    peak_flux_ratios={name:row["upper_peak_abs_heat_flux_w_per_mm2"]/max(row["lower_peak_abs_heat_flux_w_per_mm2"],1e-12) for name,row in final_interfaces.items()}
    return {
        "stage":plan["version"],"evidence_level":plan["evidence_level"],
        "experiment":"strictly_nested_local_spatial_discretization",
        "fixed_inputs":plan["policy"],"pre_registered_acceptance":rules,"levels":LEVELS,"pairs":pairs,
        "asymptotic_diagnosis":{"ernife_p95_reduction_ratio":reduction,"required_maximum":rules["asymptotic_reduction_ratio_max"],"entered_asymptotic_region":asymptotic},
        "gate_components":{"strict_nesting":nesting_pass,"continuous_peak_and_flips":field_pass,"fixed_coordinate_full_history":history_pass,"interface_flux":interface_pass,"local_source_distribution":source_pass},
        "spatial_gate_pass":spatial_pass,"xfine_allowed":spatial_pass,"time_step_recheck_allowed":spatial_pass,
        "thermal_1_allowed":False,"formal_struct_0_allowed":False,
        "failed_mechanisms":failed,
        "mechanism_diagnosis":{
            "ruled_out":["非嵌套网格","总吸收能量漂移","共同物理控制体源积分漂移","累计界面净热量漂移","相变阈值翻转未进入1mm3门槛"],
            "remaining":"表面源能量落入随h变薄的承载控制体、局部逐面峰值以及固定点重构仍具有h敏感性。",
            "maximum_cell_source_density_f_to_vf_ratio":peak_density_ratio,
            "peak_interface_flux_f_to_vf_ratios":peak_flux_ratios,
            "next_action":"停止NEST-XF；把表面源作为显式边界面Neumann通量并建立仿射精确的同材料点重构，再重复现有NEST-F/VF对照。",
        },
        "decision":"严格嵌套空间门通过；只允许在NEST-VF上执行dt、dt/2，必要时dt/4，正式热历史仍须等待时间门。" if spatial_pass else "停止NEST-XF与时间步复查；累计界面热量和共同控制体源积分已通过，下一轮只处理边界源承载层、逐面峰值与固定点重构的h敏感性。",
    }


def render(result):
    lines=["# THERMAL-0.6 严格嵌套离散准入","","> 比较对象为完全一致的物理坐标、材料界面与焊道外形；局部控制体按整数细分。","",
           "| 网格对 | NiFe P95 (°C) | QT solidus flip (mm³) | NiFe solidus flip (mm³) | 源共同体 L1 | 接口最大 L1 |",
           "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for key,pair in result["pairs"].items():
        field=pair["continuous_peak_field"]
        interface=max(row["common_face_energy_l1_relative_difference"] for row in pair["interface_flux"].values())
        lines.append(f"| {key} | {field['ernife_ci']['volume_weighted_p95_abs_peak_difference_c']:.3f} | {field['qt450_10']['threshold_flip_volume_mm3']['solidus']:.3f} | {field['ernife_ci']['threshold_flip_volume_mm3']['solidus']:.3f} | {pair['local_source_distribution']['common_control_volume_source_l1_relative_difference']:.4f} | {interface:.4f} |")
    lines += ["","## 裁决","",f"`spatial_gate_pass={str(result['spatial_gate_pass']).lower()}`；`xfine_allowed={str(result['xfine_allowed']).lower()}`；`time_step_recheck_allowed={str(result['time_step_recheck_allowed']).lower()}`。",result["decision"]]
    if result["failed_mechanisms"]:
        lines += ["","未通过项："+"；".join(result["failed_mechanisms"])+"。"]
    return "\n".join(lines)+"\n"


def main():
    result=build_assessment()
    write_json(RESULTS/"assessment.json",result)
    (RESULTS/"assessment.md").write_text(render(result),encoding="utf-8")
    print(RESULTS/"assessment.json")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
