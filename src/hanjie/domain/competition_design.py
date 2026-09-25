"""参赛修订方案的守恒核算、工装几何与工序互锁；不输出实物合格结论。"""
from __future__ import annotations

import math
import hashlib
import json
from pathlib import Path
import yaml
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeRevol
from OCP.gp import gp_Ax1, gp_Ax2, gp_Pnt, gp_Dir
from hanjie.domain.tooling_access import (read_brep, translated, cylinder, common_volume,
    clearance, make_weld_envelope, make_torch, volume)
from hanjie.domain.joint_load import evaluate_layout

SPEC = "project/competition-design.yaml"


def read_spec(root: Path):
    spec = yaml.safe_load((root / SPEC).read_text(encoding="utf-8"))
    budget = yaml.safe_load((root / spec["precision"]["allocation_source"]).read_text(encoding="utf-8"))
    spec["precision"]["radial_allocations_mm"] = budget["product_geometry_chain"]["contributions_mm"]
    spec["precision"]["measurement_expanded_uncertainty_diameter_target_mm"] = budget["measurement_chain"]["design_expanded_uncertainty_diameter_target_mm"]
    spec["precision"]["thermal_residual_closure_status"] = budget["thermal_residual_management"]["closure_status"]
    spec["precision"]["measurement_uncertainty_verified"] = budget["measurement_chain"]["expanded_uncertainty_mm"] is not None
    spec["fixture"] = resolve_fixture_candidate(spec["fixture"])
    return spec


def resolve_fixture_candidate(fixture: dict) -> dict:
    """把加工余量候选展开为当前工装尺寸，避免图纸和计算各自维护孔径。"""
    candidates = {row["id"]: row for row in fixture.get("machining_candidates", [])}
    selected = fixture.get("selected_machining_candidate")
    if not candidates or selected not in candidates:
        raise ValueError("加工余量候选或当前选择缺失")
    candidate = candidates[selected]
    resolved = dict(fixture)
    resolved["selected_candidate"] = selected
    resolved["pre_weld_bore_limits_mm"] = list(candidate["pre_weld_bore_limits_mm"])
    resolved["pre_weld_bore_diameter_mm"] = candidate["pre_weld_bore_limits_mm"][1]
    resolved["radial_machining_allowance_mm"] = candidate["nominal_radial_allowance_mm"]
    resolved["collapsed_sleeve_diameter_limits_mm"] = list(candidate["collapsed_sleeve_diameter_limits_mm"])
    resolved["maximum_sleeve_diameter_limits_mm"] = list(candidate["maximum_sleeve_diameter_limits_mm"])
    resolved["collapsed_sleeve_diameter_mm"] = candidate["collapsed_sleeve_diameter_limits_mm"][1]
    resolved["maximum_sleeve_diameter_mm"] = candidate["maximum_sleeve_diameter_limits_mm"][1]
    return resolved


def input_snapshot(root):
    spec = read_spec(root)
    load = yaml.safe_load((root/"project/load-basis-v1.yaml").read_text(encoding="utf-8"))
    paths = list(dict.fromkeys([SPEC, spec["precision"]["allocation_source"], spec["process_source"], spec["geometry_manifest"], "project/load-basis-v1.yaml",
                               "studies/TOOLING-ACCESS/config.yaml", *load["layouts"].values()]))
    return {"structured":{path:yaml.safe_load((root/path).read_text(encoding="utf-8")) for path in paths},
            "brep_sha256":{spec[key]:hashlib.sha256((root/spec[key]).read_bytes()).hexdigest() for key in ("seat_brep","shell_brep")}}


def current_assessment(root):
    result = json.loads((root/"studies/COMPETITION-DESIGN/results/assessment.json").read_text(encoding="utf-8"))
    if result.get("inputs") != input_snapshot(root):
        raise ValueError("参赛计算输入已变化，请先运行studies/COMPETITION-DESIGN/run.py")
    return result


