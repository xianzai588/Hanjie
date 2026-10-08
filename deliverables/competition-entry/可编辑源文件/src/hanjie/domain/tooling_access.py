"""工装包络检查和锥面载荷分析；物理质量结论保持未验证。"""

from __future__ import annotations

import math
from pathlib import Path

import yaml
from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeRevol, BRepPrimAPI_MakeSphere
from OCP.BRepTools import BRepTools
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.TopoDS import TopoDS_Shape


SPEC = "studies/TOOLING-ACCESS/config.yaml"


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def read_brep(path: Path):
    shape = TopoDS_Shape()
    if not BRepTools.Read_s(shape, str(path), BRep_Builder()):
        raise ValueError(f"不能读取实体：{path}")
    if not BRepCheck_Analyzer(shape).IsValid():
        raise ValueError(f"实体无效：{path}")
    return shape


def volume(shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def common_volume(a, b) -> float:
    operation = BRepAlgoAPI_Common(a, b)
    operation.Build()
    if not operation.IsDone():
        raise ValueError("布尔求交失败，不可按零干涉处理")
    return max(0., volume(operation.Shape()))


def clearance(a, b) -> float:
    check = BRepExtrema_DistShapeShape(a, b)
    check.Perform()
    if not check.IsDone():
        raise ValueError("实体距离计算失败")
    return float(check.Value())


def translated(shape, z: float):
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(0., 0., z))
    return BRepBuilderAPI_Transform(shape, transform, True).Shape()


def cylinder(radius: float, z: float, height: float, x: float = 0.):
    if radius <= 0 or height <= 0:
        raise ValueError("圆柱尺寸必须为正")
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, 0., z), gp_Dir(0., 0., 1.)), radius, height).Shape()


def make_shield(spec: dict, seat_z: float):
    radius, floor = spec["outer_radius_mm"], spec["floor_thickness_mm"]
    height, wall = spec["rim_height_mm"], spec["rim_thickness_mm"]
    if not 0 < floor < height or not 0 < wall < radius:
        raise ValueError("截留盘壁厚或高度非法")
    z = seat_z - spec["top_to_seat_bottom_gap_mm"] - height
    outer = cylinder(radius, z, height)
    inner = cylinder(radius - wall, z + floor, height)
    return BRepAlgoAPI_Cut(outer, inner).Shape(), z


def make_weld_envelope(radius: float, leg: float, seat_top: float):
    # 整圈三角角焊缝包络包含离散焊段，用作可达性障碍，不导出成形或热学结果。
    polygon = BRepBuilderAPI_MakePolygon()
    for point in ((radius - leg, 0., seat_top), (radius, 0., seat_top), (radius, 0., seat_top + leg)):
        polygon.Add(gp_Pnt(*point))
    polygon.Close()
    face = BRepBuilderAPI_MakeFace(polygon.Wire()).Face()
    return BRepPrimAPI_MakeRevol(face, gp_Ax1(gp_Pnt(0., 0., 0.), gp_Dir(0., 0., 1.))).Shape()


def cone_force_balance(small_diameter: float, large_diameter: float, length: float,
                       axial_force: float, friction: float) -> dict:
    if not all(math.isfinite(v) for v in (small_diameter, large_diameter, length, axial_force, friction)):
        raise ValueError("锥面参数必须有限")
    if not 0 < small_diameter < large_diameter or length <= 0 or axial_force <= 0 or friction < 0:
        raise ValueError("锥面尺寸、载荷或摩擦系数非法")
    tangent = (large_diameter - small_diameter) / (2 * length)
    angle = math.atan(tangent)
    normal = axial_force / (math.sin(angle) + friction * math.cos(angle))
    radial_scalar = normal * (math.cos(angle) - friction * math.sin(angle))
    return {
        "friction_coefficient": friction,
        "half_angle_deg": math.degrees(angle),
        "self_lock_threshold_mu": tangent,
        "normal_force_scalar_sum_n": normal,
        "radial_compression_scalar_sum_n": radial_scalar,
        "self_lock_possible": friction >= tangent or math.isclose(friction, tangent, rel_tol=1e-12),
        "net_radial_vector_for_axisymmetry_n": 0.,
        "axial_force_balance_n": normal * (math.sin(angle) + friction * math.cos(angle)),
        "contact_pressure_mpa": None,
    }


