"""运行 Plan 5 严格嵌套局部空间离散序列。"""

from __future__ import annotations

import argparse
from pathlib import Path

from run_credibility04r import ROOT,load,run_case


SPEC=ROOT/"project/thermal-nested-refinement-v5.6.yaml"
OUTPUT=ROOT/"simulation/thermal-v5/results/nested-refinement-study"


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",default="all")
    parser.add_argument("--output-dir",type=Path,default=OUTPUT)
    args=parser.parse_args()
    plan=load(SPEC)
    selected=[case for case in plan["cases"] if args.case in ("all",case["name"])]
    if not selected:
        parser.error("未知工况名称")
    for case in selected:
        print(case,flush=True)
        run_case(plan,case,args.output_dir/case["name"],SPEC)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
