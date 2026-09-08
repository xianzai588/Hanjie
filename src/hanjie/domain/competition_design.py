"""参赛修订方案的守恒核算、工装几何与工序互锁；不输出实物合格结论。"""
from __future__ import annotations

import math
import hashlib
import json
from pathlib import Path
import yaml
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeRevol
from OCP.gp import gp_Ax1, gp_Ax2, gp_Pnt, gp_Dir
from hanjie.domain.tooling_access import (read_brep, translated, cylinder, common_volume,
    clearance, make_weld_envelope, make_torch)
from hanjie.domain.joint_load import evaluate_layout

SPEC = "project/competition-design.yaml"


def read_spec(root: Path):
    return yaml.safe_load((root / SPEC).read_text(encoding="utf-8"))


def input_snapshot(root):
    spec = read_spec(root)
    load = yaml.safe_load((root/"project/load-basis-v1.yaml").read_text(encoding="utf-8"))
    paths = list(dict.fromkeys([SPEC, spec["process_source"], spec["geometry_manifest"], "project/load-basis-v1.yaml",
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
    return {"fixed_feed_mm_s": feed, "minimum_area_mm2": minimum_area,
            "area_range_mm2": [minimum_area, minimum_area * hi / lo],
            "equivalent_leg_range_mm": [p["minimum_leg_mm"], maximum_leg],
            "gross_energy_per_pass_j_mm": nominal["current_a"] * nominal["voltage_v"] / nominal["travel_speed_mm_s"],
            "net_energy_per_pass_j_mm": nominal["current_a"] * nominal["voltage_v"] * nominal["arc_efficiency"] / nominal["travel_speed_mm_s"]}


def precision_budget(spec):
    f, p = spec["fixture"], spec["precision"]
    # 三个等角支点中任一点达到极差，平面最大斜率为2Δh/(3R)，孔两端按全长保守计。
    tilt = 2 * p["support_height_spread_limit_mm"] / (3 * f["support_radius_mm"])
    tilt_radial = p["bore_length_mm"] * tilt
    radial = sum(p["radial_allocations_mm"].values()) + tilt_radial
    diameter = 2 * radial
    uncertainty = p["measurement_expanded_uncertainty_diameter_target_mm"]
    return {"support_tilt_rad": tilt, "tilt_radial_allowance_mm": tilt_radial,
            "design_diameter_budget_mm": diameter,
            "diameter_with_uncertainty_target_mm": diameter + uncertainty,
            "design_budget_closes": diameter + uncertainty <= p["limit_diameter_mm"],
            "manufacturing_capability_verified": False, "thermal_residual_verified": False}


def cycle_permission(stage, *, shield_present, bottom_open, return_confirmed=False,
                     clamp_released=False, inspection_passed=False, measurement_diameter=None,
                     uncertainty_diameter=None, temperature_max=None, time_after_arc=None,
                     fixture_locked=False, path_checked=False, gas_flow_l_min=None,
                     temperature_min=None):
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
        return bool(finite and temperature_ok and inspection_passed and clamp_released and return_confirmed
                    and measurement_diameter + uncertainty_diameter <= .05)
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
    shell, seat = read_brep(root / spec["shell_brep"]), translated(read_brep(root / spec["seat_brep"]), seat_z)
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
    # 上部实体为胀套和独立压环的保守外包络；内部驱动锥不再直接与工件孔接触。
    upper = cylinder(f["upper_envelope_radius_mm"], seat_top, f["upper_envelope_top_z_mm"]-seat_top)
    sleeve = cylinder(20., seat_z+1, seat_top-seat_z-2)
    upper = fuse([upper, sleeve])
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
    area = math.pi * 40 * sum(hi-lo for lo,hi in f["contact_bands_z_mm"]) * f["contact_coverage_fraction"]
    result = {"version":spec["version"], "evidence_level":"design_assumption_with_geometry_checks", "spec":spec, "inputs":input_snapshot(root),
              "four_pass_comparison":comparison,
              "process": balance, "precision": precision_budget(spec), "conditional_strength": strength,
              "fixture": {"positive_return_stroke_required_mm":stroke_needed, "positive_return_stroke_available_mm":f["positive_return_stroke_mm"],
                          "nominal_average_band_pressure_mpa":f["radial_force_limit_n"]/area, "cone_force_scenarios":forces,
                          "pressure_is_not_peak_contact_stress":True},
              "geometry": {"shape_validity":{k:BRepCheck_Analyzer(v).IsValid() for k,v in {**obstacles,**tools,"cartridge":cartridge}.items()},
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
    bodies = {**obstacles,**tools,"cartridge":cartridge}
    return result, bodies, points
