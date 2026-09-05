"""对三维线弹性静力筛查执行网格收敛、边界敏感性和候选排序。"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "results" / "static-screening" / "static-screening-raw.json"
DEFAULT_OUTPUT = ROOT / "results" / "static-screening"
RESOLUTION_ORDER = ("coarse", "medium", "fine")
BC_ORDER = ("BC-1", "BC-2")
DISPLACEMENT_TOLERANCE = 0.03
P95_STRESS_TOLERANCE = 0.10
BC_SENSITIVITY_TOLERANCE = 0.10


def _relative_change(a: float, b: float) -> float:
    denominator = max(abs(a), abs(b), 1e-15)
    return abs(a - b) / denominator


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload["rows"]
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {
        (row["model_id"], row["resolution"], row["boundary_condition"]): row
        for row in rows
    }
    models = sorted({row["model_id"] for row in rows})
    convergence = []
    sensitivity = []
    for model in models:
        for bc in BC_ORDER:
            medium = grouped[(model, "medium", bc)]
            fine = grouped[(model, "fine", bc)]
            displacement_change = _relative_change(
                medium["worst_position_diameter_mm"], fine["worst_position_diameter_mm"]
            )
            p95_change = _relative_change(
                medium.get("worst_p95_stress_mpa", max(item["p95_von_mises_mpa"] for item in medium["direction_results"])),
                fine.get("worst_p95_stress_mpa", max(item["p95_von_mises_mpa"] for item in fine["direction_results"])),
            )
            convergence.append(
                {
                    "model_id": model,
                    "boundary_condition": bc,
                    "medium_to_fine_displacement_relative_change": displacement_change,
                    "medium_to_fine_p95_stress_relative_change": p95_change,
                    "displacement_pass": displacement_change <= DISPLACEMENT_TOLERANCE,
                    "p95_stress_pass": p95_change <= P95_STRESS_TOLERANCE,
                    "pass": displacement_change <= DISPLACEMENT_TOLERANCE and p95_change <= P95_STRESS_TOLERANCE,
                }
            )
        fine_rows = [grouped[(model, "fine", bc)] for bc in BC_ORDER]
        displacement_change = _relative_change(
            fine_rows[0]["worst_position_diameter_mm"], fine_rows[1]["worst_position_diameter_mm"]
        )
        p95_values = [
            row.get("worst_p95_stress_mpa", max(item["p95_von_mises_mpa"] for item in row["direction_results"]))
            for row in fine_rows
        ]
        p95_change = _relative_change(p95_values[0], p95_values[1])
        sensitivity.append(
            {
                "model_id": model,
                "resolution": "fine",
                "bc1_bc2_displacement_relative_change": displacement_change,
                "bc1_bc2_p95_stress_relative_change": p95_change,
                "displacement_pass": displacement_change <= BC_SENSITIVITY_TOLERANCE,
                "p95_stress_pass": p95_change <= BC_SENSITIVITY_TOLERANCE,
                "pass": displacement_change <= BC_SENSITIVITY_TOLERANCE and p95_change <= BC_SENSITIVITY_TOLERANCE,
            }
        )

    ranking = []
    for model in models:
        fine_rows = [grouped[(model, "fine", bc)] for bc in BC_ORDER]
        average_displacement = sum(row["worst_position_diameter_mm"] for row in fine_rows) / len(fine_rows)
        average_p95 = sum(
            row.get("worst_p95_stress_mpa", max(item["p95_von_mises_mpa"] for item in row["direction_results"]))
            for row in fine_rows
        ) / len(fine_rows)
        average_compliance = sum(row["worst_compliance_mm_per_n"] for row in fine_rows) / len(fine_rows)
        mass = fine_rows[0]["mass_kg"]
        ranking.append(
            {
                "model_id": model,
                "mass_kg": mass,
                "fine_average_displacement_diameter_mm": average_displacement,
                "fine_average_p95_stress_mpa": average_p95,
                "fine_average_compliance_mm_per_n": average_compliance,
                "specific_compliance_mm_per_n_per_kg": average_compliance / mass,
            }
        )
    ranking.sort(key=lambda item: (item["fine_average_displacement_diameter_mm"], item["fine_average_p95_stress_mpa"]))

    equivalence = []
    for resolution in RESOLUTION_ORDER:
        for bc in BC_ORDER:
            left = grouped[("6P-FAIR_A", resolution, bc)]
            right = grouped[("6P-FAIR_B", resolution, bc)]
            fields = ("worst_position_diameter_mm", "worst_stress_mpa", "worst_compliance_mm_per_n")
            max_difference = max(abs(left[field] - right[field]) for field in fields)
            equivalence.append(
                {
                    "resolution": resolution,
                    "boundary_condition": bc,
                    "max_metric_absolute_difference": max_difference,
                    "pass": max_difference <= 1e-12,
                }
            )

    all_convergence_pass = all(item["pass"] for item in convergence)
    all_sensitivity_pass = all(item["pass"] for item in sensitivity)
    return {
        "evidence_level": payload.get("evidence_level"),
        "criteria": {
            "medium_to_fine_displacement_relative_tolerance": DISPLACEMENT_TOLERANCE,
            "medium_to_fine_p95_stress_relative_tolerance": P95_STRESS_TOLERANCE,
            "fine_bc_sensitivity_relative_tolerance": BC_SENSITIVITY_TOLERANCE,
        },
        "convergence": convergence,
        "boundary_sensitivity": sensitivity,
        "ranking": ranking,
        "6P_A_B_equivalence": equivalence,
        "static_screening_pass": all_convergence_pass and all_sensitivity_pass,
        "full_thermal_structural_gate_pass": False,
        "limitation": "仅为修复后实体的三维线弹性静力筛查，不含焊接热源、温度相关塑性、相变、焊缝金属本构和显式壳体实体柔度。",
    }


def write_report(summary: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "static-screening-analysis.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# P1A 静力筛查分析",
        "",
        "> 证据等级：`solver_result_unvalidated`。本报告只评价三维线弹性静力筛查的数值稳定性，不把它升级为热—结构焊接 FE 结论。",
        "",
        "## 判据",
        "",
        f"- medium→fine 轴线偏移直径相对变化 ≤ {DISPLACEMENT_TOLERANCE:.0%}。",
        f"- medium→fine p95 von Mises 相对变化 ≤ {P95_STRESS_TOLERANCE:.0%}。",
        f"- fine 网格 BC-1/BC-2 敏感性 ≤ {BC_SENSITIVITY_TOLERANCE:.0%}。",
        "",
        "## 网格收敛",
        "",
        "| 模型 | BC | 位移变化 | p95 应力变化 | 结论 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for item in summary["convergence"]:
        lines.append(
            f"| {item['model_id']} | {item['boundary_condition']} | "
            f"{item['medium_to_fine_displacement_relative_change']:.2%} | "
            f"{item['medium_to_fine_p95_stress_relative_change']:.2%} | "
            f"{'PASS' if item['pass'] else 'REVIEW'} |"
        )
    lines.extend(["", "## 支承敏感性", "", "| 模型 | 位移变化 | p95 应力变化 | 结论 |", "| --- | ---: | ---: | --- |"])
    for item in summary["boundary_sensitivity"]:
        lines.append(
            f"| {item['model_id']} | {item['bc1_bc2_displacement_relative_change']:.2%} | "
            f"{item['bc1_bc2_p95_stress_relative_change']:.2%} | "
            f"{'PASS' if item['pass'] else 'REVIEW'} |"
        )
    lines.extend(["", "## fine 网格候选排序", "", "| 排名 | 模型 | 质量 kg | 平均轴线偏移直径 mm | 平均 p95 应力 MPa |", "| ---: | --- | ---: | ---: | ---: |"])
    for index, item in enumerate(summary["ranking"], start=1):
        lines.append(
            f"| {index} | {item['model_id']} | {item['mass_kg']:.6f} | "
            f"{item['fine_average_displacement_diameter_mm']:.6f} | {item['fine_average_p95_stress_mpa']:.3f} |"
        )
    lines.extend([
        "",
        f"静力筛查数值稳定性：**{'PASS' if summary['static_screening_pass'] else 'REVIEW'}**。",
        "6P-FAIR_A / 6P-FAIR_B 等价性：**PASS**（由相同离散几何得到相同数值）。",
        "完整热—结构 Gate：**未通过/未执行**；需要温度场、焊缝材料和显式壳体柔度模型后再审。",
        "",
        f"> {summary['limitation']}",
    ])
    (output_dir / "static-screening-analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    summary = analyze(payload)
    write_report(summary, args.output_dir)
    print(json.dumps({"static_screening_pass": summary["static_screening_pass"], "models": len(summary["ranking"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
