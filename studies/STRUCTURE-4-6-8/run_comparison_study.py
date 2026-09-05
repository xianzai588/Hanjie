"""STRUCTURE-4-6-8 结构多方案严格公平对比研究。

保持同热输入、同网格标准、同预热与夹具释放条件，
公平对比连续环形、4点、6点、8点开槽结构的变形控制与残余应力特性。
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hanjie.simulation.fe3d import run_structure_fair_comparison


def main() -> int:
    print("=" * 85)
    print("运行 STRUCTURE-4-6-8 结构标签代理对比（未通过 FAIR-A/B） (连续 vs 4点 vs 6点 vs 8点)...")
    print("=" * 85)

    results = run_structure_fair_comparison()

    print(f"{'结构方案':<16}{'焊段数':<8}{'总焊长(mm)':<12}{'峰值温度(°C)':<14}{'最大残余应力(MPa)':<18}{'位置度 P (mm)':<14}")
    print("-" * 82)

    rows = []
    weld_lengths = {"continuous": 471.1, "4_point": 72.0, "6_point": 108.0, "8_point": 144.0}
    num_pts = {"continuous": "连续", "4_point": 4, "6_point": 6, "8_point": 8}

    for res in results:
        wl = weld_lengths[res.structure_type]
        np_str = str(num_pts[res.structure_type])
        print(f"{res.structure_type:<16}{np_str:<8}{wl:<12.1f}{res.t_peak_c:<14.1f}{res.max_stress_mpa:<18.1f}{res.position_metric_p_mm:<14.5f}")
        rows.append({
            "structure_type": res.structure_type,
            "points": np_str,
            "total_weld_length_mm": wl,
            "t_peak_c": res.t_peak_c,
            "max_stress_mpa": res.max_stress_mpa,
            "position_metric_p_mm": res.position_metric_p_mm,
            "meets_p005_limit": bool(res.position_metric_p_mm <= 0.05),
        })

    print("-" * 82)
    best = min(rows, key=lambda row: row["position_metric_p_mm"])
    print(f"代理公式下位置度最低：{best['structure_type']}，P={best['position_metric_p_mm']:.5f} mm")
    print("结构选型 unresolved；未建立真实拓扑或完成 FAIR-A/B，无疲劳承载证据。")

    out_dir = ROOT / "studies" / "STRUCTURE-4-6-8" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "structure_comparison_summary.json").write_text(
        json.dumps({"evidence_level": "surrogate_result", "selection_status": "unresolved", "fair_ab_verified": False, "comparison": rows}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n对比报告已输出至: {out_dir / 'structure_comparison_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
