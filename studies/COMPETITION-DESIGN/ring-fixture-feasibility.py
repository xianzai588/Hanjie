"""Cold equivalent-beam sizing for the ring-baseline fixture load path.

The calculation sizes a short steel load member. It does not represent a full
fixture FE model, contact compliance, thermal motion or measured positioning.
All four bending translation/rotation terms and transverse shear are retained.
"""
from __future__ import annotations

import json
from pathlib import Path


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
        "design_identity": "SUBMISSION-RING-20261008",
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


if __name__ == "__main__":
    result = evaluate()
    result["initial_section_width_60mm"] = evaluate(60.0)
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({
        "result_file": str(DESTINATION.relative_to(ROOT)),
        "complete_axis_displacement_um": result["complete_cantilever_axis_displacement_um"],
        "remaining_budget_um": result["remaining_contact_connection_base_budget_um"],
    }, ensure_ascii=False))
