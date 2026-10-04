"""生成竞赛候选方案的统一数字选择结果。

本脚本只使用已经登记的固定送丝、条件承载和净热输入结果，不把未校准
热场或合成位置度当成产品验收。目的是真正冻结一个可复核的推荐方案，
避免报告只凭文字选择 8P。
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
    # 直接读取当前 COMPETITION-R4 的两道比较，避免旧 Route-B 参数链回流。
    view = pd.DataFrame(assessment["four_pass_comparison"])
    view = view.rename(columns={"layout": "candidate_id", "net_heat_kj": "heat_kj"})
    view["candidate_id"] = view["candidate_id"] + "/2pass"
    view["capacity_margin"] = 60.0 / view["required_allowable_mpa"]
    engineering = json.loads((INPUT.parent / "engineering-checks-r3.json").read_text(encoding="utf-8"))
    damage = {r["layout"] + "/2pass": r["miner_damage"] for r in engineering["layout_checks"]}
    view["design_spectrum_damage"] = view["candidate_id"].map(damage)
    view["length_penalty"] = view["candidate_id"].map(
        {"Continuous/2pass": 471.1132343323254, "6P-FAIR_B/2pass": 108.0, "8P-FAIR_B/2pass": 144.0}
    )
    # 只在满足条件承载筛查的方案中比较热输入和焊缝长度；分数是排序工具，
    # 不是概率，也不替代热—结构正式求解。
    # four_pass_comparison 已由当前设计计算的同一条件筛查生成。
    feasible = view[(view["capacity_margin"] >= 1) & (view["design_spectrum_damage"] <= 1)].copy()
    if feasible.empty:
        raise ValueError("当前设计载荷谱和资格目标曲线下无候选满足筛查条件；须重新设计")
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
                "design_spectrum_damage": float(r["design_spectrum_damage"]),
            }
        )
    payload = {
        "version": "COMPETITION-R4-DIGITAL-SELECTION-1",
        "evidence_level": "design_assumption_reference_envelope",
        "input": str(INPUT.relative_to(ROOT)).replace("\\", "/"),
        "frozen_scenario": {
            "pass_count": 2,
            "deposition_efficiency": 0.90,
            "load_scale": 1.0,
            "assumed_allowable_mpa": 60.0,
        },
        "ranking": ranking,
        "recommended": ranking[0]["candidate_id"],
        "comparison_candidates": ["6P-FAIR_B/2pass", "Continuous/2pass"],
        "screening_conditions": "60 MPa static design allowable; Miner <=1 under the common assumed spectrum and 30 MPa qualification target curve; heat and length break ties; physical qualification follows separately",
        "interpretation": "统一条件筛查下的工程排序；8P结合控形、疲劳资格目标和洁净执行性作为当前推荐，分数不替代整件热-结构结果。",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    recommended = next(r for r in ranking if r["candidate_id"] == payload["recommended"])
    comparison = next(r for r in assessment["four_pass_comparison"] if r["layout"] == "6P-FAIR_B")
    authority = {
        "version": "COMPETITION-R4-AUTHORITY",
        "scope": "固定题焊接设计说明书与答辩统一引用的当前冻结口径",
        "selected_candidate": payload["recommended"],
        "selected_geometry": assessment["spec"]["layout"],
        "geometry_basis": "15 mm座体＋32处合并后真实R2过渡；FAIR_B为名义焊缝组比较布局，实际整件静载另由service-verification给出",
        "assumptions": {"deposition_efficiency": 0.90, "load_scale": 1.0,
                        "assumed_allowable_mpa": 60.0, "equivalent_leg_min_mm": 3.5},
        "results": {"required_allowable_mpa": recommended["required_allowable_mpa"],
                    "conditional_margin": recommended["capacity_margin"],
                    "weld_length_mm": recommended["weld_length_mm"],
                    "net_heat_input_kj": round(recommended["net_heat_input_kj"], 5),
                    "arc_on_time_s": round(float(next(r["arc_time_s"] for r in assessment["four_pass_comparison"] if r["layout"] == payload["recommended"].split("/")[0])), 3),
                    "comparison_candidate": "6P-FAIR_B/2pass",
                    "comparison_required_allowable_mpa": comparison["required_allowable_mpa"]},
        "endpoints": {"current_efficiency_0_90_required_allowable_mpa": recommended["required_allowable_mpa"],
                      "interpretation": "当前 COMPETITION-R4 两道比较按固定送丝与效率窗口闭合；此值用于条件承载筛查。"},
        "decision_rule": "8P两道为综合设计推荐；6P和连续焊为同条件布局比较。若热残余、熔合、裂纹或疲劳评定不合格，重新设计对应工艺，不自动切换至承载更弱的6P。",
    }
    AUTHORITY.write_text(yaml.safe_dump(authority, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
