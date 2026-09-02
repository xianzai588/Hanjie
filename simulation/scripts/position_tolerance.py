"""按“内孔分层拟合圆—拟合轴线”的流程计算数值位置度评价指标。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Iterable

import numpy as np


# 数字结果统一在装配基准系中解释：B 为壳体理论中心轴，原点为 B 与 A
# （壳体安装基准平面）的交点；C 只定义周向姿态，不进入本孔轴线位置度框。
DATUM_DEFINITION = {
    "A": "壳体安装基准平面（z=0）",
    "B": "Q235B 壳体理论中心轴（x=0, y=0）",
    "C": "独立周向定位特征（装配姿态基准）",
    "controlled_feature": "Ø40 轴承孔轴线",
    "position_tolerance": "Ø0.05 | A | B",
}
DATUM_REFERENCE_TEXT = "A=壳体安装基准平面；B=Q235B 壳体理论中心轴；C=独立周向定位特征；受控特征=Ø40 孔轴线；位置度=Ø0.05 | A | B"
NOMINAL_AXIS_X_MM = 0.0
NOMINAL_AXIS_Y_MM = 0.0


def fit_circle_xy(points: np.ndarray) -> tuple[float, float, float]:
    """最小二乘拟合 x²+y²+Dx+Ey+F=0，返回圆心 x,y 和半径。"""
    if points.shape[0] < 3:
        raise ValueError("每个截面至少需要 3 个点")
    x = points[:, 0]
    y = points[:, 1]
    matrix = np.column_stack((x, y, np.ones_like(x)))
    rhs = -(x * x + y * y)
    d, e, f = np.linalg.lstsq(matrix, rhs, rcond=None)[0]
    cx, cy = -d / 2.0, -e / 2.0
    radius = float(np.sqrt(max(cx * cx + cy * cy - f, 0.0)))
    return float(cx), float(cy), radius


def fit_axis(points: np.ndarray, section_count: int = 3) -> dict[str, float]:
    """在 B=(0,0) 的名义轴上，对内孔点云分层拟合圆心和 x(z)、y(z) 轴线。"""
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("points 必须是 N×3 数组，列为 x,y,z (mm)")
    if points.shape[0] < section_count * 3:
        raise ValueError("点数不足，无法完成分层拟合")

    z_values = np.linspace(float(points[:, 2].min()), float(points[:, 2].max()), section_count)
    centers: list[tuple[float, float, float]] = []
    for index, z_value in enumerate(z_values):
        if index == section_count - 1:
            mask = points[:, 2] >= z_value - 1e-9
        else:
            next_z = z_values[index + 1]
            mask = (points[:, 2] >= z_value - 1e-9) & (points[:, 2] < next_z - 1e-9)
        section = points[mask]
        if section.shape[0] < 3:
            # 真实 CMM 导出通常包含多个 z 层；此处对稀疏输入采用最近点兜底。
            distances = np.abs(points[:, 2] - z_value)
            section = points[np.argsort(distances)[: max(3, points.shape[0] // section_count)]]
        cx, cy, _ = fit_circle_xy(section[:, :2])
        centers.append((cx, cy, float(z_value)))

    center_array = np.asarray(centers)
    x_slope, x_intercept = np.polyfit(center_array[:, 2], center_array[:, 0], 1)
    y_slope, y_intercept = np.polyfit(center_array[:, 2], center_array[:, 1], 1)
    z_min, z_max = float(center_array[:, 2].min()), float(center_array[:, 2].max())
    z_eval = np.linspace(z_min, z_max, 25)
    x_eval = x_slope * z_eval + x_intercept
    y_eval = y_slope * z_eval + y_intercept
    radial = np.sqrt(
        (x_eval - NOMINAL_AXIS_X_MM) ** 2 + (y_eval - NOMINAL_AXIS_Y_MM) ** 2
    )
    r_max = float(radial.max())
    return {
        "x_intercept_mm": float(x_intercept),
        "y_intercept_mm": float(y_intercept),
        "x_slope_mm_per_mm": float(x_slope),
        "y_slope_mm_per_mm": float(y_slope),
        "r_max_mm": r_max,
        "p_sim_mm": 2.0 * r_max,
        "z_min_mm": z_min,
        "z_max_mm": z_max,
        "nominal_axis_x_mm": NOMINAL_AXIS_X_MM,
        "nominal_axis_y_mm": NOMINAL_AXIS_Y_MM,
    }


def read_points(path: Path) -> np.ndarray:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return np.asarray([[float(row["x_mm"]), float(row["y_mm"]), float(row["z_mm"])] for row in rows])


def demo_points(seed: int = 20260902) -> np.ndarray:
    rng = np.random.default_rng(seed)
    nominal_radius = 20.0
    z_levels = np.array([0.0, 6.0, 12.0])
    rows = []
    for z in z_levels:
        # 0.015 mm 截面偏移 + 0.0008 mm/mm 的轴线斜率，用于联调而非实测。
        cx = 0.015 + 0.0008 * z
        cy = -0.008 + 0.00035 * z
        theta = np.linspace(0.0, 2.0 * np.pi, 48, endpoint=False)
        noise = rng.normal(0.0, 0.002, size=(theta.size, 2))
        xy = np.column_stack((cx + nominal_radius * np.cos(theta), cy + nominal_radius * np.sin(theta)))
        xy += noise
        rows.extend(np.column_stack((xy, np.full(theta.size, z))))
    return np.asarray(rows)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--section-count", type=int, default=3)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if args.demo:
        points = demo_points()
    elif args.input:
        points = read_points(args.input)
    else:
        parser.error("请提供 --input 或 --demo")
        return 2
    result = fit_axis(points, args.section_count)
    result["limit_mm"] = 0.05
    result["pass_in_model"] = result["p_sim_mm"] <= result["limit_mm"]
    result["datum_definition"] = DATUM_DEFINITION
    result["statement"] = "二维/降阶数值评价指标，已在 A/B 装配基准系中定义，不是 CMM 认证结果。"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