def process_balance(spec, nominal):
    p = spec["process"]
    lo, hi = p["deposition_efficiency_range"]
    if not 0 < lo <= hi <= 1 or p["pass_count"] < 1:
        raise ValueError("沉积效率和道数非法")
    minimum_area = p["minimum_leg_mm"] ** 2 / 2
    feed = minimum_area * nominal["travel_speed_mm_s"] / (p["pass_count"] * lo * math.pi * p["wire_diameter_mm"] ** 2 / 4)
    maximum_leg = p["minimum_leg_mm"] * math.sqrt(hi / lo)
    if maximum_leg > p["clearance_leg_mm"]:
        raise ValueError("最大等效焊脚超出可达性包络")
    return {"eta_dep_range": [lo, hi], "eta_arc": nominal["arc_efficiency"],
            "fixed_feed_mm_s": feed, "minimum_area_mm2": minimum_area,
            "area_range_mm2": [minimum_area, minimum_area * hi / lo],
            "equivalent_leg_range_mm": [p["minimum_leg_mm"], maximum_leg],
            "gross_energy_per_pass_j_mm": nominal["current_a"] * nominal["voltage_v"] / nominal["travel_speed_mm_s"],
            "net_energy_per_pass_j_mm": nominal["current_a"] * nominal["voltage_v"] * nominal["arc_efficiency"] / nominal["travel_speed_mm_s"]}


def machining_allowance_screen(spec: dict) -> dict:
    """按预加工孔最大允许直径核对余量、装入和撑开端点。"""
    fixture = spec["fixture"]
    screen = fixture["machining_pressure_screen"]
    n = float(screen["segment_count"])
    sigma = float(screen["relative_asymmetry_sigma"])
    delta = float(screen["free_shrinkage_mm_per_segment"])
    angular_margin = float(screen["angular_margin_mm"])
    required = 1.25 * (2.0 * sigma * delta / math.sqrt(n)) + angular_margin
    final_min, final_max = map(float, fixture.get("final_bore_limits_mm", fixture["bore_limits_mm"]))
    cone_angle = math.radians(float(fixture["internal_cone_half_angle_deg"]))
    if cone_angle <= 0 or cone_angle >= math.pi / 2:
        raise ValueError("胀套锥角必须位于0～90°之间")
    return_stroke_available = float(fixture["positive_return_stroke_mm"])
    rows = []
    for candidate in fixture["machining_candidates"]:
        pre_min, pre_max = map(float, candidate["pre_weld_bore_limits_mm"])
        collapsed_min, collapsed_max = map(float, candidate["collapsed_sleeve_diameter_limits_mm"])
        expanded_min, expanded_max = map(float, candidate["maximum_sleeve_diameter_limits_mm"])
        geometric_min = (final_min - pre_max) / 2.0
        insertion_clearance = pre_min - collapsed_max
        contact_margin = expanded_min - pre_max
        return_stroke_required = (expanded_max - collapsed_min) / (2.0 * math.tan(cone_angle))
        tooling_checks = {
            "pre_bore_ordered": pre_min <= pre_max,
            "insertion_clearance_pass": insertion_clearance >= float(fixture["minimum_insertion_clearance_mm"]),
            "contact_reach_pass": contact_margin >= float(fixture["minimum_contact_interference_mm"]),
            "return_stroke_pass": return_stroke_available >= return_stroke_required,
        }
        dimension_endpoint_pass = all(tooling_checks.values())
        row = {
            "id": candidate["id"],
            "nominal_radial_allowance_mm": float(candidate["nominal_radial_allowance_mm"]),
            "pre_weld_bore_min_mm": pre_min,
            "pre_weld_bore_max_mm": pre_max,
            "final_bore_min_mm": final_min,
            "final_bore_max_mm": final_max,
            "geometric_min_radial_allowance_mm": geometric_min,
            "screen_margin_mm": geometric_min - required,
            "required_radial_allowance_mm": required,
            "insertion_clearance_min_mm": insertion_clearance,
            "contact_interference_min_mm": contact_margin,
            "return_stroke_required_mm": return_stroke_required,
            "return_stroke_available_mm": return_stroke_available,
            "tooling_checks": tooling_checks,
            "dimension_endpoint_pass": dimension_endpoint_pass,
            "tooling_chain_pass": None,
            "tooling_chain_status": "partial_pass_pending_geometry_envelope",
            "pending_checks": ["final_boring_envelope", "hole_wall_thinnest_section", "sleeve_elastic_repeatability"],
            "pressure_screen_pass": geometric_min + 1e-12 >= required,
        }
        row["pass"] = dimension_endpoint_pass and row["pressure_screen_pass"]
        rows.append(row)
    selected = next(row for row in rows if row["id"] == fixture["selected_candidate"])
    if not selected["pass"]:
        raise ValueError("当前加工余量候选未通过端点检查：" + json.dumps(selected, ensure_ascii=False))
    return {
        "formula": "A_geometric,min=(D_final,min-D_pre,max)/2; margin_screen=A_geometric,min-A_required",
        "pressure_scenario": {"n": n, "sigma": sigma, "delta_mm": delta, "angular_margin_mm": angular_margin},
        "required_radial_allowance_mm": required,
        "selected_candidate": fixture["selected_candidate"],
        "candidates": rows,
        "dimension_endpoint_status": "pass",
        "tooling_chain_status": "partial_pass_pending_geometry_envelope",
        "pending_checks": ["final_boring_envelope", "hole_wall_thinnest_section", "sleeve_elastic_repeatability"],
        "closure_status": "pressure_screen_closed_design_measurement_pending",
    }


