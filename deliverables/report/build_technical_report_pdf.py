"""从唯一 V4.3 Markdown 源和自动证据摘要构建工艺设计说明书 PDF。"""
from __future__ import annotations

from html import escape
from pathlib import Path
import re
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "deliverables/report/technical-report-v4-unified.md"
OUT = ROOT / "output/pdf/technical-report-v4.pdf"
sys.path.insert(0, str(ROOT / "src"))
from hanjie.domain.evidence import validate_evidence_graph
from hanjie.reporting.fonts import register_project_fonts
from hanjie.reporting.current_status import write_status_artifacts
import yaml

REGULAR_FONT = "HanjieCN"
BOLD_FONT = "HanjieCN-Bold"


def inline(text: str) -> str:
    # ReportLab 不解析 LaTeX；将本报告使用的有限命令显式转为可读 Unicode。
    text = text.replace("✅", "[记录]").replace("⚠️", "[注意]").replace("🔄", "[进行中]").replace("⏳", "[待验证]").replace("❌", "[撤回]")
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    replacements = {r"\widetilde{\Delta T}":"ΔT~",r"\Delta":"Δ",r"\lambda":"λ",r"\delta":"δ",
                    r"\theta":"θ",r"\le":"≤",r"\ge":"≥",r"\rightarrow":"→",r"\times":"×",r"\text":""}
    for source,target in replacements.items():
        text = text.replace(source,target)
    text = re.sub(r"\\tilde\{([^}]+)\}",r"\1~",text)
    text = re.sub(r"([A-Za-z])_\{?([A-Za-z0-9]+)\}?",r"\1_\2",text)
    text = text.replace("{","").replace("}","").replace("`","").replace("$","")
    text = escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def build_story(source: Path = SOURCE) -> list:
    body = ParagraphStyle("BodyCN", fontName=REGULAR_FONT, fontSize=9, leading=14,
                          wordWrap="CJK", spaceAfter=5)
    cell = ParagraphStyle("CellCN", parent=body, fontSize=8, leading=12)
    headings = {i: ParagraphStyle(f"H{i}", parent=body, fontName=BOLD_FONT,
                fontSize=19 if i == 1 else 14 if i == 2 else 11,
                leading=25 if i == 1 else 19, spaceBefore=12, spaceAfter=7,
                keepWithNext=True) for i in range(1, 7)}
    story = []
    table_rows = []

    def flush_table() -> None:
        if not table_rows:
            return
        n = max(len(row) for row in table_rows)
        rows = [[Paragraph(inline(value), cell) for value in row + [""] * (n - len(row))] for row in table_rows]
        table = Table(rows, colWidths=[170 * mm / n] * n, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([table, Spacer(1, 6)])
        table_rows.clear()

    for line in source.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("|"):
            row = [v.strip() for v in re.split(r"(?<!\\)\|", line.strip("|"))]
            if not all(re.fullmatch(r"[-: ]+", v) for v in row):
                table_rows.append(row)
            continue
        flush_table()
        if not line or line in {"---", "$$"} or line.startswith("```"):
            continue
        heading = re.match(r"^(#{1,6}) (.*)$", line)
        if heading:
            story.append(Paragraph(inline(heading[2]), headings[len(heading[1])]))
        else:
            story.append(Paragraph(inline(line.removeprefix("> ")), body))
    flush_table()
    return story


def on_page(canvas, doc) -> None:
    canvas.setFont(REGULAR_FONT,8)
    footer = yaml.safe_load((ROOT/"project/report.yaml").read_text(encoding="utf-8"))["pdf"]["page_footer"]
    canvas.drawString(20*mm,12*mm,footer)
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))


def main() -> int:
    graph = yaml.safe_load((ROOT / "evidence/evidence_graph.yaml").read_text(encoding="utf-8"))
    errors = validate_evidence_graph(graph, ROOT)
    if errors:
        raise ValueError("证据登记校验失败：" + "; ".join(errors))
    register_project_fonts(ROOT)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=22 * mm,
                            title="QT450-10/Q235B V4.3 Competition Design Report",author="")
    generated_status = write_status_artifacts(ROOT)
    story = build_story()+[PageBreak()]+build_story(generated_status)
    doc.build(story,onFirstPage=on_page,onLaterPages=on_page)
    print(f"工艺设计说明书已生成：{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
