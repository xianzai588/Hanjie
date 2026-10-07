"""从当前参赛正文构建设计说明书；历史文件名保留以兼容已有入口。"""
from __future__ import annotations

from html import escape
from pathlib import Path
import json
import re
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
from reportlab.platypus.tableofcontents import TableOfContents

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


class ManualDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            title = flowable.getPlainText()
            if (flowable.style.name == "H2" and re.match(r'^[0-7] ',title)) or (flowable.style.name == "H1" and
                    title.startswith(("当前候选", "主轴承座—", "HJ-W-00", "HJ-W-02", "HJ-C-01", "HJ-C-02", "HJ-Q-01", "HJ-Q-02", "HJ-Q-03", "HJ-F-01"))):
                self.notify("TOCEntry", (0, title, self.page))


def cover_and_contents():
    center = ParagraphStyle("CoverCN", fontName=REGULAR_FONT, fontSize=16,
                            leading=26, alignment=1, wordWrap="CJK")
    title = ParagraphStyle("CoverTitle", parent=center, fontName=BOLD_FONT,
                           fontSize=24, leading=37, spaceAfter=16)
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("ContentsCN", fontName=REGULAR_FONT,
                                     fontSize=11, leading=23, wordWrap="CJK")]
    review = [Spacer(1, 8*mm), Paragraph('修订审阅稿<br/>有效接头与分工序工艺窗口重选；旧控形家族未通过',
                ParagraphStyle('ReviewCover',parent=center,fontSize=11,leading=18,textColor=colors.HexColor('#9a3412')))] if '--review' in sys.argv else []
    return [Spacer(1, 35*mm),
            Paragraph("第一届辽宁省大学生材料焊接与铸造<br/>工艺设计大赛", center),
            Spacer(1, 19*mm), Paragraph("QT450-10 主轴承座<br/>— Q235B 壳体<br/>焊接工艺设计说明书", title),
            Spacer(1, 14*mm), Paragraph("中铁山桥杯 · 焊接固定命题", center),
            Paragraph("含设计工艺规程及工程图纸", center),
            Spacer(1, 33*mm), Paragraph("2026 年 10 月", center),
            *review, PageBreak(), Paragraph("目录", title), toc, PageBreak()]


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
    links=[]
    def keep_link(match):
        label,url=match.groups()
        if not url.startswith(('https://','http://')):
            return label
        token=f'\x00LINK{len(links)}\x00'
        links.append((token,f'<link href="{escape(url,{chr(34):"&quot;"})}" color="#176b7b">{escape(label)}</link>'))
        return token
    text=re.sub(r"\[([^]]+)\]\(([^)]+)\)",keep_link,text)
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
    text = text.replace("ṁ","m_dot")  # The project CJK font lacks U+1E41.
    text = escape(text)
    for token, tag in ((_SUP_TOKEN, "super"), (_SUB_TOKEN, "sub")):
        text = re.sub(re.escape(token) + r"(.*?)" + re.escape(token),
                      r"<%s>\1</%s>" % (tag, tag), text)
    text=re.sub(r"\*\*(.+?)\*\*",r"<b>\1</b>",text)
    for token,link in links:
        text=text.replace(token,link)
    return text


def build_story(source: Path = SOURCE) -> list:
    is_card=source.parent==ROOT/'deliverables/process'
    body = ParagraphStyle("BodyCN", fontName=REGULAR_FONT, fontSize=10, leading=14 if is_card else 15.5,
                          wordWrap="CJK", spaceAfter=5)
    cell = ParagraphStyle("CellCN", parent=body, fontSize=8.5, leading=12.5 if is_card else 13)
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
        widths=[170*mm/n]*n
        if n==2:widths=[40*mm,130*mm]
        if n==3 and table_rows[0][0]=='项目':widths=[30*mm,70*mm,70*mm]
        if n==3 and table_rows[0][0]=='工序':widths=[25*mm,48*mm,97*mm]
        if n==3 and table_rows[0][1]=='当前设计输入及用途':widths=[30*mm,90*mm,50*mm]
        if n==4 and table_rows[0][0]=='输入':widths=[25*mm,35*mm,35*mm,75*mm]
        table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        block=KeepTogether([table]) if table_rows[0][0] in ('前期首层核算','直径方向分配') else table
        story.extend([block, Spacer(1, 6)])
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
            if source==SOURCE and len(heading[1])==1:
                continue  # The full document title is already on the cover.
            story.append(Paragraph(inline(heading[2]), headings[len(heading[1])]))
        else:
            story.append(Paragraph(inline(line.removeprefix("> ")), body))
    flush_table()
    return story


def on_page(canvas, doc) -> None:
    canvas.setFont(REGULAR_FONT,8)
    footer = yaml.safe_load((ROOT/"project/report.yaml").read_text(encoding="utf-8"))["pdf"]["page_footer"]
    if '--review' in sys.argv:footer='修订审阅稿 · 位置度验证状态见§4'
    if '--competition-entry' in sys.argv:footer='中铁山桥杯 · 焊接固定题工艺设计'
    canvas.drawString(20*mm,12*mm,footer)
    canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))


def validate_report_numbers(result, source=SOURCE):
    """计算变更后禁止悄悄发布旧摘要；正文论证需要随数字共同修订。"""
    body = source.read_text(encoding="utf-8")
    p = result["process"]
    required = ["8P-R2-t15", "两道脉冲 TIG",
                f"弧燃 {p['arc_on_time_s']:.1f} s",
                f"送丝 {p['fixed_feed_mm_s']:.2f}",
                "冷却至20±1℃", "热残余允许上限"]
    compact = re.sub(r"\s+", "", body)
    heat_values=[float(v) for v in re.findall(r'净热\s*([0-9.]+)\s*kJ',body)]
    if not any(abs(v-p['total_net_heat_j']/1000)<0.005 for v in heat_values):
        raise ValueError('正文名义总净热与计算不一致')
    if any(re.sub(r"\s+", "", value) not in compact for value in required):
        raise ValueError("当前正文关键数值与计算不一致，必须同步论证后再发布")


