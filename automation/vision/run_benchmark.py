"""批量验证视觉定位数字样本，并输出误差预算与工程门限结果。"""

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

# Ø0.05 是直径限值，先换算为 0.025 mm 的径向总预算，再做保守的线性分配。
# 视觉门限是数字评审门，不是相机/机器人实测验收门限。
POSITION_TOLERANCE_DIAMETER_LIMIT_MM = 0.05
POSITION_TOLERANCE_RADIUS_BUDGET_MM = POSITION_TOLERANCE_DIAMETER_LIMIT_MM / 2.0
VISION_RADIAL_MAE_BUDGET_MM = 0.010
POSE_LEVER_ARM_MM = 73.8
# 将姿态误差换算为最不利的切向位移，确保该项不超过视觉径向份额。
VISION_ANGLE_MAE_BUDGET_DEG = float(np.degrees(VISION_RADIAL_MAE_BUDGET_MM / POSE_LEVER_ARM_MM))


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
    radial_error = np.sqrt(dx * dx + dy * dy)
    radial_mae = float(np.nanmean(radial_error))
    radial_p95 = float(np.nanpercentile(radial_error, 95))
    theta_mae = float(np.nanmean(np.abs(theta)))
    theta_p95 = float(np.nanpercentile(np.abs(theta), 95))
    # 工程门使用 P95，避免 MAE 掩盖少量大误差；MAE 仍作为描述性统计保留。
    engineering_gate = radial_p95 <= VISION_RADIAL_MAE_BUDGET_MM and theta_p95 <= VISION_ANGLE_MAE_BUDGET_DEG
    summary = {
        "sample_count": count,
        "success_count": successes,
        "success_rate": successes / count,
        "detection_return_rate": successes / count,
        "x_mae_mm": float(np.nanmean(np.abs(dx))),
        "y_mae_mm": float(np.nanmean(np.abs(dy))),
        "radial_mae_mm": radial_mae,
        "radial_p95_mm": radial_p95,
        "theta_mae_deg": theta_mae,
        "theta_p95_deg": theta_p95,
        "difficulty": difficulty,
        "engineering_gate": "PASS" if engineering_gate else "FAIL",
        "engineering_gate_pass": engineering_gate,
        "gate_limits": {
            "radial_p95_mm": VISION_RADIAL_MAE_BUDGET_MM,
            "theta_p95_deg": VISION_ANGLE_MAE_BUDGET_DEG,
            "pose_lever_arm_mm": POSE_LEVER_ARM_MM,
        },
        "statement": "数字样本测试结果，不代表真实工业相机精度；检测返回率仅表示算法给出结果，工程门限还需同时满足误差预算。",
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
    gate = [1.0 if item["engineering_gate_pass"] else 0.0 for item in summaries]
    x_error = [float(item["x_mae_mm"]) for item in summaries]
    y_error = [float(item["y_mae_mm"]) for item in summaries]
    theta_error = [float(item["theta_mae_deg"]) for item in summaries]
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), constrained_layout=True)
    axes[0].bar(labels, gate, color=["#0f766e" if value else "#dc2626" for value in gate])
    axes[0].set_ylim(0, 1.05)
    axes[0].set_ylabel("engineering gate (1=PASS)")
    axes[0].set_title("Vision engineering gate under difficult image conditions")
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
        "| 条件 | 样本数 | 检测返回率 | 径向 P95 (mm) | 角度 P95 (deg) | 工程判定 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in summaries:
        lines.append(f"| {item['difficulty']} | {item['sample_count']} | {item['detection_return_rate']:.3%} | {item['radial_p95_mm']:.6f} | {item['theta_p95_deg']:.6f} | {item['engineering_gate']} |")
    lines.extend([
        "",
        "## 工程误差预算",
        "",
        f"比赛位置度限值 Ø{POSITION_TOLERANCE_DIAMETER_LIMIT_MM:.2f} mm 对应径向预算 {POSITION_TOLERANCE_RADIUS_BUDGET_MM:.3f} mm。本数字评审将其按线性最坏情况分配：视觉 {VISION_RADIAL_MAE_BUDGET_MM:.3f} mm、相机标定 0.004 mm、TCP 0.003 mm、机器人重复定位 0.003 mm、夹具 0.003 mm、热变形 0.002 mm，合计 {POSITION_TOLERANCE_RADIUS_BUDGET_MM:.3f} mm。",
        f"视觉数字门限：径向 P95 ≤ {VISION_RADIAL_MAE_BUDGET_MM:.3f} mm；以 {POSE_LEVER_ARM_MM:.1f} mm 姿态作用半径换算，角度 P95 ≤ {VISION_ANGLE_MAE_BUDGET_DEG:.4f}°。MAE 作为描述性统计保留；门限是误差预算中的视觉份额，不是实测精度认证。",
        "因此“检测返回率”不等于“工程通过”：透视、遮挡、光照梯度等条件可能返回结果但工程判定 FAIL。",
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