def precision_budget(spec):
    f, p = spec["fixture"], spec["precision"]
    # 三个等角支点中任一点达到极差，平面最大斜率为2Δh/(3R)，孔两端按全长保守计。
    tilt = 2 * p["support_height_spread_limit_mm"] / (3 * f["support_radius_mm"])
    tilt_radial = p["bore_length_mm"] * tilt
    contributions = p["radial_allocations_mm"]
    if "thermal_residual_target" in contributions or "support_tilt" not in contributions:
        raise ValueError("位置度预算必须显式区分热残余加工余量，并在唯一配置中列出支点倾斜")
    if not math.isclose(contributions["support_tilt"], tilt_radial, abs_tol=1e-9):
        raise ValueError("project/tolerance.yaml 的支点倾斜分配与工装几何推导不一致")
    radial = sum(contributions.values())
    diameter = 2 * radial
    uncertainty = p["measurement_expanded_uncertainty_diameter_target_mm"]
    datum_chain_closes = diameter + uncertainty <= p["limit_diameter_mm"]
    end_to_end_closes = (datum_chain_closes
                         and p["thermal_residual_closure_status"] == "closed"
                         and p["measurement_uncertainty_verified"])
    return {"radial_contributions_mm": contributions, "radial_sum_mm": radial,
            "measurement_uncertainty_diameter_target_mm": uncertainty,
            "support_tilt_rad": tilt, "tilt_radial_allowance_mm": tilt_radial,
            "design_diameter_budget_mm": diameter,
            "diameter_with_uncertainty_target_mm": diameter + uncertainty,
            "datum_chain_arithmetic_closes": datum_chain_closes,
            "design_budget_closes": end_to_end_closes,
            "overall_closure_status": "closed" if end_to_end_closes else "not_closed_pending_weld_displacement_measurement_and_cmm_uncertainty",
            "thermal_residual_closure_status": p["thermal_residual_closure_status"],
            "measurement_uncertainty_verified": p["measurement_uncertainty_verified"],
            "thermal_residual_in_position_budget": False,
            "manufacturing_capability_verified": False, "thermal_residual_verified": False}


