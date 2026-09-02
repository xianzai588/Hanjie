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


def run_benchmark(count: int, data_dir: Path, result_dir: Path) -> dict[str, object]:
    annotation_path = generate_dataset(count, data_dir)
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
        "statement": "数字样本测试结果，不代表真实工业相机精度。",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--result-dir", type=Path, default=RESULT_DIR)
    args = parser.parse_args()
    summary = run_benchmark(args.count, args.data_dir, args.result_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

