"""执行 G-THERMAL 的能量、网格、时间步和边界敏感性审计。"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from run_thermal0 import INPUT_PATH, MATERIAL_PATH, OUTPUT_DIR, _load_yaml, run


ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = OUTPUT_DIR / "g-thermal-audit"


def _case(config: dict[str, Any], name: str, changes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    result = copy.deepcopy(config)
    for path, value in changes.items():
        target = result
        keys = path.split(".")
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
    return name, result


def run_audit() -> dict[str, Any]:
    config = _load_yaml(INPUT_PATH)
    materials = _load_yaml(MATERIAL_PATH)["materials"]
    # 敏感性覆盖固定局部窗口；完整冷却/t8/5 由基准运行保存，避免重复计算冷却尾段。
    audit_config = copy.deepcopy(config)
    audit_config["process"]["cooling_hold_s"] = 0.0
    audit_config["process"]["post_release_cooling_s"] = 0.0
    base_grid = audit_config["thermal_grid"]
    base_dt = float(base_grid["time_step_s"])
    mesh_dt = 0.003
    cases: list[tuple[str, dict[str, Any]]] = [
        ("baseline", copy.deepcopy(audit_config)),
        _case(audit_config, "mesh-coarse", {"thermal_grid.arc_points": 49, "thermal_grid.radial_points": 26, "thermal_grid.axial_points": 15, "thermal_grid.time_step_s": mesh_dt}),
        _case(audit_config, "mesh-medium", {"thermal_grid.time_step_s": mesh_dt}),
        _case(audit_config, "mesh-fine", {"thermal_grid.arc_points": 107, "thermal_grid.radial_points": 62, "thermal_grid.axial_points": 36, "thermal_grid.time_step_s": mesh_dt}),
        _case(audit_config, "dt-half", {"thermal_grid.time_step_s": base_dt / 2.0}),
        _case(audit_config, "dt-quarter", {"thermal_grid.time_step_s": base_dt / 4.0}),
        _case(audit_config, "convection-low", {"process.convection_coefficient_w_m2k": 6.0}),
        _case(audit_config, "convection-high", {"process.convection_coefficient_w_m2k": 24.0}),
        _case(audit_config, "efficiency-low", {"process.efficiency": 0.45, "process.net_power_w": 405.0, "process.net_line_energy_j_per_mm": 270.0}),
        _case(audit_config, "efficiency-high", {"process.efficiency": 0.65, "process.net_power_w": 585.0, "process.net_line_energy_j_per_mm": 390.0}),
        _case(audit_config, "source-narrow", {"heat_source.b_radial_mm": 2.0, "heat_source.c_axial_mm": 2.0}),
        _case(audit_config, "source-wide", {"heat_source.b_radial_mm": 3.0, "heat_source.c_axial_mm": 3.0}),
    ]
    rows: list[dict[str, Any]] = []
    for name, case_config in cases:
        summary = run(case_config, materials, AUDIT_DIR / name)
        energy = summary["energy"]
        rows.append(
            {
                "case": name,
                "case_config_sha256": hashlib.sha256(json.dumps(case_config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
                "grid": summary["grid"],
                "time": summary["time"],
                "peak_temperature_c": summary["peak_temperature_c"],
                "t8_5_statistics_s": summary["t8_5_statistics_s"],
                "thermal_exposure_width_estimates_mm": summary["thermal_exposure_width_estimates_mm"],
                "source_path": summary["source_path"],
                "source_domain_capture": energy["source_domain_capture"],
                "peak_location_gate": summary["peak_location_gate"],
                "source_power_max_relative_error": energy["source_power_max_relative_error"],
                "power_definition_relative_error": energy["power_definition_relative_error"],
                "line_energy_definition_relative_error": energy["line_energy_definition_relative_error"],
                "energy_balance_error_pct": energy["energy_balance_error_pct"],
                "discrete_energy_balance_error_pct": energy["discrete_energy_balance_error_pct"],
                "global_thermal_energy_balance": energy["global_thermal_energy_balance"],
                "input_sha256": summary["input_sha256"],
            }
        )

    by_name = {row["case"]: row for row in rows}
    base = by_name["baseline"]

    def relative(case_name: str, key: str) -> float:
        value = float(by_name[case_name][key])
        reference = float(base[key])
        return abs(value - reference) / max(abs(reference), 1e-12)

    def relative_between(reference_case: str, case_name: str, key: str) -> float:
        value = float(by_name[case_name][key])
        reference = float(by_name[reference_case][key])
        return abs(value - reference) / max(abs(reference), 1e-12)

    exposure_keys = ("qt450_10_parent_above_400c", "q235b_parent_above_400c")
    exposure_changes = {
        key: abs(
            float(by_name["mesh-fine"]["thermal_exposure_width_estimates_mm"][key])
            - float(by_name["mesh-medium"]["thermal_exposure_width_estimates_mm"][key])
        ) / max(abs(float(by_name["mesh-medium"]["thermal_exposure_width_estimates_mm"][key])), 1e-12)
        for key in exposure_keys
    }

    mesh_comparison = {
        "common_time_step_s": mesh_dt,
        "tmax_coarse_to_medium_relative_change": relative_between("mesh-coarse", "mesh-medium", "peak_temperature_c"),
        "tmax_medium_to_fine_relative_change": relative_between("mesh-medium", "mesh-fine", "peak_temperature_c"),
        "t85_medium_to_fine_relative_change": None,
        "parent_exposure_width_medium_to_fine_relative_change": exposure_changes,
        "note": "三档网格统一 dt=0.003 s；审计工况不含冷却尾段，因此 t8/5 留给完整基准运行，不强行比较空样本。",
    }
    time_comparison = {
        "tmax_base_to_half_relative_change": relative("dt-half", "peak_temperature_c"),
        "tmax_half_to_quarter_relative_change": abs(float(by_name["dt-quarter"]["peak_temperature_c"]) - float(by_name["dt-half"]["peak_temperature_c"])) / max(abs(float(by_name["dt-quarter"]["peak_temperature_c"])), 1e-12),
        "t85_valid_counts": {name: by_name[name]["t8_5_statistics_s"]["valid_node_count"] for name in ("baseline", "dt-half", "dt-quarter")},
        "step_travel_distance_mm": {name: float(case["thermal_grid"]["time_step_s"]) * float(case["process"]["travel_speed_mm_s"]) for name, case in cases if name in {"baseline", "dt-half", "dt-quarter"}},
        "source_resolution": base["grid"]["source_resolution"],
        "local_radial_grid_mm": float(base["grid"]["source_resolution"]["dn_mm"]),
    }
    boundary_comparison = {name: {"peak_relative_change": relative(name, "peak_temperature_c"), "exposure_width": by_name[name]["thermal_exposure_width_estimates_mm"]} for name in ("convection-low", "convection-high", "efficiency-low", "efficiency-high", "source-narrow", "source-wide")}
    energy_pass = all(
        row["source_power_max_relative_error"] < 0.01
        and row["source_domain_capture"]["status"] == "PASS"
        and row["global_thermal_energy_balance"]["residual_percent_of_source"] < 2.0
        for row in rows
    )
    audit = {
        "stage": "G-THERMAL",
        "evidence_level": "solver_result_unvalidated",
        "input_file": str(INPUT_PATH.relative_to(ROOT)).replace("\\", "/"),
        "input_sha256": base["input_sha256"],
        "criteria": {
            "source_power_max_relative_error": 0.01,
            "source_energy_normalization": "PASS when source power integral is within 1%",
            "minimum_source_domain_capture_fraction": float(base_grid["minimum_source_domain_capture_fraction"]),
            "minimum_source_s_boundary_margin_multiple": float(base_grid["minimum_source_s_boundary_margin_multiple"]),
            "global_energy_residual_percent_of_source": 2.0,
            "time_step_travel_distance_must_be_less_than_radial_grid_mm": True,
            "mesh_and_time_thresholds": "拟定工程审计门槛；不替代实验校准",
        },
        "energy_audit": {
            "source_energy_normalization_pass": all(row["source_power_max_relative_error"] < 0.01 and row["power_definition_relative_error"] < 0.01 and row["line_energy_definition_relative_error"] < 0.01 and row["energy_balance_error_pct"] < 1.0 for row in rows),
            "global_thermal_energy_balance_pass": all(row["global_thermal_energy_balance"]["residual_percent_of_source"] < 2.0 for row in rows),
            "pass": all(row["source_power_max_relative_error"] < 0.01 and row["source_domain_capture"]["status"] == "PASS" and row["global_thermal_energy_balance"]["residual_percent_of_source"] < 2.0 for row in rows),
            "cases": [{"case": row["case"], "source_power_max_relative_error": row["source_power_max_relative_error"], "source_domain_capture": row["source_domain_capture"], "power_definition_relative_error": row["power_definition_relative_error"], "line_energy_definition_relative_error": row["line_energy_definition_relative_error"], "energy_balance_error_pct": row["energy_balance_error_pct"], "discrete_energy_balance_error_pct": row["discrete_energy_balance_error_pct"], "global_thermal_energy_balance": row["global_thermal_energy_balance"]} for row in rows],
        },
        "mesh_sensitivity": mesh_comparison,
        "time_step_sensitivity": time_comparison,
        "boundary_sensitivity": boundary_comparison,
        "cases": rows,
        "fusion_status": {"baseline_peak_temperature_c": base["peak_temperature_c"], "fusion_threshold_c": config["metallurgy"]["fusion_threshold_c"], "threshold_exceeded": base["peak_temperature_c"] >= config["metallurgy"]["fusion_threshold_c"]},
        "gate_status": "review_required",
        "gate_checks": {
            "energy_pass": energy_pass,
            "source_resolution_pass": base["grid"]["source_resolution"]["target_met"],
            "source_domain_capture_pass": all(row["source_domain_capture"]["status"] == "PASS" for row in rows),
            "source_center_inside_domain_pass": all(row["source_path"]["center_outside_domain_steps"] == 0 for row in rows),
            "source_s_boundary_margin_pass": all(row["source_path"]["boundary_margin_status"] == "PASS" for row in rows),
            "peak_not_at_artificial_s_boundary_pass": all(not row["peak_location_gate"]["at_artificial_s_boundary_cell"] for row in rows),
            "mesh_pass": mesh_comparison["tmax_medium_to_fine_relative_change"] < 0.05,
            "mesh_parent_exposure_width_pass": all(value < 0.10 for value in exposure_changes.values()),
            "time_step_pass": time_comparison["tmax_half_to_quarter_relative_change"] < 0.01 and all(value < time_comparison["local_radial_grid_mm"] for value in time_comparison["step_travel_distance_mm"].values()),
            "boundary_sensitivity_review_required": any(item["peak_relative_change"] > 0.05 for item in boundary_comparison.values()),
        },
        "limitations": [
            "热源尚未用热电偶、宏观熔合区或独立验证数据校准。",
            "固定局部窗口的结果只描述焊源邻域热历史；完整圆周装配体仍需独立周期路径模型。",
            "局部展开坐标不是完整装配体三维热—结构模型。",
            "G-THERMAL 审计通过不等于 THERMAL-1 或物理焊接验证通过。",
        ],
    }
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    (AUDIT_DIR / "G-THERMAL-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    report_lines = [
        "# G-THERMAL 审计",
        "",
        "> 证据等级：`solver_result_unvalidated`。审计通过只表示数值链检查通过，不表示热源已由实验校准。",
        "",
        "## Gate 判定",
        "",
        f"- 源能量归一化：**{'PASS' if audit['energy_audit']['source_energy_normalization_pass'] else 'REVIEW'}**；最大功率体积分误差 `{max(row['source_power_max_relative_error'] for row in rows):.3e}`，连续焊段累计能量误差 `{max(row['energy_balance_error_pct'] for row in rows):.4f}%`。",
        f"- 全局热能平衡：**{'PASS' if audit['energy_audit']['global_thermal_energy_balance_pass'] else 'REVIEW'}**；最大残差 `{max(row['global_thermal_energy_balance']['residual_percent_of_source'] for row in rows):.4f}%`。",
        f"- 热源域捕获：**{'PASS' if audit['gate_checks']['source_domain_capture_pass'] else 'FAIL'}**；归一化前最小捕获率 `{min(row['source_domain_capture']['minimum_fraction'] for row in rows):.6%}`。",
        f"- 时间步审计：**{'PASS' if audit['gate_checks']['time_step_pass'] else 'REVIEW'}**；dt/2→dt/4 峰值变化 `{time_comparison['tmax_half_to_quarter_relative_change']:.3%}`。",
        f"- 网格审计：**{'PASS' if audit['gate_checks']['mesh_pass'] else 'REVIEW'}**；medium/fine 均取 dt={mesh_dt:.3f} s，峰值变化 `{mesh_comparison['tmax_medium_to_fine_relative_change']:.2%}`。",
        f"- 参数边界审计：**{'REVIEW' if audit['gate_checks']['boundary_sensitivity_review_required'] else 'PASS'}**；效率和热源尺寸变化对峰值有明显影响。",
        f"- G-THERMAL 总状态：**{audit['gate_status']}**。",
        "",
        "## 运行矩阵",
        "",
        "| 工况 | 网格 | dt (s) | 峰值温度 (°C) | 功率误差 | 能量误差 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        report_lines.append(f"| {row['case']} | {row['grid']['arc_points']}×{row['grid']['radial_points']}×{row['grid']['axial_points']} | {row['time']['time_step_s']:.4f} | {row['peak_temperature_c']:.2f} | {row['source_power_max_relative_error']:.2e} | {row['energy_balance_error_pct']:.4f}% |")
    report_lines.extend([
        "",
        "## 结论与下一步",
        "",
        "源能量归一化、归一化前域捕获和全局热能账本已独立审计。固定局部窗口只描述焊源邻域，网格/参数敏感性和实验校准仍需复核，当前不能进入 THERMAL-1，也不能把峰值写成已校准焊接热场。",
    ])
    (AUDIT_DIR / "G-THERMAL-audit.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    return audit


if __name__ == "__main__":
    result = run_audit()
    print(json.dumps({"stage": result["stage"], "energy_pass": result["energy_audit"]["pass"], "case_count": len(result["cases"])}, ensure_ascii=False))
