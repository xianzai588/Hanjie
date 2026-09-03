"""运行五组二维热—结构代理模型交叉检查。

本实现把三角形 FE、瞬态热传导、热弹性残余本征应变和位置度后处理连接起来。
模型是二维代理复核，不是完整三维焊接工艺仿真。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import scipy.sparse as sparse
from scipy.sparse.linalg import factorized, spsolve
from skfem import MeshTri
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "simulation" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from position_tolerance import DATUM_REFERENCE_TEXT, fit_axis  # noqa: E402


DEFAULT_CONFIG = ROOT / "simulation" / "configs" / "default.yaml"
OUTPUT_ROOT = ROOT / "simulation" / "fe"
CASE_ROOT = ROOT / "simulation" / "cases"

FE_MODEL_STATEMENT = "二维热—结构代理模型交叉检查，不是完整焊接 FE、完整三维焊接仿真或 CMM 结果。"
FE_MODEL_LIMITATIONS = [
    "热源峰值约 462–562 °C，远未达到钢/铸铁熔化温度，因此未模拟熔池形成、熔合和焊缝金属激活。",
    "结构部分采用平面应力、最大温度驱动的等效残余本征应变和等效径向弹簧夹具。",
    "未包含温度相关塑性、相变、真实焊缝几何与本构、三维壳体高度、接触和真实夹具预紧。",
]


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"配置必须是对象: {path}")
    return value


def angle_distance(a: np.ndarray, b: float) -> np.ndarray:
    return np.abs(np.arctan2(np.sin(a - b), np.cos(a - b)))


def sequence_for(name: str, count: int = 6) -> list[int]:
    half = count // 2
    if name == "S1":
        return list(range(count))
    if name == "S2":
        return [item for i in range(half) for item in (i, i + half)]
    if name == "S3":
        return ([0, half] + [item for i in range(1, half) for item in ((half - i) % count, (count - i) % count)])[:count]
    raise ValueError(f"未知顺序: {name}")


def build_mesh(config: dict[str, Any], mesh_points: int, structure: str) -> tuple[MeshTri, np.ndarray, np.ndarray]:
    geometry = config["geometry"]
    core_r = geometry["seat_core_outer_diameter_mm"] / 2.0
    bore_r = geometry["bearing_bore_diameter_mm"] / 2.0
    wing_r = geometry["wing_outer_radius_mm"]
    shell_outer = geometry["shell_outer_diameter_mm"] / 2.0
    shell_inner = shell_outer - geometry["shell_thickness_mm"]
    wing_half_angle = math.asin((geometry.get("wing_width", 18.0) / 2.0) / wing_r)
    # 计算域必须覆盖完整外壳外径；此前用 shell_inner 截断了 Q235B 外壳环。
    coordinate = np.linspace(-shell_outer, shell_outer, mesh_points)
    base = MeshTri.init_tensor(coordinate, coordinate)
    centers = base.p[:, base.t].mean(axis=1).T
    radius = np.linalg.norm(centers, axis=1)
    angles = np.arctan2(centers[:, 1], centers[:, 0])
    wing_angles = np.arange(6, dtype=float) * 2.0 * math.pi / 6.0
    in_wing = np.zeros(radius.shape, dtype=bool)
    for wing_angle in wing_angles:
        in_wing |= angle_distance(angles, wing_angle) <= wing_half_angle
    if structure == "baseline":
        # 基准结构：座体到壳体内壁用连续盘表示，外壳单独保留 Q235B 环。
        keep = ((radius >= bore_r) & (radius <= shell_inner)) | ((radius >= shell_inner) & (radius <= shell_outer))
    elif structure == "flex":
        # 优化结构：中心刚性区 + 六个径向连接翼，中间保留柔顺槽。
        # 柔顺槽在座体与六个径向翼之间保留；翼端至 shell_inner 的 1.2 mm
        # 是焊接桥接区的二维等效表示，避免把焊接接头错误地建成脱开结构。
        keep = ((radius >= bore_r) & (radius <= core_r)) | ((radius >= core_r - 1.5) & (radius <= shell_inner) & in_wing) | ((radius >= shell_inner) & (radius <= shell_outer))
    else:
        raise ValueError(f"未知结构: {structure}")
    # scikit-fem 的 remove_elements 接收元素索引，而不是布尔掩码。
    mesh = base.remove_elements(np.flatnonzero(~keep))
    centers = mesh.p[:, mesh.t].mean(axis=1).T
    radius = np.linalg.norm(centers, axis=1)
    angles = np.arctan2(centers[:, 1], centers[:, 0])
    in_wing = np.zeros(radius.shape, dtype=bool)
    for wing_angle in wing_angles:
        in_wing |= angle_distance(angles, wing_angle) <= wing_half_angle
    if structure == "baseline":
        is_seat = (radius >= bore_r) & (radius <= shell_inner)
    else:
        is_seat = ((radius <= core_r) & (radius >= bore_r)) | ((radius >= core_r - 1.5) & (radius <= shell_inner) & in_wing)
    is_steel = ~is_seat
    return mesh, is_seat, is_steel


def triangle_kinematics(mesh: MeshTri, is_seat: np.ndarray, config: dict[str, Any]) -> tuple[list[np.ndarray], list[float], np.ndarray]:
    materials = config["materials"]
    element_nodes = mesh.t.T
    dof_grads: list[np.ndarray] = []
    areas: list[float] = []
    for nodes in element_nodes:
        xy = mesh.p[:, nodes]
        twice_area = (
            (xy[0, 1] - xy[0, 0]) * (xy[1, 2] - xy[1, 0])
            - (xy[1, 1] - xy[1, 0]) * (xy[0, 2] - xy[0, 0])
        )
        area = abs(float(twice_area)) / 2.0
        if area <= 1e-10:
            raise ValueError("网格包含退化单元")
        gradients = np.array([
            [xy[1, 1] - xy[1, 2], xy[1, 2] - xy[1, 0], xy[1, 0] - xy[1, 1]],
            [xy[0, 2] - xy[0, 1], xy[0, 0] - xy[0, 2], xy[0, 1] - xy[0, 0]],
        ]) / (2.0 * area)
        dof_grads.append(gradients)
        areas.append(area)
    return dof_grads, areas, element_nodes


def material_values(config: dict[str, Any], seat: bool) -> tuple[float, float, float, float, float, float]:
    material = config["materials"]["qt450_10" if seat else "q235b"]
    return (
        material["density_kg_m3"] * 1e-9,
        material["specific_heat_j_kgk"],
        material["thermal_conductivity_w_mk"] / 1000.0,
        material["elastic_modulus_gpa"] * 1000.0,
        material["alpha_per_k"],
        0.3,
    )


def assemble_thermal(mesh: MeshTri, is_seat: np.ndarray, grads: list[np.ndarray], areas: list[float], nodes: np.ndarray, config: dict[str, Any]) -> tuple[sparse.csc_matrix, sparse.csc_matrix]:
    node_count = mesh.p.shape[1]
    mass = sparse.lil_matrix((node_count, node_count), dtype=float)
    conductivity = sparse.lil_matrix((node_count, node_count), dtype=float)
    thickness = config["geometry"]["seat_thickness_mm"]
    for index, element_nodes in enumerate(nodes):
        rho, cp, k, _, _, _ = material_values(config, bool(is_seat[index]))
        area = areas[index]
        local_mass = rho * cp * thickness * area / 12.0 * np.array([[2, 1, 1], [1, 2, 1], [1, 1, 2]], dtype=float)
        local_k = k * thickness * area * (grads[index].T @ grads[index])
        for i, global_i in enumerate(element_nodes):
            for j, global_j in enumerate(element_nodes):
                mass[global_i, global_j] += local_mass[i, j]
                conductivity[global_i, global_j] += local_k[i, j]

    # 外表面/内孔表面对流，边界对流系数取设计假设量级。
    h = 2.0e-5  # W/(mm²·K)，仅为二维模型边界参数
    for facet in mesh.facets[:, mesh.boundary_facets()].T:
        p0, p1 = mesh.p[:, facet[0]], mesh.p[:, facet[1]]
        midpoint = (p0 + p1) / 2.0
        radius = float(np.linalg.norm(midpoint))
        if radius < 21.5 or radius > 73.5:
            length = float(np.linalg.norm(p1 - p0))
            local_h = h * length / 6.0 * np.array([[2.0, 1.0], [1.0, 2.0]])
            for i, global_i in enumerate(facet):
                for j, global_j in enumerate(facet):
                    conductivity[global_i, global_j] += local_h[i, j]
    return mass.tocsc(), conductivity.tocsc()


def weld_source(mesh: MeshTri, element_nodes: np.ndarray, areas: list[float], segment_index: int, config: dict[str, Any]) -> sparse.csc_matrix:
    geometry = config["geometry"]
    process = config["process"]
    radius = geometry["wing_outer_radius_mm"]
    weld_length = geometry["weld_segment_length_mm"]
    angle = segment_index * 2.0 * math.pi / 6.0
    half_angle = weld_length / (2.0 * radius)
    centers = mesh.p[:, mesh.t].mean(axis=1).T
    center_radius = np.linalg.norm(centers, axis=1)
    center_angle = np.arctan2(centers[:, 1], centers[:, 0])
    active = (center_radius >= radius - 5.0) & (center_radius <= radius + 1.0) & (angle_distance(center_angle, angle) <= half_angle)
    active_indices = np.flatnonzero(active)
    if active_indices.size == 0:
        raise ValueError(f"焊段 {segment_index + 1} 没有覆盖网格单元")
    thickness = geometry["seat_thickness_mm"]
    volume = sum(areas[index] * thickness for index in active_indices)
    power = process["efficiency"] * process["current_a"] * process["voltage_v"]
    source_density = power / volume
    source = sparse.lil_matrix((mesh.p.shape[1], 1), dtype=float)
    for index in active_indices:
        for node in element_nodes[index]:
            source[node, 0] += source_density * areas[index] * thickness / 3.0
    return source.tocsc()


def transient_temperature(mesh: MeshTri, is_seat: np.ndarray, grads: list[np.ndarray], areas: list[float], nodes: np.ndarray, sequence: str, config: dict[str, Any], time_steps_per_segment: int = 18) -> tuple[np.ndarray, np.ndarray, list[dict[str, float]]]:
    mass, conductivity = assemble_thermal(mesh, is_seat, grads, areas, nodes, config)
    process = config["process"]
    dt = config["geometry"]["weld_segment_length_mm"] / process["travel_speed_mm_s"] / time_steps_per_segment
    system = (mass / dt + conductivity).tocsc()
    solve = factorized(system)
    temperature = np.full(mesh.p.shape[1], process["preheat_c"], dtype=float)
    maximum = temperature.copy()
    segment_history: list[dict[str, float]] = []
    order = sequence_for(sequence)
    for weld_number, segment_index in enumerate(order):
        source = weld_source(mesh, nodes, areas, segment_index, config)
        source_nodes = np.flatnonzero(source.toarray().ravel() > 0.0)
        peak_source = process["preheat_c"]
        bore_mask = np.abs(np.linalg.norm(mesh.p, axis=0) - config["geometry"]["bearing_bore_diameter_mm"] / 2.0) < 2.2
        peak_bore = process["preheat_c"]
        for _ in range(time_steps_per_segment):
            temperature = solve(mass @ temperature / dt + source.toarray().ravel())
            maximum = np.maximum(maximum, temperature)
            peak_source = max(peak_source, float(temperature[source_nodes].max()))
            peak_bore = max(peak_bore, float(temperature[bore_mask].max()))
        segment_history.append({
            "weld_number": weld_number + 1,
            "segment_id": segment_index + 1,
            "peak_source_c": peak_source,
            "peak_bore_c": peak_bore,
            "cooling_dt_s": dt,
        })
    # 无热源冷却阶段：记录完全冷却前的最大温度下降，而不是假设瞬间回到室温。
    cooling_steps = max(30, time_steps_per_segment * 3)
    zero_source = sparse.csc_matrix((mesh.p.shape[1], 1), dtype=float)
    for _ in range(cooling_steps):
        temperature = solve(mass @ temperature / dt + zero_source.toarray().ravel())
    return temperature, maximum, segment_history


def elasticity_solution(mesh: MeshTri, is_seat: np.ndarray, grads: list[np.ndarray], areas: list[float], nodes: np.ndarray, max_temperature: np.ndarray, config: dict[str, Any], fixture: str) -> np.ndarray:
    node_count = mesh.p.shape[1]
    dof_count = node_count * 2
    stiffness = sparse.lil_matrix((dof_count, dof_count), dtype=float)
    load = np.zeros(dof_count, dtype=float)
    thickness = config["geometry"]["seat_thickness_mm"]
    residual_fraction = config["model"]["residual_fraction"]
    nominal = config["model"]["nominal_temperature_c"]
    for index, element_nodes in enumerate(nodes):
        _, _, _, young, alpha, poisson = material_values(config, bool(is_seat[index]))
        factor = young / (1.0 - poisson * poisson)
        constitutive = factor * np.array([[1.0, poisson, 0.0], [poisson, 1.0, 0.0], [0.0, 0.0, (1.0 - poisson) / 2.0]])
        gradient = grads[index]
        b_matrix = np.zeros((3, 6), dtype=float)
        for local in range(3):
            b_matrix[0, 2 * local] = gradient[0, local]
            b_matrix[1, 2 * local + 1] = gradient[1, local]
            b_matrix[2, 2 * local] = gradient[1, local]
            b_matrix[2, 2 * local + 1] = gradient[0, local]
        area = areas[index]
        local_k = b_matrix.T @ constitutive @ b_matrix * area * thickness
        local_temp = float(max_temperature[element_nodes].max())
        residual_delta = max(local_temp - nominal, 0.0) * residual_fraction
        thermal_strain = np.array([alpha * residual_delta, alpha * residual_delta, 0.0])
        local_force = b_matrix.T @ constitutive @ thermal_strain * area * thickness
        global_dofs = np.asarray([[2 * node, 2 * node + 1] for node in element_nodes]).ravel()
        load[global_dofs] += local_force
        for i, global_i in enumerate(global_dofs):
            for j, global_j in enumerate(global_dofs):
                stiffness[global_i, global_j] += local_k[i, j]

    # 3/6 个支撑点的径向弹簧：刚性基准用高刚度，柔顺夹具用设计等效刚度。
    support_angles = np.arange(6, dtype=float) * 2.0 * math.pi / 6.0
    support_nodes = []
    outer_nodes = np.flatnonzero(np.linalg.norm(mesh.p, axis=0) > 69.0)
    for angle in support_angles:
        distances = angle_distance(np.arctan2(mesh.p[1, outer_nodes], mesh.p[0, outer_nodes]), angle)
        radial_distance = np.abs(np.linalg.norm(mesh.p[:, outer_nodes], axis=0) - 73.8)
        support_nodes.append(int(outer_nodes[np.argmin(distances + radial_distance / 73.8)]))
    spring_k = 1.0e8 if fixture == "rigid" else config["materials"]["fixture"]["equivalent_stiffness_n_mm"]
    for node in support_nodes:
        vector = mesh.p[:, node]
        unit = vector / np.linalg.norm(vector)
        block = spring_k * np.outer(unit, unit)
        dofs = [2 * node, 2 * node + 1]
        for i, global_i in enumerate(dofs):
            for j, global_j in enumerate(dofs):
                stiffness[global_i, global_j] += block[i, j]

    # 去除刚体自由度：0°支撑固定 x/y，120°支撑固定 y。
    anchor = support_nodes[0]
    secondary = support_nodes[2]
    fixed = np.array([2 * anchor, 2 * anchor + 1, 2 * secondary + 1], dtype=int)
    all_dofs = np.arange(dof_count)
    free = np.setdiff1d(all_dofs, fixed)
    displacement = np.zeros(dof_count, dtype=float)
    displacement[free] = spsolve(stiffness.tocsc()[free][:, free], load[free])
    return displacement


def export_bore_nodes(mesh: MeshTri, displacement: np.ndarray, config: dict[str, Any], path: Path | None = None) -> np.ndarray:
    bore_radius = config["geometry"]["bearing_bore_diameter_mm"] / 2.0
    nodes = np.flatnonzero(np.abs(np.linalg.norm(mesh.p, axis=0) - bore_radius) < 2.2)
    if nodes.size < 12:
        raise ValueError(f"内孔节点数量不足: {nodes.size}")
    levels = (0.0, config["model"]["bore_effective_height_mm"] / 2.0, config["model"]["bore_effective_height_mm"])
    points = []
    for z in levels:
        for node in nodes:
            points.append([
                mesh.p[0, node] + displacement[2 * node],
                mesh.p[1, node] + displacement[2 * node + 1],
                z,
            ])
    points_array = np.asarray(points)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["x_mm", "y_mm", "z_mm"])
            writer.writerows(points_array.tolist())
    return points_array


def write_case(case: dict[str, str], config: dict[str, Any], mesh_points: int, write_outputs: bool = True) -> dict[str, Any]:
    mesh, is_seat, _ = build_mesh(config, mesh_points, case["structure"])
    grads, areas, nodes = triangle_kinematics(mesh, is_seat, config)
    final_temperature, max_temperature, history = transient_temperature(mesh, is_seat, grads, areas, nodes, case["sequence"], config)
    displacement = elasticity_solution(mesh, is_seat, grads, areas, nodes, max_temperature, config, case["fixture"])
    case_dir = CASE_ROOT / case["case_id"]
    if write_outputs:
        case_dir.mkdir(parents=True, exist_ok=True)
    bore_path = case_dir / "bore-nodes.csv" if write_outputs else None
    bore_points = export_bore_nodes(mesh, displacement, config, bore_path)
    position = fit_axis(bore_points, section_count=3)
    max_disp = np.linalg.norm(displacement.reshape(-1, 2), axis=1)
    section_quality = position["section_quality"]
    fit_residual_p95 = max(float(item["residual_p95_mm"]) for item in section_quality)
    outlier_count = sum(int(item["outlier_count"]) for item in section_quality)
    result = {
        "case_id": case["case_id"],
        "structure": case["structure"],
        "fixture": case["fixture"],
        "layout_points": 6,
        "sequence": case["sequence"],
        "mesh_points_per_axis": mesh_points,
        "mesh_nodes": int(mesh.p.shape[1]),
        "mesh_elements": int(mesh.t.shape[1]),
        "max_temperature_c": round(float(max_temperature.max()), 6),
        "final_temperature_max_c": round(float(final_temperature.max()), 6),
        "max_displacement_mm": round(float(max_disp.max()), 9),
        "p_fe_mm": round(float(position["p_sim_mm"]), 9),
        "r_max_fe_mm": round(float(position["r_max_mm"]), 9),
        "axis_slope_x": round(float(position["x_slope_mm_per_mm"]), 9),
        "axis_slope_y": round(float(position["y_slope_mm_per_mm"]), 9),
        "fit_method": position["fit_method"],
        "fit_residual_p95_mm": round(fit_residual_p95, 9),
        "axis_center_residual_rms_mm": round(float(position["axis_center_residual_rms_mm"]), 9),
        "axis_center_residual_p95_mm": round(float(position["axis_center_residual_p95_mm"]), 9),
        "outlier_count": outlier_count,
        "measurement_uncertainty_proxy_mm": round(float(position["measurement_uncertainty_proxy_mm"]), 9),
        "pass_in_model": bool(position["p_sim_mm"] <= config["model"]["position_tolerance_limit_mm"]),
        "model_statement": FE_MODEL_STATEMENT,
        "model_limitations": FE_MODEL_LIMITATIONS,
        "datum_reference": DATUM_REFERENCE_TEXT,
    }
    if write_outputs:
        with (case_dir / "result.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=result.keys())
            writer.writeheader()
            writer.writerow(result)
        with (case_dir / "temperature-history.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=history[0].keys())
            writer.writeheader()
            writer.writerows(history)
        case_config = {
            "case": case,
            "mesh_points_per_axis": mesh_points,
            "model": config["model"],
            "geometry": config["geometry"],
            "process": config["process"],
            "materials": config["materials"],
        }
        (case_dir / "config.yaml").write_text(yaml.safe_dump(case_config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        (case_dir / "README.md").write_text(
            f"# {case['case_id']}\n\n"
            "本目录为二维热—结构代理模型交叉检查。\n\n"
            f"- 方案：{case['structure']} / {case['fixture']} / 6P / {case['sequence']}。\n"
            "- 节点来源：二维三角形 FE 网格；`bore-nodes.csv` 已送入 `position_tolerance.py`。\n"
            "- 热源限制：峰值温度未达到钢/铸铁熔化温度，未模拟熔池、熔合和焊缝金属激活。\n"
            "- 边界：不包含完整三维高度、温度相关塑性、相变、接触和真实材料温度曲线。\n"
            "- 二维连接：翼端至壳体内壁的 1.2 mm 间隙以等效焊接桥接区表示。\n"
            "- 结果性质：用于排序/趋势复核，不是实物 CMM 认证。\n",
            encoding="utf-8",
        )
    return result


def write_summary(rows: list[dict[str, Any]], output_dir: Path, convergence: list[dict[str, Any]] | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "fe-summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    reference = {row["case_id"]: row["p_fe_mm"] for row in rows}
    lines = [
        "# FE 五案例二维代理交叉检查结果",
        "",
        f"> {FE_MODEL_STATEMENT}",
        "",
        "| Case | 方案 | 顺序 | 网格节点 | 网格单元 | P_FE (mm) | 模型内判定 |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(f"| {row['case_id']} | {row['structure']}/{row['fixture']} | {row['sequence']} | {row['mesh_nodes']} | {row['mesh_elements']} | {row['p_fe_mm']:.9f} | {row['pass_in_model']} |")
    lines.extend([
        "",
        "## 排序",
        "",
        f"当前 FE 案例排序：{' → '.join(sorted(reference, key=reference.get))}。排序只对当前五个二维模型成立。",
        "",
        "FE 内孔节点已经写入各 Case 的 `bore-nodes.csv`，并由 `position_tolerance.fit_axis` 在 A/B 装配基准系中分层拟合圆和轴线。二维模型沿 z 复制截面，因此不提供真实三维倾斜证据。",
        "## 物理含义与限制",
        "",
        *[f"- {item}" for item in FE_MODEL_LIMITATIONS],
        "该结果的作用是独立于降阶模型的结构反例检查，不是焊后绝对位置度预测或制造放行证据。",
    ])
    if convergence:
        lines.extend(["", "## 网格收敛检查", "", "| Case | 网格点数 | 节点 | 单元 | P_FE (mm) | 相邻网格变化 (%) |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
        for row in convergence:
            change = "N/A" if row["relative_change_pct"] is None else f"{row['relative_change_pct']:.3f}"
            lines.append(f"| {row['case_id']} | {row['mesh_points_per_axis']} | {row['mesh_nodes']} | {row['mesh_elements']} | {row['p_fe_mm']:.9f} | {change} |")
        finest_change = convergence[-1]["relative_change_pct"]
        if finest_change is None:
            convergence_text = "仅有一个网格，未计算相邻变化"
        else:
            convergence_status = "通过当前 5% 参考门" if finest_change <= 5.0 else "未通过当前 5% 参考门，仍需加密或改进离散化"
            convergence_text = f"最细网格相邻变化为 {finest_change:.3f}%（{convergence_status}）"
        lines.extend(["", f"相邻网格变化按 `|P(n)-P(n-1)| / P(n-1)` 计算；{convergence_text}。该指标只检查当前二维代理离散化，不代表三维焊接模型收敛。"])
        with (output_dir / "fe-convergence.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            fields = list(convergence[0].keys())
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(convergence)
    (output_dir / "fe-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_summary(rows: list[dict[str, Any]], path: Path) -> None:
    labels = [row["case_id"] for row in rows]
    values = [row["p_fe_mm"] for row in rows]
    fig, axis = plt.subplots(figsize=(8, 4.5), constrained_layout=True)
    axis.bar(labels, values, color=["#64748b", "#0f766e", "#b45309", "#2563eb", "#7c3aed"])
    axis.axhline(0.05, color="#dc2626", linestyle="--", label="limit 0.05 mm")
    axis.set_ylabel("P_FE (mm)")
    axis.set_title("Five-case 2D FE position metric")
    axis.tick_params(axis="x", rotation=20)
    axis.legend()
    axis.grid(axis="y", alpha=0.25)
    fig.savefig(path, dpi=180)
    fig.savefig(path.with_suffix(".svg"))
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--mesh-points", type=int, default=61)
    parser.add_argument("--convergence-meshes", default="41,51,61,81", help="网格收敛点数，逗号分隔；设为空字符串跳过")
    args = parser.parse_args()
    if args.mesh_points < 31:
        parser.error("--mesh-points 至少为 31")
    config = load_yaml(args.config)
    cases = [
        {"case_id": "FE-001", "structure": "baseline", "fixture": "rigid", "sequence": "S1"},
        {"case_id": "FE-002", "structure": "baseline", "fixture": "rigid", "sequence": "S3"},
        {"case_id": "FE-003", "structure": "flex", "fixture": "compliant", "sequence": "S3"},
        {"case_id": "FE-004", "structure": "baseline", "fixture": "compliant", "sequence": "S3"},
        {"case_id": "FE-005", "structure": "flex", "fixture": "rigid", "sequence": "S3"},
    ]
    rows = [write_case(case, deepcopy(config), args.mesh_points) for case in cases]
    convergence_meshes = tuple(int(item.strip()) for item in args.convergence_meshes.split(",") if item.strip())
    if any(mesh < 31 for mesh in convergence_meshes):
        parser.error("--convergence-meshes 中每个网格点数必须至少为 31")
    convergence = []
    # 收敛矩阵使用与主对照相同的 S3/刚性夹具基准，避免把顺序变化误当成网格效应。
    convergence_case = {"case_id": "FE-CONV-BASELINE-RIGID-S3", "structure": "baseline", "fixture": "rigid", "sequence": "S3"}
    previous = None
    for mesh_points in convergence_meshes:
        result = write_case(convergence_case, deepcopy(config), mesh_points, write_outputs=False)
        value = float(result["p_fe_mm"])
        convergence.append({"case_id": convergence_case["case_id"], "mesh_points_per_axis": mesh_points, "mesh_nodes": result["mesh_nodes"], "mesh_elements": result["mesh_elements"], "p_fe_mm": value, "relative_change_pct": None if previous is None else 100.0 * abs(value - previous) / max(abs(previous), 1e-12)})
        previous = value
    write_summary(rows, OUTPUT_ROOT / "results", convergence)
    plot_summary(rows, OUTPUT_ROOT / "results" / "fe-summary.png")
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mesh_points_per_axis": args.mesh_points,
        "case_count": len(rows),
        "convergence_meshes": list(convergence_meshes),
        "matched_s3_case_count": 4,
        "solver": "scikit-fem mesh + SciPy sparse assembly",
        "statement": FE_MODEL_STATEMENT,
        "limitations": FE_MODEL_LIMITATIONS,
        "datum_reference": DATUM_REFERENCE_TEXT,
    }
    (OUTPUT_ROOT / "results" / "run-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已完成 {len(rows)} 组二维 FE 复核，结果: {OUTPUT_ROOT / 'results'}")
    for row in rows:
        print(f"{row['case_id']}: P_FE={row['p_fe_mm']:.9f} mm, pass={row['pass_in_model']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
