"""将现有接头假设转为可复算的条件选型，不提升物理证据等级。"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

from hanjie.domain.joint_load import evaluate_layout


SPEC = "studies/ROUTE-B-DESIGN/config.yaml"


def read_data(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def deposited_section(wire_diameter: float, feed: float, speed: float,
                      passes: int, efficiency: float) -> tuple[float, float]:
    if (not all(math.isfinite(v) and v > 0 for v in (wire_diameter, feed, speed))
            or not isinstance(passes, int) or isinstance(passes, bool) or passes < 1
            or not math.isfinite(efficiency) or not 0 < efficiency <= 1):
        raise ValueError("送丝、速度、道数和沉积效率必须为有效正值")
    area = math.pi * wire_diameter**2 / 4 * feed / speed * passes * efficiency
    return area, math.sqrt(2 * area)


def precision_requirements(tolerance: dict, spec: dict) -> dict:
    contributions = tolerance["product_geometry_chain"]["contributions_mm"]
    total = math.fsum(contributions.values())
    declared = tolerance["product_geometry_chain"]["worst_case_design_sum_mm"]
    if not math.isclose(total, declared, abs_tol=1e-12):
        raise ValueError("权威公差预算各项与声明总和不一致")
    limit = tolerance["target"]["radial_deviation_limit_mm"]
    if not math.isclose(2 * limit, tolerance["target"]["cylindrical_tolerance_zone_diameter_mm"], abs_tol=1e-12):
        raise ValueError("径向预算与直径位置度限值不一致")
    adjustable = spec["adjustable_contributions"]
    adjustable_sum = math.fsum(contributions[key] for key in adjustable)
    fixed = total - adjustable_sum - contributions["thermal_deformation"]
    rows = []
    for thermal in spec["thermal_radial_allocations_mm"]:
        remaining = limit - fixed - thermal
        rows.append({
            "thermal_radial_allocation_mm": thermal,
            "fixture_and_assembly_budget_max_mm": remaining,
            "required_reduction_from_current_mm": max(0., adjustable_sum - remaining),
            "nonnegative_budget_possible": remaining >= -1e-12,
        })
    return {
        "evidence_level": "design_requirement_not_achieved_capability",
        "radial_limit_mm": limit,
        "current_total_radial_mm": total,
        "radial_deficit_mm": max(0., total - limit),
        "fixed_other_contributions_mm": fixed,
        "current_fixture_and_assembly_mm": adjustable_sum,
        "thermal_budget_if_other_items_unchanged_mm": limit - (total - contributions["thermal_deformation"]),
        "budget_status": tolerance["budget_status"],
        "rows": rows,
        "measurement_uncertainty_separate": True,
        "product_position_acceptance_claim_allowed": False,
    }


def select_low_heat(candidates: list[dict], load_scale: float, allowable: float) -> dict:
    if not all(math.isfinite(v) and v > 0 for v in (load_scale, allowable)):
        raise ValueError("载荷缩放与假设许用应力必须为有效正值")
    assessed = []
    for candidate in candidates:
        demand = candidate["worst_required_allowable_mpa"] * load_scale
        assessed.append({
            "candidate_id": candidate["candidate_id"],
            "required_allowable_mpa": demand,
            "conditional_margin": allowable / demand,
            "conditional_capacity_screen_pass": demand <= allowable,
            "nominal_net_heat_input_j": candidate["nominal_net_heat_input_j"],
        })
    feasible = [row for row in assessed if row["conditional_capacity_screen_pass"]]
    best = min((row["nominal_net_heat_input_j"] for row in feasible), default=None)
    # 保留数值相同的候选，避免顺序决定“最优”；无可行项时显式返回空集。
    selected = [row["candidate_id"] for row in feasible
                if math.isclose(row["nominal_net_heat_input_j"], best, rel_tol=1e-10)]
    return {
        "load_scale": load_scale, "assumed_allowable_mpa": allowable,
        "selected_for_further_study": selected,
        "status": "conditional_capacity_only" if selected else "no_capacity_feasible_candidate",
        "assessed_candidates": assessed,
        "engineering_recommendation_released": False,
    }


def build_design_study(root: Path) -> dict:
    config = read_data(root / SPEC)
    source = {key: read_data(root / path) for key, path in config["sources"].items()}
    process = source["process"]["process"]
    nominal, joint = process["nominal"], process["joint_consistency"]
    load = source["load_basis"]
    geometry = source["geometry"]
    leg_target = float(joint["design_fillet_leg_mm"])
    if not math.isclose(leg_target, geometry["design_assumptions"]["fillet_leg_length"], abs_tol=1e-12):
        raise ValueError("CAD 与工艺卡的目标焊脚不一致")
    speed = float(nominal["travel_speed_mm_s"])
    power = float(nominal["current_a"]) * float(nominal["voltage_v"])
    net_line_energy = power * float(nominal["arc_efficiency"]) / speed
    if not math.isclose(net_line_energy, nominal["heat_input_j_per_mm"], rel_tol=1e-10):
        raise ValueError("电流、电压、速度与名义净线热输入不一致")
    efficiencies = sorted(set(map(float, joint["deposition_efficiency_range"])))
    eta_nominal = float(joint["deposition_efficiency_nominal"])
    if not 0 < efficiencies[0] <= eta_nominal <= efficiencies[-1] <= 1:
        raise ValueError("沉积效率范围未覆盖名义效率或超出物理范围")
    diameter = float(nominal["filler_diameter_mm"])
    wire_area = math.pi * diameter**2 / 4
    density = float(source["materials"]["materials"]["ernife_ci"]["nominal_properties_20c"]["density_kg_m3"])
    candidates, cases = [], []
    for name, path in load["layouts"].items():
        manifest = read_data(root / path)
        for scenario_id in config["process_scenarios"]:
            scenario = joint["scenarios"][scenario_id]
            passes = scenario["pass_count"]
            if scenario_id == "current_single_pass_diagnostic":
                feed = float(nominal["filler_feed_rate_mm_s"])
            else:
                feed = leg_target**2 / 2 * speed / (wire_area * passes * eta_nominal)
            sections = [deposited_section(diameter, feed, speed, passes, eta) for eta in efficiencies]
            layout = evaluate_layout(manifest, [section[1] for section in sections],
                                     load["reference_envelope"], load["effective_throat_factor"])
            length = layout["effective_weld_length_mm"]
            if not math.isclose(length, layout["cad_effective_weld_length_mm"], rel_tol=1e-10):
                raise ValueError(f"{name}：积分焊长与 CAD 实测焊长不一致")
            cid = f"{name}/{passes}pass"
            nominal_area, nominal_leg = deposited_section(diameter, feed, speed, passes, eta_nominal)
            arc_time = passes * length / speed
            row = {
                "candidate_id": cid, "layout": name, "scenario_id": scenario_id,
                "geometry_source": path, "pass_count": passes,
                "weld_length_mm": length, "fixed_feed_mm_s": feed,
                "wire_diameter_mm": diameter, "travel_speed_mm_s": speed,
                "deposition_efficiency_range": efficiencies,
                "nominal_deposited_area_mm2": nominal_area,
                "nominal_equivalent_leg_mm": nominal_leg,
                "equivalent_leg_range_mm": [sections[0][1], sections[-1][1]],
                "nominal_total_deposited_volume_mm3": nominal_area * length,
                "nominal_retained_filler_mass_g": nominal_area * length * density / 1e6,
                "purchased_wire_mass_g": wire_area * feed * arc_time * density / 1e6,
                "arc_on_time_s": arc_time,
                "nominal_net_heat_input_j": net_line_energy * length * passes,
                "gross_arc_energy_j": power * arc_time,
                "total_cycle_time_s": None,
                "worst_required_allowable_mpa": max(r["reference_envelope_corner_required_allowable_mpa"] for r in layout["rows"]),
                "cad_target_section_matches_nominal": math.isclose(nominal_leg, leg_target, rel_tol=1e-10),
                "volume_accounting_closed": True,
                "deposited_weld_solid_generated": False,
                "thermal_history_solved_for_this_candidate": False,
                "physical_forming_validated": False,
            }
            candidates.append(row)
            for eta, section, capacity in zip(efficiencies, sections, layout["rows"]):
                for scale in config["load_scales"]:
                    for allowable in load["allowable_stress_sensitivity_mpa"]:
                        demand = capacity["reference_envelope_corner_required_allowable_mpa"] * scale
                        cases.append({
                            "candidate_id": cid, "deposition_efficiency": eta,
                            "deposited_area_mm2": section[0], "equivalent_leg_mm": section[1],
                            "retained_filler_mass_g": section[0] * length * density / 1e6,
                            "load_scale": scale, "assumed_allowable_mpa": allowable,
                            "required_allowable_mpa": demand, "conditional_margin": allowable / demand,
                            "conditional_capacity_screen_pass": demand <= allowable,
                            "net_heat_input_j": row["nominal_net_heat_input_j"],
                            "arc_on_time_s": arc_time,
                            "evidence_level": "design_assumption_reference_envelope",
                        })
    decisions = [select_low_heat(candidates, scale, allowable)
                 for scale in config["load_scales"] for allowable in load["allowable_stress_sensitivity_mpa"]]
    uncertainty = source["structural_uncertainty"]
    return {
        "stage": "ROUTE-B-DESIGN", "evidence_level": config["evidence_level"],
        "input_config": SPEC, "input_sources": config["sources"],
        "reference_envelope": load["reference_envelope"],
        "load_scale_basis": config["load_scale_basis"],
        "allowable_basis": load["allowable_basis"],
        "feed_setting_policy": config["feed_setting_policy"],
        "selection_policy": config["selection"],
        "candidate_count": len(candidates), "case_count": len(cases),
        "candidates": candidates, "cases": cases, "decisions": decisions,
        "precision": precision_requirements(source["tolerance"], config["precision"]),
        "structural_evidence": {
            "cases_executed": uncertainty["cases_executed"],
            "robust_candidate_ranking_established": uncertainty["robust_candidate_ranking_established"],
            "pairs": uncertainty["pairs"],
            "limitations": uncertainty["limitations"],
        },
        "release": config["release"],
        "limitations": [
            "沉积截面为等脚三角形体积等效，不含母材稀释、成形与缺陷",
            "沿用简化焊缝线群模型，不含根部未熔合、局部应力集中、疲劳和服役载荷验证",
            "净热输入按共同的未校准电弧效率核算；弧燃时间不含装夹、引收弧、转位、层间等待和冷却",
            "沉积效率区间为原设计假设，固定送丝下只核算体积变化，没有求解熔池热响应",
            "当前三维图与实体不含本研究全部沉积焊缝；体积闭合不等于三材料几何或完整热结构闭合",
            "没有把简化结构敏感性位置度作为合格筛选条件；最终工程推荐仍需精度、可焊性和洁净要求共同成立",
        ],
    }


def render_design_markdown(result: dict) -> str:
    lines = ["## 无实物条件选型与精度反算", "",
             "以下为设计假设下的焊缝组核算，未增加实焊、整件热塑性或质量验收证据。",
             f"共 {result['candidate_count']} 个候选、{result['case_count']} 个确定性组合；沉积效率使用原配置两端。",
             "参考包络：径向力 0–5000 N、轴向力 0–5000 N、倾覆力矩 0–250 N·m；缩放系数同时作用于三者。",
             "许用应力仅取原配置的敏感性假设，不能作为 QT450-10 异种焊缝的真实许用值。", "",
             "| 候选 | 等效焊脚范围 mm | 固定送丝 mm/s | 所需许用 MPa | 净热输入 kJ | 弧燃时间 s |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in result["candidates"]:
        lo, hi = row["equivalent_leg_range_mm"]
        lines.append(f"| {row['candidate_id']} | {lo:.3f}–{hi:.3f} | {row['fixed_feed_mm_s']:.3f} | {row['worst_required_allowable_mpa']:.2f} | {row['nominal_net_heat_input_j']/1000:.2f} | {row['arc_on_time_s']:.1f} |")
    lines += ["", "所需许用值对应 1.0 倍参考包络和沉积效率下限。单道为诊断候选，四道只在名义效率下对应 CAD 的 3.5 mm 目标截面。",
              "保持送丝不变时，效率下降会缩小焊脚并提高所需许用应力；不能一边沿用 3.5 mm 承载能力，一边采用单道耗材与热量。", "",
              "| 载荷系数 | 假设许用 MPa | 容量筛查后的低热输入研究优先项 |",
              "| ---: | ---: | --- |"]
    for row in result["decisions"]:
        lines.append(f"| {row['load_scale']:.1f} | {row['assumed_allowable_mpa']:.0f} | {', '.join(row['selected_for_further_study']) or '无容量可行项'} |")
    precision = result["precision"]
    lines += ["", "上表仅回答简化承载约束下的名义热输入取舍，不是已经满足位置度、熔合、疲劳和洁净度的推荐工艺。",
              "", f"当前径向预算缺口 {precision['radial_deficit_mm']:.3f} mm；其他项目不变时，留给热变形的预算仅 {precision['thermal_budget_if_other_items_unchanged_mm']:.3f} mm。",
              f"固定保留基准与松夹等分配 {precision['fixed_other_contributions_mm']:.3f} mm，现有夹具与初始装配合计 {precision['current_fixture_and_assembly_mm']:.3f} mm，反算要求如下：", "",
              "| 热变形径向预算 mm | 夹具与装配合计上限 mm | 相对当前至少减少 mm |",
              "| ---: | ---: | ---: |"]
    for row in precision["rows"]:
        lines.append(f"| {row['thermal_radial_allocation_mm']:.3f} | {row['fixture_and_assembly_budget_max_mm']:.3f} | {row['required_reduction_from_current_mm']:.3f} |")
    lines += ["", "该表是设计要求反算；未调整权威预算、未证明夹具能力，也未将测量不确定度混入产品几何链。",
              "", f"现有结构敏感性已执行 {result['structural_evidence']['cases_executed']} 例。下表按既定分辨尺度比较：", "",
              "| 成对候选 | 前者更低 | 后者更低 | 无法分辨 |", "| --- | ---: | ---: | ---: |"]
    for pair in result["structural_evidence"]["pairs"]:
        lines.append(f"| {pair['a']} / {pair['b']} | {pair['a_lower']} | {pair['b_lower']} | {pair['unresolved']} |")
    lines += ["", "没有稳健的残余变形优胜方案。该敏感性链未求解候选实际焊序、壳体/焊缝塑性和松夹接触；小响应值不能用于 Ø0.05 mm 验收。", ""]
    return "\n".join(lines)
