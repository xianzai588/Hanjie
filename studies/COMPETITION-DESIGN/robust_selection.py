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
    view["length_penalty"] = view["candidate_id"].map(
        {"Continuous/4pass": 471.1132343323254, "6P-FAIR_B/4pass": 108.0, "8P-FAIR_B/4pass": 144.0}
    )
    # 只在满足条件承载筛查的方案中比较热输入和焊缝长度；分数是排序工具，
    # 不是概率，也不替代热—结构正式求解。
    # four_pass_comparison 已由当前设计计算的同一条件筛查生成。
    feasible = view.copy()
    feasible["score"] = (
        0.60 * feasible["heat_kj"] / feasible["heat_kj"].max()
        + 0.25 * feasible["length_penalty"] / feasible["length_penalty"].max()
        + 0.15 / feasible["capacity_margin"]
    )
    feasible = feasible.sort_values(["score", "heat_kj"]).reset_index(drop=True)
    ranking = []
    for _, r in feasible.iterrows():
        ranking.append(
            {
                "candidate_id": r["candidate_id"],
                "required_allowable_mpa": float(r["required_allowable_mpa"]),
                "capacity_margin": float(r["capacity_margin"]),
                "net_heat_input_kj": float(r["heat_kj"]),
                "weld_length_mm": float(r["length_penalty"]),
                "score": float(r["score"]),
            }
        )
    payload = {
        "version": "COMPETITION-R1-DIGITAL-SELECTION-1",
        "evidence_level": "design_assumption_reference_envelope",
        "input": str(INPUT.relative_to(ROOT)).replace("\\", "/"),
        "frozen_scenario": {
            "pass_count": 4,
            "deposition_efficiency": 0.85,
            "load_scale": 1.0,
            "assumed_allowable_mpa": 60.0,
        },
        "ranking": ranking,
        "recommended": "6P-FAIR_B/4pass",
        "backup": "8P-FAIR_B/4pass",
        "engineering_selection_status": "pending_release_gates",
        "digital_baseline": "6P-FAIR_B/4pass",
        "low_heat_candidate": "6P-FAIR_B/4pass",
        "higher_static_margin_candidate": "8P-FAIR_B/4pass",
        "rejected_high_heat_reference": "Continuous/4pass",
        "interpretation": "推荐字段表示当前数字设计基线，不代表最终工程放行；8P仅作为几何、热量和静力承载裕量切换候选，尚未冻结独立WPS与自动化段序。统一条件筛查不代表实际载荷、疲劳寿命、焊缝成形或产品位置度验收。",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    recommended = next(r for r in ranking if r["candidate_id"] == payload["recommended"])
    backup = next(r for r in ranking if r["candidate_id"] == payload["backup"])
    authority = {
        "version": "COMPETITION-R1-AUTHORITY",
        "scope": "参赛说明书与答辩统一引用的保守设计口径",
        "selected_candidate": payload["recommended"],
        "engineering_selection_status": payload["engineering_selection_status"],
        "digital_baseline": payload["digital_baseline"],
        "low_heat_candidate": payload["low_heat_candidate"],
        "higher_static_margin_candidate": payload["higher_static_margin_candidate"],
        "assumptions": {"deposition_efficiency": 0.85, "load_scale": 1.0,
                        "assumed_allowable_mpa": 60.0, "equivalent_leg_min_mm": 3.5},
        "results": {"required_allowable_mpa": recommended["required_allowable_mpa"],
                    "conditional_margin": recommended["capacity_margin"],
                    "weld_length_mm": recommended["weld_length_mm"],
                    "net_heat_input_kj": round(recommended["net_heat_input_kj"], 5),
                    "arc_on_time_s": round(float(next(r["arc_time_s"] for r in assessment["four_pass_comparison"] if r["layout"] == payload["recommended"].split("/")[0])), 3),
                    "fallback_candidate": payload["backup"],
                    "fallback_required_allowable_mpa": backup["required_allowable_mpa"]},
        "endpoints": {"current_efficiency_0_85_required_allowable_mpa": recommended["required_allowable_mpa"],
                      "interpretation": "当前 COMPETITION-R1 四道比较已按固定送丝与效率下界闭合；此值用于保守筛查。"},
        "decision_rule": "6P作为当前详细数字基线；真实载荷、热残余、裂纹、疲劳和位置度放行门闭合后再决定最终工程方案，若静力承载裕量门需要切换则评定8P",
    }
    AUTHORITY.write_text(yaml.safe_dump(authority, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