def cycle_permission(stage, *, shield_present, bottom_open, return_confirmed=False,
                     clamp_released=False, inspection_passed=False, measurement_diameter=None,
                     uncertainty_diameter=None, temperature_max=None, time_after_arc=None,
                     fixture_locked=False, path_checked=False, gas_flow_l_min=None,
                     temperature_min=None, boring_completed=None, cleanliness_passed=None,
                     weld_geometry_passed=None, machinability_limit_diameter=None,
                     strict_weld_geometry=False):
    """失败闭锁：信号缺失不允许开始焊接、下撤或合格出站。"""
    if stage == "weld":
        finite = all(v is not None and math.isfinite(v) for v in (temperature_min, temperature_max, gas_flow_l_min))
        return bool(finite and shield_present and bottom_open and fixture_locked and path_checked
                    and 130 <= temperature_min <= temperature_max < 200 and 8 <= gas_flow_l_min <= 12)
    if stage == "withdraw":
        finite = all(v is not None and math.isfinite(v) for v in (temperature_max, time_after_arc))
        return bool(finite and shield_present and bottom_open and return_confirmed and clamp_released
                    and temperature_max < 55 and time_after_arc >= 120)
    if stage == "accept":
        finite = all(v is not None and math.isfinite(v) and v >= 0 for v in (measurement_diameter, uncertainty_diameter))
        temperature_ok = temperature_max is not None and math.isfinite(temperature_max) and 19 <= temperature_max <= 21
        # 最终放行必须取得三道新增工序的明确结果；缺失信号保持待判，不兼容为通过。
        boring_ok = boring_completed is True
        clean_ok = cleanliness_passed is True
        weld_ok = weld_geometry_passed is True
        return bool(finite and temperature_ok and inspection_passed and clamp_released and return_confirmed
                    and boring_ok and clean_ok and weld_ok
                    and measurement_diameter + uncertainty_diameter <= .05)
    if stage == "weld_geometry":
        finite = all(v is not None and math.isfinite(v) and v >= 0 for v in (temperature_max, measurement_diameter, uncertainty_diameter))
        if strict_weld_geometry:
            geometry_limit = .05
        else:
            geometry_limit = machinability_limit_diameter
        limit_ok = geometry_limit is not None and math.isfinite(geometry_limit) and geometry_limit >= 0
        return bool(finite and limit_ok and temperature_max <= 55 and clamp_released and return_confirmed
                    and inspection_passed is True and weld_geometry_passed is True
                    and measurement_diameter + uncertainty_diameter <= geometry_limit)
    if stage == "final_boring":
        return bool(clamp_released and return_confirmed and weld_geometry_passed is True)
    if stage == "final_clean_check":
        return bool(boring_completed is True and cleanliness_passed is True)
    raise ValueError("未知工序")


def fuse(parts):
    result = parts[0]
    for part in parts[1:]:
        op = BRepAlgoAPI_Fuse(result, part)
        op.Build()
        if not op.IsDone():
            raise ValueError("工装实体合并失败")
        result = op.Shape()
    return result


def revolved_section(points):
    polygon = BRepBuilderAPI_MakePolygon()
    for r, z in points:
        polygon.Add(gp_Pnt(r, 0., z))
    polygon.Close()
    face = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    return BRepPrimAPI_MakeRevol(face, gp_Ax1(gp_Pnt(0., 0., 0.), gp_Dir(0., 0., 1.))).Shape()


def cut(base, tool):
    """用布尔差把配置孔径落实到座体实体；失败时禁止把名义尺寸当作几何结果。"""
    operation = BRepAlgoAPI_Cut(base, tool)
    operation.Build()
    if not operation.IsDone():
        raise ValueError("座体孔径布尔切除失败")
    return operation.Shape()


def bored_seat(base, *, seat_z: float, thickness_mm: float, original_bore_diameter_mm: float,
               target_bore_diameter_mm: float):
    """生成指定孔径状态的座体实体，原始 BREP 仅作为外形和焊缝界面来源。"""
    if not 0 < target_bore_diameter_mm <= original_bore_diameter_mm:
        raise ValueError("目标孔径必须不大于原始座体孔径")
    if math.isclose(target_bore_diameter_mm, original_bore_diameter_mm, abs_tol=1e-12):
        return base
    fill = cylinder(original_bore_diameter_mm / 2 + 0.02, seat_z, thickness_mm)
    filled = fuse([base, fill])
    bore = cylinder(target_bore_diameter_mm / 2, seat_z, thickness_mm)
    return cut(filled, bore)


