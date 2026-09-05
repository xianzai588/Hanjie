"""从唯一 V4 Markdown 报告源构建研究草稿 PDF，不嵌入历史 V2 正文。"""
from __future__ import annotations

from html import escape
from pathlib import Path
import re
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "deliverables/report/technical-report-v4-unified.md"
OUT = ROOT / "output/pdf/technical-report-v4.pdf"
sys.path.insert(0, str(ROOT / "src"))
from hanjie.domain.evidence import validate_evidence_graph
import yaml


def inline(text: str) -> str:
    # 先转义再转换有限 Markdown 子集，避免数学不等式被当成 XML 标签。
    text = text.replace("✅", "[记录]").replace("⚠️", "[注意]").replace("🔄", "[进行中]").replace("⏳", "[待验证]").replace("❌", "[撤回]")
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = escape(text.replace("`", "").replace("$", ""))
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def build_story(source: Path = SOURCE) -> list:
    body = ParagraphStyle("BodyCN", fontName="Deng", fontSize=9, leading=14,
                          wordWrap="CJK", spaceAfter=5)
    cell = ParagraphStyle("CellCN", parent=body, fontSize=8, leading=12)
    headings = {i: ParagraphStyle(f"H{i}", parent=body, fontName="Deng-Bold",
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
    canvas.setFont("Deng", 8)
    canvas.drawString(20 * mm, 12 * mm, "V4.2 研究草稿 | 工程验证尚未完成")
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))


def main() -> int:
    graph = yaml.safe_load((ROOT / "evidence/evidence_graph.yaml").read_text(encoding="utf-8"))
    errors = validate_evidence_graph(graph, ROOT)
    if errors:
        raise ValueError("证据登记校验失败：" + "; ".join(errors))
    pdfmetrics.registerFont(TTFont("Deng", "C:/Windows/Fonts/Deng.ttf"))
    pdfmetrics.registerFont(TTFont("Deng-Bold", "C:/Windows/Fonts/Dengb.ttf"))
    pdfmetrics.registerFontFamily("Deng", normal="Deng", bold="Deng-Bold", italic="Deng", boldItalic="Deng-Bold")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=22 * mm,
                            title="QT450-10/Q235B V4.2 Research Draft", author="")
    doc.build(build_story(), onFirstPage=on_page, onLaterPages=on_page)
    print(f"研究草稿已生成：{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
