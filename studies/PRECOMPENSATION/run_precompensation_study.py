"""PRECOMPENSATION 逆向位姿补偿与经验减法对照研究。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hanjie.control.inverse_precompensation import InversePrecompensationSolver


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 85)
    print("运行 PRECOMPENSATION 逆向位姿补偿三组对照研究 (200 次蒙特卡洛抽样)...")
    print("=" * 85)

    solver = InversePrecompensationSolver()
    bench = solver.evaluate_benchmark(num_trials=200)

    print(f"{'补偿方案':<24}{'均值误差(mm)':<16}{'P95 误差(mm)':<16}{'最大误差(mm)':<16}{'超差越界率(%)':<14}{'Ø0.05 合格率(%)':<16}")
    print("-" * 102)

    rows = []
    for key, res in bench.items():
        print(f"{res.method_name:<24}{res.nominal_position_error_mm:<16.5f}{res.p95_position_error_mm:<16.5f}{res.max_position_error_mm:<16.5f}{res.boundary_violation_rate_pct:<14.1f}{res.pass_p005_rate_pct:<16.1f}")
        rows.append({
            "key": key,
            "method_name": res.method_name,
            "mean_error_mm": res.nominal_position_error_mm,
            "p95_error_mm": res.p95_position_error_mm,
            "max_error_mm": res.max_position_error_mm,
            "boundary_violation_rate_pct": res.boundary_violation_rate_pct,
            "pass_p005_rate_pct": res.pass_p005_rate_pct,
        })

    print("-" * 102)
    print("结果仅供代理/合成演示；不支持六点最优、疲劳承载或实物补偿达标结论。")

    out_dir = ROOT / "studies" / "PRECOMPENSATION" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "precompensation_summary.json").write_text(
        json.dumps({"evidence_level": "synthetic_demo", "validation_status": "unvalidated", "benchmark": rows}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n对照研究数据已保存至: {out_dir / 'precompensation_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
