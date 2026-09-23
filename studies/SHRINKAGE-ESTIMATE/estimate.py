"""角焊缝自由横向收缩的一阶包络筛查；系数仍需原文核验。"""
from pathlib import Path
import json
import math


ROOT = Path(__file__).resolve().parents[2]

n = 6
segment_length_mm = 18.0
plate_thickness_mm = 5.0
fillet_leg_mm = 3.5
weld_area_mm2 = fillet_leg_mm**2 / 2.0
historical_allowance_mm = 0.0102

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


def main() -> Path:
    grid = {
        f"d{delta:g}_s{sigma:g}": round(residual_mm(delta, sigma), 5)
        for delta in delta_points_mm
        for sigma in sigma_points
    }
    exceeds = {key: value > historical_allowance_mm for key, value in grid.items()}
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
        "historical_allowance_comparison_mm": historical_allowance_mm,
        "residual_grid_mm": grid,
        "exceeds_historical_0p0102_mm": exceeds,
        "combined_offset_screen_with_angular_distortion_mm": [0.02, 0.16],
        "angular_distortion_screen_mm": 0.05,
        "machining_allowance_radial_mm": 0.20,
        "decision": "焊后终加工为主路线；焊序与夹具用于降低余量需求，不宣称焊接直接达到位置度限值",
        "literature_to_verify": [
            "10.1115/OMAE2002-28181",
            "10.2478/pomr-2025-0027",
            "10.22486/iwj.v15i4.148501",
        ],
        "citation_boundary": (
            "文献用于变形机理、计算方法或相近接头背景；k与beta区间尚未由原文核实，"
            "不得写成文献直接给出的系数"
        ),
    }
    out = ROOT / "studies/SHRINKAGE-ESTIMATE/results/estimate.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)
    return out


if __name__ == "__main__":
    main()
