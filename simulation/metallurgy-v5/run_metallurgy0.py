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


def _parent_exposure_width(
    field: dict[str, np.ndarray],
    material_code: int,
    interface_n_mm: float,
    threshold_c: float,
) -> float:
    """从代理母材—焊缝界面量到达到阈值的最远母材单元中心。"""
    peak_by_n = np.max(field["temperature_peak"], axis=(0, 2))
    material_by_n = field["material_id"][0, :, 0]
    indices = np.where((peak_by_n >= threshold_c) & (material_by_n == material_code))[0]
    if not indices.size:
        return 0.0
    return float(max(abs(float(field["n"][index]) - interface_n_mm) for index in indices))


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
    weld = _material_stats(field, 3)
    weld_half_width = float(metallurgy["surrogate_weld_half_width_mm"])
    low_haz_threshold = float(metallurgy["low_temperature_haz_threshold_c"])
    qt_haz_width = _parent_exposure_width(field, 2, -weld_half_width, low_haz_threshold)
    q235_haz_width = _parent_exposure_width(field, 1, weld_half_width, low_haz_threshold)
    qt_t85 = qt["t8_5_median_s"]
    q235_t85 = q235["t8_5_median_s"]
    qt_white_score = int(qt["peak_temperature_c"] >= 1200.0) + int(qt["maximum_cooling_rate_c_s"] >= 100.0) + int(qt_t85 is not None and qt_t85 < 8.0)
    qt_hardening_score = int(qt["peak_temperature_c"] >= 900.0) + int(qt["maximum_cooling_rate_c_s"] >= 80.0) + int(qt_t85 is not None and qt_t85 < 12.0)
    qt_crack_score = int(qt["peak_temperature_c"] >= 900.0) + int(qt["maximum_cooling_rate_c_s"] >= 80.0) + int(float(config["process"]["preheat_temperature_c"]) < 130.0)
    q235_grain_score = int(q235["peak_temperature_c"] >= 900.0) + int(q235["peak_temperature_c"] >= 1100.0)
    q235_hardening_score = int(q235["peak_temperature_c"] >= 723.0) + int(q235["maximum_cooling_rate_c_s"] >= 80.0) + int(q235_t85 is not None and q235_t85 < 12.0)
    risk = {
        "qt450_10": {
            "white_cast_iron_carbide_risk": _risk(qt_white_score),
            "martensite_high_hardening_risk": _risk(qt_hardening_score),
            "haz_embrittlement_risk": _risk(int(qt["peak_temperature_c"] >= 900.0) + int(qt_white_score >= 2)),
            "cold_crack_risk": _risk(qt_crack_score),
            "thermal_exposure_width_tpeak_ge_400c_mm": qt_haz_width,
            "hardness_trend": "靠近代理母材—焊缝界面和快速冷却区域预计高于 QT450-10 母材；需显微硬度线扫确认",
            "risk_location": _risk_location(field, 2, float(config["geometry"]["interface_radius_mm"])),
        },
        "q235b": {
            "high_temperature_grain_coarsening_risk": _risk(q235_grain_score),
            "hardening_risk": _risk(q235_hardening_score),
            "haz_embrittlement_risk": _risk(int(q235["peak_temperature_c"] >= 900.0) + int(q235_hardening_score >= 2)),
            "hardness_trend": "靠近代理母材—焊缝界面处出现热影响梯度；不得由硬度趋势直接推断疲劳寿命",
            "thermal_exposure_width_tpeak_ge_400c_mm": q235_haz_width,
            "risk_location": _risk_location(field, 1, float(config["geometry"]["interface_radius_mm"])),
        },
        "ernife_ci_weld_surrogate": {
            "peak_temperature_c": weld["peak_temperature_c"],
            "fusion_threshold_exceeded": weld["peak_temperature_c"] >= float(metallurgy["fusion_threshold_c"]),
            "risk_status": "not_scored_pending_high_temperature_properties_and_calibration",
            "risk_location": _risk_location(field, 3, float(config["geometry"]["interface_radius_mm"])),
        },
    }
    dilution = _dilution_estimate(config, materials)
    summary = {
        "run_timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "python_version": platform.python_version(),
        "solver_version": "METALLURGY-0.2-parent-material-risk-mapper-v5",
        "dependency_versions": {name: importlib.metadata.version(name) for name in ("numpy", "PyYAML")},
        "input_file": str(INPUT_PATH.relative_to(ROOT)).replace("\\", "/"),
        "input_sha256": _sha256(INPUT_PATH),
        "thermal_input_sha256": _sha256(thermal_dir / "thermal0-field.npz"),
        "stage": "METALLURGY-0",
        "evidence_level": "literature_supported_plus_solver_result_unvalidated",
        "thermal_input": "simulation/thermal-v5/results/thermal0-field.npz",
        "thermal_evidence_level": "solver_result_unvalidated",
        "material_statistics": {"qt450_10_parent_material": qt, "q235b_parent_material": q235, "ernife_ci_weld_surrogate": weld},
        "region_semantics": {
            "surrogate_weld_band_n_mm": [-weld_half_width, weld_half_width],
            "qt450_10_parent_condition": f"material_id == 2 (n < {-weld_half_width:g} mm)",
            "q235b_parent_condition": f"material_id == 1 (n > {weld_half_width:g} mm)",
            "parent_risk_mask_includes_weld_cells": 0,
            "parent_haz_width_includes_weld": False,
            "interfaces_are_surrogate_not_calibrated_fusion_lines": True,
        },
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
        f"- QT450-10 母材峰值温度：{qt['peak_temperature_c']:.1f} °C；最大离散冷却速率：{qt['maximum_cooling_rate_c_s']:.1f} °C/s；t8/5 中位数：{qt_t85 if qt_t85 is not None else '无有效节点'} s。",
        f"- Q235B 母材峰值温度：{q235['peak_temperature_c']:.1f} °C；最大离散冷却速率：{q235['maximum_cooling_rate_c_s']:.1f} °C/s；t8/5 中位数：{q235_t85 if q235_t85 is not None else '无有效节点'} s。",
        f"- ERNiFe-CI 代理焊缝峰值温度：{weld['peak_temperature_c']:.1f} °C；高温物性和相变模型补齐前不评分焊缝冶金风险。",
        f"- 母材热暴露宽度（Tpeak≥400 °C，排除 ±{weld_half_width:g} mm 代理焊缝带）：QT450-10={qt_haz_width:.3f} mm，Q235B={q235_haz_width:.3f} mm。",
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
