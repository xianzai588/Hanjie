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
from itertools import product
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
STRUCTURES = ("baseline", "flex")
FIXTURES = ("rigid", "compliant")
SEQUENCES = ("S1", "S2", "S3")
LAYOUTS = (4, 6, 8)


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


def _designs(layouts: tuple[int, ...] = LAYOUTS) -> list[tuple[int, str, str, str]]:
    return list(product(layouts, STRUCTURES, FIXTURES, SEQUENCES))


def _pairwise_effects(values: dict[tuple[int, str, str, str], np.ndarray], layouts: tuple[int, ...]) -> dict[str, Any]:
    """从同一扰动样本中计算单因素配对效应，避免把顺序和结构混在一起。"""
    structure_effects = []
    fixture_effects = []
    sequence_effects = []
    for layout in layouts:
        for fixture in FIXTURES:
            for sequence in SEQUENCES:
                baseline = values[(layout, "baseline", fixture, sequence)]
                flex = values[(layout, "flex", fixture, sequence)]
                delta = flex - baseline
                structure_effects.append({"layout": layout, "fixture": fixture, "sequence": sequence, "effect_flex_minus_baseline_mm": float(np.mean(delta)), "flex_better_ratio": float(np.mean(delta < 0.0)), "baseline_p50_mm": float(np.percentile(baseline, 50)), "flex_p50_mm": float(np.percentile(flex, 50))})
        for structure in STRUCTURES:
            for sequence in SEQUENCES:
                rigid = values[(layout, structure, "rigid", sequence)]
                compliant = values[(layout, structure, "compliant", sequence)]
                delta = compliant - rigid
                fixture_effects.append({"layout": layout, "structure": structure, "sequence": sequence, "effect_compliant_minus_rigid_mm": float(np.mean(delta)), "compliant_better_ratio": float(np.mean(delta < 0.0)), "rigid_p50_mm": float(np.percentile(rigid, 50)), "compliant_p50_mm": float(np.percentile(compliant, 50))})
        for structure, fixture in product(STRUCTURES, FIXTURES):
            reference = values[(layout, structure, fixture, "S1")]
            for sequence in ("S2", "S3"):
                changed = values[(layout, structure, fixture, sequence)]
                delta = changed - reference
                sequence_effects.append({"layout": layout, "structure": structure, "fixture": fixture, "sequence": sequence, "reference_sequence": "S1", "effect_vs_s1_mm": float(np.mean(delta)), "better_ratio_vs_s1": float(np.mean(delta < 0.0)), "s1_p50_mm": float(np.percentile(reference, 50)), "sequence_p50_mm": float(np.percentile(changed, 50))})
    return {"structure": structure_effects, "fixture": fixture_effects, "sequence_vs_s1": sequence_effects}


