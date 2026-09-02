"""对降阶模型执行参数敏感性扫描。

这不是“网格收敛”替代品。真正的 FE 网格收敛必须在获得求解器后，用同一几何、
边界条件和网格质量指标复核；本脚本只回答模型参数扰动是否改变方案排序。
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

SCRIPT_DIR = Path(__file__).resolve().parent
# SCRIPT_DIR=.../Hanjie/simulation/scripts，向上两级才是仓库根目录。
ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
from run_reduced_order import DEFAULT_CONFIG, evaluate_case, load_yaml  # noqa: E402


RESULT_DIR = ROOT / "simulation" / "results"


def set_nested(config: dict, path: tuple[str, ...], value: float) -> None:
    target = config
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def scan(config: dict) -> list[dict[str, object]]:
    nominal_case = (6, "S3", "flex", "compliant")
    specs = [
        ("efficiency", ("process", "efficiency"), 0.90, 1.10),
        ("current", ("process", "current_a"), 0.90, 1.10),
        ("thermal_conductivity_q235b", ("materials", "q235b", "thermal_conductivity_w_mk"), 0.90, 1.10),
        ("alpha_qt450_10", ("materials", "qt450_10", "alpha_per_k"), 0.95, 1.05),
        ("initial_eccentricity", ("model", "initial_eccentricity_mm"), -0.02, 0.02),
        ("fixture_stiffness", ("materials", "fixture", "equivalent_stiffness_n_mm"), 0.80, 1.20),
    ]
    rows = []
    for name, path, low_factor_or_value, high_factor_or_value in specs:
        base_value = config[path[0]][path[1]] if len(path) == 2 else config[path[0]][path[1]][path[2]] if len(path) == 3 else config[path[0]][path[1]][path[2]][path[3]]
        levels = (
            (("low", low_factor_or_value), ("nominal", 0.0), ("high", high_factor_or_value))
            if name == "initial_eccentricity"
            else (("low", low_factor_or_value), ("nominal", 1.0), ("high", high_factor_or_value))
        )
        for label, operand in levels:
            candidate = copy.deepcopy(config)
            if name == "initial_eccentricity":
                value = operand
            else:
                value = base_value * operand
            set_nested(candidate, path, value)
            result = evaluate_case(candidate, *nominal_case)
            rows.append({
                "parameter": name,
                "level": label,
                "input_value": value,
                "p_sim_mm": result["position_metric_p_sim_mm"],
                "axis_tilt_deg": result["axis_tilt_deg"],
                "peak_temperature_c": result["effective_peak_temperature_c"],
                "pass_in_model": result["pass_in_model"],
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=RESULT_DIR)
    args = parser.parse_args()
    rows = scan(load_yaml(args.config))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "sensitivity.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "case": "FLEX-COMPLIANT-6P-S3",
        "parameter_count": 6,
        "rows": len(rows),
        "statement": "参数扰动结果来自降阶模型；网格收敛需在 FE 求解器可用后补充。",
    }
    (args.output_dir / "sensitivity-metadata.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
