"""由权威几何、工艺和材料配置推导接头成形与耗材口径。"""

from __future__ import annotations

import math
from typing import Any, Dict

from hanjie.domain.baseline import get_baseline,get_materials,get_process


def joint_design_metrics() -> Dict[str,Any]:
    baseline = get_baseline()
    process = get_process()["process"]
    nominal = process["nominal"]
    rule = process["joint_consistency"]
    target_leg = float(rule["design_fillet_leg_mm"])
    wire_area = math.pi*float(nominal["filler_diameter_mm"])**2/4
    efficiency = float(rule["deposition_efficiency_nominal"])
    deposited_area = wire_area*float(nominal["filler_feed_rate_mm_s"])/float(nominal["travel_speed_mm_s"])*efficiency
    target_area = target_leg**2/2
    equivalent_leg = math.sqrt(2*deposited_area)
    segment_count = int(baseline["geometry"]["primary_layout_points"])
    segment_length = float(baseline["geometry"]["weld_segment_length_mm"])
    total_length = segment_count*segment_length
    density_kg_m3 = float(get_materials()["materials"]["ernife_ci"]["nominal_properties_20c"]["density_kg_m3"])
    required_feed = target_area*float(nominal["travel_speed_mm_s"])/wire_area
    lower_efficiency = min(map(float,rule["deposition_efficiency_range"]))
    scenarios = {}
    for scenario_id, scenario in rule["scenarios"].items():
        pass_count = int(scenario["pass_count"])
        if scenario_id == "current_single_pass_diagnostic":
            area_per_pass = deposited_area
            feed_range = [float(nominal["filler_feed_rate_mm_s"])] * 2
        else:
            area_per_pass = target_area / pass_count
            # 按沉积效率边界反算区间，避免把体积核算值误写成单一工艺设定。
            feed_range = [
                area_per_pass * float(nominal["travel_speed_mm_s"]) / wire_area,
                area_per_pass * float(nominal["travel_speed_mm_s"]) / (wire_area * lower_efficiency),
            ]
        total_area = area_per_pass * pass_count
        scenarios[scenario_id] = {
            **scenario,
            "area_per_pass_mm2": area_per_pass,
            "total_deposited_area_mm2": total_area,
            "equivalent_ideal_fillet_leg_mm": math.sqrt(2 * total_area),
            "wire_feed_range_mm_s": feed_range,
            "total_arc_energy_per_weld_length_j_mm": float(nominal["heat_input_j_per_mm"]) * pass_count,
            "total_retained_filler_volume_mm3": total_area * total_length,
            "total_retained_filler_mass_g": total_area * total_length * density_kg_m3 / 1e6,
            "load_basis_status": "pending",
            "macrosection_status": "pending",
            "wps_status": "not_available",
        }
    return {
        "evidence_level":"design_assumption",
        "closure_status":rule["closure_status"],
        "design_target":{"fillet_leg_mm":target_leg,"ideal_triangular_area_mm2":target_area,"basis":rule["design_basis"]},
        "nominal_wire_deposition":{
            "wire_diameter_mm":float(nominal["filler_diameter_mm"]),
            "wire_feed_mm_s":float(nominal["filler_feed_rate_mm_s"]),
            "travel_speed_mm_s":float(nominal["travel_speed_mm_s"]),
            "deposition_efficiency":efficiency,
            "area_per_weld_length_mm2":deposited_area,
            "equivalent_ideal_fillet_leg_mm":equivalent_leg,
            "target_area_fraction":deposited_area/target_area,
        },
        "primary_6p_layout":{
            "segment_count":segment_count,"segment_length_mm":segment_length,"total_weld_length_mm":total_length,
            "nominal_wire_length_mm":total_length*float(nominal["filler_feed_rate_mm_s"])/float(nominal["travel_speed_mm_s"]),
            "nominal_retained_filler_volume_mm3":deposited_area*total_length,
            "nominal_retained_filler_mass_g":deposited_area*total_length*density_kg_m3/1e6,
            "design_target_external_volume_mm3":target_area*total_length,
            "design_target_filler_equivalent_mass_g":target_area*total_length*density_kg_m3/1e6,
        },
        "diagnostic_only_feed_for_target":{
            "at_100pct_efficiency_mm_s":required_feed,
            "at_min_declared_efficiency_mm_s":required_feed/lower_efficiency,
            "usage":"仅量化缺口，未经成形、热输入和承载验证，不得直接写入 WPS",
        },
        "design_scenarios":scenarios,
        "release_boundary":rule["rule"],
    }
