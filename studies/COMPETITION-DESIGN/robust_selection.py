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
    # 保留全部对照；假定疲劳曲线不作候选淘汰门，也不以任意权重总分决策。
    # 当前几何来自独立工程设计，正式采用仍须完成各项物理与数值检查。
    selected_layout = assessment["spec"]["layout"].split("-")[0]
    selected_candidate = selected_layout + "-FAIR_B/2pass"
    if selected_candidate not in set(view["candidate_id"]):
        raise ValueError("当前实体几何没有对应的同条件布局比较")
    selected_row = view.loc[view["candidate_id"] == selected_candidate].iloc[0]
    if selected_row["capacity_margin"] < 1:
        raise ValueError("当前推荐几何未满足设定静载筛查，须重新设计")
    ranking = []
    for _, r in view.iterrows():
        ranking.append(
            {
                "candidate_id": r["candidate_id"],
                "required_allowable_mpa": float(r["required_allowable_mpa"]),
                "capacity_margin": float(r["capacity_margin"]),
                "net_heat_input_kj": float(r["heat_kj"]),
                "weld_length_mm": float(r["length_penalty"]),
                "design_spectrum_damage": float(r["design_spectrum_damage"]),
                "required_reference_range_mpa_at_2e6": 30 * float(r["design_spectrum_damage"]) ** (1 / 3),
                "static_screening_pass": bool(r["capacity_margin"] >= 1),
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
        "ranking_role": "compatibility field containing all comparison candidates; not a scored ranking",
        "recommended": selected_candidate,
        "comparison_candidates": ["6P-FAIR_B/2pass", "Continuous/2pass"],
        "screening_conditions": "60 MPa is the nominal weld-group design allowable; fatigue calculations report qualification demand under the proposed spectrum and m=3, without eliminating candidates on an assumed 30 MPa curve",
        "decision_requirements": ["released bore axis position and numerical accuracy", "Ni99/QT first interface and final weld metallurgy", "physical cleanliness isolation", "specified assembly static strength", "station time and resources"],
        "recommendation_status": "current engineering recommendation pending complete thermal-tool family",
        "global_optimum_proven": False,
        "interpretation": "8P比6P降低名义焊缝组应力与同谱资格需求；比全周焊降低热量与弧燃。结合柔顺结构、预制冶金与物理洁净控制推荐8P；完整位置度等检查决定最终采用，不以自设疲劳曲线或加权分裁决。",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    recommended = next(r for r in ranking if r["candidate_id"] == payload["recommended"])
    comparison = next(r for r in assessment["four_pass_comparison"] if r["layout"] == "6P-FAIR_B")
    authority = {
        "version": "COMPETITION-R4-AUTHORITY",
        "scope": "固定题焊接设计说明书当前工程推荐；正式工艺冻结须完成R4完整核验",
        "selected_candidate": payload["recommended"],
        "selected_geometry": assessment["spec"]["layout"],
        "recommendation_status": payload["recommendation_status"],
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
        "decision_rule": "8P两道为当前综合推荐，6P为低热对照、全周焊为高承载参考；位置度及数值精度、冶金、洁净、静载和节拍共同决定最终采用。假定S-N曲线只报告资格需求，不单独淘汰候选或证明寿命。",
    }
    AUTHORITY.write_text(yaml.safe_dump(authority, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
