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


def render_sample_geometry(dx_mm: float, dy_mm: float, theta_deg: float, seed: int,
                           noise_sigma: float = 1.2) -> tuple[np.ndarray, np.ndarray]:
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
    image = np.clip(image.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    points = np.asarray([[center[0], center[1]], [seat[0], seat[1]], [marker[0], marker[1]]], dtype=np.float32)
    return image, points


def render_sample(dx_mm: float, dy_mm: float, theta_deg: float, seed: int,
                  noise_sigma: float = 1.2) -> np.ndarray:
    """兼容旧接口：只返回未经困难条件变换的数字样本图。"""
    return render_sample_geometry(dx_mm, dy_mm, theta_deg, seed, noise_sigma)[0]


def transform_points(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack((points, np.ones(points.shape[0], dtype=np.float32)))
    transformed = homogeneous @ matrix.T
    return transformed[:, :2] / transformed[:, 2:3]


def apply_difficulty(image: np.ndarray, points: np.ndarray, difficulty: str, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """给数字样本叠加可复核的工业视觉困难因素，并同步更新标签。"""
    rng = np.random.default_rng(seed)
    output = image.copy()
    transformed = points.copy()
    height, width = output.shape[:2]

    if difficulty == "perspective":
        source = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
        # 约 10–30° 观察倾角的像面近似；实际角度需现场相机标定确认。
        jitter = rng.uniform(28.0, 62.0, size=(4, 2)).astype(np.float32)
        destination = source + np.asarray([[-jitter[0, 0], jitter[0, 1]], [jitter[1, 0], -jitter[1, 1]], [jitter[2, 0], jitter[2, 1]], [-jitter[3, 0], -jitter[3, 1]]], dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(source, destination)
        output = cv2.warpPerspective(output, matrix, (width, height), borderValue=(205, 205, 205))
        transformed = transform_points(transformed, matrix)

    if difficulty == "distortion":
        focal = float(width)
        camera = np.asarray([[focal, 0.0, width / 2.0], [0.0, focal, height / 2.0], [0.0, 0.0, 1.0]], dtype=np.float32)
        distortion = np.asarray([-0.00035, 0.00008, 0.0, 0.0, 0.0], dtype=np.float32)
        map_x, map_y = cv2.initUndistortRectifyMap(camera, distortion, None, camera, (width, height), cv2.CV_32FC1)
        output = cv2.remap(output, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(205, 205, 205))
        center = np.asarray([width / 2.0, height / 2.0], dtype=np.float32)
        normalized = (transformed - center) / focal
        radius2 = np.sum(normalized * normalized, axis=1, keepdims=True)
        transformed = center + focal * normalized * (1.0 + 0.00035 * radius2 - 0.00008 * radius2 * radius2)

    if difficulty == "illumination":
        gradient = np.linspace(0.55, 1.30, width, dtype=np.float32)[None, :, None]
        gradient = np.repeat(gradient, height, axis=0)
        output = np.clip(output.astype(np.float32) * gradient, 0, 255).astype(np.uint8)

    if difficulty == "low_contrast":
        output = np.clip(0.62 * output.astype(np.float32) + 0.38 * 175.0, 0, 255).astype(np.uint8)

    if difficulty == "occlusion":
        cv2.rectangle(output, (340, 110), (465, 215), (190, 190, 190), -1)
        cv2.rectangle(output, (65, 330), (170, 410), (230, 230, 230), -1)

    if difficulty == "missing_edges":
        cv2.rectangle(output, (45, 236), (128, 278), (245, 245, 245), -1)
        cv2.rectangle(output, (360, 350), (468, 395), (245, 245, 245), -1)

    if difficulty == "blur":
        output = cv2.GaussianBlur(output, (7, 7), 2.2)

    if difficulty == "noise":
        output = np.clip(output.astype(np.float32) + rng.normal(0.0, 14.0, output.shape), 0, 255).astype(np.uint8)
        salt = rng.random((height, width)) < 0.003
        pepper = rng.random((height, width)) < 0.003
        output[salt] = 255
        output[pepper] = 0

    return output, transformed


def generate_dataset(count: int, output_dir: Path, seed: int = 20260902, difficulty: str = "clean") -> Path:
    rng = np.random.default_rng(seed)
    output_dir.mkdir(parents=True, exist_ok=True)
    annotation_path = output_dir / "annotations.csv"
    rows = []
    for index in range(count):
        offset_limit = 5.0 if difficulty == "large_offset" else 1.5
        dx = float(rng.uniform(-offset_limit, offset_limit))
        dy = float(rng.uniform(-offset_limit, offset_limit))
        theta = float(rng.uniform(-10.0, 10.0))
        filename = f"sample_{index:04d}.png"
        image, points = render_sample_geometry(dx, dy, theta, seed + index)
        image, points = apply_difficulty(image, points, difficulty, seed + index * 17)
        cv2.imwrite(str(output_dir / filename), image)
        shell_x, shell_y = points[0]
        seat_x, seat_y = points[1]
        marker_x, marker_y = points[2]
        rows.append({
            "filename": filename,
            "dx_mm": float((seat_x - shell_x) / PIXELS_PER_MM),
            "dy_mm": float(-(seat_y - shell_y) / PIXELS_PER_MM),
            "theta_deg": float(math.degrees(math.atan2(-(marker_y - seat_y), marker_x - seat_x))),
            "difficulty": difficulty,
        })
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
