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

# 交付文档里硬编码的页数声明必须与 manifest 实际计数一致，防止口径漂移再次发生。
PAGE_CLAIM_DOCS = [
    "deliverables/submission/10-复现与版本冻结记录.md",
    "deliverables/submission-checklist.md",
    "deliverables/registration-description.md",
    "deliverables/report/technical-report-v4-unified.md",
    "deliverables/report/generated/current-status.md",
    "deliverables/submission/提交说明.txt",
]
_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
PAGE_CLAIM_RULES = [
    (re.compile(r"当前版本为(\d+)页与(\d+)页"), "pair"),          # 冻结记录：说明书页、图集页
    (re.compile(r"(\d+)\s*页说明书[、,，]\s*(\d+)\s*页设计图"), "pair"),
    (re.compile(r"说明书(\d+)页[，,]\s*设计图(\d+)页"), "pair"),   # 提交说明.txt
    (re.compile(r"([一二三四五六七八九十]{1,3})\s*页设计图集"), "drawing"),
    (re.compile(r"([一二三四五六七八九十]{1,3})\s*页图纸"), "drawing"),
    (re.compile(r"([一二三四五六七八九十]{1,3})\s*页图集"), "drawing"),
    (re.compile(r"导出图集共(\d+)\s*页"), "drawing"),
]


def parse_count(token: str) -> int:
    """把阿拉伯数字或 1~99 的简单中文数字解析为整数。"""
    if token.isdigit():
        return int(token)
    head, sep, tail = token.partition("十")
    if not sep:
        if len(token) != 1 or token not in _CN_DIGITS:
            raise ValueError(f"无法解析页数: {token}")
        return _CN_DIGITS[token]
    return (_CN_DIGITS.get(head, 1) if head else 1) * 10 + (_CN_DIGITS.get(tail, 0) if tail else 0)


def scan_page_claims(label: str, text: str, actual: dict) -> list[str]:
    """在单份文本中查找页数声明，返回与实际计数不符的条目。"""
    errors: list[str] = []
    for pattern, kind in PAGE_CLAIM_RULES:
        for match in pattern.finditer(text):
            claimed = [parse_count(g) for g in match.groups()]
            pairs = (list(zip(claimed, ("report", "drawing"))) if kind == "pair"
                     else [(claimed[0], "drawing")])
            for value, key in pairs:
                if value != actual[key]:
                    errors.append(f"页数口径漂移: {label} 写“{match.group(0)}”，实际"
                                  f"{'说明书' if key == 'report' else '图集'}为{actual[key]}页")
    return errors


def check_page_claims(manifest: dict) -> list[str]:
    """校验文档中声明的说明书/图集页数是否等于 manifest 的实际计数。"""
    actual = {"report": manifest["report_pages"], "drawing": manifest["drawing_pages"]}
    texts: list[tuple[str, str]] = []
    for rel in PAGE_CLAIM_DOCS:
        path = ROOT / rel
        if path.exists():
            texts.append((rel, path.read_text(encoding="utf-8")))
    with pymupdf.open(SUB / "01-工艺设计说明书.pdf") as pdf:
        texts.append(("01-工艺设计说明书.pdf", "\n".join(page.get_text() for page in pdf)))
    errors: list[str] = []
    for label, text in texts:
        errors.extend(scan_page_claims(label, text, actual))
    return errors


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
    errors.extend(check_page_claims(manifest))
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
