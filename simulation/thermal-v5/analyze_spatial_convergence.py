"""在共同控制体上比较 0.4R1 中、细网格，定位空间收敛失败来源。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS = ROOT / "simulation" / "thermal-v5" / "results" / "credibility04r1"
MATERIALS = ((1, "q235b"), (2, "qt450_10"), (3, "ernife_ci"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _weighted_percentile(values: np.ndarray, weights: np.ndarray, percentile: float) -> float:
    order = np.argsort(values)
    cumulative = np.cumsum(weights[order])
    index = np.searchsorted(cumulative, percentile / 100.0 * cumulative[-1])
    return float(values[order[min(index, len(order) - 1)]])


def _project_fine_to_medium(medium: np.lib.npyio.NpzFile, fine: np.lib.npyio.NpzFile) -> tuple[np.ndarray, np.ndarray]:
    """按中网格控制体聚合细网格，避免直接比较不同位置的极值单元。"""
    axes = ("s", "n", "z")
    indices = [np.searchsorted(medium[f"{axis}_edges"], fine[axis], side="right") - 1 for axis in axes]
    sizes = tuple(len(medium[f"{axis}_edges"]) - 1 for axis in axes) + (4,)
    valid = np.ones(len(fine["s"]), dtype=bool)
    for index, size in zip(indices, sizes[:3]):
        valid &= (index >= 0) & (index < size)
    keys = np.ravel_multi_index(tuple(index[valid] for index in indices) + (fine["material_id"][valid],), sizes)
    weights = fine["cell_volume_mm3"][valid] * fine["filled_fraction"][valid]
    count = int(np.prod(sizes))
    projected_volume = np.bincount(keys, weights=weights, minlength=count)
    projected_energy = np.bincount(keys, weights=weights * fine["temperature_peak"][valid], minlength=count)

    medium_indices = [np.searchsorted(medium[f"{axis}_edges"], medium[axis], side="right") - 1 for axis in axes]
    medium_keys = np.ravel_multi_index(tuple(medium_indices) + (medium["material_id"],), sizes)
    volume = projected_volume[medium_keys]
    temperature = np.divide(projected_energy[medium_keys], volume, out=np.full_like(volume, np.nan), where=volume > 0)
    return temperature, volume


def analyze(results_dir: Path = DEFAULT_RESULTS) -> dict[str, object]:
    plan_path = ROOT / "project" / "thermal-credibility-v5.4r1.yaml"
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    limit = float(plan["convergence"]["peak_absolute_limit_c"])
    medium_path = results_dir / "medium" / "field.npz"
    fine_path = results_dir / "fine" / "field.npz"
    medium_summary_path = results_dir / "medium" / "summary.json"
    fine_summary_path = results_dir / "fine" / "summary.json"
    medium_summary = json.loads(medium_summary_path.read_text(encoding="utf-8"))
    fine_summary = json.loads(fine_summary_path.read_text(encoding="utf-8"))

    with np.load(medium_path) as medium, np.load(fine_path) as fine:
        projected, projected_volume = _project_fine_to_medium(medium, fine)
        comparison: dict[str, object] = {}
        for code, name in MATERIALS:
            base_mask = (medium["material_id"] == code) & (medium["filled_fraction"] > 0)
            mask = base_mask & np.isfinite(projected) & (projected_volume > 0)
            weights = medium["cell_volume_mm3"][mask] * medium["filled_fraction"][mask]
            difference = projected[mask] - medium["temperature_peak"][mask]
            absolute = np.abs(difference)
            solidus = float(medium_summary["material_statistics"][name]["solidus_c"])
            flips = (medium["temperature_peak"][mask] > solidus) != (projected[mask] > solidus)
            comparison[name] = {
                "matched_volume_fraction": float(weights.sum() / np.sum(medium["cell_volume_mm3"][base_mask] * medium["filled_fraction"][base_mask])),
                "volume_weighted_mean_abs_peak_difference_c": float(np.average(absolute, weights=weights)),
                "volume_weighted_p95_abs_peak_difference_c": _weighted_percentile(absolute, weights, 95.0),
                "maximum_abs_peak_difference_c": float(absolute.max()),
                "solidus_threshold_flip_volume_mm3": float(weights[flips].sum()),
                "projected_field_p95_pass": bool(_weighted_percentile(absolute, weights, 95.0) <= limit),
                "projected_field_max_pass": bool(absolute.max() <= limit),
                "registered_peak_extrema_difference_c": float(abs(
                    fine_summary["material_statistics"][name]["peak_temperature_c"]
                    - medium_summary["material_statistics"][name]["peak_temperature_c"]
                )),
            }

        weld_medium_allocated = medium["material_id"] == 3
        weld_fine_allocated = fine["material_id"] == 3
        weld_medium = weld_medium_allocated & (medium["filled_fraction"] > 0)
        weld_fine = weld_fine_allocated & (fine["filled_fraction"] > 0)
        weld_volume_medium = float(np.sum(medium["cell_volume_mm3"][weld_medium] * medium["filled_fraction"][weld_medium]))
        weld_volume_fine = float(np.sum(fine["cell_volume_mm3"][weld_fine] * fine["filled_fraction"][weld_fine]))
        geometry = {
            "medium_weld_cell_count": int(weld_medium.sum()),
            "fine_weld_cell_count": int(weld_fine.sum()),
            "medium_allocated_weld_cell_count": int(weld_medium_allocated.sum()),
            "fine_allocated_weld_cell_count": int(weld_fine_allocated.sum()),
            "medium_effective_weld_volume_mm3": weld_volume_medium,
            "fine_effective_weld_volume_mm3": weld_volume_fine,
            "effective_weld_volume_relative_change": abs(weld_volume_fine - weld_volume_medium) / weld_volume_fine,
            "interpretation": "沉积体积守恒，但焊道/热源边界由更多单元重新离散；体积一致不能证明局部峰温场收敛。",
        }

    result = {
        "stage": "THERMAL-0.4R1-SPATIAL-DIAGNOSIS",
        "evidence_level": "postprocess_of_solver_result_unvalidated",
        "fixed_scenario": "surface45, nominal properties, dt=0.1 s; process and source parameters unchanged",
        "method": "将细网格峰温按材料和体积投影到中网格共同控制体后比较",
        "peak_absolute_limit_c": limit,
        "sources": {
            str(medium_path.relative_to(ROOT)).replace("\\", "/"): _sha256(medium_path),
            str(fine_path.relative_to(ROOT)).replace("\\", "/"): _sha256(fine_path),
            str(plan_path.relative_to(ROOT)).replace("\\", "/"): _sha256(plan_path),
        },
        "material_comparison": comparison,
        "geometry_comparison": geometry,
        "diagnosis": {
            "parent_bulk_field": "Q235B 和 QT450-10 的体积加权 P95 差异低于 10 °C，但局部最大差异仍超限。",
            "threshold_sensitivity": "QT450-10 在共同控制体上出现固相线跨越翻转，阈值型熔化指标对局部离散敏感。",
            "weld_hot_zone": "ERNiFe-CI 的体积加权 P95 峰温差异仍显著超限，不是仅靠阈值口径即可解释。",
            "root_cause_class": "局部高梯度焊道/热源空间离散未收敛，并叠加固相线阈值翻转；不是总沉积体积不守恒。",
        },
        "spatial_convergence_pass": False,
        "allowed_use": "定位后续网格/热源离散验证；不开放 THERMAL-1 或熔合几何结论",
    }
    return result


def render_markdown(result: dict[str, object]) -> str:
    lines = [
        "# THERMAL-0.4R1 空间收敛诊断",
        "",
        f"> {result['fixed_scenario']}。本文件是已有结果的共同控制体后处理，不是新物理校准。",
        "",
        "| 材料 | 体积加权 MAE (°C) | 体积加权 P95 (°C) | 最大差 (°C) | 固相线翻转体积 (mm³) | P95 门 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, name in MATERIALS:
        row = result["material_comparison"][name]
        lines.append(
            f"| {name} | {row['volume_weighted_mean_abs_peak_difference_c']:.3f} | "
            f"{row['volume_weighted_p95_abs_peak_difference_c']:.3f} | {row['maximum_abs_peak_difference_c']:.3f} | "
            f"{row['solidus_threshold_flip_volume_mm3']:.3f} | {'通过' if row['projected_field_p95_pass'] else '未通过'} |"
        )
    geometry = result["geometry_comparison"]
    lines += [
        "",
        "## 结论",
        "",
        f"中、细网格有效焊材体积分别为 {geometry['medium_effective_weld_volume_mm3']:.6f}/{geometry['fine_effective_weld_volume_mm3']:.6f} mm³，体积守恒；焊材单元数从 {geometry['medium_weld_cell_count']} 变为 {geometry['fine_weld_cell_count']}。",
        "Q235B 与 QT450-10 的大部分体积温度场已接近，但局部极值仍超限；QT450-10 出现固相线判定翻转。ERNiFe-CI 热区的 P95 差异仍超限，因此失败不只是阈值统计问题，而是局部焊道/热源离散尚未收敛。",
        "",
        "状态：`spatial_convergence_pass=false`。继续冻结 THERMAL-1；下一步应固定本情景，优先细化焊道与热源边界表示并复核共同物理位置，而不是调整热效率或门槛。",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()
    result = analyze(args.results_dir)
    json_path = args.results_dir / "spatial-convergence-diagnosis.json"
    md_path = args.results_dir / "spatial-convergence-diagnosis.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
