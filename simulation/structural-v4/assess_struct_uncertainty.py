"""以成对情景和C/M变化裁决敏感性排序；不授予正式焊接预测资格。"""
from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from run_struct_uncertainty import OUTPUT, SPEC, ref

VALUE = "position_sensitivity_diameter_mm"
KEYS = ["thermal_source", "material_scenario", "restraint_pattern", "foundation_n_mm3"]


def compare_pair(a, b, span_a, span_b, tolerance):
    # 两候选各自的网格变化同时计入；这是经验分辨尺度，不是假定的误差上界。
    margin = tolerance + span_a + span_b
    return np.where(a-b < -margin, -1, np.where(a-b > margin, 1, 0))


def assess(out):
    cfg = ref.load(SPEC)
    data = pd.read_csv(out/"cases.csv")
    expected = len(cfg["candidates"])*len(cfg["meshes"])*2*len(cfg["material_scenarios"])*len(cfg["restraint_patterns"])*len(cfg["foundation_stiffness_n_mm3"])
    if len(data) != expected or data.duplicated(KEYS+["candidate", "resolution"]).any():
        raise ValueError("结构成对情景不完整或存在重复")
    if data.formal_welding_residual_prediction.any() or not np.isfinite(data[VALUE]).all():
        raise ValueError("非正式证据标签或结果无效")
    grids = {r: data[data.resolution == r].pivot(index=KEYS, columns="candidate", values=VALUE) for r in cfg["meshes"]}
    coarse, medium = grids["coarse"], grids["medium"]
    span = abs(medium-coarse)
    pairs = []; paired_rows = []
    tol = cfg["metrology"]["ranking_tie_tolerance_mm"]
    for a,b in itertools.combinations(cfg["candidates"],2):
        direction = compare_pair(medium[a],medium[b],span[a],span[b],tol)
        pairs.append(dict(a=a,b=b,a_lower=int(sum(direction == -1)),b_lower=int(sum(direction == 1)),unresolved=int(sum(direction == 0)),
                          signed_a_minus_b_min_mm=float((medium[a]-medium[b]).min()),signed_a_minus_b_max_mm=float((medium[a]-medium[b]).max()),
                          all_scenarios_resolved_same_direction=bool(np.all(direction == -1) or np.all(direction == 1))))
        for i,key in enumerate(medium.index):
            paired_rows.append(dict(zip(KEYS,key),a=a,b=b,signed_a_minus_b_mm=float(medium.loc[key,a]-medium.loc[key,b]),
                                    resolution_scale_mm=float(tol+span.loc[key,a]+span.loc[key,b]),order=int(direction[i])))
    pd.DataFrame(paired_rows).to_csv(out/"paired-rankings.csv",index=False)
    span.to_csv(out/"mesh-span.csv")
    cross = data[data.resolution == "medium"].pivot(index=["candidate",*KEYS[1:]], columns="thermal_source",values=VALUE)
    envelopes = []
    for candidate in cfg["candidates"]:
        for source in ("fvm","elmer"):
            subset = data[(data.candidate == candidate)&(data.thermal_source == source)]
            envelopes.append(dict(candidate=candidate,source=source,minimum_mm=float(subset[VALUE].min()),maximum_mm=float(subset[VALUE].max()),
                                  maximum_c_m_span_mm=float(span.xs(source,level="thermal_source")[candidate].max())))
    pd.DataFrame(envelopes).to_csv(out/"sensitivity-envelopes.csv",index=False)
    checks = ref.load(out/"material-point-checks.json")
    winners = [candidate for candidate in cfg["candidates"] if all(
        (p["a_lower"] == len(medium) if p["a"] == candidate else p["b_lower"] == len(medium))
        for p in pairs if candidate in (p["a"],p["b"]))]
    result = dict(stage="STRUCT-UNCERTAINTY",route="B_no_physical_experiment",cases_executed=len(data),paired_scenarios=len(medium),
                  method=cfg["method"],evidence_level="solver_disagreement_physical_unvalidated",formal=False,
                  execution_checks_passed=bool(checks["passed"] and data.relative_linear_residual.max() < cfg["checks"]["relative_linear_residual_limit"]),
                  maximum_linear_residual=float(data.relative_linear_residual.max()),maximum_c_m_span_mm=float(span.to_numpy().max()),
                  maximum_paired_thermal_source_change_mm=float(abs(cross.fvm-cross.elmer).max()),
                  pairs=pairs,envelopes=envelopes,robust_winners=winners,robust_candidate_ranking_established=bool(winners),
                  acceptance_result="no_resolved_robust_winner" if not winners else "conditional_sensitivity_winner_only",
                  interval_kind=cfg["uncertainty_kind"],rank_resolution="0.001 mm plus each candidate's observed C/M change; not a rigorous error bound",
                  limitations=cfg["limitations"],thermal_1_allowed=False,formal_struct_0_allowed=False,
                  physical_validation=False,experimental_data_required=False,product_position_acceptance_claim_allowed=False,
                  next_action="Retain all three candidates. Quantify candidate-scale thermal transfer and fixture assumptions within digital structural research; do not reopen local thermal tuning or infer product acceptance.")
    ref.write_json(out/"assessment.json",result)
    print({k:result[k] for k in ("cases_executed","maximum_c_m_span_mm","maximum_paired_thermal_source_change_mm","robust_winners")})
    print(pairs)
    return result


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=OUTPUT)
    assess(parser.parse_args().output_dir)
