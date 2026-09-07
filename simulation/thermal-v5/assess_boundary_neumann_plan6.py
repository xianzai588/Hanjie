"""评估 Plan 6 显式边界 Neumann 的条件 F/VF 对照。"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from analyze_xsec_refinement_study import field_pair, history_pair
from analyze_nested_refinement_study import interface_pair, nesting_pair
from run_physics03 import ROOT, load, write_json


SPEC = ROOT / "project/thermal-boundary-neumann-v5.7.yaml"
RESULTS = ROOT / "simulation/thermal-v5/results/boundary-neumann-plan6"


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_assessment():
    plan = load(SPEC); rules = plan["acceptance"]
    low_dir, high_dir = RESULTS / "NEST-F", RESULTS / "NEST-VF"
    low_summary, high_summary = _read(low_dir / "summary.json"), _read(high_dir / "summary.json")
    with np.load(low_dir / "field.npz") as low_field:
        field = field_pair(low_dir / "field.npz", high_dir / "field.npz", low_summary, high_summary, rules)
        interface = interface_pair(low_dir, high_dir, low_field, rules)
    histories = history_pair(low_dir / "fixed-point-reconstructed-history.json", high_dir / "fixed-point-reconstructed-history.json", rules)
    low_faces, high_faces = _read(low_dir / "boundary-neumann-ledger.json"), _read(high_dir / "boundary-neumann-ledger.json")
    base = load(ROOT / plan["baseline"]); config = load(ROOT / base["inputs"]); source = config["heat_source"]
    longitudinal_peak = 2 * np.sqrt(3) / np.sqrt(np.pi) * max(source["front_fraction"], source["rear_fraction"]) / (source["front_fraction"] * source["a_front_mm"] + source["rear_fraction"] * source["a_rear_mm"])
    transverse_peak = np.sqrt(3 / np.pi) / source["b_radial_mm"]
    theoretical_peak = config["process"]["net_power_w"] * longitudinal_peak * transverse_peak / np.sqrt(2)
    centroid_distance = float(np.linalg.norm(np.asarray(high_faces["energy_weighted_centroid_s_n_z_mm"]) - np.asarray(low_faces["energy_weighted_centroid_s_n_z_mm"])))
    moment_relative = float(np.linalg.norm(np.asarray(high_faces["energy_weighted_covariance_mm2"]) - np.asarray(low_faces["energy_weighted_covariance_mm2"])) / max(np.linalg.norm(np.asarray(low_faces["energy_weighted_covariance_mm2"])), 1e-12))
    field_checks = [value for row in field.values() for value in row.get("checks", {}).values()]
    history_checks = [value for row in histories.values() for value in row.get("checks", {}).values()]
    p95 = float(field["ernife_ci"]["volume_weighted_p95_abs_peak_difference_c"])
    mae = float(field["ernife_ci"]["volume_weighted_mean_abs_peak_difference_c"])
    conditional_m = bool(p95 < rules["field_volume_weighted_p95_limit_c"] and mae < rules["field_volume_weighted_mae_limit_c"] and all(history_checks))
    lower_peak = max((row["maximum_face_average_flux_w_per_mm2"] for row in low_faces["steps"]), default=0.0)
    upper_peak = max((row["maximum_face_average_flux_w_per_mm2"] for row in high_faces["steps"]), default=0.0)
    lower_patch_energy = sum(row["fixed_physical_patch_power_w"] for row in low_faces["steps"]) * 0.1
    upper_patch_energy = sum(row["fixed_physical_patch_power_w"] for row in high_faces["steps"]) * 0.1
    legacy_equivalence = {}
    for level, directory in (("NEST-F", low_dir), ("NEST-VF", high_dir)):
        legacy_path = ROOT / "simulation/thermal-v5/results/nested-refinement-study" / level / "field.npz"
        with np.load(legacy_path) as old, np.load(directory / "field.npz") as new:
            legacy_equivalence[level] = {
                "maximum_abs_peak_field_difference_c": float(np.max(np.abs(old["temperature_peak"] - new["temperature_peak"]))),
                "maximum_abs_final_field_difference_c": float(np.max(np.abs(old["temperature_final"] - new["temperature_final"]))),
            }
    return {
        "stage": plan["version"], "evidence_level": plan["evidence_level"],
        "comparison": "NEST-F_to_NEST-VF", "mesh_nesting": nesting_pair(low_dir / "field.npz", high_dir / "field.npz"),
        "continuous_peak_field": field, "fixed_physical_point_histories": histories, "interface_flux": interface,
        "boundary_neumann": {
            "lower_total_face_energy_j": low_faces["total_face_energy_j"], "upper_total_face_energy_j": high_faces["total_face_energy_j"],
            "lower_fixed_physical_patch_energy_j": lower_patch_energy, "upper_fixed_physical_patch_energy_j": upper_patch_energy,
            "fixed_physical_patch_energy_relative_difference": float(abs(upper_patch_energy - lower_patch_energy) / max(abs(lower_patch_energy), abs(upper_patch_energy), 1e-12)),
            "centroid_distance_mm": centroid_distance, "second_moment_relative_difference": moment_relative,
            "theoretical_gaussian_peak_face_normal_flux_w_mm2": float(theoretical_peak),
            "lower_peak_face_average_flux_w_mm2": lower_peak, "upper_peak_face_average_flux_w_mm2": upper_peak,
            "lower_relative_error_to_theoretical_peak": float(abs(lower_peak / theoretical_peak - 1)),
            "upper_relative_error_to_theoretical_peak": float(abs(upper_peak / theoretical_peak - 1)),
            "peak_face_average_moves_toward_theory": bool(abs(upper_peak / theoretical_peak - 1) < abs(lower_peak / theoretical_peak - 1)),
            "legacy_cell_volume_density_gate": False,
        },
        "legacy_rhs_equivalence": {
            "comparison": "Plan 5按控制体聚合的面功率与Plan 6显式面对象散射到控制体RHS",
            "levels": legacy_equivalence,
            "machine_precision_equivalent": all(max(row.values()) < 1e-9 for row in legacy_equivalence.values()),
        },
        "gate_components": {"continuous_field": all(field_checks), "fixed_histories": all(history_checks), "interface_flux": all(value for row in interface.values() for value in row["checks"].values())},
        "spatial_gate_pass": False,
        "new_nest_m_allowed": conditional_m, "nest_xf_allowed": False, "time_step_recheck_allowed": False,
        "formal_struct_0_allowed": False,
        "decision": "运行同算法新NEST-M，形成三层序列后再裁决。" if conditional_m else "F/VF仍未满足预登记门槛；停止自研求解器继续细化，准备成熟FE/FVM独立参考解。",
    }


def main():
    result = build_assessment()
    write_json(RESULTS / "assessment.json", result)
    field = result["continuous_peak_field"]["ernife_ci"]
    worst_rms = max(row["rms_same_time_difference_c"] for row in result["fixed_physical_point_histories"].values())
    lines = ["# THERMAL-0.7 显式边界 Neumann 准入", "", f"NiFe F→VF：P95 `{field['volume_weighted_p95_abs_peak_difference_c']:.3f} °C`，MAE `{field['volume_weighted_mean_abs_peak_difference_c']:.3f} °C`；固定点最差 RMS `{worst_rms:.3f} °C`。", "", result["decision"]]
    (RESULTS / "assessment.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"new_nest_m_allowed": result["new_nest_m_allowed"], "decision": result["decision"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
