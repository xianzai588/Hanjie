"""从当前权威配置和结果生成报告状态摘要，避免手工表格再次分叉。"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any, Dict

import yaml
from hanjie.domain.competition_design import current_assessment


def _json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_tooling_status(root: Path) -> Dict[str, Any]:
    directory = root/"studies/TOOLING-ACCESS/results"
    inputs = _json(directory/"run-inputs.json")
    # BREP不能靠文件名判定版本；只校核本次几何证据实际依赖的实体。
    for path, expected in inputs["structured_inputs"].items():
        actual = yaml.safe_load((root/path).read_text(encoding="utf-8"))
        if actual != expected:
            raise ValueError("工装检查输入已变化，请重跑 studies/TOOLING-ACCESS/run.py")
    for path, expected in inputs["geometry_sha256"].items():
        if hashlib.sha256((root/path).read_bytes()).hexdigest() != expected:
            raise ValueError("工装检查实体已变化，请重跑 studies/TOOLING-ACCESS/run.py")
    return _json(directory/"assessment.json")


def render_tooling_markdown(tooling: Dict[str, Any]) -> str:
    shield, mandrel = tooling["shield"], tooling["mandrel"]
    lines = ["## 工装空间与锥面约束检查", "",
             "采用现有BREP和新增明确尺寸的刚性工装包络，名义座体底面z=100 mm。底口开放属于工序假设。未包含六支承、机器人腕部、送丝机构和管线。", "",
             "| 座体 | 退出方向 | 与座体相交体积 mm³ | 所列实体扫掠检查 |",
             "| --- | --- | ---: | --- |"]
    for row in shield["cases"]:
        lines.append(f"| {row['layout']} | {'底口' if row['route']=='bottom' else '上口'} | {row['seat_intersection_volume_mm3']:.2f} | {'无干涉' if row['swept_body_geometry_clear'] else '被阻挡'} |")
    lines += ["", shield["decision"],
              f"截留盘外半径 {shield['capture_outer_radius_mm']:.2f} mm，名义壁隙 {shield['nominal_shell_clearance_mm']:.2f} mm；R{shield['vertical_drop_at_interface_radius_mm']:.2f} mm接口的垂直落物路径不在盘面覆盖内。", "",
              "| 焊枪倾角（距竖直） | 枪体形式 | 三个提升姿态 | 连续竖直路径包络 |",
              "| ---: | --- | --- | --- |"]
    for row in tooling["torch"]["cases"]:
        certificate = row["vertical_path_certificate"]
        path_status = "未建立" if certificate is None else ("所列障碍下通过" if certificate["continuous_vertical_lift_clear"] else "不通过")
        lines.append(f"| {row['tilt_deg']:.0f}° | {'弯头后竖直' if row['body_style']=='bent_vertical' else '直线延长'} | {'无干涉' if row['sampled_poses_clear'] else '存在干涉'} | {path_status} |")
    lines += ["", "本轮保留30°/45°弯头后竖直枪体作为空间设计候选。该结论限于假设工具尺寸与列明障碍，不代表实际机器人可达性、保护气或焊接质量已验证。", "",
              f"原锥体整段插入圆柱孔的穿透体积为 {mandrel['naive_full_length_insertion_overlap_mm3']:.3f} mm³；沿轴向退让 {mandrel['rigid_seating_shift_mm']:.3f} mm后体积干涉为 {mandrel['seated_cone_overlap_mm3']:.3f} mm³，名义接触为孔上缘一圈。",
              "压入载荷情景：假设原500 N全部经锥面传递，库仑摩擦系数只作确定性扫描。径向数值是周向压紧载荷标量和；轴对称时径向合力矢量为零，不可将两者混用。", "",
              "| 假设摩擦系数 | 径向压紧标量和 N | 自锁可能 |", "| ---: | ---: | --- |"]
    for row in mandrel["force_scenarios"]:
        lines.append(f"| {row['friction_coefficient']:.2f} | {row['radial_compression_scalar_sum_n']:.1f} | {'是' if row['self_lock_possible'] else '否'} |")
    lines += ["", "半锥角约0.573°，自锁临界摩擦系数约0.01；实际摩擦与接触带未知，不能推导接触压力、孔扩张或定位重复性。需要补独立倾斜约束和主动退锥设计。", ""]
    return "\n".join(lines)


def collect_current_status(root: Path) -> Dict[str, Any]:
    from hanjie.domain.joint import joint_design_metrics
    from hanjie.domain.route_b_design import build_design_study

    design = build_design_study(root)
    design.pop("cases")
    recorded_design = _json(root/"studies/ROUTE-B-DESIGN/results/assessment.json")
    if design != recorded_design:
        raise ValueError("条件选型结果已过期，请先运行 studies/ROUTE-B-DESIGN/run.py")
    tolerance = yaml.safe_load((root/"project/tolerance.yaml").read_text(encoding="utf-8"))
    stages = yaml.safe_load((root/"project/stage-status.yaml").read_text(encoding="utf-8"))
    structural = _json(root/"simulation/structural-v4/results/static-screening/static-screening-analysis.json")
    thermal = _json(root/"simulation/thermal-v5/results/credibility04r1/assessment.json")
    thermal_fix = _json(root/"simulation/thermal-v5/results/spatial-fix-study/assessment.json")
    thermal_xsec = _json(root/"simulation/thermal-v5/results/xsec-refinement-study/assessment.json")
    thermal_boundary = _json(root/"simulation/thermal-v5/results/boundary-neumann-plan6/assessment.json")
    joint_load = _json(root/"simulation/structural-v4/results/joint-load-basis/joint-load-basis.json")
    structural_3d = _json(root/"simulation/structural-v4/results/struct0-prep/constitutive-3d-small-mesh.json")
    structural_newton = _json(root/"simulation/structural-v4/results/struct0-prep/global-newton-benchmarks.json")
    continuous_mesh = _json(root/"simulation/structural-v4/results/struct0-prep/continuous-unified-mesh.json")
    swept_mesh = _json(root/"simulation/structural-v4/results/struct0-prep/continuous-swept-plan6-admitted.json")
    dress_rehearsal = _json(root/"simulation/structural-v4/results/struct0-prep/struct0-prep-dress-rehearsal-plan6.json")
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
        "thermal_xsec":{
            "stage":thermal_xsec["stage"],"spatial_gate_pass":thermal_xsec["spatial_gate_pass"],
            "time_step_recheck_allowed":thermal_xsec["time_step_recheck_allowed"],
            "asymptotic_diagnosis":thermal_xsec["asymptotic_diagnosis"],
            "m_to_f_weld_p95_c":thermal_xsec["pairs"]["XSEC-M_to_XSEC-F"]["continuous_peak_field"]["ernife_ci"]["volume_weighted_p95_abs_peak_difference_c"],
            "f_to_vf_weld_p95_c":thermal_xsec["pairs"]["XSEC-F_to_XSEC-VF"]["continuous_peak_field"]["ernife_ci"]["volume_weighted_p95_abs_peak_difference_c"],
            "second_layer_diagnosis":thermal_xsec["second_layer_diagnosis"],
        },
        "thermal_boundary_neumann": {
            "stage": thermal_boundary["stage"], "formal_struct_0_allowed": thermal_boundary["formal_struct_0_allowed"],
            "new_nest_m_allowed": thermal_boundary["new_nest_m_allowed"],
            "weld_p95_c": thermal_boundary["continuous_peak_field"]["ernife_ci"]["volume_weighted_p95_abs_peak_difference_c"],
            "weld_mae_c": thermal_boundary["continuous_peak_field"]["ernife_ci"]["volume_weighted_mean_abs_peak_difference_c"],
            "worst_fixed_point_rms_c": max(row["rms_same_time_difference_c"] for row in thermal_boundary["fixed_physical_point_histories"].values()),
        },
        "joint_load_basis":{
            "evidence_level":joint_load["evidence_level"],"reference_envelope":joint_load["reference_envelope"],
            "decision":joint_load["decision"],
        },
        "structural_3d_components":{
            "evidence_level":structural_3d["evidence_level"],"checks":structural_3d["checks"],"limitations":structural_3d["limitations"],
        },
        "structural_global_newton":{"evidence_level":structural_newton["evidence_level"],"checks":structural_newton["checks"],
                                    "struct_prep_gate_pass":structural_newton["struct_prep_gate_pass"]},
        "continuous_unified_mesh":{"counts":continuous_mesh["counts"],"quality":continuous_mesh["quality"],
                                   "checks":continuous_mesh["checks"],"struct_prep_gate_pass":continuous_mesh["struct_prep_gate_pass"]},
        "continuous_swept_mesh": swept_mesh,
        "struct0_dress_rehearsal": {
            "struct0_prep_status": dress_rehearsal["struct0_prep_status"], "formal_struct_0_allowed": dress_rehearsal["formal_struct_0_allowed"],
            "maximum_newton_iterations": dress_rehearsal["maximum_newton_iterations"],
            "maximum_force_balance_error_n": dress_rehearsal["maximum_force_balance_error_n"],
            "maximum_moment_balance_error_n_mm": dress_rehearsal["maximum_moment_balance_error_n_mm"],
        },
        "precompensation":precomp,
        "route_b_design": design,
        "tooling_access": collect_tooling_status(root),
        "competition_design": current_assessment(root),
    }


def render_markdown(status: Dict[str, Any]) -> str:
    from hanjie.domain.route_b_design import render_design_markdown

    tol,joint,structural,thermal = (status[k] for k in ("tolerance","joint","structural","thermal"))
    lines = ["# 自动生成的当前证据摘要","",status["generated_from"],"",
        "## 当前参赛修订 COMPETITION-R1", "",
        "当前说明书和四页图集采用圆柱胀套、连续薄裙和Ø1.6四道固定送丝。下列ROUTE-B-DESIGN与TOOLING-ACCESS是历史选型/失败情景，不覆盖新工装。",
        f"修订直径预算（含目标测量不确定度）{status['competition_design']['precision']['diameter_with_uncertainty_target_mm']:.4f} mm；仅设计分配，实物与正式热—结构仍未放行。", "",
        render_design_markdown(status["route_b_design"]),
        render_tooling_markdown(status["tooling_access"]),
        "## 当前关键阶段","","| 阶段 | 验收状态 | 允许用途 |","| --- | --- | --- |"]
    visible_stages = {"G-INPUTS", "LOAD-BASIS-0", "THERMAL-0.4R1", "THERMAL-REF-PLAN8",
                      "THERMAL-NUMERICAL-GATE", "STRUCT-0-PREP", "STRUCT-0",
                      "STRUCT-UNCERTAINTY", "ROUTE-B-DESIGN", "TOOLING-ACCESS", "DECISION", "COMPETITION-R1"}
    acceptance_labels = {
        "design_checks_passed_physical_performance_unverified": "修订设计检查通过；实物性能未验证",
        "not_closed": "设计输入尚未全部闭合",
        "reference_envelope_only_actual_load_missing": "仅参考包络；无实际载荷",
        "failed_spatial_convergence": "空间收敛未通过",
        "diagnostic_checks_passed_local_field_disagreement_persists": "诊断执行完成；近场仍有差异",
        "not_passed": "未通过",
        "ready_pending_admitted_thermal_history": "结构准备就绪；等待可信热历史",
        "blocked_by_thermal_only": "整件结构未执行；热载荷未准入",
        "no_resolved_robust_winner": "没有可分辨的稳健优胜方案",
        "conditional_selection_available_full_engineering_release_not_available": "条件选型完成；完整工程尚未放行",
        "conditional_research_priorities_only": "仅条件性研究优先项",
        "limited_geometry_routes_available_cleanliness_and_repeatability_open": "所列包络有可行路线；洁净与定位精度未闭合",
    }
    for stage,row in status["stages"]["stages"].items():
        if stage in visible_stages:
            acceptance = acceptance_labels.get(row["acceptance_result"], row["acceptance_result"])
            lines.append(f"| {stage} | {acceptance} | {row['allowed_use']} |")
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
              "## 历史局部热诊断：THERMAL-0.4R1 名义工况","","| 材料 | 峰温 (°C) | 越固相线体积 (mm³) | 越液相线体积 (mm³) |","| --- | ---: | ---: | ---: |"]
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
              f"三维 J2 与六四面体小网格登记检查：{'全部通过' if all(status['structural_3d_components']['checks'].values()) else '存在失败'}；其后续全局求解状态见 Plan 4。"]
    xsec=status["thermal_xsec"]; newton=status["structural_global_newton"]; mesh=status["continuous_unified_mesh"]
    lines += ["","## Plan 4 数值准入与结构预备证据","",
              f"局部截面 M→F/F→VF 焊材 P95 差为 {xsec['m_to_f_weld_p95_c']:.3f}/{xsec['f_to_vf_weld_p95_c']:.3f} °C，缩减比 {xsec['asymptotic_diagnosis']['ernife_p95_reduction_ratio']:.3f}；未进入渐近区，停止 xfine 和时间步复查。",
              f"一致切线与全局 Newton 小网格登记检查：{'全部通过' if all(newton['checks'].values()) else '存在失败'}；仍不等于整件求解。",
              f"Continuous 预备网格含 {mesh['counts']['nodes']} 节点、{mesh['counts']['tetrahedra']} 四面体，无倒置单元；但 minSICN<0.1 仍有 {mesh['quality']['below_0p1_count']} 个，热场映射和接触求解尚未完成。",
              "以上为 Plan 4 历史状态；STRUCT-PREP 后续已完成扫掠网格彩排，见 Plan 6，正式结构热载荷仍未准入。"]
    boundary=status["thermal_boundary_neumann"]; swept=status["continuous_swept_mesh"]; rehearsal=status["struct0_dress_rehearsal"]
    lines += ["","## Plan 6 边界一致热离散与 Continuous 拓扑","",
              f"显式边界 Neumann 的 F→VF 焊材 P95/MAE 为 {boundary['weld_p95_c']:.3f}/{boundary['weld_mae_c']:.3f} °C；新 M 运行许可：{'是' if boundary['new_nest_m_allowed'] else '否'}。",
              f"扫掠网格 {swept['counts']['nodes']} 节点、{swept['counts']['tetrahedra']} 四面体，minSICN<0.1 为 {swept['quality']['below_0p1_count']}；彩排最大 Newton 迭代 {rehearsal['maximum_newton_iterations']}。",
              f"STRUCT-0-PREP=`{rehearsal['struct0_prep_status']}`；正式 STRUCT-0 仍不允许。"]
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
