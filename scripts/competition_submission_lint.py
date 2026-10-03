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
# 清单条目数声明与页数同属会随批次过期的计数（RC4 轮曾长期写「19 文件」而 manifest 实为 22 项）。
COUNT_CLAIM_RULES = [
    re.compile(r"清单\s*(\d+)\s*项"),
    re.compile(r"(\d+)\s*文件"),
]
# 标注为既往批次快照的行记录的是当轮计数，不参与当前 manifest 比对。
HISTORY_MARKERS = ("当轮", "历史版本", "历史批次")
PAGE_CLAIM_RULES = [
    (re.compile(r"当前版本为(\d+)页与(\d+)页"), "pair"),          # 冻结记录：说明书页、图集页
    (re.compile(r"(\d+)\s*页说明书[、,，]\s*(\d+)\s*页设计图"), "pair"),
    (re.compile(r"说明书(\d+)页[，,、]\s*(?:设计图|图集)(\d+)页"), "pair"),   # 提交说明.txt / 冻结记录
    (re.compile(r"(\d+)\s*页说明书[、,，]\s*(\d+)\s*页图集"), "pair"),
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


def scan_count_claims(label: str, text: str, actual: dict) -> list[str]:
    """逐行查找清单条目数声明；标注为既往批次的行保留当轮计数，不参与比对。"""
    errors: list[str] = []
    for line in text.splitlines():
        if any(marker in line for marker in HISTORY_MARKERS):
            continue
        for pattern in COUNT_CLAIM_RULES:
            for match in pattern.finditer(line):
                claimed = int(match.group(1))
                if claimed != actual["files"]:
                    errors.append(f"清单计数漂移: {label} 写“{match.group(0)}”，实际为"
                                  f"{actual['files']} 项")
    return errors


def check_page_claims(manifest: dict) -> list[str]:
    """校验文档中声明的说明书/图集页数是否等于 manifest 的实际计数。"""
    actual = {"report": manifest["report_pages"], "drawing": manifest["drawing_pages"],
              "files": len(manifest["files"])}
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
        errors.extend(scan_count_claims(label, text, actual))
    return errors


def main() -> None:
    manifest = json.loads((SUB / "manifest.json").read_text(encoding="utf-8"))
    authority = yaml.safe_load((ROOT / "project/competition-authority.yaml").read_text(encoding="utf-8"))
    assessment = json.loads((ROOT / "studies/COMPETITION-DESIGN/results/assessment.json").read_text(encoding="utf-8"))
    design_config = yaml.safe_load((ROOT / "project/competition-design.yaml").read_text(encoding="utf-8"))
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
    # 选择结果必须由硬约束+Pareto生成，禁止回流旧的任意加权 score。
    selection = json.loads((ROOT / "studies/COMPETITION-DESIGN/results/robust-selection.json").read_text(encoding="utf-8"))
    if "score" in selection or any("score" in row for row in selection.get("candidates", [])):
        errors.append("候选选择结果仍包含旧加权 score")
    if sorted(selection.get("pareto_front", [])) != sorted(authority.get("pareto_front", [])):
        errors.append("Pareto前沿未与authority同步")
    if selection.get("digital_baseline") != authority.get("digital_baseline"):
        errors.append("数字基线未与authority同步")
    process = yaml.safe_load((ROOT / "project/process.yaml").read_text(encoding="utf-8"))["process"]["nominal"]
    design = design_config["process"]
    gate = design_config.get("material_qualification_gate", {})
    # 当前工艺源必须与竞赛设计配置一致；历史诊断只允许作为独立附件存在。
    if process["filler_diameter_mm"] != design["wire_diameter_mm"]:
        errors.append("工艺源与竞赛设计的棒径不一致")
    if abs(process["filler_feed_rate_mm_s"] - (assessment["process"]["fixed_feed_mm_s"])) > 1e-9:
        errors.append("工艺源与设计计算的固定送丝速度不一致")
    if process["pass_count"] != design["pass_count"] or process["sequence"] != design["sequence"]:
        errors.append("工艺源与竞赛设计的道数/顺序不一致")
    if abs(process["travel_speed_mm_s"] - 1.5) > 1e-12 or abs(process["current_a"] - 75.0) > 1e-12 or abs(process["voltage_v"] - 12.0) > 1e-12:
        errors.append("当前工艺源电流/电压/焊速不在冻结口径")
    if abs(process["arc_efficiency"] - 0.55) > 1e-12 or abs(process["heat_input_j_per_mm"] - 330.0) > 1e-9:
        errors.append("当前工艺源热效率/净热输入不在冻结口径")
    if gate.get("status") != "blocked_pending_batch_evidence":
        errors.append("QT450-10批次组织证明门未保持阻断")
    if gate.get("standard_grade_family") != "ferritic_to_pearlitic" or gate.get("actual_batch_matrix_status") != "unverified":
        errors.append("QT450-10牌号组织与实际批次组织状态混淆")
    if set(gate.get("blocks", [])) != {"preheat_window_freeze", "pwht_branch_selection", "wps_pqr_release"}:
        errors.append("材料组织门未阻断预热、PWHT与WPS/PQR冻结")
    branches = gate.get("qualification_scenarios", [])
    if {branch.get("id") for branch in branches} != {"I_no_pwht_nife", "II_nife_pwht", "III_nici_pwht"}:
        errors.append("热循环三分支比较表不完整")
    if any(branch.get("approved_for_production") is not False for branch in branches):
        errors.append("文献对照分支不得标记为生产放行")
    if design["wire_diameter_mm"] != 1.6 or process["filler_diameter_mm"] != 1.6:
        errors.append("当前工艺棒径口径异常：必须为 Ø1.6")
    if design["pass_count"] != 4 or process["travel_speed_mm_s"] != 1.5:
        errors.append("道数/焊速未使用冻结工艺口径")
    text_parts = []
    for name in ("06-工艺提案.md", "07-设计参数.yaml", "10-复现与版本冻结记录.md", "提交说明.txt"):
        text_parts.append((SUB / name).read_text(encoding="utf-8"))
    with pymupdf.open(SUB / "01-工艺设计说明书.pdf") as pdf:
        text_parts.extend(page.get_text() for page in pdf)
    text = "\n".join(text_parts)
    for token in ("56.59", "当前Ø1.2", "当前 Ø1.2", "当前工艺为Ø1.2", "当前工艺为 Ø1.2", "产品已达标", "焊缝合格", "制造已释放",
                  "按说明书§9.2放行", "按§9.2放行",
                  "0.77/0.69", "FAT 63～80见 §6.2", "疲劳FAT基线"):
        if token in text:
            errors.append(f"提交包含禁止回流/越级措辞: {token}")
    required_evidence_text = ("material_qualification_gate", "焊根FAT数值", "静力等效喉部筛查值")
    report_text = "\n".join(page.get_text() for page in pymupdf.open(SUB / "01-工艺设计说明书.pdf"))
    for token in required_evidence_text[1:]:
        if token not in report_text:
            errors.append(f"说明书缺少本轮修订边界：{token}")
    if "material_qualification_gate" not in (SUB / "07-设计参数.yaml").read_text(encoding="utf-8"):
        errors.append("提交参数未包含QT450-10材料组织放行门")
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
