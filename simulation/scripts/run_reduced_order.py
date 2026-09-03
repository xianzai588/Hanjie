"""运行 Hanjie 的降阶热—结构方案筛选模型。

本脚本的结果用于相对比较和流程联调，不是商用有限元求解结果，也不能替代
焊后 CMM、金相、硬度或焊接工艺评定。模型把每个短焊段等效为一个热收缩向量，
再根据焊接顺序、结构柔顺性和夹具刚度估算孔轴线偏移。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import yaml

from position_tolerance import DATUM_REFERENCE_TEXT


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "simulation" / "configs" / "default.yaml"
RESULT_DIR = ROOT / "simulation" / "results"
CASE_DIR = ROOT / "simulation" / "cases"


def sequence_for(name: str, count: int) -> list[int]:
    """返回从 0 开始的焊段索引；S2/S3 仅适用于偶数焊段。"""
    if count < 2:
        raise ValueError("连接单元数必须 >= 2")
    if name == "S1":
        return list(range(count))
    if count % 2:
        raise ValueError(f"{name} 需要偶数连接单元，收到 {count}")
    half = count // 2
    if name == "S2":
        return [item for i in range(half) for item in (i, i + half)]
    if name == "S3":
        order: list[int] = [0, half]
        for i in range(1, half):
            order.extend(((half - i) % count, (count - i) % count))
        return order[:count]
    raise ValueError(f"未知焊接顺序: {name}")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"配置文件必须是对象: {path}")
    return value


def evaluate_case(config: dict[str, Any], layout: int, sequence: str,
                  structure: str, fixture: str) -> dict[str, Any]:
    """执行一个方案的确定性降阶计算。"""
    model = config["model"]
    geometry = config["geometry"]
    process = config["process"]
    materials = config["materials"]

    q_line = (
        process["efficiency"]
        * process["current_a"]
        * process["voltage_v"]
        / process["travel_speed_mm_s"]
    )
    effective_area = model["effective_heated_area_mm2"]
    # 每 1 mm 焊缝的等效热容；mm³ 转 m³ 的换算为 1e-9。
    rho_cp = (
        0.5
        * (
            materials["q235b"]["density_kg_m3"]
            * materials["q235b"]["specific_heat_j_kgk"]
            + materials["qt450_10"]["density_kg_m3"]
            * materials["qt450_10"]["specific_heat_j_kgk"]
        )
    )
    heat_capacity_per_mm = rho_cp * effective_area * 1e-9
    conductivity = 0.5 * (
        materials["q235b"]["thermal_conductivity_w_mk"]
        + materials["qt450_10"]["thermal_conductivity_w_mk"]
    )
    conductivity_spread = math.sqrt(40.0 / conductivity)
    delta_t = q_line / heat_capacity_per_mm * conductivity_spread
    peak_temp = process["preheat_c"] + 0.85 * delta_t

    alpha = 0.5 * (
        materials["q235b"]["alpha_per_k"] + materials["qt450_10"]["alpha_per_k"]
    )
    radius = geometry["wing_outer_radius_mm"]
    weld_length = geometry["weld_segment_length_mm"]
    base_shrink = (
        alpha
        * delta_t
        * radius
        * model["residual_fraction"]
        * (weld_length / 18.0) ** 0.25
    )
    # 降阶模型对弹性模量只做一阶等效刚度修正；完整温度依赖塑性仍需 FE/物理验证。
    reference_young = 0.5 * (210.0 + 170.0)
    actual_young = 0.5 * (
        materials["q235b"]["elastic_modulus_gpa"]
        + materials["qt450_10"]["elastic_modulus_gpa"]
    )
    material_stiffness_factor = math.sqrt(reference_young / actual_young)
    structure_factor = {"baseline": 1.0, "flex": 0.68}[structure] * material_stiffness_factor
    stiffness = materials["fixture"]["equivalent_stiffness_n_mm"]
    fixture_factor = {
        "rigid": 1.0,
        # 柔顺夹具允许受控热膨胀，等效刚度变化作为一阶修正。
        "compliant": 0.78 * (stiffness / 1200.0) ** 0.12,
    }[fixture]

    angles = np.arange(layout, dtype=float) * 2.0 * math.pi / layout
    order = sequence_for(sequence, layout)
    # 后焊段的局部热约束更强；冷却记忆项使不同顺序不再完全等价。
    memory = float(model["cooling_memory"])
    weights = np.ones(layout)
    for weld_index, segment_index in enumerate(order):
        weights[segment_index] = 0.78 + memory * (weld_index / max(layout - 1, 1))

    radial = np.column_stack((np.cos(angles), np.sin(angles)))
    tangent = np.column_stack((-np.sin(angles), np.cos(angles)))
    contractions = (
        radial
        * (base_shrink * structure_factor * fixture_factor * weights)[:, None]
    )
    tangential = (
        tangent
        * (base_shrink * 0.52 * structure_factor * fixture_factor * weights)[:, None]
    )
    center_shift = contractions.sum(axis=0) + np.array([
        model.get("initial_eccentricity_mm", 0.0), 0.0
    ])
    tangent_residual = tangential.sum(axis=0)
    center_displacement = float(np.linalg.norm(center_shift))
    effective_height = geometry.get(
        "seat_effective_height_mm", model["bore_effective_height_mm"]
    )
    tilt_rad = float(np.linalg.norm(tangent_residual) / effective_height)
    r_max = center_displacement + 0.5 * effective_height * tilt_rad
    p_sim = 2.0 * r_max

    # 椭圆度用周向一阶/二阶不均匀收缩的幅值表示，保持为工程比较指标。
    circumferential = np.linalg.norm(contractions.mean(axis=0))
    ellipticity = float(2.0 * circumferential + 0.45 * base_shrink / layout)
    haz_width = float(2.2 * math.sqrt(max(q_line, 1.0) / 100.0))
    pass_limit = p_sim <= model["position_tolerance_limit_mm"]

    return {
        "case_id": f"{structure.upper()}-{fixture.upper()}-{layout}P-{sequence}",
        "structure": structure,
        "fixture": fixture,
        "layout_points": layout,
        "sequence": sequence,
        "line_heat_input_j_mm": round(q_line, 6),
        "total_heat_input_j": round(q_line * weld_length * layout, 6),
        "effective_peak_temperature_c": round(peak_temp, 6),
        "haz_width_proxy_mm": round(haz_width, 6),
        "material_stiffness_factor": round(material_stiffness_factor, 6),
        "hole_center_shift_mm": round(center_displacement, 6),
        "axis_tilt_deg": round(math.degrees(tilt_rad), 6),
        "shell_ellipticity_proxy_mm": round(ellipticity, 6),
        "position_metric_p_sim_mm": round(p_sim, 6),
        "limit_mm": model["position_tolerance_limit_mm"],
        "pass_in_model": pass_limit,
        "sequence_indices": "-".join(str(item + 1) for item in order),
        "datum_reference": DATUM_REFERENCE_TEXT,
    }


def build_cases(config: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    # 9 组基准对比 + 6 组最终结构/夹具鲁棒对比，共 15 个真实运行算例。
    for layout in (4, 6, 8):
        for sequence in ("S1", "S2", "S3"):
            cases.append(evaluate_case(config, layout, sequence, "baseline", "rigid"))
    for layout in (4, 6, 8):
        for sequence in ("S2", "S3"):
            cases.append(evaluate_case(config, layout, sequence, "flex", "compliant"))
    baseline_s1 = {row["layout_points"]: row["position_metric_p_sim_mm"] for row in cases if row["structure"] == "baseline" and row["sequence"] == "S1"}
    for row in cases:
        reference = baseline_s1[row["layout_points"]]
        row["reduction_vs_baseline_s1_pct"] = round(
            100.0 * (reference - row["position_metric_p_sim_mm"]) / reference, 3
        )
    return cases


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_case_directories(rows: list[dict[str, Any]], config: dict[str, Any]) -> None:
    """为每个可复算算例生成最小输入、说明和提取结果。"""
    for index, row in enumerate(rows, start=1):
        case_dir = CASE_DIR / f"SIM-{index:03d}"
        case_dir.mkdir(parents=True, exist_ok=True)
        case_dir_config = {
            "case": row,
            "process": config["process"],
            "geometry": config["geometry"],
            "model": config["model"],
            "materials": config["materials"],
        }
        (case_dir / "config.yaml").write_text(
            yaml.safe_dump(case_dir_config, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        (case_dir / "README.md").write_text(
            "# {case_id}\n\n"
            "本算例由 `simulation/scripts/run_reduced_order.py` 自动生成。\n\n"
            "- 目的：比较连接单元数、焊接顺序、结构柔顺性和夹具边界对 `P_sim` 的影响。\n"
            "- 结果性质：降阶模型相对比较，不是 FE 或 CMM 结果。\n"
            "- 输入：本目录 `config.yaml`；完整参数边界见 `docs/05-design-assumptions.md`。\n"
            "- 结果：本目录 `result.csv`。\n".format(case_id=row["case_id"]),
            encoding="utf-8",
        )
        write_csv([row], case_dir / "result.csv")


def write_summary_markdown(rows: list[dict[str, Any]]) -> None:
    lines = [
        "# 第一轮数字仿真结果（R1）",
        "",
        "> 结果来自降阶热—结构代理模型；不是有限元或实物测量。",
        "",
        "| 算例 | 结构 | 夹具 | 点数 | 顺序 | P_sim (mm) | 相对同点数 S1 降低 (%) | 模型内判定 |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['case_id']} | {row['structure']} | {row['fixture']} | "
            f"{row['layout_points']} | {row['sequence']} | {row['position_metric_p_sim_mm']:.6f} | "
            f"{row['reduction_vs_baseline_s1_pct']:.3f} | {row['pass_in_model']} |"
        )
    lines.extend([
        "",
        "## 解释",
        "",
        "基准参照为相同连接单元数、刚性基准结构、刚性夹具和 S1 顺序；`P_sim` 是按内孔轴线构造的数值评价指标。",
        "当前代理模型中 S2 与 S3 对称性完全相同，因此不能据此宣称二者存在性能差异；S3 仅作为路径生成的代表顺序。",
        f"名义基准系：{DATUM_REFERENCE_TEXT}。",
        "8 点柔顺方案的 `P_sim` 最小，但 6 点方案在模型内仍低于限值且总焊段更少、总热输入更低，因此 V2 将 6 点作为主方案、8 点作为对照；最终取舍待 FE/物理验证。",
        "二维 FE 代理交叉检查没有稳定复现上述柔顺优势：同 S3 条件下 FE-003（柔顺/柔顺夹具）高于 FE-002（连续/刚性夹具），而 FE-005（柔顺/刚性夹具）略低于 FE-002。该冲突说明降阶结构因子不能外推为真实结构最优性，V2 同时保留连续座体和两种夹具边界，等待三维/物理证据裁决。",
    ])
    (RESULT_DIR / "summary-r1.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def plot_results(rows: list[dict[str, Any]], png_path: Path, svg_path: Path) -> None:
    labels = [row["case_id"] for row in rows]
    metrics = [row["position_metric_p_sim_mm"] for row in rows]
    colors = ["#0f766e" if row["structure"] == "flex" else "#64748b" for row in rows]
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), constrained_layout=True)
    axes[0].bar(labels, metrics, color=colors)
    axes[0].axhline(0.05, color="#dc2626", linestyle="--", linewidth=1.5, label="limit 0.05 mm")
    axes[0].set_ylabel("P_sim (mm)")
    axes[0].set_title("Reduced-order position metric (P_sim)")
    axes[0].tick_params(axis="x", rotation=70, labelsize=7)
    axes[0].legend()

    peak = [row["effective_peak_temperature_c"] for row in rows]
    axes[1].plot(range(len(rows)), peak, marker="o", color="#b45309", linewidth=1.6)
    axes[1].set_xticks(range(len(rows)), labels, rotation=70, fontsize=7)
    axes[1].set_ylabel("Effective peak (°C)")
    axes[1].set_title("Thermal proxy (not a calibrated temperature field)")
    axes[1].grid(axis="y", alpha=0.25)
    fig.savefig(png_path, dpi=180)
    fig.savefig(svg_path)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=RESULT_DIR)
    args = parser.parse_args()

    config = load_yaml(args.config)
    rows = build_cases(config)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(rows, args.output_dir / "summary.csv")
    write_case_directories(rows, config)
    write_summary_markdown(rows)
    plot_results(rows, args.output_dir / "summary.png", args.output_dir / "summary.svg")
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "script": str(Path(__file__).relative_to(ROOT)).replace("\\", "/"),
        "config": str(args.config.relative_to(ROOT)).replace("\\", "/"),
        "case_count": len(rows),
        "model_statement": "降阶热—结构代理模型，仅用于相对比较；不是有限元或实测结果。",
        "datum_reference": DATUM_REFERENCE_TEXT,
        "python": sys.version,
    }
    (args.output_dir / "run-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    best = min(rows, key=lambda item: item["position_metric_p_sim_mm"])
    print(f"已运行 {len(rows)} 个算例，结果目录: {args.output_dir}")
    print(f"模型指标最小算例: {best['case_id']}，P_sim={best['position_metric_p_sim_mm']:.6f} mm")
    print("注意：P_sim 不等于 CMM 位置度认证结果。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
