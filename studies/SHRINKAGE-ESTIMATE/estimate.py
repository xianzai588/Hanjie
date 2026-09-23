"""角焊缝自由横向收缩的一阶筛查，并列公开钢焊缝比较值。"""
from pathlib import Path
import json
import math


ROOT = Path(__file__).resolve().parents[2]

n = 6
segment_length_mm = 18.0
plate_thickness_mm = 5.0
fillet_leg_mm = 3.5
weld_area_mm2 = fillet_leg_mm**2 / 2.0
machining_allowance_mm = 0.20
angular_margin_mm = 0.05
twi_transverse_mm_per_weld = 0.80
twi_sigma = 0.20

r1_k = (0.20, 0.50)
r2_beta = (0.08, 0.18)
r1_mm = tuple(k * weld_area_mm2 / plate_thickness_mm for k in r1_k)
r2_mm = tuple(beta * fillet_leg_mm for beta in r2_beta)
envelope_mm = (min(r1_mm[0], r2_mm[0]), max(r1_mm[1], r2_mm[1]))
delta_points_mm = (0.25, 0.45, 0.65)
sigma_points = (0.02, 0.05, 0.10, 0.20)


def residual_mm(delta_mm: float, sigma: float) -> float:
    """六翼等刚度、刚性中心环的刚体平均位移筛查值。"""
    return 2.0 * sigma * delta_mm / math.sqrt(n)


def allowance_screen(name: str, delta_mm: float, sigma: float) -> dict:
    residual = residual_mm(delta_mm, sigma)
    required = 1.25 * residual + angular_margin_mm
    return {
        "scenario": name,
        "free_shrinkage_mm_per_segment": delta_mm,
        "relative_asymmetry_sigma": sigma,
        "estimated_asymmetric_residual_mm": round(residual, 6),
        "angular_distortion_margin_mm": angular_margin_mm,
        "required_radial_allowance_mm": round(required, 6),
        "available_radial_allowance_mm": machining_allowance_mm,
        "arithmetic_fit": required <= machining_allowance_mm,
        "evidence_status": "unvalidated screening calculation",
    }


def main() -> Path:
    grid = {
        f"d{delta:g}_s{sigma:g}": round(residual_mm(delta, sigma), 5)
        for delta in delta_points_mm
        for sigma in sigma_points
    }
    allowance_rows = [
        allowance_screen("内部筛查上界δ=0.65，σ=0.20", 0.65, 0.20),
        allowance_screen("TWI钢焊缝比较值δ=0.80，σ=0.20", twi_transverse_mm_per_weld, twi_sigma),
    ]
    payload = {
        "version": "SHRINKAGE-ESTIMATE-2",
        "evidence_level": "literature_order_screening",
        "geometry": {
            "segments": n,
            "segment_length_mm": segment_length_mm,
            "plate_thickness_mm": plate_thickness_mm,
            "fillet_leg_mm": fillet_leg_mm,
            "equal_area_fillet_section_mm2": weld_area_mm2,
        },
        "relations": {
            "R1_delta = k*A_w/t": {
                "A_w_mm2": weld_area_mm2,
                "t_mm": plate_thickness_mm,
                "k": list(r1_k),
                "result_mm_per_segment": list(r1_mm),
                "coefficient_status": "工程筛查假设，非所列文献已核实系数",
                "literature_to_verify": [
                    "10.1115/OMAE2002-28181",
                    "10.2478/pomr-2025-0027",
                ],
            },
            "R2_delta = beta*z": {
                "z_mm": fillet_leg_mm,
                "beta": list(r2_beta),
                "result_mm_per_segment": list(r2_mm),
                "coefficient_status": "工程筛查假设，非所列文献已核实系数",
                "literature_to_verify": [
                    "10.1115/OMAE2002-28181",
                    "10.2478/pomr-2025-0027",
                    "10.22486/iwj.v15i4.148501",
                ],
            },
            "TWI transverse fillet-weld shrinkage comparator": {
                "value_mm_per_weld": twi_transverse_mm_per_weld,
                "condition": "weld leg <= 0.75 * plate thickness",
                "condition_met": fillet_leg_mm <= 0.75 * plate_thickness_mm,
                "source_scope": "TWI rule of thumb for steel welding",
                "project_material_scope_match": False,
                "use": "comparative stress screen only; not a validated coefficient for the QT450-10/Q235B joint",
            },
        },
        "free_transverse_shrinkage_per_segment_mm": [
            round(envelope_mm[0], 4), round(envelope_mm[1], 4)
        ],
        "residual_model": "U = 2*sigma*delta/sqrt(n); 六翼等刚度并联、刚性中心环",
        "sigma_definition": "六段自由收缩量的相对均方根离散度",
        "asymmetry_sigma_basis": (
            "径向间隙0.01~0.04mm(均值0.025、相对极差60%)会改变各段熔合边界与热路径；"
            "按四分之一传递的工程假设取sigma约0.15，未实测"
        ),
        "delta_sensitivity_points_mm": list(delta_points_mm),
        "sigma_sensitivity_points": list(sigma_points),
        "residual_grid_mm": grid,
        "machining_allowance_screen": {
            "formula": "required_radial_allowance = 1.25 * (2*sigma*delta/sqrt(n)) + angular_margin",
            "angular_margin_mm": angular_margin_mm,
            "available_radial_allowance_mm": machining_allowance_mm,
            "scenarios": allowance_rows,
            "closure_status": "not_closed_due_to_exceedance_in_external_comparison_and_unvalidated_inputs",
        },
        "combined_offset_screen_with_angular_distortion_mm": [0.02, 0.16],
        "combined_offset_evidence_status": "unvalidated engineering screen; not simulation or measurement",
        "decision": "0.20 mm径向加工余量未闭合；TWI钢焊缝比较情景需要0.213 mm，当前值短缺约0.013 mm。须用接头试验/实测或兼容的余量与工装重设计关闭。",
        "literature_to_verify": [
            "10.1115/OMAE2002-28181",
            "10.2478/pomr-2025-0027",
            "10.22486/iwj.v15i4.148501",
        ],
        "citation_boundary": (
            "TWI的0.8 mm/焊经验规则针对钢焊缝，虽满足焊脚/板厚几何条件，但材料为球铁—钢异种接头，"
            "仅作为比较压力筛查；k与beta区间仍是工程假设，未由所列论文原文核实"
        ),
    }
    out = ROOT / "studies/SHRINKAGE-ESTIMATE/results/estimate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)
    return out


if __name__ == "__main__":
    main()