def main() -> int:
    global OUT
    if '--competition-entry' in sys.argv:
        # A design-report submission is not an assertion that a production
        # process has passed verification. Default engineering release keeps
        # every existing physical gate below. The report itself states the
        # remaining measured/calculated deficiencies in sections0 and4.
        OUT=ROOT/'output/pdf/工艺设计说明书-参赛设计稿.pdf'
    elif '--review' in sys.argv:
        OUT=ROOT/'output/pdf/工艺设计说明书-修订审阅稿.pdf'
    else:
        verification=ROOT/'simulation/competition-r4/results/verification.json'
        if not verification.exists() or not json.loads(verification.read_text(encoding='utf8')).get('position_design_pass',False):
            raise ValueError('位置度或空间/时间精度未通过；用--review生成明确标识的修订审阅稿')
        if not json.loads(verification.read_text(encoding='utf8')).get('bore_size_design_pass',False):
            raise ValueError('焊后孔径与微珩尺寸链未通过；用--review生成修订审阅稿')
        current=json.loads(verification.read_text(encoding='utf8'))
        if any(not json.loads((verification.parent/case/'input.json').read_text(encoding='utf8')).get('fixture_thermal') for case in current['cases']):
            raise ValueError('正式稿须采用芯/胀套及托垫热耦合的完整冷态结果')
        service=json.loads((verification.parent/'service-verification.json').read_text(encoding='utf8'))
        if not service.get('complete_welded_strength_design_pass',False):
            raise ValueError('完整焊接件强度须补残余张量及过渡层/界面核验；当前仅可生成审阅稿')
        current_bore=json.loads((verification.parent/current['cases'][0]/'input.json').read_text(encoding='utf8'))['initial_bore_diameter_mm']
        if not service.get('static_service_design_pass',False) or any(json.loads((verification.parent/case/'input.json').read_text(encoding='utf8')).get('initial_bore_diameter_mm') != current_bore for case in service['cases']):
            raise ValueError('正式稿须采用与已接受制造窗口同孔径的服役强度核验')
    validate_report_numbers(current_assessment(ROOT))
    graph = yaml.safe_load((ROOT / "evidence/evidence_graph.yaml").read_text(encoding="utf-8"))
    errors = validate_evidence_graph(graph, ROOT)
    if errors:
        raise ValueError("证据登记校验失败：" + "; ".join(errors))
    register_project_fonts(ROOT)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = ManualDocTemplate(str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=22 * mm,
                            title="QT450-10/Q235B 焊接固定题工艺设计说明书",author="")
    # 研究状态独立保留，正文只呈现比赛论证所需证据。
    story = cover_and_contents() + build_story()
    # The workshop cards belong in the readable manual, not only in loose attachments.
    for card in ("current-candidate-state.md", "independent-precoat-design-card.md", "first-layer-input-card.md", "precoat-tolerance-and-feed-card.md", "joint-process-card.md", "cold-weld-and-peening-card.md", "copper-shield-card.md", "fixture-load-and-transfer-card.md", "NDT-inspection-card.md", "cleanliness-inspection-card.md", "bore-compensation-and-finish-card.md", "clean-shield-engineering-detail.md", "pilot-production-and-resource-card.md"):
        if '--competition-entry' in sys.argv and card in ('current-candidate-state.md','cold-weld-and-peening-card.md'):
            continue  # Internal execution ledger and optional tooling card.
        story += [PageBreak()] + build_story(ROOT / "deliverables/process" / card)
    if "--include-research-status" in sys.argv:
        generated_status = write_status_artifacts(ROOT)
        story += [PageBreak()]+build_story(generated_status)
    doc.multiBuild(story,onFirstPage=on_page,onLaterPages=on_page)
    print(f"工艺设计说明书已生成：{OUT}")
    if '--with-drawings' in sys.argv:
        if '--review' not in sys.argv and '--competition-entry' not in sys.argv:
            raise ValueError('--with-drawings仅用于统一审阅稿；正式包按build_submission发布')
        from pypdf import PdfReader, PdfWriter
        drawings=ROOT/'cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf'
        manifest=json.loads((drawings.parent/'pdf-exports.json').read_text(encoding='utf8'))
        if len(PdfReader(drawings).pages)!=manifest['sheet_count'] or {sheet['number'] for sheet in manifest['sheets']} != set(range(1,22)):
            raise ValueError('先生成HJ-001至HJ-021连续图号的当前图集')
        bundle=PdfWriter();bundle.append(OUT);bundle.append(drawings)
        bundle.add_metadata({'/Title':'QT450-10/Q235B 工艺设计说明书与工程图（修订审阅稿）',
                             '/Author':'','/Subject':f"当前MMA首层候选、工艺规程与{manifest['sheet_count']}张工程图"})
        combined=ROOT/'output/pdf/工艺设计说明书与工程图-修订审阅稿.pdf'
        if '--competition-entry' in sys.argv:
            combined=ROOT/'output/pdf/工艺设计说明书与工程图-参赛设计稿.pdf'
            bundle.add_metadata({'/Title':'QT450-10/Q235B 焊接工艺设计说明书与工程图','/Author':'',
                                 '/Subject':'工艺设计研究报告；参数与验证状态见正文，非生产合格声明'})
        with combined.open('wb') as stream:bundle.write(stream)
        print(f'统一审阅稿已生成：{combined}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
