"""从数字标定图中识别壳体中心、轴承座中心和姿态标记。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


PIXELS_PER_MM = 3.0


def _component_geometry(mask: np.ndarray, min_area: int) -> tuple[tuple[float, float], dict[str, float]]:
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        raise ValueError("未找到有效分割区域")
    candidates = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= min_area]
    if not candidates:
        raise ValueError("分割区域面积不足")
    index = max(candidates, key=lambda item: stats[item, cv2.CC_STAT_AREA])
    component = np.where(labels == index, 255, 0).astype(np.uint8)
    contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    contour = max(contours, key=cv2.contourArea)
    if len(contour) >= 5:
        # 外轮廓椭圆拟合比带噪环带的像素矩更稳定；仍只适用于本数字标定图。
        (center_x, center_y), (axis_a, axis_b), _ = cv2.fitEllipse(contour)
        contour_area = float(cv2.contourArea(contour))
        perimeter = float(cv2.arcLength(contour, True))
        circularity = 4.0 * math.pi * contour_area / max(perimeter * perimeter, 1e-9)
        return (float(center_x), float(center_y)), {
            "area_px": float(stats[index, cv2.CC_STAT_AREA]),
            "aspect_ratio": float(min(axis_a, axis_b) / max(axis_a, axis_b)),
            "circularity": float(circularity),
        }
    return (float(centroids[index][0]), float(centroids[index][1])), {
        "area_px": float(stats[index, cv2.CC_STAT_AREA]),
        "aspect_ratio": 0.0,
        "circularity": 0.0,
    }


def largest_component_center(mask: np.ndarray, min_area: int) -> tuple[float, float]:
    """返回最大有效连通域中心；保留该接口供旧调用方使用。"""
    center, _ = _component_geometry(mask, min_area)
    return center


def detect_image(image_path: Path, reject_quality: bool = True) -> dict[str, object]:
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(image_path)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    shell_mask = cv2.inRange(gray, 65, 145)
    shell_mask = cv2.morphologyEx(shell_mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    (shell_x, shell_y), shell_quality = _component_geometry(shell_mask, 5000)

    seat_mask = cv2.inRange(hsv, np.array([90, 55, 35]), np.array([125, 255, 240]))
    seat_mask = cv2.morphologyEx(seat_mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    (seat_x, seat_y), seat_quality = _component_geometry(seat_mask, 100)

    red_a = cv2.inRange(hsv, np.array([0, 80, 60]), np.array([12, 255, 255]))
    red_b = cv2.inRange(hsv, np.array([165, 80, 60]), np.array([179, 255, 255]))
    marker_mask = cv2.morphologyEx(red_a | red_b, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    (marker_x, marker_y), marker_quality = _component_geometry(marker_mask, 20)

    # 运行时质量门：严重透视、遮挡、光照断裂或噪声下禁止把错误坐标送入路径规划。
    # 阈值来自数字困难集的几何可观测量，实际设备仍需用标定样本重新定标。
    quality_checks = {
        "shell_circularity": shell_quality["circularity"] >= 0.82,
        "shell_aspect_ratio": shell_quality["aspect_ratio"] >= 0.96,
        "seat_circularity": seat_quality["circularity"] >= 0.78,
        "marker_area": marker_quality["area_px"] >= 20.0,
    }
    failed_checks = [name for name, passed in quality_checks.items() if not passed]
    confidence = float(min(
        shell_quality["circularity"] / 0.90,
        shell_quality["aspect_ratio"],
        seat_quality["circularity"] / 0.90,
        min(marker_quality["area_px"] / 50.0, 1.0),
        1.0,
    ))

    dx = (seat_x - shell_x) / PIXELS_PER_MM
    dy = -(seat_y - shell_y) / PIXELS_PER_MM
    theta = math.degrees(math.atan2(-(marker_y - seat_y), marker_x - seat_x))
    result = {
        "shell_center_x_px": shell_x,
        "shell_center_y_px": shell_y,
        "seat_center_x_px": seat_x,
        "seat_center_y_px": seat_y,
        "dx_mm": dx,
        "dy_mm": dy,
        "theta_deg": theta,
        "quality": {
            "confidence": max(0.0, min(confidence, 1.0)),
            "accepted": not failed_checks,
            "failed_checks": failed_checks,
            "checks": quality_checks,
            "shell": shell_quality,
            "seat": seat_quality,
            "marker": marker_quality,
        },
    }
    if reject_quality and failed_checks:
        raise ValueError("视觉质量门拒绝: " + ", ".join(failed_checks))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = detect_image(args.image)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
