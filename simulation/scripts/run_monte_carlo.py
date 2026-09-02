"""对降阶模型执行可追溯的参数扰动蒙特卡洛分析。

该脚本用于评估输入不确定性下的相对风险，不把 ``P_sim`` 当作 CMM
位置度。每次扰动都保存到 CSV，统计量、随机种子和扰动边界写入 JSON。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "simulation" / "configs" / "default.yaml"
DEFAULT_OUTPUT = ROOT / "simulation" / "results" / "monte-carlo"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_reduced_order import evaluate_case, load_yaml  # noqa: E402


SEED = 20260902
LIMIT_MM = 0.05


def perturb_config(base: dict[str, Any], rng: np.random.Generator) -> dict[str, Any]:
    """按设计边界生成一组共同输入，确保两个结构使用同一扰动。"""
    config = deepcopy(base)
    process = config["process"]
    materials = config["materials"]

    efficiency_factor = float(rng.uniform(0.90, 1.10))
    current_factor = float(rng.uniform(0.90, 1.10))
    voltage_factor = float(rng.uniform(0.90, 1.10))
    speed_factor = float(rng.uniform(0.90, 1.10))
    process["efficiency"] *= efficiency_factor
    process["current_a"] *= current_factor
    process["voltage_v"] *= voltage_factor
    process["travel_speed_mm_s"] *= speed_factor

    conductivity_factor_q235 = float(rng.uniform(0.90, 1.10))
    conductivity_factor_qt = float(rng.uniform(0.90, 1.10))
    alpha_factor_q235 = float(rng.uniform(0.95, 1.05))
    alpha_factor_qt = float(rng.uniform(0.95, 1.05))
    young_factor_q235 = float(rng.uniform(0.95, 1.05))
    young_factor_qt = float(rng.uniform(0.95, 1.05))
    materials["q235b"]["thermal_conductivity_w_mk"] *= conductivity_factor_q235
    materials["qt450_10"]["thermal_conductivity_w_mk"] *= conductivity_factor_qt
    materials["q235b"]["alpha_per_k"] *= alpha_factor_q235
    materials["qt450_10"]["alpha_per_k"] *= alpha_factor_qt
    materials["q235b"]["elastic_modulus_gpa"] *= young_factor_q235
    materials["qt450_10"]["elastic_modulus_gpa"] *= young_factor_qt
    materials["fixture"]["equivalent_stiffness_n_mm"] *= float(rng.uniform(0.80, 1.20))
    config["model"]["initial_eccentricity_mm"] = float(rng.uniform(-0.03, 0.03))

    config["_perturbation"] = {
        "efficiency_factor": efficiency_factor,
        "current_factor": current_factor,
        "voltage_factor": voltage_factor,
        "travel_speed_factor": speed_factor,
        "conductivity_factor_q235b": conductivity_factor_q235,
        "conductivity_factor_qt450_10": conductivity_factor_qt,
        "alpha_factor_q235b": alpha_factor_q235,
        "alpha_factor_qt450_10": alpha_factor_qt,
        "young_factor_q235b": young_factor_q235,
        "young_factor_qt450_10": young_factor_qt,
        "fixture_stiffness_factor": materials["fixture"]["equivalent_stiffness_n_mm"] / base["materials"]["fixture"]["equivalent_stiffness_n_mm"],
        "initial_eccentricity_mm": config["model"]["initial_eccentricity_mm"],
    }
    return config


def summarize(values: np.ndarray) -> dict[str, float]:
    return {
        "count": int(values.size),
        "p05_mm": float(np.percentile(values, 5)),
        "p50_mm": float(np.percentile(values, 50)),
        "p95_mm": float(np.percentile(values, 95)),
        "mean_mm": float(np.mean(values)),
        "worst_mm": float(np.max(values)),
        "best_mm": float(np.min(values)),
        "exceed_ratio": float(np.mean(values > LIMIT_MM)),
        "pass_ratio": float(np.mean(values <= LIMIT_MM)),
    }


def run_monte_carlo(config: dict[str, Any], count: int, seed: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    baseline_values: list[float] = []
    flex_values: list[float] = []
    for sample_index in range(1, count + 1):
        perturbed = perturb_config(config, rng)
        baseline = evaluate_case(perturbed, 6, "S1", "baseline", "rigid")
        flex = evaluate_case(perturbed, 6, "S3", "flex", "compliant")
        baseline_p = float(baseline["position_metric_p_sim_mm"])
        flex_p = float(flex["position_metric_p_sim_mm"])
        baseline_values.append(baseline_p)
        flex_values.append(flex_p)
        perturbation = perturbed["_perturbation"]
        for design, result, metric in (("baseline-rigid-6P-S1", baseline, baseline_p), ("flex-compliant-6P-S3", flex, flex_p)):
            row = {
                "sample_id": sample_index,
                "design": design,
                "p_sim_mm": metric,
                "pass_in_model": bool(metric <= LIMIT_MM),
                "delta_vs_pair_mm": flex_p - baseline_p,
                "flex_better_than_baseline": flex_p < baseline_p,
            }
            row.update(perturbation)
            rows.append(row)

    baseline_array = np.asarray(baseline_values)
    flex_array = np.asarray(flex_values)
    summary = {
        "sample_count": count,
        "seed": seed,
        "limit_mm": LIMIT_MM,
        "baseline_rigid_6p_s1": summarize(baseline_array),
        "flex_compliant_6p_s3": summarize(flex_array),
        "pairwise": {
            "flex_better_ratio": float(np.mean(flex_array < baseline_array)),
            "baseline_better_ratio": float(np.mean(baseline_array < flex_array)),
            "mean_flex_minus_baseline_mm": float(np.mean(flex_array - baseline_array)),
            "mean_reduction_flex_vs_baseline_pct": float(np.mean((baseline_array - flex_array) / baseline_array * 100.0)),
        },
        "uncertainties": {
            "efficiency": "uniform ±10%",
            "current": "uniform ±10%",
            "voltage": "uniform ±10%",
            "travel_speed": "uniform ±10%",
            "thermal_conductivity": "independent uniform ±10% per material",
            "thermal_expansion": "independent uniform ±5% per material",
            "elastic_modulus": "independent uniform ±5% per material",
            "fixture_stiffness": "uniform ±20%",
            "initial_eccentricity": "uniform [-0.03, 0.03] mm along model x axis",
        },
        "model_assumption_status": {
            "structure_factor": "未由 FE 或实测标定；baseline=1.0，flex=0.68 是降阶模型预设",
            "fixture_factor": "未由 FE 或实物标定；rigid/compliant 系数是降阶模型预设",
            "interpretation": "柔顺优势只在当前模型结构和预设系数成立的条件下具有鲁棒性",
        },
        "statement": "蒙特卡洛仅对降阶代理模型做输入不确定性传播；P_sim 不等于 CMM 位置度，也不独立验证结构优劣。",
    }
    return rows, summary


def write_outputs(rows: list[dict[str, Any]], summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "monte-carlo.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "monte-carlo-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    by_design = {
        "baseline-rigid-6P-S1": np.asarray([row["p_sim_mm"] for row in rows if row["design"] == "baseline-rigid-6P-S1"]),
        "flex-compliant-6P-S3": np.asarray([row["p_sim_mm"] for row in rows if row["design"] == "flex-compliant-6P-S3"]),
    }
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    axes[0].hist(by_design["baseline-rigid-6P-S1"], bins=35, alpha=0.65, label="baseline rigid 6P-S1", color="#64748b")
    axes[0].hist(by_design["flex-compliant-6P-S3"], bins=35, alpha=0.65, label="flex compliant 6P-S3", color="#0f766e")
    axes[0].axvline(LIMIT_MM, color="#dc2626", linestyle="--", label="limit 0.05 mm")
    axes[0].set_xlabel("P_sim (mm)")
    axes[0].set_ylabel("samples")
    axes[0].set_title("Monte Carlo distributions")
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].boxplot(list(by_design.values()), tick_labels=["baseline\nrigid", "flex\ncompliant"], showmeans=True)
    axes[1].axhline(LIMIT_MM, color="#dc2626", linestyle="--")
    axes[1].set_ylabel("P_sim (mm)")
    axes[1].set_title("P50 / spread / outliers")
    axes[1].grid(axis="y", alpha=0.25)
    fig.savefig(output_dir / "monte-carlo.png", dpi=180)
    fig.savefig(output_dir / "monte-carlo.svg")
    plt.close(fig)

    b = summary["baseline_rigid_6p_s1"]
    f = summary["flex_compliant_6p_s3"]
    lines = [
        "# 降阶模型蒙特卡洛结果",
        "",
        "> 本结果是对降阶代理模型的输入不确定性传播，不是 FE 或 CMM 结果。",
        "",
        "| 设计 | P5 (mm) | P50 (mm) | P95 (mm) | worst (mm) | 超限比例 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| baseline rigid 6P-S1 | {b['p05_mm']:.6f} | {b['p50_mm']:.6f} | {b['p95_mm']:.6f} | {b['worst_mm']:.6f} | {b['exceed_ratio']:.3%} |",
        f"| flex compliant 6P-S3 | {f['p05_mm']:.6f} | {f['p50_mm']:.6f} | {f['p95_mm']:.6f} | {f['worst_mm']:.6f} | {f['exceed_ratio']:.3%} |",
        "",
        f"样本数：{summary['sample_count']}；随机种子：{summary['seed']}；限值：{LIMIT_MM:.3f} mm。",
        f"配对比较中柔顺方案更优比例：{summary['pairwise']['flex_better_ratio']:.3%}；刚性基准更优比例：{summary['pairwise']['baseline_better_ratio']:.3%}。",
        "",
        "## 解读边界",
        "",
        "材料参数、热输入、速度、夹具等扰动用于风险排序；未建立真实材料温度依赖、塑性、接触和三维测量误差模型，因此不能把超限比例解释成实际失效概率。",
        "`structure_factor` 与 `fixture_factor` 未由 FE/实测标定，属于模型预设；因此“柔顺方案更优”只表示在当前降阶模型结构及其预设系数下对输入扰动具有鲁棒性，不是第三套独立证据。",
    ]
    (output_dir / "monte-carlo.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.count < 100:
        parser.error("--count 至少为 100，正式运行建议 1000 或以上")
    rows, summary = run_monte_carlo(load_yaml(args.config), args.count, args.seed)
    write_outputs(rows, summary, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
