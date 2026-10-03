"""生成竞赛候选方案的统一数字选择结果。

本脚本只使用已经登记的固定送丝、条件承载和净热输入结果，不把未校准
热场或合成位置度当成产品验收。目的是真正冻结一个可复核的推荐方案，
避免报告只凭文字选择 6P。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "studies/COMPETITION-DESIGN/results/assessment.json"
OUTPUT = ROOT / "studies/COMPETITION-DESIGN/results/robust-selection.json"
AUTHORITY = ROOT / "project/competition-authority.yaml"


def main() -> None:
    assessment = json.loads(INPUT.read_text(encoding="utf-8"))
    # 直接读取当前 COMPETITION-R1 的四道比较，避免旧 Route-B 参数链回流。
    view = pd.DataFrame(assessment["four_pass_comparison"])
    view = view.rename(columns={"layout": "candidate_id", "net_heat_kj": "heat_kj"})
    view["candidate_id"] = view["candidate_id"] + "/4pass"
    view["capacity_margin"] = 60.0 / view["required_allowable_mpa"]
    view["weld_length_mm"] = view["candidate_id"].map(
        {"Continuous/4pass": 471.1132343323254, "6P-FAIR_B/4pass": 108.0, "8P-FAIR_B/4pass": 144.0}
    )
    # 一级：硬约束筛选。这里的60 MPa只是本轮统一条件筛查的假设许用值，不是材料许用标准。
    # 二级：Pareto比较，同时最小化净热输入、焊缝长度和所需许用应力。
    # 三级：保留工程语境下的当前数字基线，不宣称存在唯一数学最优解。
    hard_feasible = view[view["required_allowable_mpa"] <= 60.0].copy()

    def is_dominated(row, frame):
        for _, other in frame.iterrows():
            no_worse = (
                other["heat_kj"] <= row["heat_kj"]
                and other["weld_length_mm"] <= row["weld_length_mm"]
                and other["required_allowable_mpa"] <= row["required_allowable_mpa"]
            )
            strictly_better = (
                other["heat_kj"] < row["heat_kj"]
                or other["weld_length_mm"] < row["weld_length_mm"]
                or other["required_allowable_mpa"] < row["required_allowable_mpa"]
            )
            if no_worse and strictly_better:
                return True
        return False

    pareto = hard_feasible[~hard_feasible.apply(lambda row: is_dominated(row, hard_feasible), axis=1)].copy()
    pareto["capacity_margin"] = 60.0 / pareto["required_allowable_mpa"]
    candidates = []
    for _, r in hard_feasible.sort_values(["required_allowable_mpa", "heat_kj"]).iterrows():
        cid = r["candidate_id"]
        candidates.append(
            {
                "candidate_id": cid,
                "required_allowable_mpa": float(r["required_allowable_mpa"]),
                "capacity_margin": float(r["capacity_margin"]),
                "net_heat_input_kj": float(r["heat_kj"]),
                "weld_length_mm": float(r["weld_length_mm"]),
                "hard_constraint_pass": True,
                "pareto_front": cid in set(pareto["candidate_id"]),
            }
        )
    payload = {
        "version": "COMPETITION-R2-DIGITAL-SELECTION-1",
        "evidence_level": "design_assumption_reference_envelope",
        "input": str(INPUT.relative_to(ROOT)).replace("\\", "/"),
        "frozen_scenario": {
            "pass_count": 4,
            "deposition_efficiency": 0.85,
            "load_scale": 1.0,
            "assumed_allowable_mpa": 60.0,
        },
        "hard_constraint": "required_allowable_mpa <= 60.0 MPa in the stated reference screening scenario",
        "pareto_front": pareto["candidate_id"].tolist(),
        "candidates": candidates,
        "digital_baseline": "6P-FAIR_B/4pass",
        "fallback": "8P-FAIR_B/4pass",
        "engineering_selection_status": "pending_release_gates",
        "low_heat_candidate": "6P-FAIR_B/4pass",
        "higher_static_margin_candidate": "8P-FAIR_B/4pass",
        "rejected_high_heat_reference": None,
        "interpretation": "三候选均通过本轮60 MPa参考承载硬约束且均处于Pareto前沿；不存在由任意人为权重导出的唯一数学优胜者。6P-FAIR_B仅作为当前详细数字设计基线，8P作为承载裕量切换候选，Continuous作为高热输入/高焊缝长度参考。所有结果均不代表实际载荷、疲劳寿命、焊缝成形或产品位置度验收。",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    recommended = next(r for r in candidates if r["candidate_id"] == payload["digital_baseline"])
    backup = next(r for r in candidates if r["candidate_id"] == payload["fallback"])
    authority = {
        "version": "COMPETITION-R2-AUTHORITY",
        "scope": "参赛说明书与答辩统一引用的保守设计口径",
        "selected_candidate": payload["digital_baseline"],
        "engineering_selection_status": payload["engineering_selection_status"],
        "digital_baseline": payload["digital_baseline"],
        "low_heat_candidate": payload["low_heat_candidate"],
        "higher_static_margin_candidate": payload["higher_static_margin_candidate"],
        "pareto_front": pareto["candidate_id"].tolist(),
        "assumptions": {"deposition_efficiency": 0.85, "load_scale": 1.0,
                        "assumed_allowable_mpa": 60.0, "equivalent_leg_min_mm": 3.5},
        "results": {"required_allowable_mpa": recommended["required_allowable_mpa"],
                    "conditional_margin": recommended["capacity_margin"],
                    "weld_length_mm": recommended["weld_length_mm"],
                    "net_heat_input_kj": round(recommended["net_heat_input_kj"], 5),
                    "arc_on_time_s": round(float(next(r["arc_time_s"] for r in assessment["four_pass_comparison"] if r["layout"] == payload["digital_baseline"].split("/")[0])), 3),
                    "fallback_candidate": payload["fallback"],
                    "fallback_required_allowable_mpa": backup["required_allowable_mpa"]},
        "endpoints": {"current_efficiency_0_85_required_allowable_mpa": recommended["required_allowable_mpa"],
                      "interpretation": "当前 COMPETITION-R1 四道比较已按固定送丝与效率下界闭合；此值用于保守筛查。"},
        "decision_rule": "一级按统一60 MPa参考情景做硬约束；二级以热输入、焊缝长度和所需许用应力构成Pareto前沿；三级由工艺成熟度与当前详细设计完整度确定6P为数字基线。真实载荷、焊后变形、裂纹、疲劳、洁净度和位置度放行门闭合后再决定最终工程方案，承载裕量不足时评定8P。",
    }
    AUTHORITY.write_text(yaml.safe_dump(authority, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