def make_torch(spec: dict, process: dict, target: tuple[float, float], tilt: float, bent: bool):
    angle = math.radians(tilt)
    direction = (-math.sin(angle), 0., math.cos(angle))
    origin = (target[0], 0., target[1])

    def point(distance):
        return tuple(origin[i] + direction[i] * distance for i in range(3))

    standoff = process["standoff_distance_mm"]
    face_distance = standoff + spec["exposed_tungsten_length_mm"]
    end_distance = face_distance + spec["nozzle_length_mm"]
    tip, face, end = point(standoff), point(face_distance), point(end_distance)
    nozzle_r = process["nozzle_diameter_mm"] / 2
    tungsten_r, body_r = spec["tungsten_radius_mm"], spec["body_radius_mm"]
    parts = [
        BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*tip), gp_Dir(*direction)), tungsten_r, spec["exposed_tungsten_length_mm"]).Shape(),
        BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*face), gp_Dir(*direction)), nozzle_r, spec["nozzle_length_mm"]).Shape(),
    ]
    if bent:
        parts += [BRepPrimAPI_MakeSphere(gp_Pnt(*end), body_r).Shape(),
                  cylinder(body_r, end[2], spec["body_top_z_mm"] - end[2], end[0])]
    else:
        length = (spec["body_top_z_mm"] - end[2]) / direction[2]
        parts.append(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*end), gp_Dir(*direction)), body_r, length).Shape())
    shape = parts[0]
    for part in parts[1:]:
        operation = BRepAlgoAPI_Fuse(shape, part)
        operation.Build()
        if not operation.IsDone():
            raise ValueError("焊枪包络布尔运算失败")
        shape = operation.Shape()
    # 对弯头方案给出整个竖直提升路径的保守径向包络；不是只采样若干姿态。
    certificate = None
    if bent:
        extents = [
            (tip[0] + tungsten_r, face[0] - tungsten_r, tip[2] - tungsten_r),
            (face[0] + nozzle_r, end[0] - nozzle_r, face[2] - nozzle_r),
            (end[0] + body_r, end[0] - body_r, end[2] - body_r),
        ]
        certificate = {
            "radial_upper_bound_mm": max(row[0] for row in extents),
            "radial_lower_bound_mm": min(row[1] for row in extents),
            "z_lower_bound_mm": min(row[2] for row in extents),
            "min_z_minus_radial_upper_mm": min(row[2] - row[0] for row in extents),
        }
    return shape, certificate, {"tip": tip, "face": face, "end": end}


