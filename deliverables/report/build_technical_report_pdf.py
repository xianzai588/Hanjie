"""从当前参赛正文构建设计说明书；历史文件名保留以兼容已有入口。"""
from __future__ import annotations

from html import escape
from pathlib import Path
import re
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "deliverables/report/technical-report-v4-unified.md"
OUT = ROOT / "output/pdf/technical-report-v4.pdf"
sys.path.insert(0, str(ROOT / "src"))
from hanjie.domain.evidence import validate_evidence_graph
from hanjie.reporting.fonts import register_project_fonts
from hanjie.reporting.current_status import write_status_artifacts
from hanjie.domain.competition_design import current_assessment
import yaml

REGULAR_FONT = "HanjieCN"
BOLD_FONT = "HanjieCN-Bold"


SUPERSCRIPT = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
               "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-", "⁺": "+"}
SUBSCRIPT = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5",
             "₆": "6", "₇": "7", "₈": "8", "₉": "9", "₊": "+", "₋": "-", "₌": "="}
_SUP_TOKEN = "\x00SUP"
_SUB_TOKEN = "\x00SUB"


def inline(text: str) -> str:
    # ReportLab 不解析 LaTeX；将本报告使用的有限命令显式转为可读 Unicode。
    text = text.replace("✅", "[记录]").replace("⚠️", "[注意]").replace("🔄", "[进行中]").replace("⏳", "[待验证]").replace("❌", "[撤回]")
    text = text.replace("📋", "[计划]").replace("≈", "约等于 ")
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    # 上标/下标区间在中文字体子集中缺字形，统一转为 <super>/<sub> 标签。
    for table, token, tag in ((SUPERSCRIPT, _SUP_TOKEN, "super"), (SUBSCRIPT, _SUB_TOKEN, "sub")):
        text = re.sub("[%s]+" % "".join(table),
                      lambda m, t=table, k=token: k + "".join(t[c] for c in m.group(0)) + k, text)
    replacements = {r"\widetilde{\Delta T}":"ΔT~",r"\Delta":"Δ",r"\lambda":"λ",r"\delta":"δ",
                    r"\theta":"θ",r"\le":"≤",r"\ge":"≥",r"\rightarrow":"→",r"\times":"×",
                    r"\%":"%",r"\text":"",r"\,":"",r"\;":""}
    for source,target in replacements.items():
        text = text.replace(source,target)
    text = re.sub(r"\\tilde\{([^}]+)\}",r"\1~",text)
    text = re.sub(r"([A-Za-z])_\{?([A-Za-z0-9]+)\}?",r"\1_\2",text)
    text = text.replace("{","").replace("}","").replace("`","").replace("$","")
    # 数学减号 U+2212 在中文字体子集中缺字形，统一为 ASCII 连字符以保证 PDF 可读。
    text = text.replace("\u2212","-")
    text = escape(text)
    for token, tag in ((_SUP_TOKEN, "super"), (_SUB_TOKEN, "sub")):
        text = re.sub(re.escape(token) + r"(.*?)" + re.escape(token),
                      r"<%s>\1</%s>" % (tag, tag), text)
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
        if line == "<!-- pagebreak -->":
            story.append(PageBreak())
            continue
        illustration = re.fullmatch(r"!\[([^]]+)\]\(([^)]+)\)", line)
        if illustration:
            figure = Image(str(ROOT / illustration[2]))
            ratio = min(170*mm/figure.imageWidth, 99*mm/figure.imageHeight)
            figure.drawWidth = figure.imageWidth*ratio
            figure.drawHeight = figure.imageHeight*ratio
            story.extend([figure,Paragraph(inline(illustration[1]),cell),Spacer(1,5)])
            continue
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


def validate_report_numbers(result, source=SOURCE):
    """计算变更后禁止悄悄发布旧摘要；正文论证需要随数字共同修订。"""
    body = source.read_text(encoding="utf-8")
    p = result["process"]
    required = ["8P-FAIR_B", "两道脉冲 TIG",
                f"净热 {p['total_net_heat_j']/1000:.2f} kJ",
                f"弧燃 {p['arc_on_time_s']:.1f} s",
                f"送丝 {p['fixed_feed_mm_s']:.2f}",
                "冷却至20±1℃", "热残余允许上限"]
    if any(value not in body for value in required):
        raise ValueError("当前正文关键数值与计算不一致，必须同步论证后再发布")


def main() -> int:
    validate_report_numbers(current_assessment(ROOT))
    graph = yaml.safe_load((ROOT / "evidence/evidence_graph.yaml").read_text(encoding="utf-8"))
    errors = validate_evidence_graph(graph, ROOT)
    if errors:
        raise ValueError("证据登记校验失败：" + "; ".join(errors))
    register_project_fonts(ROOT)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=22 * mm,
                            title="QT450-10/Q235B Welding Fixed Topic R3 Design Report",author="")
    generated_status = write_status_artifacts(ROOT)
    # 研究状态独立保留，正文只呈现比赛论证所需证据。
    story = build_story()
    if "--include-research-status" in sys.argv:
        story += [PageBreak()]+build_story(generated_status)
    doc.build(story,onFirstPage=on_page,onLaterPages=on_page)
    print(f"工艺设计说明书已生成：{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
