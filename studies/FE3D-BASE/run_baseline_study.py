"""FE3D-BASE 3D 基线网格收敛验证研究脚本。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hanjie.simulation.fe3d import run_mesh_convergence_study


def main() -> int:
    print("=" * 70)
    print("运行 FE3D-BASE 3D 热—弹塑性基线网格收敛验证 (Gate B.1)...")
    print("=" * 70)

    study = run_mesh_convergence_study(structure_type="continuous")

    coarse = study["coarse"]
    med = study["medium"]
    fine = study["fine"]
    p_change = study["p_change_fine_vs_med_pct"]
    stress_change = study["stress_change_pct"]
    temp_change = study["temp_change_pct"]
    passed = study["gate_b1_passed"]

    print(f"{'网格':<8}{'节点数':<10}{'单元数':<10}{'峰值温度(°C)':<14}{'最大等效应力(MPa)':<18}{'位置度 P (mm)':<14}")
    print("-" * 74)
    print(f"{'G51(粗)':<8}{coarse.num_nodes:<10}{coarse.num_elements:<10}{coarse.t_peak_c:<14.1f}{coarse.max_stress_mpa:<18.1f}{coarse.position_metric_p_mm:<14.5f}")
    print(f"{'G61(中)':<8}{med.num_nodes:<10}{med.num_elements:<10}{med.t_peak_c:<14.1f}{med.max_stress_mpa:<18.1f}{med.position_metric_p_mm:<14.5f}")
    print(f"{'G71(细)':<8}{fine.num_nodes:<10}{fine.num_elements:<10}{fine.t_peak_c:<14.1f}{fine.max_stress_mpa:<18.1f}{fine.position_metric_p_mm:<14.5f}")
    print("-" * 74)
    print(f"位置度变化率 |P_fine - P_med| / P_fine: {p_change:.2f}% (标准: <5.0%)")
    print(f"峰值温度变化率: {temp_change:.2f}% (标准: <10.0%)")
    print(f"应力变化率: {stress_change:.2f}% (标准: <15.0%)")
    print(f"Gate B.1 网格收敛判定结果: {'【通过 (PASSED)】' if passed else '【未通过 (FAILED)】'}")

    out_dir = ROOT / "studies" / "FE3D-BASE" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "model": "FE3D-BASE",
        "structure": "continuous",
        "gate_b1_passed": passed,
        "p_change_pct": p_change,
        "stress_change_pct": stress_change,
        "temp_change_pct": temp_change,
        "fine_position_metric_p_mm": fine.position_metric_p_mm,
        "fine_peak_temp_c": fine.t_peak_c,
        "fine_max_stress_mpa": fine.max_stress_mpa,
    }
    (out_dir / "convergence_summary.json").write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
    print(f"收敛报告已输出至: {out_dir / 'convergence_summary.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
