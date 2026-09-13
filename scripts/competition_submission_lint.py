"""COMPETITION-R1 提交包质量门：检查权威数字、清单、措辞和压缩包闭合。"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pymupdf
import yaml

ROOT = Path(__file__).resolve().parents[1]
SUB = ROOT / "deliverables/submission"


def main() -> None:
    manifest = json.loads((SUB / "manifest.json").read_text(encoding="utf-8"))
    authority = yaml.safe_load((ROOT / "project/competition-authority.yaml").read_text(encoding="utf-8"))
    assessment = json.loads((ROOT / "studies/COMPETITION-DESIGN/results/assessment.json").read_text(encoding="utf-8"))
    errors: list[str] = []
    files = manifest["files"]
    for name, source in files.items():
        if not (ROOT / source).exists() or not (SUB / name).exists():
            errors.append(f"清单文件缺失: {name} <- {source}")
    if manifest["report_pages"] != len(pymupdf.open(SUB / "01-工艺设计说明书.pdf")):
        errors.append("说明书页数与 manifest 不一致")
    if manifest["drawing_pages"] != len(pymupdf.open(SUB / "02-设计图集.pdf")):
        errors.append("图集页数与 manifest 不一致")
    selected = authority["selected_candidate"]
    selected_row = next(r for r in assessment["four_pass_comparison"] if r["layout"] == selected.split("/")[0])
    if abs(authority["results"]["required_allowable_mpa"] - selected_row["required_allowable_mpa"]) > 1e-9:
        errors.append("authority.required_allowable_mpa 未与 assessment 对齐")
    if abs(authority["results"]["net_heat_input_kj"] - selected_row["net_heat_kj"]) > 1e-6:
        errors.append("authority.net_heat_input_kj 未与 assessment 对齐")
    process = yaml.safe_load((ROOT / "project/process.yaml").read_text(encoding="utf-8"))["process"]["nominal"]
    design = yaml.safe_load((ROOT / "project/competition-design.yaml").read_text(encoding="utf-8"))["process"]
    if design["wire_diameter_mm"] != 1.6 or process["filler_diameter_mm"] != 1.2:
        errors.append("当前工艺棒径口径异常：设计应为 Ø1.6，历史 nominal 不得回流")
    if design["pass_count"] != 4 or process["travel_speed_mm_s"] != 1.5:
        errors.append("道数/焊速未使用冻结工艺口径")
    text_parts = []
    for name in ("06-工艺提案.md", "07-设计参数.yaml", "10-复现与版本冻结记录.md", "提交说明.txt"):
        text_parts.append((SUB / name).read_text(encoding="utf-8"))
    with pymupdf.open(SUB / "01-工艺设计说明书.pdf") as pdf:
        text_parts.extend(page.get_text() for page in pdf)
    text = "\n".join(text_parts)
    for token in ("56.59", "当前Ø1.2", "当前 Ø1.2", "当前工艺为Ø1.2", "当前工艺为 Ø1.2", "产品已达标", "焊缝合格", "制造已释放"):
        if token in text:
            errors.append(f"提交包含禁止回流/越级措辞: {token}")
    archive = ROOT / "deliverables/COMPETITION-R1-技术包.zip"
    if archive.exists():
        expected = set(files) | {"提交说明.txt", "manifest.json"}
        with zipfile.ZipFile(archive) as z:
            actual = set(z.namelist())
        if actual != expected:
            errors.append(f"ZIP显式清单不一致: extra={sorted(actual-expected)}, missing={sorted(expected-actual)}")
    if errors:
        raise SystemExit("\n".join("FAIL: " + e for e in errors))
    print(json.dumps({"status": "PASS", "files": len(files), "report_pages": manifest["report_pages"],
                      "drawing_pages": manifest["drawing_pages"], "selected": selected}, ensure_ascii=False))


if __name__ == "__main__":
    main()
