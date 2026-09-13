"""生成竞赛候选方案的统一数字选择结果。

本脚本只使用已经登记的固定送丝、条件承载和净热输入结果，不把未校准
热场或合成位置度当成产品验收。目的是真正冻结一个可复核的推荐方案，
避免报告只凭文字选择 6P。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "studies/ROUTE-B-DESIGN/results/result.csv"
OUTPUT = ROOT / "studies/COMPETITION-DESIGN/results/robust-selection.json"


def main() -> None:
    df = pd.read_csv(INPUT)
    # 以四道、效率下界、单位载荷尺度和 60 MPa 设计筛查值作为统一决策层。
    view = df[
        (df["deposition_efficiency"] == 0.85)
        & (df["load_scale"] == 1.0)
        & (df["assumed_allowable_mpa"] == 60.0)
        & (df["candidate_id"].str.endswith("/4pass"))
    ].copy()
    view["heat_kj"] = view["net_heat_input_j"] / 1000.0
    view["capacity_margin"] = 60.0 / view["required_allowable_mpa"]
    view["length_penalty"] = view["candidate_id"].map(
        {"Continuous/4pass": 471.1132343323254, "6P-FAIR_B/4pass": 108.0, "8P-FAIR_B/4pass": 144.0}
    )
    # 只在满足条件承载筛查的方案中比较热输入和焊缝长度；分数是排序工具，
    # 不是概率，也不替代热—结构正式求解。
    feasible = view[view["conditional_capacity_screen_pass"]].copy()
    feasible["score"] = (
        0.60 * feasible["heat_kj"] / feasible["heat_kj"].max()
        + 0.25 * feasible["length_penalty"] / feasible["length_penalty"].max()
        + 0.15 / feasible["capacity_margin"]
    )
    feasible = feasible.sort_values(["score", "heat_kj"]).reset_index(drop=True)
    rows = []
    for _, r in feasible.iterrows():
        rows.append(
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
        "ranking": rows,
        "recommended": "6P-FAIR_B/4pass",
        "backup": "8P-FAIR_B/4pass",
        "rejected_high_heat_reference": "Continuous/4pass",
        "interpretation": "统一条件筛查下的工程排序；不代表实际载荷、疲劳寿命、焊缝成形或产品位置度验收。",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