def run_design(root):
    spec = read_spec(root)
    nominal = yaml.safe_load((root / spec["process_source"]).read_text(encoding="utf-8"))["process"]["nominal"]
    manifest = yaml.safe_load((root / spec["geometry_manifest"]).read_text(encoding="utf-8"))
    a, f, s, p = (spec[k] for k in ("assembly", "fixture", "shield", "process"))
    seat_z = a["seat_bottom_z_mm"]
    seat_top = seat_z + manifest["seat"]["thickness_mm"]
    shell_r = manifest["geometry"]["shell_inner_radius_mm"]
    if not math.isclose(s["installed_lip_radius_mm"], shell_r):
        raise ValueError("名义薄裙没有贴合壳体内壁，不能建立连续屏障")
    if s["lip_z_mm"] >= seat_z or f["support_top_z_mm"] != seat_z:
        raise ValueError("防护与支承轴向装配尺寸不闭合")
    shell = read_brep(root / spec["shell_brep"])
    seat_base = translated(read_brep(root / spec["seat_brep"]), seat_z)
    original_bore_diameter = float(manifest["seat"]["bore_nominal_diameter_mm"])
    final_bore_min = float(f["final_bore_limits_mm"][0])
    pre_bore_min, pre_bore_max = map(float, f["pre_weld_bore_limits_mm"])
    seat_final_bore = bored_seat(
        seat_base, seat_z=seat_z, thickness_mm=manifest["seat"]["thickness_mm"],
        original_bore_diameter_mm=original_bore_diameter, target_bore_diameter_mm=final_bore_min)
    # 焊接状态使用最不利的预加工孔上限；最小孔端点仍由筛查和装入间隙单独核对。
    seat_pre_weld = bored_seat(
        seat_base, seat_z=seat_z, thickness_mm=manifest["seat"]["thickness_mm"],
        original_bore_diameter_mm=original_bore_diameter, target_bore_diameter_mm=pre_bore_max)
    seat = seat_pre_weld
    floor = cylinder(s["rigid_radius_mm"], s["floor_z_mm"], s["floor_thickness_mm"])
    r0, r1, z0, z1, t = s["rigid_radius_mm"] - 2, s["installed_lip_radius_mm"], s["floor_z_mm"], s["lip_z_mm"], s["lip_thickness_mm"]
    lip = revolved_section([(r0, z0 + .5), (r1, z1), (r1, z1-t), (r0, z0+.5-t)])
    low, high = f["carrier_disk_z_mm"]
    support = [cylinder(f["carrier_post_radius_mm"], f["carrier_post_bottom_z_mm"], low-f["carrier_post_bottom_z_mm"]),
               cylinder(f["carrier_disk_radius_mm"], low, high-low)]
    for i in range(f["support_count"]):
        angle = 2 * math.pi * i / f["support_count"]
        axis = gp_Ax2(gp_Pnt(f["support_radius_mm"] * math.cos(angle), f["support_radius_mm"] * math.sin(angle), high), gp_Dir(0., 0., 1.))
        support.append(BRepPrimAPI_MakeCylinder(axis, f["support_pad_radius_mm"], seat_z-high).Shape())
    cartridge = fuse([floor, lip] + support)
    # 上部实体为独立压环的保守外包络；胀套三种状态单独建模并检查，不再用Ø40包络替代。
    upper = cylinder(f["upper_envelope_radius_mm"], seat_top, f["upper_envelope_top_z_mm"]-seat_top)
    sleeve_z = seat_z + 1
    sleeve_height = seat_top - seat_z - 2
    collapsed_sleeve = cylinder(f["collapsed_sleeve_diameter_limits_mm"][1] / 2, sleeve_z, sleeve_height)
    contact_sleeve = cylinder(f["maximum_sleeve_diameter_limits_mm"][0] / 2, sleeve_z, sleeve_height)
    maximum_sleeve = cylinder(f["maximum_sleeve_diameter_limits_mm"][1] / 2, sleeve_z, sleeve_height)
    weld = make_weld_envelope(shell_r, p["clearance_leg_mm"], seat_top)
    torch_spec = yaml.safe_load((root / "studies/TOOLING-ACCESS/config.yaml").read_text(encoding="utf-8"))["torch"]
    target = (shell_r-p["clearance_leg_mm"]/2, seat_top+p["clearance_leg_mm"]/2)
    torch, bounds, points = make_torch(torch_spec, nominal, target, 30., True)
    # 棒材从上方斜向送进，和焊枪错开周向；模型包含管口至壳体上方的直线包络。
    direction = (-.2, -.35, math.sqrt(1-.2**2-.35**2))
    offset = p["wire_entry_offset_xyz_mm"]
    def feed_point(distance):
        return gp_Pnt(target[0]+offset[0]+direction[0]*distance, offset[1]+direction[1]*distance, target[1]+offset[2]+direction[2]*distance)
    feed_axis = lambda distance: gp_Ax2(feed_point(distance), gp_Dir(*direction))
    guide_end = (220-target[1])/direction[2]
    wire = BRepPrimAPI_MakeCylinder(feed_axis(.5), p["wire_diameter_mm"]/2, 14.5).Shape()
    guide = BRepPrimAPI_MakeCylinder(feed_axis(15.), 2., guide_end-15.).Shape()
    feed = fuse([wire, guide])
    obstacles = {"shell": shell, "seat": seat, "upper_fixture": upper, "weld_keepout": weld}
    tools = {"torch": torch, "wire_guide": feed}
    poses = []
    for lift in (0., 40., 120.):
        for name, tool in tools.items():
            moved = translated(tool, lift)
            intersections = {key: common_volume(moved, shape) for key, shape in obstacles.items()}
            poses.append({"tool": name, "lift_mm": lift, "intersections_mm3": intersections,
                          "clear": max(intersections.values()) < 1e-6})
    # 工装只下移，所有支承已在座体底面以下；R75圆柱包络给出连续路径充分条件。
    sweep = cylinder(shell_r, -a["bottom_clearance_mm"]-30, seat_z+a["bottom_clearance_mm"]+30)
    sweep_intersections = {"shell": common_volume(sweep, shell), "seat": common_volume(sweep, seat)}
    insertion_overlap = common_volume(collapsed_sleeve, seat_pre_weld)
    contact_overlap = common_volume(contact_sleeve, seat_pre_weld)
    maximum_overlap = common_volume(maximum_sleeve, seat_pre_weld)
    balance = process_balance(spec, nominal)
    length = manifest["manufacturing"]["cad_measured_total_weld_length_mm"]
    balance.update({"weld_length_mm": length, "arc_on_time_s": length / nominal["travel_speed_mm_s"] * p["pass_count"],
                    "total_net_heat_j": balance["net_energy_per_pass_j_mm"] * length * p["pass_count"],
                    "wire_length_mm": balance["fixed_feed_mm_s"] * length / nominal["travel_speed_mm_s"] * p["pass_count"],
                    "deposited_volume_range_mm3": [v*length for v in balance["area_range_mm2"]]})
    load = yaml.safe_load((root/"project/load-basis-v1.yaml").read_text(encoding="utf-8"))
    strength = evaluate_layout(manifest, [p["minimum_leg_mm"]], load["reference_envelope"], load["effective_throat_factor"])
    comparison = []
    for name, path in load["layouts"].items():
        m = yaml.safe_load((root/path).read_text(encoding="utf-8"))
        row = evaluate_layout(m, [p["minimum_leg_mm"]], load["reference_envelope"], load["effective_throat_factor"])
        length_i = row["effective_weld_length_mm"]
        comparison.append({"layout":name,"net_heat_kj":length_i*balance["net_energy_per_pass_j_mm"]*p["pass_count"]/1000,
                           "arc_time_s":length_i/nominal["travel_speed_mm_s"]*p["pass_count"],
                           "required_allowable_mpa":row["rows"][0]["reference_envelope_corner_required_allowable_mpa"]})
    angle = math.radians(f["internal_cone_half_angle_deg"])
    stroke_needed = (f["maximum_sleeve_diameter_mm"]-f["collapsed_sleeve_diameter_mm"]) / (2*math.tan(angle))
    forces = [{"mu": mu, "drive_force_for_radial_limit_n": f["radial_force_limit_n"] * (math.sin(angle)+mu*math.cos(angle))/(math.cos(angle)-mu*math.sin(angle)),
               "self_lock_possible": mu >= math.tan(angle)} for mu in f["friction_scenarios"]]
    contact_diameter_limits = [pre_bore_min, pre_bore_max]
    contact_band_length = sum(hi-lo for lo,hi in f["contact_bands_z_mm"])
    contact_area_limits = [math.pi * diameter * contact_band_length * f["contact_coverage_fraction"]
                           for diameter in contact_diameter_limits]
    contact_pressure_range = [f["radial_force_limit_n"] / max(contact_area_limits),
                              f["radial_force_limit_n"] / min(contact_area_limits)]
    area = math.pi * f["pre_weld_bore_diameter_mm"] * contact_band_length * f["contact_coverage_fraction"]
    machining = machining_allowance_screen(spec)
    fixture_states = {
        "seat_pre_weld_bore_limits_mm": [pre_bore_min, pre_bore_max],
        "seat_final_bore_limits_mm": list(f["final_bore_limits_mm"]),
        "sleeve_collapsed_diameter_mm": f["collapsed_sleeve_diameter_limits_mm"][1],
        "sleeve_contact_diameter_mm": f["maximum_sleeve_diameter_limits_mm"][0],
        "sleeve_maximum_diameter_mm": f["maximum_sleeve_diameter_limits_mm"][1],
        "insertion_overlap_mm3": insertion_overlap,
        "contact_overlap_mm3": contact_overlap,
        "maximum_overlap_mm3": maximum_overlap,
        "insertion_geometry_clear": insertion_overlap < 1e-6,
        "contact_geometry_reached": contact_overlap > 1e-6,
        "return_stroke_pass": next(row for row in machining["candidates"] if row["id"] == f["selected_candidate"])["tooling_checks"]["return_stroke_pass"],
        "final_boring_envelope_status": "pending",
        "hole_wall_thinnest_section_status": "pending",
        "sleeve_elastic_repeatability_status": "pending",
        "status": "dimension_endpoint_pass_with_pending_geometry_envelope",
    }
    result = {"version":spec["version"], "evidence_level":"design_assumption_with_geometry_checks", "spec":spec, "inputs":input_snapshot(root),
              "four_pass_comparison":comparison,
              "process": balance, "precision": precision_budget(spec),
              "machining_allowance": machining,
              "conditional_strength": strength,
              "fixture": {"positive_return_stroke_required_mm":stroke_needed, "positive_return_stroke_available_mm":f["positive_return_stroke_mm"],
                          "contact_diameter_limits_mm":contact_diameter_limits,
                          "nominal_average_band_pressure_mpa":f["radial_force_limit_n"]/area,
                          "average_band_pressure_mpa_range":contact_pressure_range,
                          "cone_force_scenarios":forces,
                          "pressure_is_not_peak_contact_stress":True},
              "geometry": {"shape_validity":{k:BRepCheck_Analyzer(v).IsValid() for k,v in {**obstacles,**tools,"cartridge":cartridge,
                                                                                                    "seat_final_bore":seat_final_bore,
                                                                                                    "seat_pre_weld":seat_pre_weld,
                                                                                                    "sleeve_collapsed":collapsed_sleeve,
                                                                                                    "sleeve_contact":contact_sleeve,
                                                                                                    "sleeve_maximum":maximum_sleeve}.items()},
                           "fixture_states": fixture_states,
                           "seat_state_volumes_mm3": {"pre_weld": volume(seat_pre_weld), "final_bore": volume(seat_final_bore)},
                           "cartridge_intersections_mm3":{k:common_volume(cartridge,v) for k,v in {"shell":shell,"seat":seat,"upper_fixture":upper}.items()},
                           "bottom_sweep_intersections_mm3":sweep_intersections,
                           "bottom_route_allowed":a["bottom_open"] and max(sweep_intersections.values()) < 1e-6,
                           "poses":poses, "torch_feed_intersection_mm3":common_volume(torch, feed),
                           "torch_feed_clearance_mm":clearance(torch,feed), "torch_shell_radial_bound_mm":shell_r-bounds["radial_upper_bound_mm"],
                           "torch_upper_radial_bound_mm":bounds["radial_lower_bound_mm"]-f["upper_envelope_radius_mm"],
                           "nominal_vertical_drop_coverage":s["installed_lip_radius_mm"]>=shell_r,
                           "coverage_requires_continuous_wall_contact":True},
              "release":{"physical_position_verified":False,"physical_cleanliness_verified":False,
                         "formal_thermal_structural_allowed":False,"manufacturing_released":False}}
    bodies = {**obstacles,**tools,"cartridge":cartridge,
              "seat_pre_weld": seat_pre_weld, "seat_final_bore": seat_final_bore,
              "sleeve_collapsed": collapsed_sleeve, "sleeve_contact": contact_sleeve,
              "sleeve_maximum": maximum_sleeve}
    return result, bodies, points
