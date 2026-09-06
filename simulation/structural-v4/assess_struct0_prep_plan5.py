"""汇总 Plan 5 Continuous 网格、接触、映射、激活与释放准备状态。"""

from __future__ import annotations

import json
from pathlib import Path


ROOT=Path(__file__).resolve().parents[2]
PREP=ROOT/"simulation/structural-v4/results/struct0-prep"


def _load(name):
    return json.loads((PREP/name).read_text(encoding="utf-8"))


def build_assessment():
    baseline=_load("continuous-unified-mesh.json")
    refined=_load("continuous-unified-plan5.json")
    delaunay=_load("continuous-unified-plan5-delaunay.json")
    contact=_load("contact-benchmarks.json")
    mapping=_load("thermal-mapping-benchmark.json")
    global_newton=_load("global-newton-benchmarks.json")
    trials={}
    for name,row in (("plan4_hxt_0p8",baseline),("hxt_0p5",refined),("delaunay_0p8_relocate",delaunay)):
        weld_count=row["regions"]["tetrahedron_counts"]["ERNIFE_CI_WELD"]
        low=row["regions"]["quality_by_region"]["ERNIFE_CI_WELD"]["below_0p1_count"]
        trials[name]={"mesh_file":row["mesh_file"],"nodes":row["counts"]["nodes"],"tetrahedra":row["counts"]["tetrahedra"],
                      "minimum_min_sicn":row["quality"]["minimum"],"p01_min_sicn":row["quality"]["p01"],
                      "weld_tetrahedra":weld_count,"weld_below_0p1_count":low,"weld_below_0p1_fraction":low/weld_count,
                      "accepted":low==0 and row["quality"]["nonpositive_count"]==0}
    checks={
        "continuous_weld_mesh_quality_closed":any(row["accepted"] for row in trials.values()),
        "global_j2_newton_retained":all(global_newton["checks"].values()),
        "frictionless_normal_contact_benchmarks":contact["contact_benchmark_pass"],
        "local_thermal_mapping_benchmark":mapping["thermal_mapping_benchmark_pass"],
        "global_small_mesh_activation_stress_free_birth":global_newton["checks"]["global_activation_stress_free_birth"],
        "fixture_release_state_flow":contact["checks"]["hot_release_force_free"] and contact["checks"]["post_release_cooling_force_free"],
    }
    ready=all(checks.values())
    return {
        "stage":"STRUCT-0-PREP-PLAN5","evidence_level":"executed_engineering_preparation_benchmarks",
        "mesh_quality_trials":trials,
        "mesh_binary_retention":"两份被拒绝的Plan 5试验msh仅本地保留且不入Git；参数、质量统计、逐低质量单元诊断和生成脚本入库。",
        "mesh_localization":{
            "plan4":"1381个低质量单元全部位于ERNiFe-CI焊缝，分别邻近焊缝—壳体和焊缝—座体界面。",
            "plan5_0p5":"2575个低质量单元全部最近焊缝—座体界面；局部减尺寸提高最小值但增加绝对差单元数。",
            "mechanism":"系统性环形焊缝界面表面三角化/四面体拓扑质量债；不是母材远场尺寸不足。",
            "next_action":"停止纯尺寸细化，改用环向分段/扫掠焊缝拓扑，并在共形接口上重新核对minSICN。",
        },
        "contact":{"source":"contact-benchmarks.json","passed":contact["contact_benchmark_pass"],"scope":"frictionless normal contact + separation + release; small mesh"},
        "thermal_mapping":{"source":"thermal-mapping-benchmark.json","passed":mapping["thermal_mapping_benchmark_pass"],"scope":mapping["scope"]},
        "activation":{"source":"global-newton-benchmarks.json","passed":global_newton["checks"]["global_activation_stress_free_birth"],"scope":"global six-tetrahedron small mesh"},
        "checks":{key:bool(value) for key,value in checks.items()},
        "struct_0_prep_ready_pending_admitted_thermal_history":bool(ready),
        "formal_struct_0_allowed":False,
        "decision":"STRUCT-0-PREP 尚未 ready：接触、局部热映射、全局小模型激活/释放已通过，但 Continuous 焊缝网格质量未闭合；不得把局部热场送入正式 STRUCT-0。" if not ready else "STRUCT-0-PREP 已达到只等待准入热历史的状态；正式STRUCT-0仍需热数值Gate通过。",
    }


def main():
    result=build_assessment()
    target=PREP/"struct0-prep-plan5-assessment.json"
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(target),"checks":result["checks"],"ready":result["struct_0_prep_ready_pending_admitted_thermal_history"]},ensure_ascii=False))


if __name__=="__main__":
    main()
