"""执行 V5.2 计划一的 THERMAL-0 三维瞬态热模型。

模型在 R74.98 mm 接口附近使用周期展开坐标 (s, n, z)：s 为周向弧长，n 为
接口法向距离，z 为局部轴向距离。热源沿 s 移动，采用离散 Goldak 双椭球，
热传导使用温度相关物性和显式有限体积更新。该实现用于建立可追溯的三维热
历史，不替代商业焊接 FE，也不代表实验校准。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.metadata
import json
import math
import platform
from pathlib import Path
import subprocess
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = ROOT / "project" / "g-inputs-v5.2.yaml"
MATERIAL_PATH = ROOT / "project" / "materials.yaml"
OUTPUT_DIR = ROOT / "simulation" / "thermal-v5" / "results"


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _traceability() -> dict[str, Any]:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {
        "run_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_commit": commit,
        "python_version": platform.python_version(),
        "dependency_versions": {
            name: importlib.metadata.version(name)
            for name in ("numpy", "scipy", "matplotlib", "PyYAML")
        },
    }


def _interp(table: dict[str, Any], key: str, temperature_c: np.ndarray) -> np.ndarray:
    return np.interp(
        temperature_c,
        np.asarray(table["temperatures_c"], dtype=float),
        np.asarray(table[key], dtype=float),
    )


def _material_fields(
    temperatures_c: np.ndarray,
    material_id: np.ndarray,
    materials: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """返回每个网格点的 k、rho、cp；焊缝采用独立常温物性假设。"""
    shape = temperatures_c.shape
    conductivity = np.empty(shape, dtype=float)
    capacity = np.empty(shape, dtype=float)
    density = np.empty(shape, dtype=float)
    for material_key, material_code in (("q235b", 1), ("qt450_10", 2)):
        mask = material_id == material_code
        table = materials[material_key]
        temp_table = table["temperature_dependent"]
        conductivity[mask] = _interp(temp_table, "thermal_conductivity_w_mk", temperatures_c[mask]) / 1000.0
        capacity[mask] = _interp(temp_table, "specific_heat_j_kgk", temperatures_c[mask])
        density[mask] = float(table["nominal_properties_20c"]["density_kg_m3"]) / 1e9
    weld_mask = material_id == 3
    weld = materials["ernife_ci"]["nominal_properties_20c"]
    conductivity[weld_mask] = float(weld["thermal_conductivity_w_mk"]) / 1000.0
    capacity[weld_mask] = float(weld["specific_heat_j_kgk"])
    density[weld_mask] = float(weld["density_kg_m3"]) / 1e9
    return conductivity, density, capacity


def _goldak_source(
    s: np.ndarray,
    n: np.ndarray,
    z: np.ndarray,
    center_s: float,
    circumference_mm: float,
    power_w: float,
    a_front: float,
    a_rear: float,
    b: float,
    c: float,
    front_fraction: float,
    rear_fraction: float,
    cell_volume_mm3: float,
) -> np.ndarray:
    """按当前离散网格归一化 Goldak 双椭球，使每个时间步输入功率可追溯。"""
    delta_s = (s - center_s + circumference_mm / 2.0) % circumference_mm - circumference_mm / 2.0
    front = delta_s >= 0.0
    a = np.where(front, a_front, a_rear)
    fraction = np.where(front, front_fraction, rear_fraction)
    weights = fraction * np.exp(-3.0 * (delta_s / a) ** 2 - 3.0 * (n / b) ** 2 - 3.0 * (z / c) ** 2)
    weight_sum = float(weights.sum())
    if weight_sum <= 0.0:
        return np.zeros_like(weights)
    return weights * (power_w / (weight_sum * cell_volume_mm3))


def _crossing_time(previous: np.ndarray, current: np.ndarray, threshold: float, time_s: float, time_step: float) -> np.ndarray:
    crossed = (previous >= threshold) & (current < threshold)
    denominator = previous - current
    fraction = np.divide(previous - threshold, denominator, out=np.zeros_like(previous), where=denominator > 1e-12)
    return np.where(crossed, time_s - time_step + time_step * fraction, np.nan)


def _laplacian_neumann(values: np.ndarray, spacing: float, axis: int) -> np.ndarray:
    """用边缘复制实现零法向梯度，避免 np.gradient 在边界产生非物理热源。"""
    pad_width = [(0, 0)] * values.ndim
    pad_width[axis] = (1, 1)
    padded = np.pad(values, pad_width, mode="edge")
    center = [slice(None)] * values.ndim
    lower = [slice(None)] * values.ndim
    upper = [slice(None)] * values.ndim
    center[axis] = slice(1, -1)
    lower[axis] = slice(0, -2)
    upper[axis] = slice(2, None)
    return (padded[tuple(upper)] - 2.0 * padded[tuple(center)] + padded[tuple(lower)]) / spacing**2


def run(config: dict[str, Any], materials: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    geometry = config["geometry"]
    process = config["process"]
    heat_source = config["heat_source"]
    grid = config["thermal_grid"]
    circumference = 2.0 * math.pi * float(geometry["interface_radius_mm"])
    s = np.linspace(0.0, circumference, int(grid["arc_points"]), endpoint=False)
    n = np.linspace(float(grid["radial_min_offset_mm"]), float(grid["radial_max_offset_mm"]), int(grid["radial_points"]))
    z = np.linspace(float(grid["axial_min_offset_mm"]), float(grid["axial_max_offset_mm"]), int(grid["axial_points"]))
    ss, nn, zz = np.meshgrid(s, n, z, indexing="ij")
    ds = circumference / len(s)
    dn = float(n[1] - n[0])
    dz = float(z[1] - z[0])
    cell_volume = ds * dn * dz

    # n<0 为 QT 座体侧，n>0 为 Q235B 壳体侧，中间带作为 NiFe 焊缝。
    material_id = np.where(nn < -3.0, 2, np.where(nn > 3.0, 1, 3)).astype(np.int8)
    temperature = np.full(ss.shape, float(process["cooling_environment_c"]), dtype=float)
    temperature[(material_id == 3)] = float(process["preheat_temperature_c"])
    temperature[(material_id != 3)] = float(process["preheat_temperature_c"])
    peak = temperature.copy()
    peak_time = np.zeros_like(temperature)
    previous = temperature.copy()
    t800_down = np.full_like(temperature, np.nan)
    t500_down = np.full_like(temperature, np.nan)
    history: list[dict[str, float]] = []
    sensor_indices = {
        "QT_HAZ": (len(s) // 4, max(0, np.searchsorted(n, -5.0)), len(z) // 2),
        "fusion_line": (0, np.searchsorted(n, 0.0), len(z) // 2),
        "weld_center": (0, np.searchsorted(n, 1.0), len(z) // 2),
        "Q235B_HAZ": (len(s) // 4, min(len(n) - 1, np.searchsorted(n, 5.0)), len(z) // 2),
    }
    sensor_history: dict[str, list[dict[str, float]]] = {key: [] for key in sensor_indices}

    time_step = float(grid["time_step_s"])
    output_interval = float(grid["output_interval_s"])
    weld_duration = float(geometry["weld_length_mm"]) / float(process["travel_speed_mm_s"])
    total_duration = weld_duration + float(process["cooling_hold_s"]) + float(process.get("post_release_cooling_s", 0.0))
    ui_net_power_w = float(process["efficiency"]) * float(process["current_a"]) * float(process["voltage_v"])
    ui_line_energy_j_per_mm = ui_net_power_w / float(process["travel_speed_mm_s"])
    steps = int(math.ceil(total_duration / time_step))
    kappa_source = (float(process["convection_coefficient_w_m2k"]) / 1e6) * time_step
    epsilon = float(process["emissivity"])
    sigma = 5.670374419e-8 / 1e6
    source_energy_j = 0.0
    source_power_min_w = math.inf
    source_power_max_w = -math.inf
    source_power_max_relative_error = 0.0
    source_active_steps = 0
    loss_energy_j = 0.0
    max_cooling_rate = np.zeros_like(temperature)
    next_output = 0.0

    for step in range(steps + 1):
        time_s = step * time_step
        conductivity, density, capacity = _material_fields(temperature, material_id, materials)
        # 周向周期；法向和轴向采用绝热内部边界，外边界再施加对流/辐射损失。
        lap_s = (np.roll(temperature, -1, axis=0) - 2.0 * temperature + np.roll(temperature, 1, axis=0)) / ds**2
        lap_n = _laplacian_neumann(temperature, dn, axis=1)
        lap_z = _laplacian_neumann(temperature, dz, axis=2)
        alpha = np.divide(conductivity, density * capacity, out=np.zeros_like(temperature), where=density * capacity > 0)
        temperature += time_step * alpha * (lap_s + lap_n + lap_z)

        if time_s <= weld_duration:
            center_s = (float(process["travel_speed_mm_s"]) * time_s) % circumference
            source = _goldak_source(
                ss,
                nn,
                zz,
                center_s,
                circumference,
                float(process["net_power_w"]),
                float(heat_source["a_front_mm"]),
                float(heat_source["a_rear_mm"]),
                float(heat_source["b_radial_mm"]),
                float(heat_source["c_axial_mm"]),
                float(heat_source["front_fraction"]),
                float(heat_source["rear_fraction"]),
                cell_volume,
            )
            temperature += time_step * source / (density * capacity)
            source_power_w = float(np.sum(source) * cell_volume)
            source_power_min_w = min(source_power_min_w, source_power_w)
            source_power_max_w = max(source_power_max_w, source_power_w)
            source_power_max_relative_error = max(
                source_power_max_relative_error,
                abs(source_power_w - float(process["net_power_w"])) / float(process["net_power_w"]),
            )
            source_energy_j += source_power_w * time_step
            source_active_steps += 1

        boundary = np.zeros_like(temperature, dtype=bool)
        boundary[:, 0, :] = True
        boundary[:, -1, :] = True
        boundary[:, :, 0] = True
        boundary[:, :, -1] = True
        delta_t = np.maximum(temperature - float(process["cooling_environment_c"]), 0.0)
        loss_w_mm3 = np.zeros_like(temperature)
        loss_w_mm3[boundary] = (
            float(process["convection_coefficient_w_m2k"]) * delta_t[boundary] / 1e6
            + epsilon * sigma * ((temperature[boundary] + 273.15) ** 4 - (float(process["cooling_environment_c"]) + 273.15) ** 4)
        )
        temperature[boundary] -= time_step * loss_w_mm3[boundary] / (density[boundary] * capacity[boundary])
        loss_energy_j += float(np.sum(loss_w_mm3) * cell_volume * time_step)
        max_cooling_rate = np.maximum(max_cooling_rate, np.maximum(previous - temperature, 0.0) / time_step)

        higher = temperature > peak
        peak = np.where(higher, temperature, peak)
        peak_time = np.where(higher, time_s, peak_time)
        crossing_800 = _crossing_time(previous, temperature, 800.0, time_s, time_step)
        crossing_500 = _crossing_time(previous, temperature, 500.0, time_s, time_step)
        t800_down = np.where(np.isnan(t800_down), crossing_800, t800_down)
        t500_down = np.where((~np.isnan(t800_down)) & np.isnan(t500_down), crossing_500, t500_down)
        if time_s + 1e-9 >= next_output:
            row = {"time_s": time_s}
            for name, (i, j, k) in sensor_indices.items():
                row[name + "_c"] = float(temperature[i, j, k])
                sensor_history[name].append({"time_s": time_s, "temperature_c": float(temperature[i, j, k])})
            history.append(row)
            next_output += output_interval
        previous = temperature.copy()

    valid_t85 = (peak > 800.0) & np.isfinite(t800_down) & np.isfinite(t500_down) & (t500_down >= t800_down)
    t85 = np.where(valid_t85, t500_down - t800_down, np.nan)
    continuous_expected_energy_j = float(process["net_power_w"]) * weld_duration
    discrete_expected_energy_j = float(process["net_power_w"]) * source_active_steps * time_step
    energy_balance_error_pct = abs(source_energy_j - continuous_expected_energy_j) / continuous_expected_energy_j * 100.0
    discrete_energy_balance_error_pct = abs(source_energy_j - discrete_expected_energy_j) / discrete_expected_energy_j * 100.0
    metadata = {
        **_traceability(),
        "stage": "THERMAL-0",
        "evidence_level": "solver_result_unvalidated",
        "solver_version": "THERMAL-0-explicit-finite-volume-v5",
        "model": "3d_periodic_unwrapped_goldak_explicit_finite_volume",
        "input_file": str(INPUT_PATH.relative_to(ROOT)).replace("\\", "/"),
        "input_sha256": _sha256(INPUT_PATH),
        "material_file": str(MATERIAL_PATH.relative_to(ROOT)).replace("\\", "/"),
        "material_sha256": _sha256(MATERIAL_PATH),
        "grid": {"arc_points": len(s), "radial_points": len(n), "axial_points": len(z), "cell_count": int(temperature.size)},
        "time": {"time_step_s": time_step, "total_duration_s": total_duration, "steps": steps},
        "energy": {
            "nominal_net_power_w": float(process["net_power_w"]),
            "nominal_net_line_energy_j_per_mm": float(process["net_line_energy_j_per_mm"]),
            "ui_net_power_w": ui_net_power_w,
            "ui_line_energy_j_per_mm": ui_line_energy_j_per_mm,
            "power_definition_relative_error": abs(ui_net_power_w - float(process["net_power_w"])) / float(process["net_power_w"]),
            "line_energy_definition_relative_error": abs(ui_line_energy_j_per_mm - float(process["net_line_energy_j_per_mm"])) / float(process["net_line_energy_j_per_mm"]),
            "source_input_j": source_energy_j,
            "continuous_expected_source_energy_j": continuous_expected_energy_j,
            "discrete_expected_source_energy_j": discrete_expected_energy_j,
            "source_active_steps": source_active_steps,
            "source_power_min_w": source_power_min_w,
            "source_power_max_w": source_power_max_w,
            "source_power_max_relative_error": source_power_max_relative_error,
            "energy_balance_error_pct": energy_balance_error_pct,
            "discrete_energy_balance_error_pct": discrete_energy_balance_error_pct,
            "boundary_loss_estimate_j": loss_energy_j,
            "energy_balance_note": "热源体积分和焊段积分已审计；内部能量、边界损失和数值耗散仍未按商业 FE 全局能量审计定义闭合。",
        },
        "assumptions": [
            "Goldak 尺寸、前后能量比例和效率均为 design_assumption，未用热电偶/宏观截面校准。",
            "接口展开坐标用于局部三维热历史；未包含完整装配体的实体接触换热。",
            "未模拟熔池流动、相变、焊缝逐道激活或温度相关塑性。",
            "t8/5 只作为热循环描述量，不是 QT450-10 的独立相组成判据。",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_dir / "thermal0-field.npz",
        s=s,
        n=n,
        z=z,
        temperature_final=temperature,
        temperature_peak=peak,
        peak_time_s=peak_time,
        max_cooling_rate_c_s=max_cooling_rate,
        t8_5_s=t85,
        t800_down_s=t800_down,
        t500_down_s=t500_down,
        t8_5_valid=valid_t85,
        material_id=material_id,
    )
    (output_dir / "thermal0-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "thermal0-sensor-history.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = list(history[0].keys())
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(history)
    sensor_metadata = {
        "evidence_level": metadata["evidence_level"],
        "sensors": {
            name: {"index": [int(value) for value in index], "arc_position_deg": float(index[0] * 360.0 / len(s))}
            for name, index in sensor_indices.items()
        },
        "history": sensor_history,
    }
    (output_dir / "thermal0-sensors.json").write_text(json.dumps(sensor_metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / "thermal0-t85-samples.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["s_index", "n_index", "z_index", "s_mm", "n_mm", "z_mm", "material", "tmax_c", "t800_down_s", "t500_down_s", "t8_5_s", "valid"],
        )
        writer.writeheader()
        for location in np.ndindex(peak.shape):
            material_name = {1: "Q235B", 2: "QT450-10", 3: "ERNiFe-CI"}[int(material_id[location])]
            writer.writerow(
                {
                    "s_index": location[0],
                    "n_index": location[1],
                    "z_index": location[2],
                    "s_mm": float(s[location[0]]),
                    "n_mm": float(n[location[1]]),
                    "z_mm": float(z[location[2]]),
                    "material": material_name,
                    "tmax_c": float(peak[location]),
                    "t800_down_s": None if not np.isfinite(t800_down[location]) else float(t800_down[location]),
                    "t500_down_s": None if not np.isfinite(t500_down[location]) else float(t500_down[location]),
                    "t8_5_s": None if not np.isfinite(t85[location]) else float(t85[location]),
                    "valid": bool(valid_t85[location]),
                }
            )

    peak_by_n = np.max(peak, axis=(0, 2))
    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.plot(n, peak_by_n, color="#b23a48", linewidth=2.0)
    axis.axvline(0.0, color="#333333", linestyle="--", linewidth=1.0, label="interface n=0")
    for threshold, label in ((400.0, "low HAZ"), (600.0, "medium HAZ"), (900.0, "high HAZ"), (1350.0, "fusion threshold")):
        axis.axhline(threshold, linestyle=":", linewidth=0.9, label=f"{label} {threshold:.0f}°C")
    axis.set_xlabel("Interface-normal distance n (mm; negative = QT450-10)")
    axis.set_ylabel("Peak nodal temperature (°C)")
    axis.set_title("THERMAL-0: peak temperature and HAZ thresholds")
    axis.grid(alpha=0.25)
    axis.legend(fontsize=8, ncol=2)
    figure.tight_layout()
    figure.savefig(output_dir / "thermal0-peak-profile.svg")
    figure.savefig(output_dir / "thermal0-peak-profile.png", dpi=180)
    plt.close(figure)

    summary = {
        **metadata,
        "peak_temperature_c": float(np.max(peak)),
        "peak_temperature_location": {
            "s_mm": float(ss.flat[int(np.argmax(peak))]),
            "n_mm": float(nn.flat[int(np.argmax(peak))]),
            "z_mm": float(zz.flat[int(np.argmax(peak))]),
            "angle_deg": float((ss.flat[int(np.argmax(peak))] / circumference) * 360.0),
        },
        "thermal_exposure_width_estimates_mm": {
            "qt450_10_side_above_400c": float(max(0.0, -n[np.where((peak_by_n >= 400.0) & (n < 0.0))[0][0]])) if np.any((peak_by_n >= 400.0) & (n < 0.0)) else 0.0,
            "q235b_side_above_400c": float(n[np.where((peak_by_n >= 400.0) & (n > 0.0))[0][-1]]) if np.any((peak_by_n >= 400.0) & (n > 0.0)) else 0.0,
        },
        "t8_5_statistics_s": {
            "valid_definition": "Tmax > 800°C and both descending crossings of 800°C and 500°C exist with t500_down >= t800_down",
            "valid_node_count": int(np.isfinite(t85).sum()),
            "median": float(np.nanmedian(t85)) if np.any(np.isfinite(t85)) else None,
            "p25": float(np.nanpercentile(t85, 25)) if np.any(np.isfinite(t85)) else None,
            "p75": float(np.nanpercentile(t85, 75)) if np.any(np.isfinite(t85)) else None,
            "minimum": float(np.nanmin(t85)) if np.any(np.isfinite(t85)) else None,
            "maximum": float(np.nanmax(t85)) if np.any(np.isfinite(t85)) else None,
        },
        "fusion_threshold_c": float(process.get("fusion_threshold_c", 1350.0)),
        "fusion_threshold_exceeded": bool(np.max(peak) >= float(config["metallurgy"]["fusion_threshold_c"])),
    }
    (output_dir / "thermal0-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_files = [
        "thermal0-field.npz",
        "thermal0-metadata.json",
        "thermal0-sensor-history.csv",
        "thermal0-sensors.json",
        "thermal0-t85-samples.csv",
        "thermal0-summary.json",
        "thermal0-peak-profile.svg",
        "thermal0-peak-profile.png",
    ]
    (output_dir / "thermal0-result-manifest.json").write_text(
        json.dumps(
            {
                "stage": "THERMAL-0",
                "evidence_level": metadata["evidence_level"],
                "input_file": metadata["input_file"],
                "input_sha256": metadata["input_sha256"],
                "files": {name: _sha256(output_dir / name) for name in manifest_files},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    config = _load_yaml(INPUT_PATH)
    materials = _load_yaml(MATERIAL_PATH)["materials"]
    summary = run(config, materials, args.output_dir)
    print(json.dumps({"stage": summary["stage"], "evidence_level": summary["evidence_level"], "peak_temperature_c": summary["peak_temperature_c"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
