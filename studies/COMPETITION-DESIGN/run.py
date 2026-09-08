"""重建参赛修订计算和名义装配实体，校验失败时禁止生成可用结果。"""
from pathlib import Path
import csv
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from hanjie.domain.competition_design import run_design
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone

ROOT = Path(__file__).resolve().parents[2]


def main():
    result, bodies, _ = run_design(ROOT)
    g = result["geometry"]
    checks = [all(g["shape_validity"].values()), g["bottom_route_allowed"],
              all(row["clear"] for row in g["poses"]), g["torch_feed_intersection_mm3"] < 1e-6,
              g["torch_feed_clearance_mm"] >= 1.5,
              max(g["cartridge_intersections_mm3"].values()) < 1e-6,
              result["precision"]["design_budget_closes"]]
    if not all(checks):
        raise ValueError("参赛设计内部检查未通过："+json.dumps(result, ensure_ascii=False))
    out = ROOT / "studies/COMPETITION-DESIGN/results"
    cad = ROOT / "cad/generated/competition-design"
    out.mkdir(parents=True, exist_ok=True)
    cad.mkdir(parents=True, exist_ok=True)
    writer = STEPControl_Writer()
    for shape in bodies.values():
        if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
            raise ValueError("STEP转换失败")
    if writer.Write(str(cad / "competition-assembly.step")) != IFSelect_RetDone:
        raise ValueError("STEP写入失败")
    (out / "assessment.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "result.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["category", "metric", "value"])
        for category in ("process", "precision", "fixture"):
            for key, value in result[category].items():
                if isinstance(value, (float, int, bool)):
                    writer.writerow([category, key, value])
    print(json.dumps({"process":result["process"], "precision":result["precision"],
                      "torch_feed_gap_mm":g["torch_feed_clearance_mm"],"checks":checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
