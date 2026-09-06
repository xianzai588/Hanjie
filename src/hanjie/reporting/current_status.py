"""从当前权威配置和结果生成报告状态摘要，避免手工表格再次分叉。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import yaml


def _json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_current_status(root: Path) -> Dict[str, Any]:
    from hanjie.domain.joint import joint_design_metrics

    tolerance = yaml.safe_load((root/"project/tolerance.yaml").read_text(encoding="utf-8"))
    stages = yaml.safe_load((root/"project/stage-status.yaml").read_text(encoding="utf-8"))
    structural = _json(root/"simulation/structural-v4/results/static-screening/static-screening-analysis.json")
    thermal = _json(root/"simulation/thermal-v5/results/credibility04r1/assessment.json")
    thermal_fix = _json(root/"simulation/thermal-v5/results/spatial-fix-study/assessment.json")
    joint_load = _json(root/"simulation/structural-v4/results/joint-load-basis/joint-load-basis.json")
    structural_3d = _json(root/"simulation/structural-v4/results/struct0-prep/constitutive-3d-small-mesh.json")
    precomp = _json(root/"studies/PRECOMPENSATION/results/precompensation_summary.json")
    return {
        "generated_from":"当前权威配置与已执行结果；非实测证据仍保留原等级",
        "stages": stages,
        "tolerance":{
            "status":tolerance["budget_status"],
            "radial_limit_mm":tolerance["target"]["radial_deviation_limit_mm"],
            "product_worst_case_design_sum_mm":tolerance["product_geometry_chain"]["worst_case_design_sum_mm"],
            "measurement_expanded_uncertainty_mm":tolerance["measurement_chain"]["expanded_uncertainty_mm"],
        },
        "joint":joint_design_metrics(),
        "structural":{
            "evidence_level":structural["evidence_level"],
            "static_screening_pass":structural["static_screening_pass"],
            "full_thermal_structural_gate_pass":structural["full_thermal_structural_gate_pass"],
            "ranking":structural["ranking"],
        },
        "thermal":{
            "stage":thermal["stage"],"evidence_level":thermal["evidence_level"],
            "conditional_numerical_convergence":thermal["conditional_numerical_convergence"],
            "experimentally_validated":thermal["experimentally_validated"],
            "thermal_1_allowed":thermal["thermal_1_allowed"],
            "baseline":thermal["cases"]["baseline"]["material_statistics"],
            "baseline_energy":thermal["cases"]["baseline"]["energy"],
            "spatial_convergence_pass":(
                thermal["comparisons"]["coarse_to_medium"]["nonzero_metrics_pass"]
                and thermal["comparisons"]["medium_to_fine"]["nonzero_metrics_pass"]
            ),
            "time_step_convergence_pass":(
                thermal["comparisons"]["medium_to_dt-0.05"]["nonzero_metrics_pass"]
                and thermal["comparisons"]["dt-0.05_to_dt-0.025"]["nonzero_metrics_pass"]
            ),
            "discretization_change":thermal["discretization_change"],
        },
        "thermal_spatial_fix":{
            "stage":thermal_fix["stage"],"a_control_completed":thermal_fix["a_control_completed"],
            "spatial_gate_pass":thermal_fix["spatial_gate_pass"],"diagnosis":thermal_fix["diagnosis"],
            "direction_diagnosis":thermal_fix["direction_diagnosis"],
            "medium_to_fine_weld_p95_c":thermal_fix["pairs"]["A-field-medium-fixed6_to_A-field-fine-fixed6"]["common_control_volume_peak_field"]["ernife_ci"]["volume_weighted_p95_abs_peak_difference_c"],
            "medium_to_fine_qt_flip_volume_mm3":thermal_fix["pairs"]["A-field-medium-fixed6_to_A-field-fine-fixed6"]["common_control_volume_peak_field"]["qt450_10"]["solidus_threshold_flip_volume_mm3"],
        },
        "joint_load_basis":{
            "evidence_level":joint_load["evidence_level"],"reference_envelope":joint_load["reference_envelope"],
            "decision":joint_load["decision"],
        },
        "structural_3d_components":{
            "evidence_level":structural_3d["evidence_level"],"checks":structural_3d["checks"],"limitations":structural_3d["limitations"],
        },
        "precompensation":precomp,
    }


def render_markdown(status: Dict[str, Any]) -> str:
    tol,joint,structural,thermal = (status[k] for k in ("tolerance","joint","structural","thermal"))
    lines = ["# 自动生成的当前证据摘要","",status["generated_from"],"",
        "## 阶段状态","","| 阶段 | 执行状态 | 验收结果 | 允许用途 |","| --- | --- | --- | --- |"]
    for stage,row in status["stages"]["stages"].items():
        lines.append(f"| {stage} | {row['execution_status']} | {row['acceptance_result']} | {row['allowed_use']} |")
    lines += ["",
        "## 公差与接头闭合状态","","| 项目 | 当前值 |","| --- | ---: |",
        f"| 产品几何链径向限值 | {tol['radial_limit_mm']:.3f} mm |",
        f"| 产品链最坏情况设计和 | {tol['product_worst_case_design_sum_mm']:.3f} mm |",
        f"| 预算状态 | {tol['status']} |",
        f"| 测量扩展不确定度 | {tol['measurement_expanded_uncertainty_mm'] if tol['measurement_expanded_uncertainty_mm'] is not None else '待实测评定'} |",
        f"| 设计角焊缝截面积 | {joint['design_target']['ideal_triangular_area_mm2']:.3f} mm² |",
        f"| 名义送丝新增截面积 | {joint['nominal_wire_deposition']['area_per_weld_length_mm2']:.3f} mm² |",
        f"| 名义送丝等效焊脚 | {joint['nominal_wire_deposition']['equivalent_ideal_fillet_leg_mm']:.3f} mm |","",
        "## 三维静力筛查","","| 排名 | 候选 | 细网格平均轴线偏移直径 (mm) | P95 应力 (MPa) |","| ---: | --- | ---: | ---: |"]
    for index,row in enumerate(structural["ranking"],1):
        lines.append(f"| {index} | {row['model_id']} | {row['fine_average_displacement_diameter_mm']:.6f} | {row['fine_average_p95_stress_mpa']:.3f} |")
    lines += ["",f"静力筛查门：{'通过' if structural['static_screening_pass'] else '未通过'}；完整热—结构门：{'通过' if structural['full_thermal_structural_gate_pass'] else '未通过'}。","",
              "## THERMAL-0.4R1 名义工况","","| 材料 | 峰温 (°C) | 越固相线体积 (mm³) | 越液相线体积 (mm³) |","| --- | ---: | ---: | ---: |"]
    for key,label in (("q235b","Q235B"),("qt450_10","QT450-10"),("ernife_ci","ERNiFe-CI")):
        row = thermal["baseline"][key]
        lines.append(f"| {label} | {row['peak_temperature_c']:.2f} | {row['ever_solidus_exceeded_volume_mm3']:.6f} | {row['ever_liquidus_exceeded_volume_mm3']:.6f} |")
    lines += ["",f"名义能量残差：{thermal['baseline_energy']['residual_pct']:.3e}%；空间网格收敛：{'通过' if thermal['spatial_convergence_pass'] else '未通过'}；时间步收敛：{'通过' if thermal['time_step_convergence_pass'] else '未通过'}。",
              f"条件数值收敛：{'通过' if thermal['conditional_numerical_convergence'] else '未通过'}；实物校准：{'已完成' if thermal['experimentally_validated'] else '未完成'}；允许进入正式结构耦合：{'是' if thermal['thermal_1_allowed'] else '否'}。",
              "",("相对历史 0.4R 的峰温差："
                   f"Q235B {thermal['discretization_change']['baseline_peak_difference_c']['q235b']:+.2f} °C、"
                   f"QT450-10 {thermal['discretization_change']['baseline_peak_difference_c']['qt450_10']:+.2f} °C、"
                   f"ERNiFe-CI {thermal['discretization_change']['baseline_peak_difference_c']['ernife_ci']:+.2f} °C。"
                   "该差值只表示离散修正影响。")]
    fix=status["thermal_spatial_fix"]
    lines += ["","## Plan 3 新增工程证据","",
              f"固定六条带几何的场网格 A 对照已执行；medium→fine 焊材热区 P95 差为 {fix['medium_to_fine_weld_p95_c']:.3f} °C，QT 固相线翻转体积为 {fix['medium_to_fine_qt_flip_volume_mm3']:.3f} mm³，空间 Gate 仍为未通过。",
              f"方向控制结论：{fix['direction_diagnosis']}。",
              f"条件性接头承载证据等级：`{status['joint_load_basis']['evidence_level']}`；3.5 mm 是否唯一必要：尚不能确定。",
              f"三维 J2 与六四面体小网格登记检查：{'全部通过' if all(status['structural_3d_components']['checks'].values()) else '存在失败'}；任意边界全局求解、接触与整件网格仍未完成。"]
    return "\n".join(lines)+"\n"


def write_status_artifacts(root: Path) -> Path:
    status = collect_current_status(root)
    output = root/"deliverables/report/generated"
    output.mkdir(parents=True,exist_ok=True)
    json_path = output/"current-status.json"
    markdown_path = output/"current-status.md"
    json_path.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding="utf-8")
    markdown_path.write_text(render_markdown(status),encoding="utf-8")
    return markdown_path
