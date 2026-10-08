"""参赛候选方案的守恒核算、工装名义几何与工序互锁。"""
from __future__ import annotations

import math
import hashlib
import json
from pathlib import Path
import yaml
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeRevol, BRepPrimAPI_MakeBox
from OCP.gp import gp_Ax1, gp_Ax2, gp_Pnt, gp_Dir, gp_Trsf, gp_Vec
from hanjie.domain.tooling_access import (read_brep, translated, cylinder, common_volume,
    clearance, make_weld_envelope, make_torch)
from hanjie.domain.joint_load import evaluate_layout

SPEC = "project/competition-design.yaml"


def read_spec(root: Path):
    return yaml.safe_load((root / SPEC).read_text(encoding="utf-8"))


def input_snapshot(root):
    spec = read_spec(root)
    load = yaml.safe_load((root/"project/load-basis-v1.yaml").read_text(encoding="utf-8"))
    paths = list(dict.fromkeys([SPEC, spec["process_source"], "project/materials.yaml", spec["geometry_manifest"], "project/load-basis-v1.yaml",
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
    feed = p.get('feed_nominal_mm_s', minimum_area * nominal["travel_speed_mm_s"] / (p["pass_count"] * lo * math.pi * p["wire_diameter_mm"] ** 2 / 4))
    ferr=p.get('feed_tolerance_mm_s',0);derr=p.get('wire_diameter_tolerance_mm',0);verr=p.get('travel_relative_tolerance',0)
    minarea=p['pass_count']*lo*math.pi*(p['wire_diameter_mm']-derr)**2/4*(feed-ferr)/(nominal['travel_speed_mm_s']*(1+verr))
    maxarea=p['pass_count']*hi*math.pi*(p['wire_diameter_mm']+derr)**2/4*(feed+ferr)/(nominal['travel_speed_mm_s']*(1-verr))
    maximum_leg=math.sqrt(2*maxarea)
    if math.sqrt(2*minarea)<p['minimum_leg_mm']:raise ValueError('鲁棒送丝下限不足')
    if maximum_leg > p["clearance_leg_mm"]:
        raise ValueError("最大等效焊脚超出可达性包络")
    return {"fixed_feed_mm_s": feed, "minimum_area_mm2": minimum_area,
            "area_range_mm2": [minarea,maxarea],
            "equivalent_leg_range_mm": [math.sqrt(2*minarea), maximum_leg],
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
    honing = p['honing_axis_allocation_diameter_mm']
    nonthermal = diameter-2*p['radial_allocations_mm']['thermal_residual_target']
    return {"support_tilt_rad": tilt, "tilt_radial_allowance_mm": tilt_radial,
            "design_diameter_budget_mm": diameter,
            "diameter_with_uncertainty_target_mm": diameter + uncertainty,
            "honing_axis_allocation_diameter_mm":honing,
            "diameter_with_honing_and_uncertainty_target_mm":diameter+uncertainty+honing,
            "thermal_diameter_allowance_with_honing_mm":p['limit_diameter_mm']-nonthermal-uncertainty-honing,
            "thermal_diameter_allowance_without_removal_mm":p['limit_diameter_mm']-nonthermal-uncertainty,
            "design_budget_closes": diameter + uncertainty + honing <= p["limit_diameter_mm"],
            "thermal_residual_design_verified": False, "physical_validation_recommended": True}


def cycle_permission(stage, *, shield_present, bottom_open, return_confirmed=False,
                     clamp_released=False, inspection_passed=False, measurement_diameter=None,
                     uncertainty_diameter=None, temperature_max=None, time_after_arc=None,
                     fixture_locked=False, path_checked=False, gas_flow_l_min=None,
                     temperature_min=None, curtain_flow_l_min=None, curtain_manifold_pressure_pa=None,
                     copper_temperature_c=None, lower_ring_temperature_c=None, seal_band_temperature_c=None, coolant_flow_l_min=None, water_leak_free=None,
                     energy_in_range=None, guard_closed=None, seal_retracted=None,
                     simultaneous_heads=1, head_gas_flows_l_min=None,
                     head_energy_in_range=None, head_path_checked=None,
                     shell_base_released=False, coolant_branch_flows_l_min=None,
                     bore_diameter_min_mm=None, bore_diameter_max_mm=None,
                     bore_uncertainty_mm=None, bore_temperature_c=None,
                     finish_applied=False, pre_finish_position_mm=None,
                     finish_radial_stock_mm=None, upper_stop_open=False, upper_lift_mm=None,
                     datum_holder_locked=False, transfer_support_locked=None, nest_lock_released=False):
    """失败闭锁：信号缺失不允许焊接、壳体上提或合格出站。"""
    if stage in {"weld", "first_weld"}:
        flow_values = (temperature_min, temperature_max, gas_flow_l_min,curtain_flow_l_min,
                       curtain_manifold_pressure_pa, copper_temperature_c, lower_ring_temperature_c, seal_band_temperature_c, coolant_flow_l_min)
        finite = all(v is not None and math.isfinite(v) for v in flow_values)
        curtain_ok = curtain_flow_l_min is not None and math.isfinite(curtain_flow_l_min) and 10 <= curtain_flow_l_min <= 15
        limit = 35 if stage == "first_weld" else 100
        branches_ok = (isinstance(coolant_branch_flows_l_min,(tuple,list))
                       and len(coolant_branch_flows_l_min)==8)
        if branches_ok:
            branches_ok = all(v is not None and math.isfinite(v) and .075 <= v <= .07875
                              for v in coolant_branch_flows_l_min)
        head_ok = simultaneous_heads == 1
        if simultaneous_heads == 2:
            signals = (head_gas_flows_l_min, head_energy_in_range, head_path_checked)
            head_ok = all(isinstance(v, (tuple, list)) and len(v) == 2 for v in signals)
            if head_ok:
                head_ok = (all(v is not None and math.isfinite(v) and 8 <= v <= 12
                               for v in head_gas_flows_l_min)
                           and all(v is True for v in head_energy_in_range)
                           and all(v is True for v in head_path_checked))
        return bool(finite and branches_ok and head_ok and curtain_ok and shield_present and bottom_open and fixture_locked and path_checked
                    and water_leak_free is True and energy_in_range is True and guard_closed is True
                    and 15 <= temperature_min <= temperature_max <= limit and 8 <= gas_flow_l_min <= 12
                    and 250 <= curtain_manifold_pressure_pa <= 2800 and 5 <= copper_temperature_c <= 45 and 5 <= lower_ring_temperature_c <= 48
                    and 5 <= seal_band_temperature_c <= 180 and coolant_flow_l_min >= .6)
    if stage == "withdraw":
        finite = all(v is not None and math.isfinite(v) for v in (temperature_max, time_after_arc))
        transfer_ok=isinstance(transfer_support_locked,(tuple,list)) and len(transfer_support_locked)==6 and all(v is True for v in transfer_support_locked)
        return bool(finite and shield_present and bottom_open and return_confirmed and clamp_released
                    and seal_retracted is True and water_leak_free is True
                    and upper_stop_open is True and datum_holder_locked is True and transfer_ok and nest_lock_released is True
                    and upper_lift_mm is not None and math.isfinite(upper_lift_mm) and upper_lift_mm >= 260
                    and temperature_max < 55 and time_after_arc >= 120)
    if stage == "accept":
        finite = all(v is not None and math.isfinite(v) and v >= 0 for v in (measurement_diameter, uncertainty_diameter))
        temperature_ok = temperature_max is not None and math.isfinite(temperature_max) and 19 <= temperature_max <= 21
        sizes=(bore_diameter_min_mm,bore_diameter_max_mm,bore_uncertainty_mm,bore_temperature_c)
        size_ok=all(v is not None and math.isfinite(v) for v in sizes)
        if size_ok:
            size_ok=(0 <= bore_uncertainty_mm <= .0005 and 19.8 <= bore_temperature_c <= 20.2
                     and bore_diameter_min_mm <= bore_diameter_max_mm
                     and bore_diameter_min_mm-bore_uncertainty_mm >= 40
                     and bore_diameter_max_mm+bore_uncertainty_mm <= 40.025)
        finish_ok=not finish_applied
        if finish_applied:
            finish_ok=(pre_finish_position_mm is not None and math.isfinite(pre_finish_position_mm)
                       and uncertainty_diameter is not None and math.isfinite(uncertainty_diameter)
                       and pre_finish_position_mm >= 0 and pre_finish_position_mm+uncertainty_diameter <= .05
                       and finish_radial_stock_mm is not None and math.isfinite(finish_radial_stock_mm)
                       and 0 <= finish_radial_stock_mm <= .003)
        return bool(finite and temperature_ok and size_ok and finish_ok and inspection_passed and clamp_released and shell_base_released and return_confirmed
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


def run_design(root, *, assembly_only=False):
    spec = read_spec(root)
    nominal = yaml.safe_load((root / spec["process_source"]).read_text(encoding="utf-8"))["process"]["nominal"]
    manifest = yaml.safe_load((root / spec["geometry_manifest"]).read_text(encoding="utf-8"))
    a, f, s, p = (spec[k] for k in ("assembly", "fixture", "shield", "process"))
    seat_z = a["seat_bottom_z_mm"]
    seat_top = seat_z + manifest["seat"]["thickness_mm"]
    shell_r = manifest["geometry"]["shell_inner_radius_mm"]
    if s['ring_outer_radius_mm']>shell_r or s['ring_outer_radius_mm']+s.get('seal_radial_thickness_mm',0)<shell_r:
        raise ValueError('铜环及静态密封尺寸没有覆盖壳体内壁')
    if s["ring_top_z_mm"] >= seat_z or f["support_top_z_mm"] != seat_z:
        raise ValueError("防护与支承轴向装配尺寸不闭合")
    if not (s["ring_inner_radius_mm"] < s["ring_outer_radius_mm"]
            and s["ring_wall_thickness_mm"] == s["ring_outer_radius_mm"] - s["ring_inner_radius_mm"]):
        raise ValueError("铜衬环截面尺寸不闭合")
    gas_min, gas_max = s["gas_curtain"]["flow_range_l_min"]
    if not (0 < gas_min <= gas_max):
        raise ValueError("氩气幕流量窗口非法")
    shell, seat = read_brep(root / spec["shell_brep"]), translated(read_brep(root / spec["seat_brep"]), seat_z)
    floor = cylinder(s["rigid_radius_mm"], s["floor_z_mm"], s["floor_thickness_mm"])
    r0, r1 = s["ring_inner_radius_mm"], s["ring_outer_radius_mm"]
    z0, z1 = s["ring_bottom_z_mm"], s["ring_top_z_mm"]
    from hanjie.domain.copper_sectors import sectors, backing_ring, pan_rim, lower_stop, water_bulkheads
    ring = fuse(sectors(s['seal_engineering']['copper_sector_gap_mm']))
    lower_carrier = backing_ring()
    rim = pan_rim()
    low, high = f["carrier_disk_z_mm"]
    support = [cylinder(f["carrier_post_radius_mm"], f["carrier_post_bottom_z_mm"], low-f["carrier_post_bottom_z_mm"]),
               cylinder(f["carrier_disk_radius_mm"], low, high-low)]
    flange=cylinder(f['carrier_base_flange_radius_mm'],f['carrier_post_bottom_z_mm']-f['carrier_base_flange_height_mm'],f['carrier_base_flange_height_mm'])
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    for i in range(f['carrier_base_bolt_count']):
        angle=2*math.pi*i/f['carrier_base_bolt_count']
        axis=gp_Ax2(gp_Pnt(f['carrier_base_bolt_radius_mm']*math.cos(angle),f['carrier_base_bolt_radius_mm']*math.sin(angle),f['carrier_post_bottom_z_mm']-f['carrier_base_flange_height_mm']-1),gp_Dir(0.,0.,1.))
        hole=BRepPrimAPI_MakeCylinder(axis,f['carrier_base_clearance_hole_mm']/2,f['carrier_base_flange_height_mm']+2).Shape()
        flange=BRepAlgoAPI_Cut(flange,hole).Shape()
    support.append(flange)
    guide_low,guide_high=f['mandrel_lower_guide_z_mm']
    support.append(cylinder(30.,guide_low,guide_high-guide_low))
    fixed_core=revolved_section([(0.,99.8),(19.1449047,99.8),(16.4294692,115.2),(0.,115.2)])
    support.append(fixed_core)
    for i in range(f["support_count"]):
        angle = 2 * math.pi * i / f["support_count"]
        axis = gp_Ax2(gp_Pnt(f["support_radius_mm"] * math.cos(angle), f["support_radius_mm"] * math.sin(angle), high), gp_Dir(0., 0., 1.))
        support.append(BRepPrimAPI_MakeCylinder(axis, f["support_pad_radius_mm"], seat_z-high).Shape())
    from hanjie.domain.water_route import moving_union_envelopes, moving_elbow_envelopes
    water_hardware=water_bulkheads()+moving_union_envelopes()+moving_elbow_envelopes()
    cartridge = fuse([floor, ring, lower_carrier, rim, lower_stop()] + water_hardware + support)
    # Qualification witness plates above the Ø144 column, under the fixed pan.
    # The former z70/R62 location was inside the enlarged column.
    witness=[]
    for i in range(4):
        plate=BRepPrimAPI_MakeBox(gp_Pnt(40,-10,82.2),20,20,1).Shape()
        tr=gp_Trsf();tr.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),math.pi/4+i*math.pi/2)
        witness.append(BRepBuilderAPI_Transform(plate,tr,True).Shape())
    witness_intersections={str(i+1):common_volume(plate,cartridge) for i,plate in enumerate(witness)}
    witness_clearances={str(i+1):clearance(plate,cartridge) for i,plate in enumerate(witness)}
    holder=BRepAlgoAPI_Cut(cylinder(90.,-20.,20.),cylinder(75.1,-20.01,20.02)).Shape()
    holder_count=f['datum_holder_transfer_support_count']
    for i in range(holder_count):
        z0,z1=f['datum_holder_outer_grip_slot_z_mm']
        width=f['datum_holder_outer_grip_slot_width_mm']
        depth=f['datum_holder_outer_grip_slot_depth_mm']
        slot=BRepPrimAPI_MakeBox(gp_Pnt(90-depth,-width/2,z0),depth+1,width,z1-z0).Shape()
        tr=gp_Trsf();tr.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),2*math.pi*i/holder_count)
        holder=BRepAlgoAPI_Cut(holder,BRepBuilderAPI_Transform(slot,tr,True).Shape()).Shape()
    holder_span=2*math.pi*f['datum_holder_support_pitch_radius_mm']/holder_count
    # Treat the full circumference as weakened by the grip groove and use
    # the largest ID. This is conservative relative to six local slots.
    holder_width=90-150.24/2-depth
    holder_I=holder_width*20**3/12
    holder_deflection=f['datum_holder_point_load_limit_N']*holder_span**3/(48*180000*holder_I)
    if holder_count!=6 or holder_deflection>.001 or not BRepCheck_Analyzer(holder).IsValid():
        raise ValueError('A基准托环六点转运挠度或实际槽体未通过')
    upper=cylinder(f['upper_envelope_radius_mm'],115.4,400.-115.4)
    sleeve=BRepAlgoAPI_Cut(cylinder(20.,99.8,15.6),fixed_core).Shape()
    upper=fuse([upper,sleeve])
    # Portal plate/columns and positive axial stop. Stop blocks retract before
    # lifting the Ø100 head through the Ø110 aperture.
    portal_plate=BRepPrimAPI_MakeBox(gp_Pnt(-230,-230,400),460,460,100).Shape()
    portal_plate=BRepAlgoAPI_Cut(portal_plate,cylinder(55.,399.9,100.2)).Shape()
    keepers=[];open_keepers=[]
    for sign in (-1,1):
        low=42. if sign>0 else -90.
        pocket=BRepPrimAPI_MakeBox(gp_Pnt(low,-15,399.99),48,30,20.02).Shape()
        portal_plate=BRepAlgoAPI_Cut(portal_plate,pocket).Shape()
        low=42. if sign>0 else -68.
        keeper=BRepPrimAPI_MakeBox(gp_Pnt(low,-15,400),26,30,20).Shape()
        keepers.append(keeper)
        tr=gp_Trsf();tr.SetTranslation(gp_Vec(sign*20.,0.,0.))
        open_keepers.append(BRepBuilderAPI_Transform(keeper,tr,True).Shape())
    columns=[]
    for px in (-180.,180.):
        for py in (-180.,180.):
            columns.append(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(px,py,-160),gp_Dir(0,0,1)),40.,560.).Shape())
    portal=fuse([portal_plate,*columns,*keepers]);portal_open=fuse([portal_plate,*columns,*open_keepers])
    upper=fuse([upper,cylinder(50.,380.,20.)])
    weld = make_weld_envelope(shell_r, p["clearance_leg_mm"], seat_top)
    torch_spec = yaml.safe_load((root / "studies/TOOLING-ACCESS/config.yaml").read_text(encoding="utf-8"))["torch"]
    from hanjie.domain.following_tools import tools as following_tools
    target=(74.5,seat_top+2.3)
    torch, bounds, points=make_torch(torch_spec,nominal,target,30.,True)
    torch,feed,_inactive_peener=following_tools(root,2.8,5.)
    obstacles={"shell":shell,"seat":seat,"upper_fixture":upper,"weld_keepout":weld,"upper_portal":portal}
    # 最终组焊停用轻击；历史工具构造仍可由原研究脚本使用，当前装配不导出它。
    tools={"torch":torch,"wire_guide":feed}
    bodies = {**obstacles,**tools,"cartridge":cartridge,"external_datum_holder":holder}
    bodies.update({f'qualification_witness_{i+1}':plate for i,plate in enumerate(witness)})
    if assembly_only:
        # 单装配整改入口：不重算工艺/承载比较、升降扫掠或历史assessment。
        return None, bodies, points
    poses = []
    for lift in (0., 40., 120.):
        for name, tool in tools.items():
            moved = translated(tool, lift)
            intersections = {key: common_volume(moved, shape) for key, shape in obstacles.items()}
            poses.append({"tool": name, "lift_mm": lift, "intersections_mm3": intersections,
                          "intentional_bead_contact": name=="wire_guide" and lift==0,
                          "clear": max(value for key,value in intersections.items() if not (key=="weld_keepout" and name=="wire_guide" and lift==0)) < 1e-6})
    # Fixed lower cartridge. The upper core/sleeve lift first, then the shell,
    # seat and their independent datum-A holder lift without moving the pan.
    upper_lift=a['upper_fixture_lift_mm'];housing_lift=a['housing_lift_mm']
    withdrawal_stroke=housing_lift
    flange_bottom=f['carrier_post_bottom_z_mm']-f['carrier_base_flange_height_mm']
    root_space_ok=a['bottom_clearance_mm']>=-flange_bottom
    retract_upper=translated(upper,upper_lift)
    sweep_intersections={}
    for ul in (0.,1.,5.,15.,40.,80.,120.,200.,upper_lift):
        moving=translated(upper,ul)
        for name,shape in {'shell':shell,'seat':seat,'fixed_core':cartridge,'opened_portal':portal_open}.items():
            sweep_intersections[f'upper_{name}_travel_{ul:g}']=common_volume(moving,shape)
    for lift in (0.,.5,1.,5.,20.,50.,80.,housing_lift):
        moved_shell=translated(shell,lift);moved_seat=translated(seat,lift)
        # The intentional cold copper seal contact at zero lift is handled by
        # the separate four-sector retreat proof, not by nominal closed seals.
        sweep_intersections[f'upper_shell_{lift:g}']=common_volume(retract_upper,moved_shell)
        sweep_intersections[f'upper_seat_{lift:g}']=common_volume(retract_upper,moved_seat)
        sweep_intersections[f'holder_post_{lift:g}']=common_volume(translated(holder,lift),cartridge)
    exit_clearance=a['seat_bottom_z_mm']-s['ring_top_z_mm']+housing_lift
    complete_pan_clearance=housing_lift-s['ring_top_z_mm']
    upper_tail_clearance=99.8+upper_lift-(200.+housing_lift)
    holder_to_core_clearance=housing_lift-20.-115.2
    if min(complete_pan_clearance,upper_tail_clearance,holder_to_core_clearance)<=0 or not root_space_ok:
        raise ValueError('上提回收行程或固定柱根服务净空不足')
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
                          "contact_pressure_caliber":"名义平均带压；峰值接触应力由试制阶段重复装夹试验评价"},
              "shield_control": {"type": s["type"], "ring_material": s["ring_material"],
                                 "gas_curtain_flow_range_l_min": [gas_min, gas_max],
                                 "flow_interlock": s["gas_curtain"]["flow_interlock"],
                                 "ring_contact_design":"四瓣铜环与闭合FFKM密封；冷热压缩及全周撤出包络见尺寸化核算"},
              "datum_holder_transfer":{"support_count":holder_count,"point_load_limit_N":f['datum_holder_point_load_limit_N'],
                           "span_mm":holder_span,"minimum_effective_width_mm":holder_width,
                           "section_I_mm4":holder_I,"E_lower_MPa":180000,
                           "elastic_deflection_bound_mm":holder_deflection,
                           "scope":"six positive outer grip supports; simply supported developed arc, full circumference weakened by grip depth; not measured repeatability"},
              "geometry": {"shape_validity":{k:BRepCheck_Analyzer(v).IsValid() for k,v in {**obstacles,**tools,"cartridge":cartridge,"external_datum_holder":holder}.items()},
                           "witness_intersections_mm3":witness_intersections,
                           "witness_minimum_clearance_mm":min(witness_clearances.values()),
                           "cartridge_intersections_mm3":{k:common_volume(cartridge,v) for k,v in {"shell":shell,"seat":seat,"upper_fixture":upper}.items()},
                           "bottom_sweep_intersections_mm3":sweep_intersections,
                           "bottom_route_allowed":a["bottom_open"] and root_space_ok and max(sweep_intersections.values()) < 1e-6,
                           "route":"fixed lower fixture; upper lift then housing/holder lift",
                           "housing_lift_mm":housing_lift,"upper_lift_mm":upper_lift,
                           "pan_to_lifted_bottom_clearance_mm":complete_pan_clearance,
                           "upper_tail_to_lifted_mouth_clearance_mm":upper_tail_clearance,
                           "holder_bottom_to_fixed_core_clearance_mm":holder_to_core_clearance,
                           "withdrawal_stroke_mm":withdrawal_stroke,"root_flange_space_pass":root_space_ok,
                           "poses":poses, "torch_feed_intersection_mm3":common_volume(torch, feed),
                           "torch_feed_clearance_mm":clearance(torch,feed), "peener_in_current_assembly":False, "torch_shell_radial_bound_mm":shell_r-bounds["radial_upper_bound_mm"],
                           "torch_upper_radial_bound_mm":bounds["radial_lower_bound_mm"]-f["upper_envelope_radius_mm"],
                           "nominal_vertical_drop_coverage":s["ring_outer_radius_mm"]+s.get('seal_radial_thickness_mm',0)>=shell_r,
                           "coverage_requires_ring_alignment":True},
              "release":{"design_verified":False,"physical_validation_recommended":True,
                         "product_conformity_claimed":False}}
    return result, bodies, points
