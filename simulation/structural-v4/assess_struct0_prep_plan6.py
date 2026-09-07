"""汇总 Plan 6 扫掠网格与结构执行链彩排准入。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "simulation/structural-v4/results/struct0-prep"


def _load(name):
    return json.loads((OUTPUT / name).read_text(encoding="utf-8"))


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    mesh = _load("continuous-swept-plan6-admitted.json")
    rehearsal = _load("struct0-prep-dress-rehearsal-plan6.json")
    sources = [
        Path(__file__),
        ROOT / "simulation/structural-v4/build_continuous_swept_mesh.py",
        ROOT / "simulation/structural-v4/run_struct0_prep_dress_rehearsal.py",
        ROOT / "src/hanjie/simulation/nonlinear_fem.py",
        OUTPUT / "continuous-swept-plan6-admitted.json",
        OUTPUT / "struct0-prep-dress-rehearsal-plan6.json",
    ]
    passed = bool(mesh["mesh_acceptance_pass"] and rehearsal["dress_rehearsal_pass"])
    result = {
        "stage": "STRUCT-0-PREP-PLAN6", "evidence_level": "executed_swept_mesh_and_synthetic_sector_rehearsal",
        "mesh_quality": {"nodes": mesh["counts"]["nodes"], "tetrahedra": mesh["counts"]["tetrahedra"], "minimum_sicn": mesh["quality"]["minimum"], "below_0p1_count": mesh["quality"]["below_0p1_count"], "weld_below_0p1_count": mesh["regions"]["quality_by_region"]["ERNIFE_CI_WELD"]["below_0p1_count"]},
        "dress_rehearsal": {"maximum_newton_iterations": rehearsal["maximum_newton_iterations"], "maximum_force_balance_error_n": rehearsal["maximum_force_balance_error_n"], "maximum_moment_balance_error_n_mm": rehearsal["maximum_moment_balance_error_n_mm"], "maximum_penetration_mm": max((row["contact"]["maximum_penetration_mm"] for row in rehearsal["steps"] if row["contact"]), default=0.0), "release_displacement_mm": rehearsal["release_displacement_mm"], "synthetic_pfep_fe_mm": rehearsal["bore_axis_fit"]["pfep_fe_mm"], "engineering_meaning": "none"},
        "checks": {"swept_mesh_quality": mesh["mesh_acceptance_pass"], "synthetic_state_flow": rehearsal["dress_rehearsal_pass"], "formal_thermal_history_absent": True},
        "struct0_prep_status": "ready_pending_admitted_thermal_history" if passed else "not_ready",
        "formal_struct_0_allowed": False,
        "hashes": {path.relative_to(ROOT).as_posix(): _digest(path) for path in sources},
        "limitations": rehearsal["limitations"],
    }
    (OUTPUT / "struct0-prep-plan6-assessment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": result["struct0_prep_status"], "formal_struct_0_allowed": False, **result["mesh_quality"], **result["dress_rehearsal"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
