"""批量验证视觉定位数字样本，并输出 MAE、成功率和误差图。"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from detect_center import detect_image
from generate_dataset import DEFAULT_OUTPUT, generate_dataset


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "automation" / "vision" / "results"
DIFFICULTIES = ("clean", "noise", "blur", "illumination", "perspective", "occlusion", "missing_edges", "low_contrast", "distortion", "large_offset")


def run_benchmark(count: int, data_dir: Path, result_dir: Path, difficulty: str = "clean", seed: int = 20260902) -> dict[str, object]:
    annotation_path = generate_dataset(count, data_dir, seed=seed, difficulty=difficulty)
    with annotation_path.open("r", encoding="utf-8-sig", newline="") as handle:
        annotations = list(csv.DictReader(handle))
    errors = []
    successes = 0
    for row in annotations:
        try:
            prediction = detect_image(data_dir / row["filename"])
            error = {
                "filename": row["filename"],
                "dx_error_mm": prediction["dx_mm"] - float(row["dx_mm"]),
                "dy_error_mm": prediction["dy_mm"] - float(row["dy_mm"]),
                "theta_error_deg": prediction["theta_deg"] - float(row["theta_deg"]),
            }
            errors.append(error)
            successes += 1
        except (FileNotFoundError, ValueError):
            errors.append({"filename": row["filename"], "dx_error_mm": np.nan, "dy_error_mm": np.nan, "theta_error_deg": np.nan})

    dx = np.asarray([item["dx_error_mm"] for item in errors], dtype=float)
    dy = np.asarray([item["dy_error_mm"] for item in errors], dtype=float)
    theta = np.asarray([item["theta_error_deg"] for item in errors], dtype=float)
    summary = {
        "sample_count": count,
        "success_count": successes,
        "success_rate": successes / count,
        "x_mae_mm": float(np.nanmean(np.abs(dx))),
        "y_mae_mm": float(np.nanmean(np.abs(dy))),
        "theta_mae_deg": float(np.nanmean(np.abs(theta))),
        "difficulty": difficulty,
        "statement": "数字样本测试结果，不代表真实工业相机精度；困难条件标签是变换后的像面标签。",
    }
    result_dir.mkdir(parents=True, exist_ok=True)
    with (result_dir / "errors.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=errors[0].keys())
        writer.writeheader()
        writer.writerows(errors)
    (result_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5), constrained_layout=True)
    for axis, values, label in zip(axes, (dx, dy, theta), ("X error (mm)", "Y error (mm)", "Angle error (deg)")):
        axis.hist(values[np.isfinite(values)], bins=25, color="#0f766e", alpha=0.85)
        axis.set_xlabel(label)
        axis.set_ylabel("count")
        axis.grid(axis="y", alpha=0.25)
    fig.savefig(result_dir / "error-distribution.png", dpi=180)
    fig.savefig(result_dir / "error-distribution.svg")
    plt.close(fig)
    return summary


def run_difficult_benchmark(count_per_condition: int, data_root: Path, result_dir: Path) -> list[dict[str, object]]:
    """运行噪声、模糊、遮挡、透视和偏移等条件的分组基准。"""
    summaries = []
    for index, difficulty in enumerate(DIFFICULTIES):
        data_dir = data_root / difficulty
        condition_result_dir = result_dir / "difficult" / difficulty
        summaries.append(run_benchmark(count_per_condition, data_dir, condition_result_dir, difficulty, 20260902 + index * 10000))

    result_dir.mkdir(parents=True, exist_ok=True)
    with (result_dir / "difficult-summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["difficulty", "sample_count", "success_rate", "x_mae_mm", "y_mae_mm", "theta_mae_deg"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for summary in summaries:
            writer.writerow({field: summary.get(field) for field in fields})
    (result_dir / "difficult-summary.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")

    labels = [str(item["difficulty"]) for item in summaries]
    success = [float(item["success_rate"]) for item in summaries]
    x_error = [float(item["x_mae_mm"]) for item in summaries]
    y_error = [float(item["y_mae_mm"]) for item in summaries]
    theta_error = [float(item["theta_mae_deg"]) for item in summaries]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), constrained_layout=True)
    axes[0].bar(labels, success, color="#0f766e")
    axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("success rate")
    axes[0].set_title("Vision benchmark under difficult image conditions")
    axes[0].tick_params(axis="x", rotation=35)
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].plot(labels, x_error, marker="o", label="X MAE (mm)")
    axes[1].plot(labels, y_error, marker="o", label="Y MAE (mm)")
    axes[1].plot(labels, theta_error, marker="o", label="angle MAE (deg)")
    axes[1].set_ylabel("error")
    axes[1].tick_params(axis="x", rotation=35)
    axes[1].legend(ncol=3, fontsize=8)
    axes[1].grid(axis="y", alpha=0.25)
    fig.savefig(result_dir / "difficult-summary.png", dpi=180)
    fig.savefig(result_dir / "difficult-summary.svg")
    plt.close(fig)

    lines = [
        "# 困难视觉条件基准",
        "",
        "> 样本为数字渲染与图像退化，不代表真实工业相机/镜头/光源标定结果。",
        "",
        "| 条件 | 样本数 | 成功率 | X MAE (mm) | Y MAE (mm) | 角度 MAE (deg) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summaries:
        lines.append(f"| {item['difficulty']} | {item['sample_count']} | {item['success_rate']:.3%} | {item['x_mae_mm']:.6f} | {item['y_mae_mm']:.6f} | {item['theta_mae_deg']:.6f} |")
    lines.extend([
        "",
        "条件覆盖：噪声、模糊、光照梯度、约 10–30° 像面透视近似、遮挡、缺失边缘、低对比度、畸变和 ±5 mm 大偏移。",
        "所有困难条件均同步变换 shell/seat/marker 标签；指标是变换后像面坐标上的误差。",
    ])
    (result_dir / "difficult-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summaries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--result-dir", type=Path, default=RESULT_DIR)
    parser.add_argument("--difficult", action="store_true", help="运行全部困难条件分组基准")
    parser.add_argument("--count-per-condition", type=int, default=100)
    args = parser.parse_args()
    if args.difficult:
        summaries = run_difficult_benchmark(args.count_per_condition, args.data_dir / "difficult", args.result_dir)
        print(json.dumps(summaries, ensure_ascii=False, indent=2))
        return 0
    summary = run_benchmark(args.count, args.data_dir, args.result_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
