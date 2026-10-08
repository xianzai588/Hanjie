"""A small compatibility model for choosing symmetric-weld control targets.

Eight equal radial channels represent the annular seat. Opposing channel
shrinkage differences are design inputs, not measured temperatures or a
thermal-plastic solution. The triangle inequality gives a conservative
translation bound within this explicitly stated spring model.
"""
from pathlib import Path
import json
import math

ROOT = Path(__file__).resolve().parents[2]


def calculate():
    length = 74.98 - 20.0
    alpha = 12e-6  # /K, design approximation for QT; not a fitted property.
    allowance = 12e-3  # mm, internal target within the 13.5 um budget.
    unit_sensitivity = 2 * alpha * length
    return {
        "physical_object": "complete-ring simplified eight-channel compatibility model",
        "model_role": "historical analytical interpretation; active control window uses explicit FE response kernels",
        "assumptions": {
            "channel_count": 8,
            "equal_radial_stiffness": True,
            "small_displacement": True,
            "radial_length_mm": length,
            "thermal_expansion_per_k": alpha,
        },
        "equilibrium": "u = (1/4) sum_j alpha L DeltaT_pair,j n_j; j=1..4",
        "conservative_model_bound": "position_diameter <= 2 alpha L max(abs(DeltaT_pair))",
        "position_diameter_per_equivalent_pair_kelvin_um": unit_sensitivity * 1000,
        "actual_residual_position_predicted": False,
        "internal_position_target_um": allowance * 1000,
        "maximum_equivalent_difference_for_target_k": allowance / (2 * alpha * length),
        "process_inputs": {
            "opposing_sequence": [1, 5, 3, 7, 2, 6, 4, 8],
            "per_segment_online_energy_deviation_pct": 2,
            "measured_temperature_role": "interpass and opposing-point control inputs; not DeltaT_eq itself",
        },
        "decision": "Use opposing short segments and energy/temperature monitoring. Relate their settings to effective shrinkage by the same-part trial evaluation; do not substitute this bound for actual residual position.",
    }


if __name__ == "__main__":
    output = ROOT / "studies/COMPETITION-DESIGN/results/ring-control-screening.json"
    output.write_text(json.dumps(calculate(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
