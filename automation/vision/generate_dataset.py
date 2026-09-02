"""生成带已知偏心、偏转标签的视觉定位数字样本。"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "automation" / "vision" / "data"
IMAGE_SIZE = 512
PIXELS_PER_MM = 3.0


def render_sample(dx_mm: float, dy_mm: float, theta_deg: float, seed: int,
                  noise_sigma: float = 1.2) -> np.ndarray:
    """渲染一张简化标定图；颜色只用于数字样本的分割，不代表工业相机方案。"""
    rng = np.random.default_rng(seed)
    image = np.full((IMAGE_SIZE, IMAGE_SIZE, 3), 245, dtype=np.uint8)
    center = (IMAGE_SIZE // 2, IMAGE_SIZE // 2)
    seat = (
        int(round(center[0] + dx_mm * PIXELS_PER_MM)),
        int(round(center[1] - dy_mm * PIXELS_PER_MM)),
    )
    # Q235B 壳体环带：灰色；轴承座环带：蓝色；姿态标记：红色。
    cv2.circle(image, center, 230, (105, 105, 105), -1, cv2.LINE_AA)
    cv2.circle(image, center, 210, (245, 245, 245), -1, cv2.LINE_AA)
    cv2.circle(image, seat, 126, (170, 105, 40), 8, cv2.LINE_AA)
    cv2.circle(image, seat, 70, (245, 245, 245), -1, cv2.LINE_AA)
    cv2.circle(image, seat, 70, (170, 105, 40), 5, cv2.LINE_AA)
    theta = math.radians(theta_deg)
    marker = (
        int(round(seat[0] + 93 * math.cos(theta))),
        int(round(seat[1] - 93 * math.sin(theta))),
    )
    cv2.circle(image, marker, 7, (35, 35, 210), -1, cv2.LINE_AA)
    noise = rng.normal(0.0, noise_sigma, image.shape)
    return np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def generate_dataset(count: int, output_dir: Path, seed: int = 20260902) -> Path:
    rng = np.random.default_rng(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    annotation_path = output_dir / "annotations.csv"
    rows = []
    for index in range(count):
        dx = float(rng.uniform(-1.5, 1.5))
        dy = float(rng.uniform(-1.5, 1.5))
        theta = float(rng.uniform(-10.0, 10.0))
        filename = f"sample_{index:04d}.png"
        cv2.imwrite(str(output_dir / filename), render_sample(dx, dy, theta, seed + index))
        # 标签必须对应渲染后实际落在像素网格上的真值，不能把连续输入误当成
        # 图像中可恢复的亚像素量；否则 benchmark 会把栅格化误差算成算法误差。
        rendered_dx = (round(IMAGE_SIZE / 2 + dx * PIXELS_PER_MM) - IMAGE_SIZE / 2) / PIXELS_PER_MM
        rendered_dy = -(round(IMAGE_SIZE / 2 - dy * PIXELS_PER_MM) - IMAGE_SIZE / 2) / PIXELS_PER_MM
        marker_x = round(round(IMAGE_SIZE / 2 + dx * PIXELS_PER_MM) + 93 * math.cos(math.radians(theta)))
        marker_y = round(round(IMAGE_SIZE / 2 - dy * PIXELS_PER_MM) - 93 * math.sin(math.radians(theta)))
        seat_x = round(IMAGE_SIZE / 2 + dx * PIXELS_PER_MM)
        seat_y = round(IMAGE_SIZE / 2 - dy * PIXELS_PER_MM)
        rendered_theta = math.degrees(math.atan2(-(marker_y - seat_y), marker_x - seat_x))
        rows.append({"filename": filename, "dx_mm": rendered_dx, "dy_mm": rendered_dy, "theta_deg": rendered_theta})
    with annotation_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return annotation_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    annotation = generate_dataset(args.count, args.output_dir)
    print(f"已生成 {args.count} 张数字样本: {annotation}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
