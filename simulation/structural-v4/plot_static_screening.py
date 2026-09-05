"""由静力筛查原始结果生成可追溯的极坐标和 Pareto SVG 图。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "results" / "static-screening" / "static-screening-raw.json"
DEFAULT_OUTPUT = ROOT / "figures"


def _load_fine_rows(payload: dict) -> dict[tuple[str, str], dict]:
    return {
        (row["model_id"], row["boundary_condition"]): row
        for row in payload["rows"]
        if row["resolution"] == "fine"
    }


def make_figures(payload: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fine = _load_fine_rows(payload)
    models = sorted({model for model, _ in fine})
    colors = plt.cm.tab10(np.linspace(0, 1, len(models)))
    fig = plt.figure(figsize=(8.2, 6.4))
    ax = fig.add_subplot(111, projection="polar")
    for color, model in zip(colors, models):
        rows = [fine[(model, bc)] for bc in ("BC-1", "BC-2")]
        direction_results = rows[0]["direction_results"]
        measured_angles = np.deg2rad([item["load_angle_deg"] for item in direction_results])
        measured_values = np.array([item["compliance_mm_per_n"] for item in direction_results]) * 1000.0
        ax.plot(measured_angles, measured_values, marker="o", markersize=3, color=color, linewidth=1.5, label=model)
    ax.set_title("Fine-mesh radial compliance (0–90°, BC-1, 1 kN)", pad=18)
    ax.set_ylabel("Compliance (mm/kN)")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper right", bbox_to_anchor=(1.28, 1.15), fontsize=8)
    fig.tight_layout()
    fig.savefig(output_dir / "polar-radial-compliance.svg", format="svg", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8.2, 5.8))
    for color, model in zip(colors, models):
        rows = [fine[(model, bc)] for bc in ("BC-1", "BC-2")]
        x = np.mean([row["mass_kg"] for row in rows])
        y = np.mean([row["worst_p95_stress_mpa"] for row in rows])
        size = 5000.0 * np.mean([row["worst_position_diameter_mm"] for row in rows])
        ax.scatter(x, y, s=max(30.0, size), color=color, alpha=0.82, edgecolor="white", linewidth=0.8)
        ax.annotate(model, (x, y), xytext=(5, 5), textcoords="offset points", fontsize=8)
    ax.set_xlabel("Mass (kg)")
    ax.set_ylabel("Fine-mesh p95 von Mises (MPa)")
    ax.set_title("Static screening: mass / stress / axis-drift trade-off")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "pareto-stiffness-stress-mass.svg", format="svg", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    make_figures(payload, args.output_dir)
    print(json.dumps({"figures": 2, "output_dir": str(args.output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
