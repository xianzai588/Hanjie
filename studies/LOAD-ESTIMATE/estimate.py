"""往复压缩机载荷、倾覆力矩与应力比的一阶筛查。"""
from pathlib import Path
import json
import math


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent / "results/load-estimate.json"

INPUTS = {
    "reciprocating_mass_kg": 0.8,
    "crank_radius_m": 0.02,
    "speed_rpm": 3000.0,
    "rod_ratio": 0.25,
    "bore_diameter_m": 0.04,
    "pressure_difference_pa": 1.5e6,
    "force_line_to_weld_centroid_m": 0.07,
}
REFERENCE = {"radial_force_n": 5000.0, "axial_force_n": 5000.0, "moment_n_mm": 250000.0}


def calculate() -> dict:
    m = INPUTS["reciprocating_mass_kg"]
    crank_radius = INPUTS["crank_radius_m"]
    omega = 2.0 * math.pi * INPUTS["speed_rpm"] / 60.0
    # 按指定R口径，往复惯性只取完全反向的基频幅值；连杆二阶项未纳入筛查。
    inertial = m * crank_radius * omega**2
    gas = math.pi * INPUTS["bore_diameter_m"]**2 * INPUTS["pressure_difference_pa"] / 4.0

    # 两个独立载荷源按平方和合成，与说明书§3的合力口径一致。
    radial = math.hypot(inertial, gas)
    axial = gas
    moment_nm = (
        inertial * INPUTS["force_line_to_weld_centroid_m"]
        + gas * crank_radius / 2.0
    )
    moment_n_mm = moment_nm * 1000.0
    interaction = math.sqrt(
        (radial / REFERENCE["radial_force_n"]) ** 2
        + (axial / REFERENCE["axial_force_n"]) ** 2
        + (moment_n_mm / REFERENCE["moment_n_mm"]) ** 2
    )

    # 同向、相位未知时叠加载荷极值：惯性[-Fi,+Fi]，气体[0,Fg]。
    combined_min = -inertial
    combined_max = inertial + gas
    return {
        "version": "LOAD-ESTIMATE-3",
        "evidence_level": "parameterized_first_order_screening",
        "inputs": INPUTS,
        "reference": REFERENCE,
        "formulas": {
            "omega": "2*pi*n/60",
            "inertial_force_amplitude": "m*r*omega^2; 忽略连杆二阶项",
            "gas_force": "pi*D^2*delta_p/4",
            "radial_force": "sqrt(F_i^2+F_g^2)",
            "tipover_moment": "F_i*e + F_g*(r/2)",
            "reference_interaction": "sqrt((Fr/5000)^2+(Fa/5000)^2+(M/250000)^2)",
            "combined_R": "Fmin/Fmax; 同向极值保守叠加，未建模相位",
        },
        "stress_ratio_R": {
            "inertial": -1.0,
            "gas": 0.0,
            "combined": combined_min / combined_max,
            "combined_force_min_n": combined_min,
            "combined_force_max_n": combined_max,
        },
        "results": {
            "inertial_force_n": inertial,
            "gas_force_n": gas,
            "radial_force_n": radial,
            "axial_force_n": axial,
            "tipover_moment_n_mm": moment_n_mm,
            "reference_moment_n_mm": REFERENCE["moment_n_mm"],
            "reference_interaction_ratio": interaction,
        },
        "interpretation": (
            "参数化一阶筛查；按平方和合成径向载荷，并以Fi*e+Fg*(r/2)估倾覆力矩。"
            "惯性项R=-1、气体项R≈0；同向极值叠加后的R为非对称值。"
            "载荷幅值、相位、连杆二阶项及支承偏心仍须由实际机型数据验证。"
        ),
    }


def main() -> Path:
    payload = calculate()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    main()
