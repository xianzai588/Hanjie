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
    cell_volume_mm3: np.ndarray,
    periodic_s: bool = True,
) -> np.ndarray:
    """按当前离散网格归一化 Goldak 双椭球，使每个时间步输入功率可追溯。"""
    delta_s = (s - center_s + circumference_mm / 2.0) % circumference_mm - circumference_mm / 2.0 if periodic_s else s - center_s
    front = delta_s >= 0.0
    a = np.where(front, a_front, a_rear)
    fraction = np.where(front, front_fraction, rear_fraction)
    weights = fraction * np.exp(-3.0 * (delta_s / a) ** 2 - 3.0 * (n / b) ** 2 - 3.0 * (z / c) ** 2)
    weight_sum = float(weights.sum())
    if weight_sum <= 0.0:
        return np.zeros_like(weights)
    return weights * (power_w / weight_sum) / cell_volume_mm3


def _cell_centers(start: float, stop: float, count: int) -> tuple[np.ndarray, float]:
    """返回有限体积单元中心和统一单元宽度。"""
    width = (stop - start) / count
    return start + (np.arange(count, dtype=float) + 0.5) * width, width


def _locally_refined_cells(
    start: float,
    stop: float,
    fine_start: float,
    fine_stop: float,
    fine_width: float,
    coarse_width: float,
) -> tuple[np.ndarray, np.ndarray]:
    """构造焊源附近细化、远场较粗的有限体积单元中心和宽度。"""
    segments = ((start, fine_start, coarse_width), (fine_start, fine_stop, fine_width), (fine_stop, stop, coarse_width))
    edges: list[float] = []
    for index, (lower, upper, target_width) in enumerate(segments):
        count = max(1, int(math.ceil((upper - lower) / target_width)))
        segment_edges = np.linspace(lower, upper, count + 1)
        edges.extend(segment_edges if index == 0 else segment_edges[1:])
    faces = np.asarray(edges, dtype=float)
    return 0.5 * (faces[:-1] + faces[1:]), np.diff(faces)


def _enthalpy_per_mass(temperature_c: np.ndarray, material_id: np.ndarray, materials: dict[str, Any]) -> np.ndarray:
    """按分段线性 cp 积分得到相对 20 C 的比焓，用于全局能量账本。"""
    result = np.empty_like(temperature_c, dtype=float)
    for material_key, material_code in (("q235b", 1), ("qt450_10", 2)):
        mask = material_id == material_code
        table = materials[material_key]["temperature_dependent"]
        temperatures = np.asarray(table["temperatures_c"], dtype=float)
        cp = np.asarray(table["specific_heat_j_kgk"], dtype=float)
        values = np.zeros(np.count_nonzero(mask), dtype=float)
        selected = temperature_c[mask]
        for index in range(len(temperatures) - 1):
            lower = temperatures[index]
            upper = temperatures[index + 1]
            segment = np.maximum(0.0, np.clip(selected, lower, upper) - lower)
            values += segment * (cp[index] + (cp[index + 1] - cp[index]) * segment / (2.0 * (upper - lower)))
        below = selected < temperatures[0]
        values[below] = (selected[below] - temperatures[0]) * cp[0]
        above = selected > temperatures[-1]
        values[above] += (selected[above] - temperatures[-1]) * cp[-1]
        result[mask] = values
    weld_mask = material_id == 3
    weld_cp = float(materials["ernife_ci"]["nominal_properties_20c"]["specific_heat_j_kgk"])
    result[weld_mask] = (temperature_c[weld_mask] - 20.0) * weld_cp
    return result


