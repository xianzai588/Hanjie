"""基于 THERMAL-0 热历史执行 METALLURGY-0 风险级预测。

本脚本只输出 HAZ 分区、焊缝几何稀释估计、成分区间和 Low/Medium/High 风险。
没有本项目金相、硬度或 CALPHAD 数据时，不输出相含量和未经校准的精确硬度。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
from typing import Any

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = ROOT / "project" / "g-inputs-v5.2.yaml"
MATERIAL_PATH = ROOT / "project" / "materials.yaml"
THERMAL_DIR = ROOT / "simulation" / "thermal-v5" / "results"
OUTPUT_DIR = ROOT / "simulation" / "metallurgy-v5" / "results"


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _risk(score: int) -> str:
    if score >= 3:
        return "High"
    if score >= 1:
        return "Medium"
    return "Low"


def _material_stats(field: dict[str, np.ndarray], material_code: int) -> dict[str, Any]:
    mask = field["material_id"] == material_code
    peak = field["temperature_peak"][mask]
    cooling = field["max_cooling_rate_c_s"][mask]
    t85 = field["t8_5_s"][mask]
    valid_t85 = t85[np.isfinite(t85)]
    return {
        "node_count": int(mask.sum()),
        "peak_temperature_c": float(np.max(peak)),
        "peak_temperature_p95_c": float(np.percentile(peak, 95)),
        "maximum_cooling_rate_c_s": float(np.max(cooling)),
        "t8_5_valid_node_count": int(valid_t85.size),
        "t8_5_median_s": float(np.median(valid_t85)) if valid_t85.size else None,
        "t8_5_minimum_s": float(np.min(valid_t85)) if valid_t85.size else None,
    }


def _side_stats(field: dict[str, np.ndarray], side: str) -> dict[str, Any]:
    """按接口法向空间区域统计，避免焊缝分类带来的母材侧风险漏计。"""
    n_grid = field["n"][None, :, None]
    mask = np.broadcast_to(n_grid < 0.0 if side == "qt450_10_side" else n_grid > 0.0, field["temperature_peak"].shape)
    peak = field["temperature_peak"][mask]
    cooling = field["max_cooling_rate_c_s"][mask]
    t85 = field["t8_5_s"][mask]
    valid_t85 = t85[np.isfinite(t85)]
    return {
        "node_count": int(mask.sum()),
        "peak_temperature_c": float(np.max(peak)),
        "peak_temperature_p95_c": float(np.percentile(peak, 95)),
        "maximum_cooling_rate_c_s": float(np.max(cooling)),
        "t8_5_valid_node_count": int(valid_t85.size),
        "t8_5_median_s": float(np.median(valid_t85)) if valid_t85.size else None,
        "t8_5_minimum_s": float(np.min(valid_t85)) if valid_t85.size else None,
    }


def _risk_location(field: dict[str, np.ndarray], material_code: int, radius_mm: float) -> dict[str, float]:
    mask = field["material_id"] == material_code
    score = np.where(mask, field["temperature_peak"], -np.inf)
    index = int(np.argmax(score))
    s = float(field["s"].reshape(-1)[np.unravel_index(index, field["temperature_peak"].shape)[0]])
    # 展开网格的 n/z 轴可直接从三维索引读取，避免把孔轴当作自身基准。
    location = np.unravel_index(index, field["temperature_peak"].shape)
    n_value = float(field["n"][location[1]])
    z_value = float(field["z"][location[2]])
    return {
        "angle_deg": float(s / (2.0 * np.pi * radius_mm) * 360.0),
        "n_mm": n_value,
        "z_mm": z_value,
        "peak_temperature_c": float(field["temperature_peak"][location]),
    }


def _risk_location_side(field: dict[str, np.ndarray], side: str, radius_mm: float) -> dict[str, float]:
    n_grid = field["n"][None, :, None]
    mask = np.broadcast_to(n_grid < 0.0 if side == "qt450_10_side" else n_grid > 0.0, field["temperature_peak"].shape)
    score = np.where(mask, field["temperature_peak"], -np.inf)
    location = np.unravel_index(int(np.argmax(score)), field["temperature_peak"].shape)
    return {
        "angle_deg": float(field["s"][location[0]] / (2.0 * np.pi * radius_mm) * 360.0),
        "n_mm": float(field["n"][location[1]]),
        "z_mm": float(field["z"][location[2]]),
        "peak_temperature_c": float(field["temperature_peak"][location]),
    }


def _dilution_estimate(config: dict[str, Any], materials: dict[str, Any]) -> dict[str, Any]:
    """用名义焊脚和假设熔入深度计算区间，不把几何估计写成化学实测。"""
    leg = float(config["geometry"]["fillet_leg_length_mm"])
    weld_area = 0.5 * leg**2
    qt_depth = 1.5
    q235_depth = 1.0
    qt_area = qt_depth * leg
    q235_area = q235_depth * leg
    total_area = weld_area + qt_area + q235_area
    fractions = {"weld_metal": weld_area / total_area, "qt450_10": qt_area / total_area, "q235b": q235_area / total_area}
    scales = np.linspace(0.75, 1.25, 11)
    compositions: list[dict[str, float]] = []
    weld_nominal = materials["ernife_ci"]["composition_nominal_wt_pct"]
    qt_nominal = materials["qt450_10"]["composition_nominal_wt_pct"]
    q235_nominal = materials["q235b"]["composition_nominal_wt_pct"]
    for qt_scale in scales:
        for q235_scale in scales:
            qt_a = qt_area * qt_scale
            q235_a = q235_area * q235_scale
            denominator = weld_area + qt_a + q235_a
            compositions.append(
                {
                    "Ni": float(weld_nominal["Ni"] * weld_area / denominator),
                    "C": float((weld_nominal["C"] * weld_area + qt_nominal["C"] * qt_a + q235_nominal["C"] * q235_a) / denominator),
                }
            )
    composition_ranges = {
        element: {"min_wt_pct": float(min(item[element] for item in compositions)), "max_wt_pct": float(max(item[element] for item in compositions))}
        for element in ("Ni", "C")
    }
    return {
        "dilution_method": "geometry_based_nominal",
        "evidence_level": "design_assumption",
        "nominal_cross_section_area_mm2": {"weld_metal": weld_area, "qt450_10_parent": qt_area, "q235b_parent": q235_area, "total": total_area},
        "nominal_dilution_fraction": fractions,
        "qt450_10_fraction": fractions["qt450_10"],
        "q235b_fraction": fractions["q235b"],
        "filler_fraction": fractions["weld_metal"],
        "thermal_fusion_validated": False,
        "chemistry_validated": False,
        "parent_fusion_depth_assumption_mm": {"qt450_10": qt_depth, "q235b": q235_depth},
        "parent_fusion_depth_sensitivity": "each parent fusion depth varied independently from 75% to 125%",
        "composition_range_wt_pct": composition_ranges,
        "fe_content": "balance; not independently resolved from nominal compositions",
        "limitation": "未进行宏观截面实测、化学成分分析或 CALPHAD 计算；只能报告区间和趋势。",
    }


def run(config: dict[str, Any], materials: dict[str, Any], thermal_dir: Path, output_dir: Path) -> dict[str, Any]:
    with np.load(thermal_dir / "thermal0-field.npz") as loaded:
        field = {key: loaded[key] for key in loaded.files}
    metallurgy = config["metallurgy"]
    qt = _material_stats(field, 2)
    q235 = _material_stats(field, 1)
    qt_side = _side_stats(field, "qt450_10_side")
    q235_side = _side_stats(field, "q235b_side")
    peak_by_n = np.max(field["temperature_peak"], axis=(0, 2))
    low_haz_threshold = float(metallurgy["low_temperature_haz_threshold_c"])
    qt_haz_indices = np.where((peak_by_n >= low_haz_threshold) & (field["n"] < 0.0))[0]
    q235_haz_indices = np.where((peak_by_n >= low_haz_threshold) & (field["n"] > 0.0))[0]
    qt_haz_width = float(abs(field["n"][qt_haz_indices[0]])) if qt_haz_indices.size else 0.0
    q235_haz_width = float(field["n"][q235_haz_indices[-1]]) if q235_haz_indices.size else 0.0
    qt_t85 = qt_side["t8_5_median_s"]
    q235_t85 = q235_side["t8_5_median_s"]
    qt_white_score = int(qt_side["peak_temperature_c"] >= 1200.0) + int(qt_side["maximum_cooling_rate_c_s"] >= 100.0) + int(qt_t85 is not None and qt_t85 < 8.0)
    qt_hardening_score = int(qt_side["peak_temperature_c"] >= 900.0) + int(qt_side["maximum_cooling_rate_c_s"] >= 80.0) + int(qt_t85 is not None and qt_t85 < 12.0)
    qt_crack_score = int(qt_side["peak_temperature_c"] >= 900.0) + int(qt_side["maximum_cooling_rate_c_s"] >= 80.0) + int(float(config["process"]["preheat_temperature_c"]) < 130.0)
    q235_grain_score = int(q235_side["peak_temperature_c"] >= 900.0) + int(q235_side["peak_temperature_c"] >= 1100.0)
    q235_hardening_score = int(q235_side["peak_temperature_c"] >= 723.0) + int(q235_side["maximum_cooling_rate_c_s"] >= 80.0) + int(q235_t85 is not None and q235_t85 < 12.0)
    risk = {
        "qt450_10": {
            "white_cast_iron_carbide_risk": _risk(qt_white_score),
            "martensite_high_hardening_risk": _risk(qt_hardening_score),
            "haz_embrittlement_risk": _risk(int(qt["peak_temperature_c"] >= 900.0) + int(qt_white_score >= 2)),
            "cold_crack_risk": _risk(qt_crack_score),
            "thermal_exposure_width_tpeak_ge_400c_mm": qt_haz_width,
            "hardness_trend": "靠近熔合线和快速冷却区域预计高于 QT450-10 母材；需显微硬度线扫确认",
            "risk_location": _risk_location_side(field, "qt450_10_side", float(config["geometry"]["interface_radius_mm"])),
        },
        "q235b": {
            "high_temperature_grain_coarsening_risk": _risk(q235_grain_score),
            "hardening_risk": _risk(q235_hardening_score),
            "haz_embrittlement_risk": _risk(int(q235["peak_temperature_c"] >= 900.0) + int(q235_hardening_score >= 2)),
            "hardness_trend": "靠近熔合线处出现热影响梯度；不得由硬度趋势直接推断疲劳寿命",
            "thermal_exposure_width_tpeak_ge_400c_mm": q235_haz_width,
            "risk_location": _risk_location_side(field, "q235b_side", float(config["geometry"]["interface_radius_mm"])),
        },
    }
    dilution = _dilution_estimate(config, materials)
    summary = {
        "run_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "python_version": platform.python_version(),
        "solver_version": "METALLURGY-0-risk-mapper-v5",
        "dependency_versions": {name: importlib.metadata.version(name) for name in ("numpy", "PyYAML")},
        "input_file": str(INPUT_PATH.relative_to(ROOT)).replace("\\", "/"),
        "input_sha256": _sha256(INPUT_PATH),
        "thermal_input_sha256": _sha256(thermal_dir / "thermal0-field.npz"),
        "stage": "METALLURGY-0",
        "evidence_level": "literature_supported_plus_solver_result_unvalidated",
        "thermal_input": "simulation/thermal-v5/results/thermal0-field.npz",
        "thermal_evidence_level": "solver_result_unvalidated",
        "material_statistics": {"qt450_10_material_zone": qt, "q235b_material_zone": q235, "qt450_10_side_region": qt_side, "q235b_side_region": q235_side},
        "haz_thresholds_c": {
            "fusion": float(metallurgy["fusion_threshold_c"]),
            "high_temperature": float(metallurgy["high_temperature_haz_threshold_c"]),
            "medium_temperature": float(metallurgy["medium_temperature_haz_threshold_c"]),
            "low_temperature": float(metallurgy["low_temperature_haz_threshold_c"]),
        },
        "risk_assessment": risk,
        "weld_dilution_and_composition": dilution,
        "evidence_boundary": [
            "组织输出为风险等级、区间、趋势和位置，不含伪精确相含量。",
            "t8/5 作为热循环描述量，不单独等同于 QT450-10 的 CCT 相组成判据。",
            "显微硬度只能支持组织变化和脆硬趋势，不能替代拉伸、韧性或疲劳试验。",
            "当前没有金相、显微硬度和化学成分实测，G-METALLURGY 仍未完成物理验证。",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metallurgy0-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [
        {"material": "QT450-10", "peak_temperature_c": qt["peak_temperature_c"], "max_cooling_rate_c_s": qt["maximum_cooling_rate_c_s"], "t8_5_median_s": qt_t85, "white_cast_iron_risk": risk["qt450_10"]["white_cast_iron_carbide_risk"], "hardening_risk": risk["qt450_10"]["martensite_high_hardening_risk"], "crack_risk": risk["qt450_10"]["cold_crack_risk"]},
        {"material": "Q235B", "peak_temperature_c": q235["peak_temperature_c"], "max_cooling_rate_c_s": q235["maximum_cooling_rate_c_s"], "t8_5_median_s": q235_t85, "white_cast_iron_risk": "not_applicable", "hardening_risk": risk["q235b"]["hardening_risk"], "crack_risk": "not_scored"},
    ]
    with (output_dir / "metallurgy0-risk.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# METALLURGY-0 组织—性能风险预测",
        "",
        "> 证据等级：`literature_supported_plus_solver_result_unvalidated`。本报告消费 THERMAL-0 热历史，未消费任何实测金相、硬度或化学成分数据。",
        "",
        "## 结果摘要",
        "",
        f"- QT450-10 侧空间区域峰值温度：{qt_side['peak_temperature_c']:.1f} °C；最大离散冷却速率：{qt_side['maximum_cooling_rate_c_s']:.1f} °C/s；t8/5 中位数：{qt_t85 if qt_t85 is not None else '无有效节点'} s。",
        f"- Q235B 侧空间区域峰值温度：{q235_side['peak_temperature_c']:.1f} °C；最大离散冷却速率：{q235_side['maximum_cooling_rate_c_s']:.1f} °C/s；t8/5 中位数：{q235_t85 if q235_t85 is not None else '无有效节点'} s。",
        "",
        "## 风险判定",
        "",
        "| 材料侧 | 风险项 | 等级 |",
        "| --- | --- | --- |",
    ]
    for material, assessments in risk.items():
        for key, value in assessments.items():
            if key.endswith("risk") or key.endswith("_risk"):
                lines.append(f"| {material} | {key} | **{value}** |")
    lines.extend([
        "",
        "## 焊缝稀释—成分区间",
        "",
        f"- 名义焊缝金属截面积：{dilution['nominal_cross_section_area_mm2']['weld_metal']:.3f} mm²。",
        f"- 名义 QT450-10 熔入比例：{dilution['nominal_dilution_fraction']['qt450_10']:.1%}；Q235B 熔入比例：{dilution['nominal_dilution_fraction']['q235b']:.1%}。",
        f"- Ni 区间：{dilution['composition_range_wt_pct']['Ni']['min_wt_pct']:.2f}–{dilution['composition_range_wt_pct']['Ni']['max_wt_pct']:.2f} wt%；C 区间：{dilution['composition_range_wt_pct']['C']['min_wt_pct']:.2f}–{dilution['composition_range_wt_pct']['C']['max_wt_pct']:.2f} wt%。",
        "- 上述成分为 geometry_based_nominal 稀释贡献的敏感性估计，不是焊缝化学分析结果；填充金属贡献约为 41.2%。",
        "",
        "## Gate 边界",
        "",
        "- G-METALLURGY：**未通过物理验证**；当前可作为 THERMAL-0 驱动的风险筛查。",
        "- 下一步物理证据：宏观截面 → 金相（QT 母材—QT HAZ—熔合线—NiFe 焊缝—Q235B HAZ—母材）→ 显微硬度线扫。",
    ])
    (output_dir / "metallurgy0-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_files = ["metallurgy0-summary.json", "metallurgy0-risk.csv", "metallurgy0-report.md"]
    (output_dir / "metallurgy0-result-manifest.json").write_text(
        json.dumps(
            {
                "stage": "METALLURGY-0",
                "evidence_level": summary["evidence_level"],
                "input_file": summary["input_file"],
                "input_sha256": summary["input_sha256"],
                "thermal_input": summary["thermal_input"],
                "thermal_input_sha256": summary["thermal_input_sha256"],
                "files": {name: _sha256(output_dir / name) for name in manifest_files},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thermal-dir", type=Path, default=THERMAL_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    config = _load_yaml(INPUT_PATH)
    materials = _load_yaml(MATERIAL_PATH)["materials"]
    summary = run(config, materials, args.thermal_dir, args.output_dir)
    print(json.dumps({"stage": summary["stage"], "evidence_level": summary["evidence_level"], "qt_risk": summary["risk_assessment"]["qt450_10"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
