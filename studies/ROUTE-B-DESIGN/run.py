"""运行有限候选条件筛查，保存输入快照、明细和选型结果。"""

import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hanjie.domain.route_b_design import SPEC, build_design_study, read_data


def main() -> None:
    result = build_design_study(ROOT)
    output = Path(__file__).resolve().parent / "results"
    output.mkdir(parents=True, exist_ok=True)
    cases = result.pop("cases")
    with (output / "result.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    # 保存实际消费的结构化输入，避免日后把新版参数误认成本轮条件。
    inputs = {SPEC: read_data(ROOT / SPEC)}
    inputs.update({path: read_data(ROOT / path) for path in result["input_sources"].values()})
    inputs.update({row["geometry_source"]: read_data(ROOT / row["geometry_source"]) for row in result["candidates"]})
    (output / "run-inputs.json").write_text(json.dumps(inputs, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "assessment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已完成 {result['candidate_count']} 候选、{result['case_count']} 组合；结果：{output}")
    for row in result["decisions"]:
        print(row["load_scale"], row["assumed_allowable_mpa"], row["selected_for_further_study"])


if __name__ == "__main__":
    main()