def run_tooling_study(root: Path):
    config = read_yaml(root / SPEC)
    geometry = read_yaml(root / config["sources"]["geometry"])
    process = read_yaml(root / config["sources"]["process"])["process"]["nominal"]
    layout_paths = read_yaml(root / config["sources"]["load_basis"])["layouts"]
    design, official = geometry["design_assumptions"], geometry["official"]
    shell = read_brep(root / config["sources"]["shell_brep"])
    shell_r = official["shell_outer_diameter"] / 2 - official["shell_thickness"]
    shell_h = official["shell_height"]
    seat_z = config["assembly"]["seat_bottom_z_mm"]
    seat_top = seat_z + design["seat_thickness"]
    shield, shield_z = make_shield(config["shield"], seat_z)
    shield_r = config["shield"]["outer_radius_mm"]
    shield_top = shield_z + config["shield"]["rim_height_mm"]
    tol = config["checks"]["boolean_volume_tolerance_mm3"]
    # 托盘底板为实心圆盘，足够长的轴向平移扫掠体是精确圆柱；上撤作为失败对照。
    below = config["shield"]["extraction_below_shell_mm"]
    bottom_sweep = cylinder(shield_r, -below - config["shield"]["rim_height_mm"],
                            shield_top + below + config["shield"]["rim_height_mm"])
    top_sweep = cylinder(shield_r, shield_z, shell_h + below - shield_z)
    bodies = {"shell": shell, "shield": shield}
    shield_cases = []
    for name, path in layout_paths.items():
        manifest = read_yaml(root / path)
        brep = Path(path).parent / Path(manifest["generation"]["brep_file"]).name
        seat = translated(read_brep(root / brep), seat_z)
        bodies[name] = seat
        for route, swept in (("bottom", bottom_sweep), ("top", top_sweep)):
            seat_overlap = common_volume(swept, seat)
            shell_overlap = common_volume(swept, shell)
            passes = max(seat_overlap, shell_overlap) <= tol
            shield_cases.append({
                "layout": name, "route": route,
                "seat_intersection_volume_mm3": seat_overlap,
                "shell_intersection_volume_mm3": shell_overlap,
                "swept_body_geometry_clear": passes,
                "process_route_admissible": passes and (route != "bottom" or config["assembly"]["bottom_access_open"]),
                "coverage": "所列壳体和座体；未包含支承、机器人及管线",
            })
    bore_r = official["bearing_bore_diameter"] / 2
    mandrel_r = design["mandrel_large_diameter"] / 2
    upper_top = config["mandrel"]["upper_obstruction_top_z_mm"]
    upper_mandrel = cylinder(mandrel_r, seat_top, upper_top - seat_top)
    bodies["upper_mandrel_envelope"] = upper_mandrel
    weld = make_weld_envelope(shell_r, design["fillet_leg_length"], seat_top)
    bodies["weld_keepout"] = weld
    target = (shell_r - design["fillet_leg_length"] / 2, seat_top + design["fillet_leg_length"] / 2)
    torch_cases = []
    for tilt in config["torch"]["tilt_from_vertical_deg"]:
        for bent in (False, True):
            shape, bounds, points = make_torch(config["torch"], process, target, tilt, bent)
            obstacles = {"shell": shell, "upper_mandrel": upper_mandrel, "weld_keepout": weld,
                         "continuous_seat": bodies["Continuous"]}
            poses = []
            for lift in config["checks"]["pose_lifts_mm"]:
                tool = translated(shape, lift)
                intersections = {name: common_volume(tool, obstacle) for name, obstacle in obstacles.items()}
                poses.append({"lift_mm": lift, "intersections_mm3": intersections,
                              "geometry_clear": max(intersections.values()) <= tol})
            certificate = None
            if bounds:
                shell_gap = shell_r - bounds["radial_upper_bound_mm"]
                mandrel_gap = bounds["radial_lower_bound_mm"] - mandrel_r
                # 三角焊缝上表面 z=r+seat_top+leg-shell_r；竖直上移只会增大此间距。
                weld_gap = bounds["min_z_minus_radial_upper_mm"] - (seat_top + design["fillet_leg_length"] - shell_r)
                seat_gap = bounds["z_lower_bound_mm"] - seat_top
                requirement = config["torch"]["radial_clearance_requirement_mm"]
                certificate = {**bounds, "shell_gap_lower_bound_mm": shell_gap,
                               "mandrel_gap_lower_bound_mm": mandrel_gap,
                               "weld_halfplane_margin_mm": weld_gap,
                               "seat_z_gap_lower_bound_mm": seat_gap,
                               "continuous_vertical_lift_clear": min(shell_gap, mandrel_gap) >= requirement and min(weld_gap, seat_gap) > 0,
                               "applies_to_all_circumferential_angles": True,
                               "scope": "竖直提升/下降与列明轴对称包络；不包括机器人运动学或管线"}
            torch_cases.append({"tilt_deg": tilt, "body_style": "bent_vertical" if bent else "straight",
                                "poses": poses, "vertical_path_certificate": certificate,
                                "nominal_shell_clearance_mm": clearance(shape, shell),
                                "nominal_mandrel_clearance_mm": clearance(shape, upper_mandrel),
                                "sampled_poses_clear": all(pose["geometry_clear"] for pose in poses)})
            if bent and tilt == config["torch"]["export_tilt_deg"]:
                bodies["torch_envelope"] = shape
                bodies["torch_points"] = points
    small, large, length = design["mandrel_small_diameter"], design["mandrel_large_diameter"], design["mandrel_effective_length"]
    taper = (large - small) / length
    if not math.isclose(taper, design["mandrel_taper_ratio"], abs_tol=1e-12):
        raise ValueError("锥形心轴尺寸与声明锥度不一致")
    cone = BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(0., 0., seat_top - length), gp_Dir(0., 0., 1.)), small / 2, large / 2, length).Shape()
    naive_overlap = common_volume(cone, bodies["Continuous"])
    cone_shift = (large - 2 * bore_r) / taper
    seated_cone = translated(cone, cone_shift)
    seated_overlap = common_volume(seated_cone, bodies["Continuous"])
    forces = [cone_force_balance(small, large, length, design["axial_clamping_force"], mu)
              for mu in config["mandrel"]["friction_coefficients"]]
    result = {
        "stage": "TOOLING-ACCESS", "evidence_level": "design_assumption_with_occ_geometry_checks",
        "input_config": SPEC, "config": config,
        "assembly": {"seat_bottom_z_mm": seat_z, "seat_top_z_mm": seat_top, "shell_inner_radius_mm": shell_r,
                     "shield_floor_z_mm": shield_z, "shield_top_z_mm": shield_top, "weld_target_rz_mm": target},
        "shape_validity": {name: BRepCheck_Analyzer(shape).IsValid() for name, shape in bodies.items() if name != "torch_points"},
        "shield": {"cases": shield_cases, "nominal_shell_clearance_mm": clearance(shield, shell),
                   "vertical_drop_at_interface_radius_mm": design["wing_outer_radius"],
                   "capture_outer_radius_mm": shield_r,
                   "vertical_drop_at_interface_captured": design["wing_outer_radius"] <= shield_r,
                   "uncaptured_radial_band_to_shell_mm": shell_r - shield_r,
                   "cleanliness_validated": False,
                   "decision": "整块刚性盘只保留底口退出情景；上撤穿过已焊座体被排除。周边间隙仍漏接垂直落物，需另设计可收拢挡边或源头封挡，不能宣称洁净达标"},
        "torch": {"cases": torch_cases, "full_system_access_validated": False},
        "mandrel": {"naive_full_length_insertion_overlap_mm3": naive_overlap,
                    "rigid_seating_shift_mm": cone_shift,
                    "seated_cone_overlap_mm3": seated_overlap,
                    "nominal_contact_z_mm": seat_top,
                    "nominal_contact_type": "圆柱孔上缘圆周线接触；不是全长锥面贴合",
                    "force_scenarios": forces,
                    "repeatability_validated": False,
                    "decision": "保留为待设计定位元件；需独立轴向/倾斜约束和主动退锥机构，不能默认全孔固定边界或自动松脱"},
        "release": {"product_position_acceptance_claim_allowed": False, "cleanliness_validated": False,
                    "fixture_manufacturing_released": False, "formal_struct_0_allowed": False},
    }
    return result, bodies