def _trilinear_periodic(
    values: np.ndarray,
    s: np.ndarray,
    n: np.ndarray,
    z: np.ndarray,
    target: tuple[float, float, float],
    circumference_mm: float,
    periodic_s: bool = True,
) -> float:
    """在精确物理坐标处输出周期 s 方向和 n/z 方向的三线性插值。"""
    target_s, target_n, target_z = target
    def bracket(axis: np.ndarray, value: float) -> tuple[int, int, float]:
        position = float(np.clip(value, axis[0], axis[-1]))
        upper = int(np.searchsorted(axis, position, side="right"))
        upper = min(max(upper, 1), len(axis) - 1)
        lower = upper - 1
        fraction = (position - axis[lower]) / (axis[upper] - axis[lower])
        return lower, upper, fraction

    if periodic_s:
        s_position = target_s % circumference_mm
        s_step = circumference_mm / len(s)
        s_float = s_position / s_step - 0.5
        s0 = math.floor(s_float) % len(s)
        s_weight = s_float - math.floor(s_float)
    else:
        s0, s1, s_weight = bracket(s, target_s)
        s_indices = ((s0, 1.0 - s_weight), (s1, s_weight))

    n0, n1, nw = bracket(n, target_n)
    z0, z1, zw = bracket(z, target_z)
    value = 0.0
    for si, sw in s_indices if not periodic_s else ((s0, 1.0 - s_weight), ((s0 + 1) % len(s), s_weight)):
        value += sw * (
            (1.0 - nw) * (1.0 - zw) * values[si, n0, z0]
            + (1.0 - nw) * zw * values[si, n0, z1]
            + nw * (1.0 - zw) * values[si, n1, z0]
            + nw * zw * values[si, n1, z1]
        )
    return float(value)


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
    local_mode = grid.get("coordinate_mode") == "local_moving_source"
    if local_mode:
        s, ds = _cell_centers(float(grid["arc_min_offset_mm"]), float(grid["arc_max_offset_mm"]), int(grid["arc_points"]))
        source_path_length = float(grid["arc_max_offset_mm"]) - float(grid["arc_min_offset_mm"])
    else:
        s, ds = _cell_centers(0.0, circumference, int(grid["arc_points"]))
        source_path_length = circumference
    n, dn = _cell_centers(float(grid["radial_min_offset_mm"]), float(grid["radial_max_offset_mm"]), int(grid["radial_points"]))
    z, dz = _cell_centers(float(grid["axial_min_offset_mm"]), float(grid["axial_max_offset_mm"]), int(grid["axial_points"]))
    ss, nn, zz = np.meshgrid(s, n, z, indexing="ij")
    cell_volume = ds * dn * dz
    source_resolution = {
        "ds_mm": ds,
        "dn_mm": dn,
        "dz_mm": dz,
        "ds_over_a_front": ds / float(heat_source["a_front_mm"]),
        "dn_over_b": dn / float(heat_source["b_radial_mm"]),
        "dz_over_c": dz / float(heat_source["c_axial_mm"]),
        "target_max_ratio": 1.0 / 3.0,
        "target_met": all(
            ratio <= 1.0 / 3.0
            for ratio in (
                ds / float(heat_source["a_front_mm"]),
                dn / float(heat_source["b_radial_mm"]),
                dz / float(heat_source["c_axial_mm"]),
            )
        ),
    }

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
    sensor_coordinates = {
        "QT_HAZ": (0.0, -5.0, 0.0),
        "fusion_line": (0.0, 0.0, 0.0),
        "weld_center": (0.0, 1.0, 0.0),
        "Q235B_HAZ": (0.0, 5.0, 0.0),
    }
    sensor_history: dict[str, list[dict[str, float]]] = {key: [] for key in sensor_coordinates}

    time_step = float(grid["time_step_s"])
    output_interval = float(grid["output_interval_s"])
    weld_duration = (
        float(grid.get("local_duration_s", 0.0))
        if local_mode
        else float(geometry["weld_length_mm"]) / float(process["travel_speed_mm_s"])
    )
    total_duration = weld_duration + float(process["cooling_hold_s"]) + float(process.get("post_release_cooling_s", 0.0))
    ui_net_power_w = float(process["efficiency"]) * float(process["current_a"]) * float(process["voltage_v"])
    ui_line_energy_j_per_mm = ui_net_power_w / float(process["travel_speed_mm_s"])
    steps = int(math.ceil(total_duration / time_step))
    epsilon = float(process["emissivity"])
    sigma = 5.670374419e-8 / 1e6
    source_energy_j = 0.0
    source_power_min_w = math.inf
    source_power_max_w = -math.inf
    source_power_max_relative_error = 0.0
    source_active_steps = 0
    convection_energy_j = 0.0
    radiation_energy_j = 0.0
    advective_energy_export_j = 0.0
    max_cooling_rate = np.zeros_like(temperature)
    next_output = 0.0
    initial_density = _material_fields(temperature, material_id, materials)[1]
    initial_internal_energy_j = float(np.sum(_enthalpy_per_mass(temperature, material_id, materials) * initial_density * cell_volume))

    for step in range(steps):
        time_s = step * time_step
        step_dt = min(time_step, max(0.0, total_duration - time_s))
        if step_dt <= 0.0:
            break
        conductivity, density, capacity = _material_fields(temperature, material_id, materials)
        # 面心谐均导热系数使内部导热通量守恒；局部窗口的两端为零通量边界。
        if local_mode:
            k_s_faces = 2.0 * conductivity[:-1, :, :] * conductivity[1:, :, :] / np.maximum(conductivity[:-1, :, :] + conductivity[1:, :, :], 1e-30)
            cond_s = np.zeros_like(temperature)
            cond_s[0, :, :] = k_s_faces[0, :, :] * (temperature[1, :, :] - temperature[0, :, :]) / ds**2
            cond_s[1:-1, :, :] = (k_s_faces[1:, :, :] * (temperature[2:, :, :] - temperature[1:-1, :, :]) - k_s_faces[:-1, :, :] * (temperature[1:-1, :, :] - temperature[:-2, :, :])) / ds**2
            cond_s[-1, :, :] = -k_s_faces[-1, :, :] * (temperature[-1, :, :] - temperature[-2, :, :]) / ds**2
        else:
            k_s_plus = 2.0 * conductivity * np.roll(conductivity, -1, axis=0) / np.maximum(conductivity + np.roll(conductivity, -1, axis=0), 1e-30)
            k_s_minus = np.roll(k_s_plus, 1, axis=0)
            cond_s = (k_s_plus * (np.roll(temperature, -1, axis=0) - temperature) - k_s_minus * (temperature - np.roll(temperature, 1, axis=0))) / ds**2
        cond_n = np.zeros_like(temperature)
        k_n_plus = 2.0 * conductivity[:, 1:, :] * conductivity[:, :-1, :] / np.maximum(conductivity[:, 1:, :] + conductivity[:, :-1, :], 1e-30)
        cond_n[:, 0, :] = k_n_plus[:, 0, :] * (temperature[:, 1, :] - temperature[:, 0, :]) / dn**2
        cond_n[:, 1:-1, :] = (k_n_plus[:, 1:, :] * (temperature[:, 2:, :] - temperature[:, 1:-1, :]) - k_n_plus[:, :-1, :] * (temperature[:, 1:-1, :] - temperature[:, :-2, :])) / dn**2
        cond_n[:, -1, :] = -k_n_plus[:, -1, :] * (temperature[:, -1, :] - temperature[:, -2, :]) / dn**2
        cond_z = np.zeros_like(temperature)
        k_z_plus = 2.0 * conductivity[:, :, 1:] * conductivity[:, :, :-1] / np.maximum(conductivity[:, :, 1:] + conductivity[:, :, :-1], 1e-30)
        cond_z[:, :, 0] = k_z_plus[:, :, 0] * (temperature[:, :, 1] - temperature[:, :, 0]) / dz**2
        cond_z[:, :, 1:-1] = (k_z_plus[:, :, 1:] * (temperature[:, :, 2:] - temperature[:, :, 1:-1]) - k_z_plus[:, :, :-1] * (temperature[:, :, 1:-1] - temperature[:, :, :-2])) / dz**2
        cond_z[:, :, -1] = -k_z_plus[:, :, -1] * (temperature[:, :, -1] - temperature[:, :, -2]) / dz**2
        temperature += step_dt * (cond_s + cond_n + cond_z) / (density * capacity)

        if time_s < weld_duration - 1e-12:
            source_dt = min(step_dt, weld_duration - time_s)
            center_s = (
                -float(grid["arc_max_offset_mm"]) / 2.0 + float(process["travel_speed_mm_s"]) * (time_s + source_dt / 2.0)
                if local_mode
                else (float(process["travel_speed_mm_s"]) * (time_s + source_dt / 2.0)) % circumference
            )
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
                periodic_s=not local_mode,
            )
            temperature += source_dt * source / (density * capacity)
            source_power_w = float(np.sum(source) * cell_volume)
            source_power_min_w = min(source_power_min_w, source_power_w)
            source_power_max_w = max(source_power_max_w, source_power_w)
            source_power_max_relative_error = max(
                source_power_max_relative_error,
                abs(source_power_w - float(process["net_power_w"])) / float(process["net_power_w"]),
            )
            source_energy_j += source_power_w * source_dt
            source_active_steps += 1

        # 外边界按暴露面面积计热损失；角单元会自然累加两个面的面积。
        ambient = float(process["cooling_environment_c"])
        delta_t = temperature - ambient
        convection_flux = float(process["convection_coefficient_w_m2k"]) * delta_t / 1e6
        radiation_flux = epsilon * sigma * ((temperature + 273.15) ** 4 - (ambient + 273.15) ** 4)
        exposed_area = np.zeros_like(temperature)
        exposed_area[:, 0, :] += ds * dz
        exposed_area[:, -1, :] += ds * dz
        exposed_area[:, :, 0] += ds * dn
        exposed_area[:, :, -1] += ds * dn
        loss_w_mm3 = (convection_flux + radiation_flux) * exposed_area / cell_volume
        temperature -= step_dt * loss_w_mm3 / (density * capacity)
        convection_energy_j += float(np.sum(convection_flux * exposed_area) * step_dt)
        radiation_energy_j += float(np.sum(radiation_flux * exposed_area) * step_dt)
        max_cooling_rate = np.maximum(max_cooling_rate, np.maximum(previous - temperature, 0.0) / step_dt)

        higher = temperature > peak
        peak = np.where(higher, temperature, peak)
        peak_time = np.where(higher, time_s, peak_time)
        sample_time = time_s + step_dt
        crossing_800 = _crossing_time(previous, temperature, 800.0, sample_time, step_dt)
        crossing_500 = _crossing_time(previous, temperature, 500.0, sample_time, step_dt)
        t800_down = np.where(np.isnan(t800_down), crossing_800, t800_down)
        t500_down = np.where((~np.isnan(t800_down)) & np.isnan(t500_down), crossing_500, t500_down)
        if sample_time + 1e-9 >= next_output:
            row = {"time_s": sample_time}
            for name, target in sensor_coordinates.items():
                sensor_target = (target[0] - float(process["travel_speed_mm_s"]) * sample_time, target[1], target[2]) if local_mode else target
                sensor_temperature = _trilinear_periodic(temperature, s, n, z, sensor_target, circumference, periodic_s=not local_mode)
                row[name + "_c"] = sensor_temperature
                sensor_history[name].append({"time_s": sample_time, "temperature_c": sensor_temperature})
            history.append(row)
            while next_output <= sample_time + 1e-9:
                next_output += output_interval
        previous = temperature.copy()

    valid_t85 = (peak > 800.0) & np.isfinite(t800_down) & np.isfinite(t500_down) & (t500_down >= t800_down)
    t85 = np.where(valid_t85, t500_down - t800_down, np.nan)
    continuous_expected_energy_j = float(process["net_power_w"]) * weld_duration
    discrete_expected_energy_j = float(process["net_power_w"]) * source_active_steps * time_step
    final_density = _material_fields(temperature, material_id, materials)[1]
    final_internal_energy_j = float(np.sum(_enthalpy_per_mass(temperature, material_id, materials) * final_density * cell_volume))
    delta_internal_energy_j = final_internal_energy_j - initial_internal_energy_j
    loss_energy_j = convection_energy_j + radiation_energy_j
    global_energy_residual_j = source_energy_j - convection_energy_j - radiation_energy_j - advective_energy_export_j - delta_internal_energy_j
    energy_balance_error_pct = abs(source_energy_j - continuous_expected_energy_j) / continuous_expected_energy_j * 100.0
    discrete_energy_balance_error_pct = abs(source_energy_j - discrete_expected_energy_j) / discrete_expected_energy_j * 100.0
    metadata = {
        **_traceability(),
        "stage": "THERMAL-0",
        "evidence_level": "solver_result_unvalidated",
        "solver_version": "THERMAL-0.1-conservative-finite-volume-v5",
        "model": "3d_local_source_window_goldak_conservative_finite_volume",
        "input_file": str(INPUT_PATH.relative_to(ROOT)).replace("\\", "/"),
        "input_sha256": _sha256(INPUT_PATH),
        "material_file": str(MATERIAL_PATH.relative_to(ROOT)).replace("\\", "/"),
        "material_sha256": _sha256(MATERIAL_PATH),
        "grid": {"coordinate_mode": "local_moving_source" if local_mode else "periodic_full_path", "arc_points": len(s), "radial_points": len(n), "axial_points": len(z), "cell_count": int(temperature.size), "cell_volume_mm3": cell_volume, "source_resolution": source_resolution, "local_source_window_mm": [float(s[0]), float(s[-1])] if local_mode else None},
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
            "source_energy_normalization": {
                "status": "PASS" if source_power_max_relative_error < 0.01 else "REVIEW",
                "description": "离散 Goldak 体积分对应名义净输入功率。",
            },
            "boundary_loss_estimate_j": loss_energy_j,
            "delta_internal_energy_j": delta_internal_energy_j,
            "convection_energy_j": convection_energy_j,
            "radiation_energy_j": radiation_energy_j,
            "advective_energy_export_j": advective_energy_export_j,
            "global_thermal_energy_balance": {
                "source_energy_j": source_energy_j,
                "delta_internal_energy_j": delta_internal_energy_j,
                "convection_energy_j": convection_energy_j,
                "radiation_energy_j": radiation_energy_j,
                "advective_energy_export_j": advective_energy_export_j,
                "residual_j": global_energy_residual_j,
                "residual_percent_of_source": abs(global_energy_residual_j) / max(abs(source_energy_j), 1e-30) * 100.0,
                "status": "PASS" if abs(global_energy_residual_j) / max(abs(source_energy_j), 1e-30) < 0.02 else "REVIEW",
            },
            "energy_balance_note": "全局账本按 E_source = ΔU + E_convection + E_radiation + residual 记录；残差包含有限体积边界/显式离散误差。",
        },
        "assumptions": [
            "Goldak 尺寸、前后能量比例和效率均为 design_assumption，未用热电偶/宏观截面校准。",
            "接口展开坐标用于局部三维热历史；未包含完整装配体的实体接触换热。",
            "未模拟熔池流动、相变、焊缝逐道激活或温度相关塑性。",
            "t8/5 只作为热循环描述量，不是 QT450-10 的独立相组成判据。",
            "焊缝金属采用焊前已存在的 pre-existing weld metal thermal surrogate；逐段激活留待 THERMAL-1。",
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
        "sampling": {"method": "trilinear_interpolation", "coordinate_system": "local_moving_source_s_n_z_cell_centers" if local_mode else "periodic_s_n_z_cell_centers"},
        "sensors": {
            name: {
                "requested_coordinate_mm": [float(value) for value in target],
                "material_region": "QT450-10" if target[1] < -3.0 else "Q235B" if target[1] > 3.0 else "ERNiFe-CI",
                "arc_position_mm": float(target[0]),
                "arc_position_deg": float(target[0] / circumference * 360.0),
            }
            for name, target in sensor_coordinates.items()
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
        "fusion_threshold_c": float(config["metallurgy"]["fusion_threshold_c"]),
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