def run_monte_carlo(config: dict[str, Any], count: int, seed: int, layouts: tuple[int, ...] = LAYOUTS) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    layouts = tuple(dict.fromkeys(int(layout) for layout in layouts))
    if not layouts:
        raise ValueError("layouts 不能为空")
    if any(layout < 2 or layout % 2 for layout in layouts):
        raise ValueError("layouts 中的点数必须为不小于 2 的偶数")
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    design_values: dict[tuple[int, str, str, str], list[float]] = {(layout, structure, fixture, sequence): [] for layout, structure, fixture, sequence in _designs(layouts)}
    for sample_index in range(1, count + 1):
        perturbed = perturb_config(config, rng)
        perturbation = perturbed["_perturbation"]
        for layout, structure, fixture, sequence in _designs(layouts):
            result = evaluate_case(perturbed, layout, sequence, structure, fixture)
            metric = float(result["position_metric_p_sim_mm"])
            design_values[(layout, structure, fixture, sequence)].append(metric)
            row = {
                "sample_id": sample_index,
                "layout_points": layout,
                "structure": structure,
                "fixture": fixture,
                "sequence": sequence,
                "design": f"{structure}-{fixture}-{layout}P-{sequence}",
                "p_sim_mm": metric,
                "pass_in_model": bool(metric <= LIMIT_MM),
            }
            row.update(perturbation)
            rows.append(row)

    arrays = {key: np.asarray(item) for key, item in design_values.items()}
    design_summary = {}
    for (layout, structure, fixture, sequence), values in arrays.items():
        design_summary[f"{structure}_{fixture}_{layout}p_{sequence.lower()}"] = summarize(values)
    effects = _pairwise_effects({key: values for key, values in arrays.items() if key[0] in layouts}, layouts)
    # 默认以 6 点为报告参考；缩小测试布局时选传入的首个布局，避免摘要接口依赖不存在的键。
    reference_layout = 6 if 6 in layouts else layouts[0]
    baseline_array = arrays[(reference_layout, "baseline", "rigid", "S1")]
    flex_array = arrays[(reference_layout, "flex", "compliant", "S3")]
    matched = arrays[(reference_layout, "baseline", "rigid", "S3")]
    matched_flex = arrays[(reference_layout, "flex", "rigid", "S3")]
    baseline_key = f"baseline_rigid_{reference_layout}p_s1"
    flex_key = f"flex_compliant_{reference_layout}p_s3"
    matched_key = f"matched_{reference_layout}p_s3_structure"
    summary = {
        "sample_count": count,
        "design_count": len(arrays),
        "layouts": list(layouts),
        "seed": seed,
        "limit_mm": LIMIT_MM,
        "reference_layout": reference_layout,
        "designs": design_summary,
        # 保留旧键，便于已有报告/调用方迁移；主结论使用 matched_effects。
        baseline_key: summarize(baseline_array),
        flex_key: summarize(flex_array),
        "pairwise": {
            "flex_better_ratio": float(np.mean(flex_array < baseline_array)),
            "baseline_better_ratio": float(np.mean(baseline_array < flex_array)),
            "mean_flex_minus_baseline_mm": float(np.mean(flex_array - baseline_array)),
            "mean_reduction_flex_vs_baseline_pct": float(np.mean((baseline_array - flex_array) / baseline_array * 100.0)),
        },
        "matched_effects": effects,
        matched_key: {
            "baseline_rigid": summarize(matched),
            "flex_rigid": summarize(matched_flex),
            "flex_better_ratio": float(np.mean(matched_flex < matched)),
            "mean_flex_minus_baseline_mm": float(np.mean(matched_flex - matched)),
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
        "statement": "蒙特卡洛对完整结构×夹具×顺序因子组合做共同输入扰动；P_sim 不等于 CMM 位置度，配对效应也不独立验证结构优劣。",
    }
    # 默认报告和外部调用方仍读取 6 点兼容键；非 6 点测试使用动态键和 reference_layout。
    if reference_layout == 6:
        summary["baseline_rigid_6p_s1"] = summary[baseline_key]
        summary["flex_compliant_6p_s3"] = summary[flex_key]
        summary["matched_6p_s3_structure"] = summary[matched_key]
    return rows, summary


def write_outputs(rows: list[dict[str, Any]], summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "monte-carlo.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "monte-carlo-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    reference_layout = int(summary["reference_layout"])
    design_specs = (
        ("baseline", "rigid", "S1", "baseline", "rigid", "S1"),
        ("baseline", "rigid", "S3", "baseline", "rigid", "S3"),
        ("flex", "rigid", "S3", "flex", "rigid", "S3"),
        ("flex", "compliant", "S3", "flex", "compliant", "S3"),
    )
    by_design = {}
    labels = []
    for structure, fixture, sequence, _, _, _ in design_specs:
        design = f"{structure}-{fixture}-{reference_layout}P-{sequence}"
        values = np.asarray([row["p_sim_mm"] for row in rows if row["design"] == design])
        if values.size:
            by_design[design] = values
            labels.append(f"{structure}\n{fixture} {sequence}")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    histogram_specs = (
        (f"baseline-rigid-{reference_layout}P-S3", "baseline rigid S3", "#94a3b8"),
        (f"flex-rigid-{reference_layout}P-S3", "flex rigid S3", "#0f766e"),
        (f"flex-compliant-{reference_layout}P-S3", "flex compliant S3", "#b45309"),
    )
    for key, label, color in histogram_specs:
        if key in by_design:
            axes[0].hist(by_design[key], bins=35, alpha=0.55, label=label, color=color)
    axes[0].axvline(LIMIT_MM, color="#dc2626", linestyle="--", label="limit 0.05 mm")
    axes[0].set_xlabel("P_sim (mm)")
    axes[0].set_ylabel("samples")
    axes[0].set_title("Monte Carlo distributions")
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y", alpha=0.25)
    axes[1].boxplot(list(by_design.values()), tick_labels=labels, showmeans=True)
    axes[1].axhline(LIMIT_MM, color="#dc2626", linestyle="--")
    axes[1].set_ylabel("P_sim (mm)")
    axes[1].set_title("P50 / spread / outliers")
    axes[1].grid(axis="y", alpha=0.25)
    fig.savefig(output_dir / "monte-carlo.png", dpi=180)
    fig.savefig(output_dir / "monte-carlo.svg")
    plt.close(fig)

    # 主表只展示同布局、同顺序、同夹具的结构配对；混合旧口径放在边界说明中。
    matched_summary = summary[f"matched_{reference_layout}p_s3_structure"]
    b = matched_summary["baseline_rigid"]
    f = matched_summary["flex_rigid"]
    lines = [
        "# 降阶模型蒙特卡洛结果",
        "",
        "> 本结果是对降阶代理模型的输入不确定性传播，不是 FE 或 CMM 结果；主比较采用相同布局、夹具和顺序的配对设计。",
        "",
        "| 设计 | P5 (mm) | P50 (mm) | P95 (mm) | worst (mm) | 超限比例 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        f"| baseline rigid {reference_layout}P-S3 | {b['p05_mm']:.6f} | {b['p50_mm']:.6f} | {b['p95_mm']:.6f} | {b['worst_mm']:.6f} | {b['exceed_ratio']:.3%} |",
        f"| flex rigid {reference_layout}P-S3 | {f['p05_mm']:.6f} | {f['p50_mm']:.6f} | {f['p95_mm']:.6f} | {f['worst_mm']:.6f} | {f['exceed_ratio']:.3%} |",
        "",
        f"样本数：{summary['sample_count']}；随机种子：{summary['seed']}；限值：{LIMIT_MM:.3f} mm。",
        f"混合旧口径（baseline rigid S1 vs flex compliant S3）中柔顺方案更优比例：{summary['pairwise']['flex_better_ratio']:.3%}；该数字不作为因果结论。",
        f"{reference_layout}P、S3、同为刚性夹具的结构配对中，柔顺方案更优比例：{summary[f'matched_{reference_layout}p_s3_structure']['flex_better_ratio']:.3%}。",
        "",
        "## 解读边界",
        "",
        "材料参数、热输入、速度、夹具等扰动用于风险排序；未建立真实材料温度依赖、塑性、接触和三维测量误差模型，因此不能把超限比例解释成实际失效概率。",
        "结构、夹具和顺序已拆为同扰动配对效应；`structure_factor` 与 `fixture_factor` 仍未由 FE/实测标定，因此任何效应只表示当前降阶模型预设下的相对变化，不是第三套独立证据。",
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
