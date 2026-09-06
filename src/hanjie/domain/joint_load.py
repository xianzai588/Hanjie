"""基于 CAD 有效焊长的参数化焊缝组承载筛查。"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import yaml


def _segment_integrals(radius_mm: float, segments: list[dict[str, Any]]) -> tuple[float, np.ndarray]:
    length = 0.0
    inertia = np.zeros((2,2),float)
    for segment in segments:
        lo,hi = np.deg2rad([segment["start_angle_deg"],segment["end_angle_deg"]])
        if hi<=lo:
            hi += 2*np.pi
        length += radius_mm*(hi-lo)
        sin2 = (hi-lo)/2-(np.sin(2*hi)-np.sin(2*lo))/4
        cos2 = (hi-lo)/2+(np.sin(2*hi)-np.sin(2*lo))/4
        sincos = (np.sin(hi)**2-np.sin(lo)**2)/2
        inertia += radius_mm**3*np.array([[sin2,-sincos],[-sincos,cos2]])
    return length,inertia


def evaluate_layout(manifest: dict[str, Any], legs_mm: list[float], envelope: dict[str, list[float]], throat_factor: float) -> dict[str, Any]:
    radius = float(manifest["seat"]["outer_radius_mm"])
    length,inertia = _segment_integrals(radius,manifest["manufacturing"]["weld_segments"])
    principal = np.linalg.eigvalsh(inertia)
    maximum_force = math.hypot(float(envelope["radial_force_n"][1]),float(envelope["axial_force_n"][1]))
    maximum_moment = float(envelope["overturning_moment_n_mm"][1])
    rows = []
    for leg in legs_mm:
        throat = throat_factor*float(leg)
        area = throat*length
        force_coefficient = math.sqrt(3.0)/area
        moment_coefficient = radius/(throat*float(principal[0]))
        corner_stress = math.hypot(force_coefficient*maximum_force,moment_coefficient*maximum_moment)
        rows.append({
            "fillet_leg_mm":float(leg),
            "effective_throat_mm":throat,
            "effective_throat_area_mm2":area,
            "von_mises_per_resultant_force_mpa_per_n":force_coefficient,
            "worst_overturning_stress_mpa_per_n_mm":moment_coefficient,
            "reference_envelope_corner_required_allowable_mpa":corner_stress,
            "force_capacity_n_per_allowable_mpa":1.0/force_coefficient,
            "moment_capacity_n_mm_per_allowable_mpa":1.0/moment_coefficient,
        })
    return {
        "model_id":manifest["model_id"],
        "effective_weld_length_mm":length,
        "cad_effective_weld_length_mm":manifest["manufacturing"]["cad_measured_total_weld_length_mm"],
        "line_group_principal_second_moments_mm3":principal.tolist(),
        "line_group_isotropy_ratio":float(principal[0]/principal[1]),
        "rows":rows,
    }


def build_load_basis(root: Path) -> dict[str, Any]:
    config = yaml.safe_load((root/"project/load-basis-v1.yaml").read_text(encoding="utf-8"))
    layouts = {}
    for name,path in config["layouts"].items():
        manifest = json.loads((root/path).read_text(encoding="utf-8"))
        layouts[name] = evaluate_layout(manifest,config["weld_legs_mm"],config["reference_envelope"],float(config["effective_throat_factor"]))
    process = yaml.safe_load((root/"project/process.yaml").read_text(encoding="utf-8"))["process"]["nominal"]
    costs = {}
    for name,row in layouts.items():
        length = row["effective_weld_length_mm"]
        costs[name] = {
            "single_pass_arc_time_s":length/float(process["travel_speed_mm_s"]),
            "four_pass_arc_time_s":4*length/float(process["travel_speed_mm_s"]),
            "single_pass_net_heat_input_j":length*float(process["heat_input_j_per_mm"]),
            "four_pass_net_heat_input_j":4*length*float(process["heat_input_j_per_mm"]),
        }
    static = json.loads((root/"simulation/structural-v4/results/static-screening/static-screening-analysis.json").read_text(encoding="utf-8"))
    radial_reference = float(config["reference_envelope"]["radial_force_n"][1])
    radial_response = {}
    for row in static["ranking"]:
        if row["model_id"] in layouts:
            radial_response[row["model_id"]] = {
                "compliance_mm_per_n":row["fine_average_compliance_mm_per_n"],
                "reference_envelope_radial_displacement_mm":row["fine_average_compliance_mm_per_n"]*radial_reference,
                "source_evidence_level":static["evidence_level"],
                "limitation":"既有座体径向静力筛查未显式建模焊缝，不能证明焊脚承载能力",
            }
    return {
        "stage":"LOAD-BASIS-0 / JOINT-BASIS-0",
        "evidence_level":config["evidence_level"],
        "reference_envelope":config["reference_envelope"],
        "allowable_stress_sensitivity_mpa":config["allowable_stress_sensitivity_mpa"],
        "model":config["model"],
        "layouts":layouts,
        "process_costs":costs,
        "existing_radial_static_screening":radial_response,
        "fatigue_boundary":config["fatigue_boundary"],
        "decision":{
            "three_point_five_mm_necessary":None,
            "reason":"参考包络下3.5 mm可降低条件应力并增加裕量，但题面载荷、真实焊缝许用和疲劳谱缺失，不能证明它是唯一必要尺寸。",
            "current_1p737_limitation":"容量与焊脚近似成正比；在同一焊长下，其力/力矩容量约为3.5 mm情景的49.6%。",
            "four_pass_disposition":"保留为待真实载荷与成形验证的上界候选，不升级为推荐工艺。",
        },
    }
