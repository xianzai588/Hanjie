"""Cold sizing of the real complete-ring fixture and its physical load path.

The initial equivalent beam remains a historical comparison. The selected
design integrates real circular sections, service holes, taper, preloaded
base/steel bed and upper axial reaction; interface and foundation targets are
explicit finite allocations. Thermal response and product welding results
are independent of this cold tooling calculation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from scipy.integrate import quad
import yaml


ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "studies/COMPETITION-DESIGN/results/ring-fixture-feasibility.json"


def evaluate(width: float = 80.0) -> dict:
    # N, mm and MPa; transverse loading directions are aligned conservatively.
    length = 120.0
    height = 120.0
    modulus = 206000.0
    poisson_ratio = 0.30
    shear_factor = 5.0 / 6.0
    force = 5000.0
    moment = 170000.0
    axis_lever = 100.0
    radial_budget_um = 6.5
    inertia = width * height**3 / 12.0
    rigidity = modulus * inertia
    force_translation = force * length**3 / (3.0 * rigidity)
    moment_translation = moment * length**2 / (2.0 * rigidity)
    force_rotation = force * length**2 / (2.0 * rigidity)
    moment_rotation = moment * length / rigidity
    shear_modulus = modulus / (2.0 * (1.0 + poisson_ratio))
    shear_translation = force * length / (shear_factor * shear_modulus * width * height)
    parts_um = {
        "force_end_translation": force_translation * 1000.0,
        "moment_end_translation": moment_translation * 1000.0,
        "force_rotation_at_axis_lever": force_rotation * axis_lever * 1000.0,
        "moment_rotation_at_axis_lever": moment_rotation * axis_lever * 1000.0,
        "transverse_shear_translation": shear_translation * 1000.0,
    }
    total = sum(parts_um.values())
    # Only the equivalent rectangular load member, not the entire station.
    member_mass_kg = length * width * height * 7.85e-6
    bending_stress = (force * length + moment) * height / (2.0 * inertia)
    return {
        "design_identity": yaml.safe_load((ROOT/"project/submission-baseline.yaml").read_text(encoding="utf8"))["version"],
        "configuration": "基础站短受力闭环；等效钢梁截面起点",
        "scope": "冷态悬臂弯曲与矩形截面剪切核算，不是全架有限元或实测定位结果",
        "inputs": {
            "beam_length_mm": length,
            "section_width_mm": width,
            "section_height_mm": height,
            "elastic_modulus_MPa": modulus,
            "poisson_ratio": poisson_ratio,
            "shear_modulus_MPa": shear_modulus,
            "rectangular_shear_factor": shear_factor,
            "transverse_force_N": force,
            "end_moment_N_mm": moment,
            "axis_lever_from_beam_end_mm": axis_lever,
            "radial_clamping_allocation_um": radial_budget_um,
        },
        "assumptions": [
            "矩形等截面梁、线弹性小挠度，夹固端为计算边界",
            "力与端矩产生的端部平移和孔轴杠杆转角位移按同向叠加",
            "短梁L/h=1，计入剪切挠度；接触、连接、基座与热态变化另占剩余工装预算",
        ],
        "section": {
            "second_moment_mm4": inertia,
            "equivalent_member_mass_kg": member_mass_kg,
            "root_bending_stress_MPa": bending_stress,
            "mass_scope": f"仅120×{width:g}×120 mm等效受力件，不是工作站总质量",
        },
        "formulas": {
            "I": "b*h^3/12",
            "force_end_translation": "F*L^3/(3*E*I)",
            "moment_end_translation": "M*L^2/(2*E*I)",
            "force_rotation_at_axis_lever": "F*L^2*lever/(2*E*I)",
            "moment_rotation_at_axis_lever": "M*L*lever/(E*I)",
            "transverse_shear_translation": "F*L/(kappa*G*b*h), G=E/[2*(1+nu)]",
        },
        "axis_displacement_components_um": parts_um,
        "complete_cantilever_axis_displacement_um": total,
        "remaining_contact_connection_base_budget_um": radial_budget_um - total,
        "section_fits_radial_allocation": total < radial_budget_um,
        "design_decision": (
            "采用短受力闭环作为基础站的截面设计起点；完整梁端平移、转角投影和剪切"
            "纳入后仍保留工装预算。接触、连接与基础柔度按剩余额度设计，"
            "总站热态与重复定位在工装首件确认。"
        ),
        "historical_fixture_scope": "既有重型门架为八翼研究详图，不列为圆环基础站主配置",
    }


def evaluate_real_fixture() -> dict:
    """Size the actual stepped arbor, preloaded base and upper axial load path.

    Cold elastic analysis. Positive contact and friction are checked against
    explicitly specified preloads. Unmodelled seating and machine foundation
    remain a separate, finite allocation; they are not assigned zero stiffness.
    """
    E, nu, F, M = 206000.0, 0.30, 5000.0, 170000.0
    G, kappa = E / (2 * (1 + nu)), 0.90
    z_load = 115.2
    angle = math.radians(3.0)
    cone_d0 = 38.2898094
    cone_d1 = cone_d0 - 2 * 15.4 * math.tan(angle)
    water_ports = []
    for quarter in range(4):
        a = math.radians(45+90*quarter)
        for r in (52.0,58.0):
            for t in (-4.0,4.0):
                water_ports.append((r*math.cos(a)-t*math.sin(a),r*math.sin(a)+t*math.cos(a)))
    water_removed_I = 16*math.pi*4**4/64 + math.pi*4**2/4*sum(x*x for x,y in water_ports)
    gas_removed_I = 2*(math.pi*6**4/64+math.pi*6**2/4*62**2)
    removed_area = 16*math.pi*4**2/4+2*math.pi*6**2/4
    sections = [
        ("RF01柱", -20.0, 80.0, 144.0, 144.0),
        ("RF01短颈", 80.0, 99.8, 96.0, 96.0),
        ("RF01固定反锥", 99.8, 115.2, cone_d0, cone_d1),
    ]
    parts = []
    for name, low, high, d0, d1 in sections:
        diameter = lambda z: d0 + (d1-d0) * (z-low)/(high-low)
        inertia = lambda z: math.pi * diameter(z)**4/64 - (water_removed_I+gas_removed_I if name=="RF01柱" else 0)
        area = lambda z: math.pi * diameter(z)**2/4 - (removed_area if name=="RF01柱" else 0)
        bend = quad(lambda z: (F*(z_load-z)**2 + M*(z_load-z))/(E*inertia(z)), low, high)[0]
        shear = quad(lambda z: F/(kappa*G*area(z)), low, high)[0]
        rotation = quad(lambda z: (F*(z_load-z)+M)/(E*inertia(z)), low, high)[0]
        parts.append({"part": name, "z_mm": [low, high], "diameters_mm": [d0, d1],
                      "bending_axis_um": 1000*bend, "shear_axis_um": 1000*shear,
                      "end_rotation_rad": rotation,
                      "maximum_bending_stress_MPa": (F*(z_load-low)+M)*d0/(2*inertia(low))})
    arbor_axis = sum(p["bending_axis_um"]+p["shear_axis_um"] for p in parts)
    # The force and couple are applied at the highest arbor point. This covers
    # the two bore endpoints without inventing a 100 mm extension above it.
    base_width, base_depth, base_height = 460.0, 400.0, 80.0
    bed_height = 100.0
    joint_z = -100.0
    root_lever = z_load-joint_z
    joint_moment = F*root_lever+M
    anchors = [(x, y) for y in (-150.0, 150.0) for x in (-165.0,-110.0,-55.0,0.0,55.0,110.0,165.0)]
    anchors += [(x,y) for x in (-185.0,185.0) for y in (-75.0,75.0)]
    bolt_area, bolt_length = 561.0, 110.0
    bolt_preload, preload_tolerance = 100000.0, 0.10
    bolt_k = E*bolt_area/bolt_length
    # Both lateral directions checked; use the weaker screw-group direction.
    sums = {"x": sum(x*x for x,y in anchors), "y": sum(y*y for x,y in anchors)}
    rotational_k = bolt_k*min(sums.values())
    bolt_axis = joint_moment/rotational_k*root_lever*1000
    increments = [joint_moment * max(abs(x),abs(y))/min(sums.values()) for x,y in anchors]
    preload_min = len(anchors)*bolt_preload*(1-preload_tolerance)
    footprint = base_width*base_depth
    weakest_I = min(base_width*base_depth**3,base_depth*base_width**3)/12
    weakest_W = min(base_width*base_depth**2,base_depth*base_width**2)/6
    pressure_min = preload_min/footprint-joint_moment/weakest_W
    # Full-face bedded base block and supplied steel bed. The bench underneath
    # the bed is the final boundary and its rocking goes into the remaining
    # foundation allocation, not into this material-compression calculation.
    base_net_factor = 0.85  # conservative uniform loss for the two cross-drilled service layers
    base_bend = (F*base_height**3/3+(F*(z_load+20)+M)*base_height**2/2)/(E*weakest_I*base_net_factor)
    base_rotation = (F*base_height**2/2+(F*(z_load+20)+M)*base_height)/(E*weakest_I*base_net_factor)
    base_axis = (base_bend+base_rotation*(z_load+20)+F*base_height/(kappa*G*footprint*base_net_factor))*1000
    bed_axis = (joint_moment*bed_height/(E*weakest_I)*root_lever+
                F*bed_height/(kappa*G*footprint))*1000
    axial_force = 500.0 + F*(math.tan(angle)+0.20)/(1-0.20*math.tan(angle))
    upper_tube_area = math.pi*(70.0**2-24.0**2)/4
    columns_area = 2*math.pi*70.0**2/4
    # Central Ø110 aperture is subtracted from the full-width bridge strip.
    bridge_net_width, bridge_height, bridge_span = 220.0-110.0, 80.0, 280.0
    bridge_I = bridge_net_width*bridge_height**3/12
    upper_terms = {
        "slotted_sleeve_neck_axial_compression_mm": axial_force*30/(200000*(math.pi*(39.94**2-38.34**2)/4-6*.8*.8)),
        "tube_axial_compression_mm": axial_force*284.6/(E*upper_tube_area),
        "two_columns_axial_compression_mm": axial_force*420/(E*columns_area),
        "two_column_root_6mm_fillet_weld_shear_mm": axial_force*3/(G*2*math.pi*70*(6/math.sqrt(2))),
        "net_bridge_bending_mm": axial_force*bridge_span**3/(48*E*bridge_I),
        "net_bridge_shear_mm": axial_force*bridge_span/(4*(5/6)*G*bridge_net_width*bridge_height),
        "two_positive_stops_compression_mm": axial_force*20/(E*2*7*30),
    }
    upper_radial = sum(upper_terms.values())*math.tan(angle)*1000
    structural_total = arbor_axis+base_axis+bed_axis+bolt_axis+upper_radial
    seating_allocation = 0.25
    radial_budget = 6.5
    with_seating = structural_total+seating_allocation
    pullout_stroke = 1.5
    radial_release = pullout_stroke*math.tan(angle)
    return {
        "design_identity": yaml.safe_load((ROOT/"project/submission-baseline.yaml").read_text(encoding="utf8"))["version"],
        "version": "HJ-F-S01-R2",
        "configuration": "HJ-F-S01完整圆环专属整体下背承、双柱上桥和主动退锥工装",
        "scope": "实际分段截面、预紧底座和上部轴压的冷态解析核算；接触坐实、基础摇摆和热态分别确认",
        "geometry_source": "cad/parametric/ring_fixture/build_ring_fixture.py",
        "inputs": {"elastic_modulus_MPa": E,"poisson_ratio": nu,"transverse_force_N": F,
                   "end_moment_N_mm": M,"load_at_z_mm": z_load,"bore_endpoint_z_mm":[100,115],
                   "radial_clamping_allocation_um":radial_budget,"cone_half_angle_deg":3.0,
                   "cone_bottom_diameter_mm":cone_d0,"cone_top_diameter_mm":cone_d1,
                   "base_dimensions_mm":[460,400,80],"bed_dimensions_mm":[460,400,100],
                   "upper_bridge_dimensions_mm":[340,220,80],"bridge_bottom_z_mm":400,
                   "column_diameter_mm":70,"column_centers_mm":[[-140,0],[140,0]],
                   "positive_pullout_stroke_mm":pullout_stroke},
        "service_bore_net_section": {"water_vertical_bores_count":16,"water_vertical_bore_diameter_mm":4,
                                     "water_port_coordinates_mm":water_ports,"gas_vertical_bores_count":2,
                                     "gas_vertical_bore_diameter_mm":6,"gas_port_coordinates_mm":[[-62,0],[62,0]],
                                     "arbor_column_removed_area_mm2":removed_area,
                                     "arbor_column_removed_second_moment_mm4":water_removed_I+gas_removed_I,
                                     "base_cross_drill_conservative_net_section_factor":base_net_factor,
                                     "routing":"水口在基板z-40/-30两层径向引至外侧；气口z-55单独出侧面，不穿反锥，也不从A托环下方拖管"},
        "assumptions": [
            "5kN及170kN·mm同向施加于z115.2锥顶；评价包含实际孔端z100/115，不使用100mm虚拟孔轴伸长",
            "圆柱剪切系数0.90，变截面反锥使用局部I(z)积分，不以等效矩形梁代替",
            "RF01/RF02全底面磨削贴合，18只M30预紧均匀分级施加；最小接触压和防滑储备按载荷验证",
            "螺栓弹性转角额外同向计入，接触压缩并未据此当作零刚度；最终机台摇摆须守剩余分配",
            "上驱动径向浮动，5kN侧向载荷经固定反锥和下背承入基座；上桥传递退锥/压环轴力",
        ],
        "real_arbor_sections": parts,
        "lower_arbor_axis_displacement_um":arbor_axis,
        "base_block_axis_displacement_um":base_axis,
        "steel_bed_axis_displacement_um":bed_axis,
        "anchor_elastic_axis_displacement_um":bolt_axis,
        "upper_axial_path": {"force_N":axial_force,"friction_upper_bound":0.20,
                             "components":upper_terms,"radial_equivalent_um":upper_radial,
                             "aperture_subtracted_net_bridge_width_mm":bridge_net_width,
                             "slotted_neck_net_area_mm2":math.pi*(39.94**2-38.34**2)/4-6*.8*.8,
                             "sleeve_neck_modulus_MPa":200000.0,"column_root_continuous_fillet_leg_mm":6.0},
        "anchors": {"count":len(anchors),"specification":"18-M30×140 ISO4762-8.8；RF02有效螺纹≥60mm",
                    "coordinates_mm":anchors,"tensile_area_mm2":bolt_area,"effective_elastic_length_mm":bolt_length,
                    "pretension_N_per_bolt":bolt_preload,"pretension_relative_tolerance":preload_tolerance,
                    "rotation_stiffness_N_mm_rad":rotational_k,"incremental_tension_max_N":max(increments),
                    "maximum_nominal_bolt_tensile_stress_MPa":(bolt_preload*1.10+max(increments))/bolt_area,
                    "minimum_contact_pressure_MPa":pressure_min,"assumed_static_friction_lower_bound":0.10,
                    "minimum_sliding_capacity_N":0.10*preload_min,"required_transverse_force_N":F,
                    "full_face_no_opening_under_nominal_load":pressure_min>0,
                    "static_slip_reserve_ratio":0.10*preload_min/F},
        "cold_structural_axis_displacement_um":structural_total,
        "seated_contact_increment_allocation_um":seating_allocation,
        "cold_structural_plus_seating_allocation_um":with_seating,
        "remaining_foundation_and_seating_budget_um":radial_budget-with_seating,
        "structural_screen_fits_radial_allocation":with_seating<radial_budget,
        "qualification": {"contact_seating_increment_measured":False,"foundation_rocking_measured":False,
                          "thermal_displacement_validated":False,"product_axis_after_welding_validated_by_this_study":False,
                          "required_seating_increment_um_max":seating_allocation,
                          "required_bench_rocking_equivalent_axis_um_max":radial_budget-with_seating,
                          "cold_loading_acceptance":"以独立A/B基准施加±5kN和±170kN·mm组合；两孔端径向变化≤6.5μm，加载卸载复测坐实与永久变化"},
        "release": {"half_angle_deg":3,"friction_self_lock_threshold":math.tan(angle),
                    "positive_pullout_required":True,"stroke_mm":pullout_stroke,
                    "available_radial_taper_release_mm":radial_release,
                    "required_radial_sleeve_release_mm":(40.04-39.94)/2,
                    "radial_release_margin_mm":radial_release-(40.04-39.94)/2,
                    "sequence":"停弧、最高温<55℃且停弧≥120s→压环卸载→双止挡外退30→上退1.5主动退锥→铜瓣径退1.10→上工具升260→A托环接管→壳体与托环升140；盘/铜/下反锥保持原位"},
        "precision_budget_relationship":"6.5μm为径向夹紧分项，已含于制造装配定位28μm直径项；不得再次加到50μm总预算",
        "historical_equivalent_beam": evaluate(),
        "initial_section_width_60mm": evaluate(60.0),
        "design_decision":"保留同一6.5μm径向分配。采用真实短颈、3°反锥、净截面上桥和连续贴合预紧底座；冷态结构预算与热态控形结果分开记录。完整固定件质量从CAD实体汇总，不以等效梁9kg代表全架。",
    }


if __name__ == "__main__":
    result = evaluate_real_fixture()
    manifest_path=ROOT/"cad/generated/ring-fixture/geometry-quality-and-bom.json"
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding="utf8"))
        if manifest["design_identity"]==result["design_identity"]:
            result["cad_assembly"]={"manifest":str(manifest_path.relative_to(ROOT)),
                                   "working_solid_count":manifest["working_solid_count"],
                                   "all_exported_solids_valid":all(x["all_solids_valid"] for x in manifest["step_rechecks"]),
                                   "mass_summary_kg":manifest["mass_summary_kg"],"mass_scope":manifest["mass_scope"]}
            result["motion_clearances_mm"]=manifest["clearances_mm"]
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({
        "result_file": str(DESTINATION.relative_to(ROOT)),
        "cold_structure_and_seating_allocation_um": result["cold_structural_plus_seating_allocation_um"],
        "remaining_foundation_budget_um": result["remaining_foundation_and_seating_budget_um"],
    }, ensure_ascii=False))
