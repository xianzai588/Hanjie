"""One specified root/cover allocation, reusing the saved section arithmetic.

This is a wire/geometry/energy design calculation. It does not simulate formation,
assign fusion, change process sources, or rerun tooling clearance calculations.
"""
from pathlib import Path
import importlib.util
import itertools
import json
import math

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "studies/COMPETITION-DESIGN/results"
NAME = "final-pass-forming-revision-20261008"


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def section_functions():
    source = ROOT / "studies/COMPETITION-DESIGN/delivery_section_envelope.py"
    spec = importlib.util.spec_from_file_location("saved_delivery_section", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def calculate():
    f = section_functions()
    baseline = yaml.safe_load((ROOT / "project/submission-baseline.yaml").read_text(encoding="utf-8"))
    joint = read("deliverables/process/joint-process-card.json")
    previous = read("studies/COMPETITION-DESIGN/results/section-forming-envelope-20261008.json")
    clearance = read("cad/generated/engineering-supplements-20261007/pressure-interface-clearance.json")
    spec = joint["spec"]
    layout = baseline["weld_layout"]
    process = baseline["final_GTAW"]
    # One frozen candidate. The total increase is placed in the cover pass;
    # root nominal feed follows the existing 2.80 mm root geometry target.
    feeds = {"root": 3.42, "cover": 3.78}
    d = spec["wire_diameter_mm"]
    dt = spec["wire_diameter_tolerance_mm"]
    ft = spec["feed_tolerance_mm_s"]
    etas = spec["deposition_efficiency_range"]
    eta_mid = sum(etas) / 2
    v = process["travel_speed_mm_s"]
    vt = spec["travel_relative_tolerance"]
    area_wire = math.pi * d*d / 4
    target_root_leg = 2.8
    reverse_root_feed = target_root_leg**2 / 2 * v / (eta_mid * area_wire)
    length_pass = layout["length_per_pass_mm"]
    zmin = process["minimum_total_leg_mm"]
    zmax = process["maximum_geometric_envelope_leg_mm"]
    amin = zmin / math.sqrt(2)
    rho = previous["single_feed_contrast"]["density_kg_m3"] * 1e-9
    h = previous["single_feed_contrast"]["specific_incoming_enthalpy_relative_20C_J_kg"]
    pnet = process["nominal_net_energy_J_mm"] * v

    def supply(wire_d, eta, travel, root_feed, cover_feed):
        aw = math.pi * wire_d*wire_d / 4
        arc_time = length_pass / travel
        passes = {}
        for name, feed in [("root", root_feed), ("cover", cover_feed)]:
            volume = eta * aw * feed * arc_time
            incoming_mass = aw * feed * arc_time * rho
            area = volume / length_pass
            entering_h = volume * rho * h
            net = pnet * arc_time
            passes[name] = dict(feed_mm_s=feed, wire_length_mm=feed*arc_time,
                consumed_mass_g=incoming_mass*1000, deposited_volume_mm3=volume,
                deposited_mass_g=volume*rho*1000, added_section_area_mm2=area,
                equivalent_equal_leg_mm=math.sqrt(2*area), entering_wire_enthalpy_J=entering_h,
                net_energy_J=net, parent_pool_and_loss_remainder_J=net-entering_h)
        total_area = sum(a["added_section_area_mm2"] for a in passes.values())
        return dict(wire_diameter_mm=wire_d, deposition_efficiency=eta,
            travel_mm_s=travel, actual_arc_time_each_pass_s=arc_time, passes=passes,
            total_section_area_mm2=total_area,
            total_consumed_wire_mm=sum(a["wire_length_mm"] for a in passes.values()),
            total_consumed_wire_mass_g=sum(a["consumed_mass_g"] for a in passes.values()),
            total_deposited_mass_g=sum(a["deposited_mass_g"] for a in passes.values()),
            total_entering_wire_enthalpy_J=sum(a["entering_wire_enthalpy_J"] for a in passes.values()),
            total_net_energy_J=sum(a["net_energy_J"] for a in passes.values()),
            total_parent_pool_and_loss_remainder_J=sum(a["parent_pool_and_loss_remainder_J"] for a in passes.values()))

    nominal = supply(d, eta_mid, v, feeds["root"], feeds["cover"])
    corners = []
    # Only fixed tolerance corners of this one candidate; no feed/shape search.
    for diameter, eta, travel, fr, fc in itertools.product(
            [d-dt, d+dt], etas, [v*(1-vt), v*(1+vt)],
            [feeds["root"]-ft, feeds["root"]+ft],
            [feeds["cover"]-ft, feeds["cover"]+ft]):
        corners.append(supply(diameter, eta, travel, fr, fc))
    smin = min(c["total_section_area_mm2"] for c in corners)
    smax = max(c["total_section_area_mm2"] for c in corners)

    def range_of(key):
        return [min(c[key] for c in corners), max(c[key] for c in corners)]

    pass_ranges = {}
    for name in feeds:
        keys = ["wire_length_mm", "consumed_mass_g", "deposited_mass_g",
                "added_section_area_mm2", "equivalent_equal_leg_mm", "entering_wire_enthalpy_J",
                "net_energy_J", "parent_pool_and_loss_remainder_J"]
        pass_ranges[name] = {k: [min(c["passes"][name][k] for c in corners),
                                max(c["passes"][name][k] for c in corners)] for k in keys}

    def boundaries(area):
        # Exact conditional straight-profile bounds, with zero unallocated area.
        throat_k = 2*area / (amin*amin)
        ratio_throat = (throat_k + math.sqrt(throat_k*throat_k-4))/2
        ratio_legs = 2*area / (zmin*zmin)
        ratio_keepout = zmax*zmax / (2*area)
        ratio = min(ratio_throat, ratio_legs, ratio_keepout)
        straight_row = f.classify(f.straight(area, ratio), zmin, amin, zmax)
        # Equal-leg parabolic concavity: derive the two coupled geometry limits,
        # rather than declaring an independent manufacturing concavity window.
        c_throat = amin - math.sqrt(4*amin*amin - 3*area)
        c_keepout = (zmax*zmax/2-area) / ((2/3)*math.sqrt(2)*zmax)
        c = min(c_throat, c_keepout)
        concave_row = f.classify(f.parabola(area, 1., c), zmin, amin, zmax)
        return dict(area_mm2=area, straight_ratio_limit_from_two_legs=ratio_legs,
            straight_ratio_limit_from_throat=ratio_throat,
            straight_ratio_limit_from_triangle=ratio_keepout,
            straight_joint_ratio_limit=ratio, straight_boundary_profile=straight_row,
            equal_leg_concavity_limit_from_throat_mm=c_throat,
            equal_leg_concavity_limit_from_triangle_mm=c_keepout,
            equal_leg_joint_concavity_limit_mm=c, equal_leg_concave_boundary_profile=concave_row,
            equal_leg_straight_profile=f.classify(f.straight(area, 1.), zmin, amin, zmax),
            non_throat_area_allowance_before_3p80_triangle_mm2=area-zmin*zmin/2,
            scope="Reverse geometry bounds for this specified profile family and actual section area. Not statistical forming limits or a guaranteed response to feeder/torch errors.")

    bounds = [boundaries(s) for s in [smin, smax]]
    old = previous["original_supply_envelope"]
    old_energy = previous["single_feed_contrast"]["energy_cases"][0]
    nominal_at_eta_edges = [supply(d, eta, v, feeds["root"], feeds["cover"]) for eta in etas]
    incoming_range = [c["total_entering_wire_enthalpy_J"] for c in nominal_at_eta_edges]
    differences = [a-b for a,b in zip(incoming_range, old_energy["entering_enthalpy_at_nominal_dimensions_J"])]
    remelt = previous["saved_tolerance_family_summary"]
    return dict(date="2026-10-08",decision_problem="One root/cover deposition allocation within the unchanged 4.30 mm triangle",
        revision=dict(root_feed_mm_s=feeds["root"], cover_feed_mm_s=feeds["cover"],
            feed_tolerance_each_mm_s=ft, mean_feed_mm_s=sum(feeds.values())/2,
            root_feed_reverse_from_nominal_2p8_triangle_mm_s=reverse_root_feed,
            reverse_basis=dict(root_equal_leg_target_mm=target_root_leg,
                nominal_eta_used_only_for_design_target=eta_mid, nominal_wire_diameter_mm=d,
                nominal_travel_mm_s=v, feeder_resolution_mm_s=.01),
            root_feed_reason="Round the 2.80 mm nominal root target to the existing 0.01 mm/s design resolution; root deposit is not increased.",
            cover_feed_reason="Place the one total-deposition increase in the cover pass. Mean 3.60 replaces the rejected independent 3.68/r/c-window proposal, and retains headroom below the real 4.30 triangle.",
            candidate_count=1, fixed_tolerance_corner_count=len(corners), process_source_changed_by_this_script=False),
        unchanged=dict(wire_diameter_mm=d, wire_diameter_tolerance_mm=dt,
            deposition_efficiency_range=etas, travel_mm_s=v, travel_relative_tolerance=vt,
            net_energy_per_pass_J_mm=process["nominal_net_energy_J_mm"],
            actual_length_each_pass_mm=length_pass,
            stable_length_each_segment_mm=layout["effective_segment_length_mm"],
            total_effective_length_mm=layout["effective_length_per_pass_mm"],
            both_legs_minimum_mm=zmin, minimum_geometric_throat_mm=amin,
            keepout_equation="x>=0,y>=0,x+y<=4.30 mm", maximum_coordinate_sum_mm=zmax,
            root_and_cover_paths="Existing root/cover targets, straight pass path and 150 mm transitions; no weaving or pose change"),
        nominal=nominal, nominal_geometry_eta_edges=nominal_at_eta_edges,
        pass_tolerance_ranges=pass_ranges,
        total_tolerance_ranges={k:range_of(k) for k in ["total_section_area_mm2", "total_consumed_wire_mm",
            "total_consumed_wire_mass_g", "total_deposited_mass_g", "total_entering_wire_enthalpy_J",
            "total_net_energy_J", "total_parent_pool_and_loss_remainder_J"]},
        contour_joint_geometry_bounds=bounds,
        original_comparison=dict(original_area_range_mm2=old["area_range_mm2"],
            original_equal_leg_throat_margin_um=old["equal_leg_throat_margin_mm"]*1000,
            revised_equal_leg_minimum_throat_margin_um=(math.sqrt(smin)-amin)*1000,
            revised_equivalent_total_equal_leg_range_mm=[math.sqrt(2*smin), math.sqrt(2*smax)],
            original_unallocated_area_margin_mm2=old["allowable_non_throat_area_at_min_area_mm2"],
            revised_unallocated_area_margin_mm2=smin-zmin*zmin/2,
            original_nominal_wire_mm=old_energy["wire_length_mm"],
            revised_nominal_wire_mm=nominal["total_consumed_wire_mm"],
            revised_15pct_preparation_wire_mm=nominal["total_consumed_wire_mm"]*1.15,
            extra_nominal_wire_mm=nominal["total_consumed_wire_mm"]-old_energy["wire_length_mm"],
            original_root_feed_mm_s=3.5, revised_root_feed_mm_s=feeds["root"],
            original_cover_feed_mm_s=3.5, revised_cover_feed_mm_s=feeds["cover"]),
        heat_ledger=dict(density_kg_m3=rho*1e9,
            entering_specific_enthalpy_J_kg=h,
            entering_temperature_design_C=1470.,
            enthalpy_basis=previous["single_feed_contrast"]["enthalpy_basis"],
            nominal_total_net_energy_J=process["net_energy_kJ"]*1000,
            nominal_total_entering_wire_enthalpy_at_eta_edges_J=incoming_range,
            extra_entering_wire_enthalpy_at_eta_edges_J=differences,
            extra_entering_wire_enthalpy_per_actual_total_path_J_mm=[a/layout["total_arc_length_mm"] for a in differences],
            nominal_parent_pool_and_loss_remainder_at_eta_edges_J=[process["net_energy_kJ"]*1000-a for a in incoming_range],
            thermal_scope="Saved NiFe55 engineering Cp and latent-heat inputs, not supplier high-temperature properties. Incoming retained-wire H is deducted once from arc-net heat; heated discarded material belongs to loss. A positive remainder alone does not prove fusion.",
            current_and_voltage_or_travel_changed=False,
            changed_pass_heat_partition_requires_fusion_remelt_and_residual_qualification=True),
        tooling_reuse=dict(source="cad/generated/engineering-supplements-20261007/pressure-interface-clearance.json",
            checked_poses_reused=clearance["checked_poses"], new_clearance_run=False,
            actual_pose_shape_unchanged=True,
            root_target_R_z_mm=[74.5,117.3],root_wire_tip_R_z_mm=[73.2,116.0],
            cover_target_R_z_mm=[74.,118.],cover_wire_tip_R_z_mm=[72.7,116.7],
            nominal_minimum_gap_mm=min(clearance["nominal_minimum_gaps_mm"].values()),
            dimensional_allowance_mm=clearance["dimensional_allowance_mm"],
            lower_bound_gap_mm=min(clearance["nominal_minimum_gaps_mm"].values())-clearance["dimensional_allowance_mm"],
            geometry_condition="All actual deposited contours, including toes, remain inside the existing triangular envelope; no new tooling qualification granted"),
        layer_survival=dict(root_remelt_design_limit_mm=remelt["final_root_remelt_design_limit_mm"],
            two_pass_union_remelt_design_limit_mm=remelt["final_union_remelt_design_limit_mm"],
            minimum_second_before_final_mm=remelt["minimum_finished_second_flat_mm"],
            conditional_second_after_final_mm=remelt["conditional_minimum_second_remaining_flat_mm"],
            conditional_total_after_final_mm=remelt["conditional_minimum_total_remaining_flat_mm"],
            physical_remelt_result_available=False,
            scope="Unchanged geometry budget only. Lower root deposit moves wire H out of the root pass at the same arc power; it cannot be claimed to lower remelt. New cover partition may reheat/remelt the root and must be separately qualified."),
        local_distribution_gap=dict(supply_to_profile_relation_qualified=False,
            actual_non_throat_area_or_below_face_gap_fill_known=False,
            maximum_unallocated_area_at_low_supply_mm2=smin-zmin*zmin/2,
            comparison_only_full_15mm_height_0p04mm_gap_area_mm2=.04*baseline["geometry"]["seat"]["thickness_mm"],
            scope="0.60 mm2 is the geometry of a fully filled 15 mm contact-height gap, not a predicted capillary penetration. It exceeds the low-supply allowance; neither gap fill nor parent-metal contribution is invented to close the account."),
        acceptance_joint_rules=[
            "At each actual qualified section in every stable 16 mm segment, both measured toes minus their actual expanded uncertainty are at least 3.80 mm.",
            "The whole actual contour plus outward measurement uncertainty lies within x>=0,y>=0,x+y<=4.30 mm. Checking only toe lengths is insufficient.",
            "Root-to-surface minimum distance minus its actual uncertainty is at least 2.6870057685 mm; effective throat additionally excludes unfused or unacceptable defect regions.",
            "For the specified concave-parabola family only, calculate its actual area/ratio/concavity with the saved analytic polynomial routine; satisfy both legs, exact minimum root distance and maximum coordinate sum jointly. No independent ratio/concavity manufacturing window is assigned.",
            "For a general surface use measured chord distance a0 and inward normal deviation c with a0-c-U>=2.6870057685 mm as a sufficient throat check. Actual profile area, under-face gap fill and start/end redistribution are recorded separately from total feed.",
            "Two-side continuous fusion, root remelt<=0.30 mm and the two-pass remelt union<=0.40 mm remain separate qualification targets. The 1 mm ends are not counted in the 128 mm capacity length."],
        decision=dict(proposed_action="Adopt this one allocation as the engineering-design pWPS candidate; do not assign a robust production forming window or fusion/performance qualification.",
            conditional_profile_geometry_feasible=True, actual_forming_window_verified=False,
            continuous_final_bilateral_fusion_verified=False, effective_throat_verified=False,
            remelt_limits_verified=False, manufacturing_residual_position_verified=False,
            extra_candidates_allowed_by_this_record=False),
        fixed_corners=corners,
        sources=["studies/COMPETITION-DESIGN/delivery_section_envelope.py",
            "studies/COMPETITION-DESIGN/results/section-forming-envelope-20261008.json",
            "deliverables/process/joint-process-card.json", "project/submission-baseline.yaml",
            "src/hanjie/domain/following_tools.py", "src/hanjie/domain/tooling_access.py:83",
            "cad/generated/engineering-supplements-20261007/pressure-interface-clearance.json"])


def write_markdown(r):
    old=r["original_comparison"]; nom=r["nominal"]; t=r["total_tolerance_ranges"]; heat=r["heat_ledger"]
    lines=["# 最终组焊一次根/盖分道供料修订", "", "日期：2026-10-08。保持8P-R2-t15、18 mm实际/16 mm稳定段、原两道姿态、Ø1.60±0.01 mm、1.65 mm/s±2%、沉积效率0.90～0.98和名义各道300 J/mm。只作一个分道修订及其固定公差角点算术；没有成形搜索、FE或工装重复核算。", "", "## 工程决定", "",
        "采用为设计pWPS候选的唯一新分道参数：**根道3.42±0.05、盖道3.78±0.05 mm/s**，设备设计分辨率仍≤0.01 mm/s。根道按已有名义焊脚2.80 mm三角截面、η名义0.94及原丝径/焊速反算，增加的供料放到盖道。两道平均3.60 mm/s，原3.68/r1.05/c0.080独立全窗口不再使用。",
        f"反算根道供丝{r['revision']['root_feed_reverse_from_nominal_2p8_triangle_mm_s']:.9f} mm/s，按0.01设定取3.42；名义根道等效脚{nom['passes']['root']['equivalent_equal_leg_mm']:.9f} mm。2.80是名义根道目标，下供料角点不保证等于2.80。根/盖数值是可执行设定；公差没有缩小，设备达到分辨率也不等于实际成形窗口获得资格。", "", "## 实际供料及截面结果", "",
        "| 项目 | 根道 | 盖道 |", "| --- | ---: | ---: |"]
    for key,label,unit in [("added_section_area_mm2","单道新增截面积","mm²"),("equivalent_equal_leg_mm","单道面积等效等腿","mm"),("wire_length_mm","实际耗丝","mm"),("consumed_mass_g","来丝质量","g"),("deposited_mass_g","沉积质量","g"),("entering_wire_enthalpy_J","进入丝焓","J")]:
        a=r['pass_tolerance_ranges']['root'][key];b=r['pass_tolerance_ranges']['cover'][key]
        lines.append(f"| {label}/{unit} | {a[0]:.6f}～{a[1]:.6f} | {b[0]:.6f}～{b[1]:.6f} |")
    lines += ["", f"32个固定公差角点（共用丝径、沉积效率和焊速，根/盖各自供丝偏差）得到两道S={t['total_section_area_mm2'][0]:.9f}～{t['total_section_area_mm2'][1]:.9f} mm²；原值{old['original_area_range_mm2'][0]:.9f}～{old['original_area_range_mm2'][1]:.9f}。理想等腿下端喉厚余量由{old['original_equal_leg_throat_margin_um']:.3f}增至{old['revised_equal_leg_minimum_throat_margin_um']:.3f} μm；能分配给非喉部面积的最低余量由{old['original_unallocated_area_margin_mm2']:.9f}增至{old['revised_unallocated_area_margin_mm2']:.9f} mm²。", "",
        f"名义耗丝{old['revised_nominal_wire_mm']:.9f} mm，15%备料{old['revised_15pct_preparation_wire_mm']:.9f} mm；较原多{old['extra_nominal_wire_mm']:.9f} mm。名义来丝{nom['total_consumed_wire_mass_g']:.9f} g（η不改变来丝质量）；全部公差耗丝{t['total_consumed_wire_mm'][0]:.6f}～{t['total_consumed_wire_mm'][1]:.6f} mm、来丝{t['total_consumed_wire_mass_g'][0]:.6f}～{t['total_consumed_wire_mass_g'][1]:.6f} g。稳定16 mm内供料只有在局部分配、轮廓及熔合均获约束后才计有效喉部；不以全件质量替代局部验收。", "", "## 面积相关的联合轮廓验收集合", "",
        "复用原解析函数：直线S=z₁z₂/2，r=z长/z短≥1，a₀=√[2S/(r+1/r)]。直线轮廓的条件联合上界r≤min{2S/3.80²，4.30²/(2S)，由a₀≥2.687006解出的喉部界}。这个界随实际截面积改变，不声明一个独立小脚长比制造窗口。", "",
        "对既有固定面积凹面族P(t)=(1−t)(z₁,0)+t(0,z₂)−4ct(1−t)n，S=z₁z₂/2−(2/3)c√(z₁²+z₂²)。每个实际S、r、c均联合检验两脚、三次驻点求得的最短根距及二次轮廓x+y最大值。没有从枪偏±0.05推定脚差或凹度。等腿凹面上界由喉部和4.30包络反算，不能彼此独立取极值。", "",
        "| 固定供料面积角点/mm² | 直线联合r上界 | 等腿凹面联合c上界/mm | 主要约束 |", "| ---: | ---: | ---: | --- |"]
    for b in r["contour_joint_geometry_bounds"]:
        dominant="最低喉部" if b["equal_leg_concavity_limit_from_throat_mm"]<b["equal_leg_concavity_limit_from_triangle_mm"] else "x+y≤4.30"
        lines.append(f"| {b['area_mm2']:.9f} | {b['straight_joint_ratio_limit']:.9f} | {b['equal_leg_joint_concavity_limit_mm']:.9f} | {dominant} |")
    lines += ["", "上述两端都有满足几何条件的轮廓，证明一次修订具有几何可行性；它不保证所有实际轮廓或整个制造波动窗口通过。焊趾、凹陷和截面积必须联合验收；测量不确定度依实际方法资格扣除。双脚均≥3.80、最短几何喉部≥2.687006且全自由面x+y≤4.30，仍不自动成为有效喉部。", "",
        "全接触高度15 mm、最大间隙0.04 mm完全充填的几何面积为0.600000 mm²，高于本修订最低非喉部面积余量；这是下流填料的几何对照，未预测真实毛细渗入15 mm。实际间隙填入、母材熔化参与、端区迁移与局部成形分配未获量化，不能任意设为零，也不能假设母材补料来制造通过。", "", "## 原热账内的进入焓", "",
        f"沿用已存NiFe55工程输入ρ={heat['density_kg_m3']:.0f} kg/m³、H20→1470℃={heat['entering_specific_enthalpy_J_kg']/1e6:.6f} MJ/kg；未新增高温物性来源。名义两道净热仍86.400 kJ、174.545455 s纯弧时间；公差速度下实际净热{t['total_net_energy_J'][0]/1000:.6f}～{t['total_net_energy_J'][1]/1000:.6f} kJ。", "",
        f"名义尺寸、η0.90～0.98下两道进入丝焓{heat['nominal_total_entering_wire_enthalpy_at_eta_edges_J'][0]/1000:.6f}～{heat['nominal_total_entering_wire_enthalpy_at_eta_edges_J'][1]/1000:.6f} kJ；新增{heat['extra_entering_wire_enthalpy_at_eta_edges_J'][0]:.6f}～{heat['extra_entering_wire_enthalpy_at_eta_edges_J'][1]:.6f} J，约{heat['extra_entering_wire_enthalpy_per_actual_total_path_J_mm'][0]:.6f}～{heat['extra_entering_wire_enthalpy_per_actual_total_path_J_mm'][1]:.6f} J/mm实际两道总路径。净热减去进入丝焓后，η由0.90增至0.98时余热由{heat['nominal_parent_pool_and_loss_remainder_at_eta_edges_J'][0]/1000:.6f}降至{heat['nominal_parent_pool_and_loss_remainder_at_eta_edges_J'][1]/1000:.6f} kJ，分配给母材/熔池及损失；不是另加焊丝焓。正余量不证明双侧熔合。", "",
        "根道供料下降意味着同电弧净功率下用于升温/熔化根道焊丝的份额降低，不能宣称根部熔深必然减小；盖道增加供料改变二次重热与再熔化。必须重新约束双侧熔合、0.30 mm根道/0.40 mm两道时域并集及制造残余响应。", "", "## 工装可达与重熔留层", "",
        f"只改变供丝指令，Ø1.60棒、枪/丝实体、根道R74.50/z117.30与盖道R74.00/z118.00、棒端R73.20/z116.00和R72.70/z116.70及150 mm退位均不变。复用已有{r['tooling_reuse']['checked_poses_reused']}姿态核算，名义最小净隙{r['tooling_reuse']['nominal_minimum_gap_mm']:.9f} mm，扣0.65后{r['tooling_reuse']['lower_bound_gap_mm']:.9f} mm；未重跑工装计算。复用前提是实际沉积轮廓完整位于原4.30三角禁入体内。", "",
        f"公差CAD的平直第二层≥{r['layer_survival']['minimum_second_before_final_mm']:.2f} mm。保持根道≤0.30、两道重熔并集≤0.40的设计目标时，条件第二层余≥{r['layer_survival']['conditional_second_after_final_mm']:.2f}、总余≥{r['layer_survival']['conditional_total_after_final_mm']:.2f} mm。这些是几何预算；没有新物理重熔解或最小冶金安全厚度证据。实际熔合/重熔及冷态制造状态仍未取得资格，故不进行位置度达标预测。", "", "## 运行与结果身份", "",
        "已实际运行本脚本，JSON保留32个固定公差角点、两个解析边界、每道质量/焓和既有来源引用。结果身份：一次分道工艺设计修订；几何条件可行，生产成形全窗口、有效喉部、双侧连续熔合、留层冶金资格和完全卸夹残余均未获得验证。", ""]
    lines += [f"- `{s}`" for s in r["sources"]]
    (OUT/f"{NAME}.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def main():
    r=calculate()
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/f"{NAME}.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write_markdown(r)
    print(json.dumps({k:r[k] for k in ["revision","pass_tolerance_ranges","total_tolerance_ranges","original_comparison","decision"]},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
