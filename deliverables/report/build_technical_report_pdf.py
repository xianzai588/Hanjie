"""排版匿名工艺设计说明书及配套工艺卡、工程图合订本。"""
from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import json
import re
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph as ReportLabParagraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether, CondPageBreak
from reportlab.platypus.tableofcontents import TableOfContents

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
SANS_FONT = "HanjieCN-Sans"
REPORT_CONFIG = yaml.safe_load((ROOT / "project/report.yaml").read_text(encoding="utf8"))["pdf"]
PAPER = ROOT / REPORT_CONFIG.get("paper_pdf", "output/pdf/焊接工艺设计说明书-正文.pdf")
TEXT_WIDTH = 160 * mm
INK = colors.black
NAVY = INK


class Paragraph(ReportLabParagraph):
    """Honor short numeric nobr fragments in ReportLab's CJK layout."""
    def breakLinesCJK(self,maxWidths):
        if not any(getattr(f,'nobr',False) for f in self.frags):
            return super().breakLinesCJK(maxWidths)
        if hasattr(self,'blPara') and getattr(self,'_splitpara',0):
            return self.blPara
        from reportlab.platypus.paragraph import cjkU,makeCJKParaLine,ParaLines,sameFrag
        widths=list(maxWidths) if isinstance(maxWidths,(list,tuple)) else [maxWidths]
        atoms=[]
        closing='，。；：、,.;:）)]%'
        for frag in self.frags:
            text=getattr(frag,'text','')
            pieces=[text] if getattr(frag,'nobr',False) else list(text) if text else ['']
            for piece in pieces:
                if piece and piece[0] in closing and atoms and sameFrag(atoms[-1].frag,frag):
                    previous=atoms.pop();atoms.append(cjkU(str(previous)+piece,frag,'utf8'))
                else:
                    atoms.append(cjkU(piece,frag,'utf8'))
        lines=[];current=[];used=0.0
        calcBounds=getattr(self,'autoLeading',getattr(self.style,'autoLeading','')) not in ('','off')
        def finish(explicit=False):
            nonlocal current,used
            limit=widths[min(len(lines),len(widths)-1)]
            lines.append(makeCJKParaLine(current,limit,used,limit-used,explicit,calcBounds))
            current=[];used=0.0
        for atom in atoms:
            limit=widths[min(len(lines),len(widths)-1)]
            if current and used+atom.width>limit+1e-6:
                finish()
            current.append(atom);used+=atom.width
            if hasattr(atom.frag,'lineBreak'):finish(True)
        if current:finish()
        return ParaLines(kind=1,lines=lines)


class ManualDocTemplate(SimpleDocTemplate):
    def beforeDocument(self):
        # The declared page margins are the text margins, without Frame's
        # implicit six-point padding on each side.
        for template in self.pageTemplates:
            for frame in template.frames:
                frame._leftPadding=frame._rightPadding=0
                frame._topPadding=frame._bottomPadding=0
                frame._geom()
                frame._reset()

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        title = flowable.getPlainText()
        style = flowable.style.name
        if style == "H2" and re.match(r'^\d{1,2}\s+', title):
            self.notify("TOCEntry", (0, title, self.page))
        elif style in {"AbstractTitle", "ReferencesTitle", "AppendixTitle"}:
            self.notify("TOCEntry", (0, title, self.page))
        elif style == "CardH1":
            self.notify("TOCEntry", (1, title, self.page))


def cover_and_contents():
    center = ParagraphStyle("CoverCN", fontName=REGULAR_FONT, fontSize=14,
                            leading=24, alignment=TA_CENTER, wordWrap="CJK", textColor=INK)
    title = ParagraphStyle("CoverTitle", parent=center, fontName=BOLD_FONT,
                           fontSize=20, leading=31, spaceAfter=12)
    contents_title = ParagraphStyle("ContentsTitle", parent=center, fontName=BOLD_FONT,
                                    fontSize=16, leading=25, spaceAfter=15)
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle("ContentsCN", fontName=REGULAR_FONT, fontSize=12, leading=21,
                       wordWrap="CJK", textColor=INK, leftIndent=0, firstLineIndent=0),
        ParagraphStyle("ContentsCardCN", fontName=REGULAR_FONT, fontSize=10.5, leading=18,
                       wordWrap="CJK", textColor=INK, leftIndent=12, firstLineIndent=0),
    ]
    review = [Spacer(1, 8*mm), Paragraph('修订审阅稿', center)] if '--review' in sys.argv else []
    return [Spacer(1, 25*mm),
            Paragraph("第一届辽宁省大学生材料焊接与铸造工艺设计大赛", center),
            Spacer(1, 32*mm),
            Paragraph("QT450-10主轴承座与Q235B壳体<br/>焊接工艺设计", title),
            Spacer(1, 14*mm), Paragraph("焊接固定题", center),
            Paragraph("配套pWPS及工程图", center),
            Spacer(1, 38*mm), Paragraph("2026年10月", center),
            *review, PageBreak(), Paragraph("目录", contents_title), toc, PageBreak()]


SUPERSCRIPT = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5",
               "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-", "⁺": "+"}
SUBSCRIPT = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5",
             "₆": "6", "₇": "7", "₈": "8", "₉": "9", "₊": "+", "₋": "-", "₌": "="}
_SUP_TOKEN = "\x00SUP"
_SUB_TOKEN = "\x00SUB"


def inline(text: str, superscript_references: bool = True) -> str:
    # ReportLab 不解析 LaTeX；将本报告使用的有限命令显式转为可读 Unicode。
    text = text.replace("✅", "[记录]").replace("⚠️", "[注意]").replace("🔄", "[进行中]").replace("⏳", "[待验证]").replace("❌", "[撤回]")
    text = text.replace("📋", "[计划]")
    links=[]
    def keep_link(match):
        label,url=match.groups()
        if not url.startswith(('https://','http://')):
            return label
        token=f'\x00LINK{len(links)}\x00'
        links.append((token,f'<link href="{escape(url,{chr(34):"&quot;"})}" color="#000000">{escape(label)}</link>'))
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
    text = text.replace("{","").replace("}","").replace("`","").replace("$","")
    if superscript_references:
        # Mathematical variables only: one Latin letter or up to two Greek
        # letters, excluding identifiers inside paths and filenames.
        variable_subscript=r"(?<![A-Za-z0-9_./\\-])([A-Za-z]|[Α-Ωα-ω]{1,2})_([A-Za-z]{1,8}|\d{1,2})(?![A-Za-z0-9_./\\-])"
        text=re.sub(variable_subscript,lambda m:m[1]+_SUB_TOKEN+m[2]+_SUB_TOKEN,text)
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
    if superscript_references:
        text=re.sub(r"(?<!^)(\[(?:\d+)(?:[–—,-]\d+)*(?:,\d+(?:[–—-]\d+)*)*\])",r"<super>\1</super>",text)
    if not superscript_references:
        return text
    # Protect scalar values and short units, while leaving long English prose,
    # hyperlinks and filenames available to wrap normally.
    scalar=r"[+−-]?\d+(?:\.\d+)?(?:[±～~-]\d+(?:\.\d+)?)?"
    unit=r"(?:μm|µm|mm/s|mm/min|J/mm|L/min|MPa|GPa|kPa|kN|kg|kJ|mm|cm|min|℃|°C|%|s|h|g|J|W|N|A|V|元/件)"
    technical=r"(?<![A-Za-z0-9_./\\-])[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*(?![A-Za-z0-9_./\\-])"
    protected=re.compile(r"(?:"+technical+r")|(?:"+scalar+r"(?:\s*"+unit+r")?[，。；：,.;:）)]*)")
    def protect_short(match):
        value=match.group(0)
        if value[0].isalpha():
            is_technical=len(value)<=15 and (any(c.isdigit() for c in value) or sum(c.isupper() for c in value)>=2 or value in ('Feret', 'Miner'))
            return '<nobr>'+value+'</nobr>' if is_technical else value
        return '<nobr>'+value+'</nobr>' if len(value)<=24 else value
    nodes=re.split(r'(<[^>]+>)',text)
    for index in range(0,len(nodes),2):
        nodes[index]=protected.sub(protect_short,nodes[index])
    return ''.join(nodes)


def figure_image(path: Path, *, max_height: float = 105*mm) -> Image:
    """Prefer the same-name vector export, rasterized at 300 dpi for ReportLab."""
    vector = path if path.suffix.lower() == '.pdf' else path.with_suffix('.pdf')
    paper_drawing=ROOT/REPORT_CONFIG.get('drawing_pdf','cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf')
    grayscale_vector=paper_drawing.parent/path.with_suffix('.pdf').name
    if path.resolve().is_relative_to((ROOT/'cad').resolve()) and grayscale_vector.is_file():
        vector=grayscale_vector
    if vector.is_file():
        import fitz
        with fitz.open(vector) as doc:
            if len(doc) != 1:
                raise ValueError(f'Figure PDF must contain one page: {vector}')
            pixels = doc[0].get_pixmap(matrix=fitz.Matrix(300/72,300/72), alpha=False)
            figure=Image(BytesIO(pixels.tobytes('png')))
    else:
        figure=Image(str(path))
    scale=min(TEXT_WIDTH/figure.imageWidth,max_height/figure.imageHeight)
    figure.drawWidth=figure.imageWidth*scale
    figure.drawHeight=figure.imageHeight*scale
    return figure


def equation_flowable(latex: str, style: ParagraphStyle):
    """Render explicit lines at 12 pt with a right-aligned equation number."""
    from matplotlib.mathtext import math_to_image
    from matplotlib.font_manager import FontProperties
    from matplotlib import rc_context
    number_match=re.search(r'\\tag\{([^}]+)\}',latex)
    legacy_number=re.search(r'\\qquad\s*\((\d+)\)\s*$',latex)
    number='('+number_match.group(1)+')' if number_match else '('+legacy_number.group(1)+')' if legacy_number else ''
    formula=re.sub(r'\\tag\{[^}]+\}','',latex).strip()
    if legacy_number:formula=formula[:legacy_number.start()].strip()
    lines=[line.strip() for line in re.split(r'\\\\',formula) if line.strip()]
    images=[]
    for index,line in enumerate(lines):
        buffer=BytesIO()
        try:
            with rc_context({'mathtext.fontset':'stix'}):
                math_to_image('$'+line+'$',buffer,prop=FontProperties(size=12),dpi=300,format='png',color='black')
        except Exception as exc:
            raise ValueError('Display formula requires supported LaTeX/MathText or a supplied formula figure: '+line) from exc
        image=Image(BytesIO(buffer.getvalue()))
        image.drawWidth=image.imageWidth*72/300
        image.drawHeight=image.imageHeight*72/300
        image.hAlign='CENTER'
        if image.drawWidth>TEXT_WIDTH-15*mm:
            raise ValueError('Equation line exceeds the 12 pt layout; insert an explicit double-backslash line break: '+line)
        if index:images.append(Spacer(1,5))
        images.append(image)
    number_style=ParagraphStyle('EquationNumberCN',parent=style,alignment=TA_RIGHT,firstLineIndent=0)
    table=Table([[images,Paragraph(escape(number),number_style)]],colWidths=[TEXT_WIDTH-15*mm,15*mm],hAlign='CENTER')
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(0,0),(0,0),'CENTER'),
                              ('ALIGN',(1,0),(1,0),'RIGHT'),('TOPPADDING',(0,0),(-1,-1),7),
                              ('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    return table


def build_story(source: Path = SOURCE) -> list:
    is_card=source.parent==ROOT/'deliverables/process'
    body = ParagraphStyle("CardBodyCN" if is_card else "BodyCN", fontName=REGULAR_FONT,
                          fontSize=9.5 if is_card else 12, leading=14 if is_card else 19.5,
                          wordWrap="CJK", alignment=TA_LEFT if is_card else TA_JUSTIFY,
                          firstLineIndent=0 if is_card else 24, spaceAfter=4 if is_card else 5,
                          textColor=INK, allowOrphans=0, allowWidows=0)
    no_indent = ParagraphStyle("NoIndentCN",parent=body,firstLineIndent=0)
    cell = ParagraphStyle("CellCN", parent=body, fontName=REGULAR_FONT,
                          fontSize=9 if is_card else 10.5, leading=13 if is_card else 15,
                          firstLineIndent=0, alignment=TA_LEFT, spaceAfter=0)
    header_cell = ParagraphStyle("HeaderCellCN", parent=cell, fontName=BOLD_FONT, textColor=INK)
    table_caption = ParagraphStyle("TableCaptionCN", parent=body, fontName=REGULAR_FONT,
                                   fontSize=10.5, leading=15, alignment=TA_CENTER, firstLineIndent=0,
                                   keepWithNext=True, spaceBefore=7, spaceAfter=6)
    figure_caption = ParagraphStyle("FigureCaptionCN", parent=table_caption,
                                    keepWithNext=False, spaceBefore=5, spaceAfter=7)
    reference = ParagraphStyle("ReferenceCN", parent=body, fontSize=10.5, leading=16,
                               firstLineIndent=0, alignment=TA_LEFT, spaceAfter=4)
    abstract_title = ParagraphStyle("AbstractTitle",parent=no_indent,fontName=BOLD_FONT,
                                    fontSize=14,leading=22,alignment=TA_CENTER,
                                    spaceBefore=8,spaceAfter=12,keepWithNext=True)
    references_title = ParagraphStyle("ReferencesTitle",parent=abstract_title,alignment=TA_LEFT)
    keyword = ParagraphStyle("KeywordCN",parent=body,firstLineIndent=0,alignment=TA_LEFT,
                             spaceBefore=5,spaceAfter=10)
    headings = {i: ParagraphStyle(f"CardH{i}" if is_card else f"H{i}", parent=no_indent,
                fontName=BOLD_FONT,fontSize=14 if i<=2 else 12,
                leading=22 if i<=2 else 19,spaceBefore=12,spaceAfter=8,
                textColor=INK,keepWithNext=True) for i in range(1,7)}
    story = []
    table_rows = []
    pending_caption = None

    def flush_table() -> None:
        nonlocal pending_caption
        if not table_rows:
            return
        n = max(len(row) for row in table_rows)
        rows = [[Paragraph(inline(value), header_cell if i==0 else cell)
                 for value in row + [""] * (n - len(row))] for i,row in enumerate(table_rows)]
        widths=[TEXT_WIDTH/n]*n
        if n==2:widths=[TEXT_WIDTH*40/170,TEXT_WIDTH*130/170]
        if n==3 and table_rows[0][0]=='项目':widths=[TEXT_WIDTH*30/170,TEXT_WIDTH*70/170,TEXT_WIDTH*70/170]
        if n==3 and table_rows[0][0]=='工序':widths=[TEXT_WIDTH*25/170,TEXT_WIDTH*48/170,TEXT_WIDTH*97/170]
        if n==3 and table_rows[0][1]=='当前设计输入及用途':widths=[TEXT_WIDTH*30/170,TEXT_WIDTH*90/170,TEXT_WIDTH*50/170]
        if n==4 and table_rows[0][0]=='输入':widths=[TEXT_WIDTH*25/170,TEXT_WIDTH*35/170,TEXT_WIDTH*35/170,TEXT_WIDTH*75/170]
        table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (-1, 0), 0.9, NAVY),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY),
            ("LINEBELOW", (0, -1), (-1, -1), 0.9, NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        height=table.wrap(TEXT_WIDTH,245*mm)[1]
        # Keep a section heading with the opening of its captioned table.
        # A separate heading keepWithNext cannot bridge a nested KeepTogether.
        prefix=[]
        if story and isinstance(story[-1],Paragraph) and re.fullmatch(r'(?:Card)?H[1-6]',story[-1].style.name):
            prefix.append(story.pop())
        if pending_caption is not None:
            prefix.append(pending_caption)
        if prefix:
            # Reserve only the title/caption and the header plus first data
            # row. The remaining table can then split at the real page edge.
            needed=sum(table._rowHeights[:min(2,len(rows))])
            for paragraph in prefix:
                paragraph.style=paragraph.style.clone(paragraph.style.name)
                paragraph.style.keepWithNext=False
                needed+=paragraph.wrap(TEXT_WIDTH,245*mm)[1]+paragraph.getSpaceBefore()+paragraph.getSpaceAfter()
            story.append(CondPageBreak(needed))
            story.extend(prefix)
            story.append(table)
            pending_caption=None
        else:
            story.append(KeepTogether([table]) if len(rows)<=7 and height<=90*mm else table)
        story.append(Spacer(1, 6))
        table_rows.clear()

    source_lines=source.read_text(encoding="utf-8").splitlines()
    consumed_captions=set()
    def append_equation(latex):
        equation=equation_flowable(latex,no_indent)
        prefix=[]
        if story and isinstance(story[-1],Paragraph) and story[-1].style.name in {'BodyCN','NoIndentCN'}:
            prefix.append(story.pop())
        story.append(KeepTogether(prefix+[equation]))
    formula_lines=None
    frontmatter=source==SOURCE
    for line_index,line in enumerate(source_lines):
        if line_index in consumed_captions:continue
        line = line.strip()
        if frontmatter:
            if line.startswith('## '):frontmatter=False
            else:continue
        if formula_lines is not None:
            if line == '$$':
                append_equation(' '.join(formula_lines))
                formula_lines=None
            else:
                formula_lines.append(line)
            continue
        if line.startswith('$$'):
            flush_table()
            if line == '$$':
                formula_lines=[]
            elif line.endswith('$$') and len(line)>4:
                append_equation(line[2:-2].strip())
            else:
                raise ValueError('Display formula requires a closing $$ delimiter')
            continue
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
            image_path = ROOT / illustration[2]
            if not image_path.is_file():
                image_path = (source.parent / illustration[2]).resolve()
            figure = figure_image(image_path,max_height=105*mm if not is_card else 100*mm)
            caption=illustration[1]
            for next_index in range(line_index+1,len(source_lines)):
                following=source_lines[next_index].strip()
                if not following:continue
                if re.match(r'^图\s*\d+',following):
                    caption=following
                    consumed_captions.add(next_index)
                break
            figure_prefix=[]
            if story and isinstance(story[-1],Paragraph) and re.fullmatch(r'(?:Card)?H[1-6]',story[-1].style.name):
                figure_prefix.append(story.pop())
            story.extend([KeepTogether(figure_prefix+[figure,Paragraph(inline(caption),figure_caption)]),Spacer(1,6)])
            continue
        if not line or line in {"---", "$$"} or line.startswith("```"):
            continue
        heading = re.match(r"^(#{1,6}) (.*)$", line)
        if heading:
            level,title=len(heading[1]),heading[2]
            if source==SOURCE and level==1:
                continue
            normalized=re.sub(r'\s+','',title)
            if not is_card and normalized in ('摘要','设计概要'):
                story.append(Paragraph(title,abstract_title))
            elif not is_card and normalized in ('参考文献','参考资料'):
                if story and not isinstance(story[-1],PageBreak):story.append(PageBreak())
                story.append(Paragraph(title,references_title))
            else:
                story.append(Paragraph(inline(title),headings[level]))
        else:
            is_reference=bool(re.match(r'^\[\d+\]',line))
            is_keyword=bool(re.match(r'^(?:关键词|关键字)\s*[：:]',line.replace('**','')))
            is_abstract_prefix=bool(re.match(r'^摘要\s*[：:]',line.replace('**','')))
            if is_keyword:style=keyword
            elif is_abstract_prefix:style=no_indent
            elif re.match(r'^表\s*\d+',line):style=table_caption
            elif is_reference:style=reference
            else:style=body
            paragraph=Paragraph(inline(line.removeprefix("> "),superscript_references=not is_reference),style)
            if style is table_caption:pending_caption=paragraph
            else:story.append(paragraph)
    if formula_lines is not None:raise ValueError('Unclosed display-formula block')
    flush_table()
    if pending_caption is not None:story.append(pending_caption)
    return story


def on_page(canvas, doc) -> None:
    if doc.page == 1:
        return
    canvas.setFillColor(INK)
    canvas.setFont(REGULAR_FONT,9)
    canvas.drawCentredString(A4[0]/2,13*mm,str(doc.page))


def validate_report_numbers(source=SOURCE):
    """计算变更后禁止悄悄发布旧摘要；正文论证需要随数字共同修订。"""
    body = source.read_text(encoding="utf-8")
    baseline=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text(encoding='utf8'))
    layout,p=baseline['weld_layout'],baseline['final_GTAW']
    revision=json.loads((ROOT/p['local_forming_source']).read_text(encoding='utf8'))
    required = ["8P-R2-t15", "两道", "脉冲GTAW",
                f"{p['pass_feed_mm_s']['root']:.2f}±0.05",
                f"{p['pass_feed_mm_s']['cover']:.2f}±0.05",
                "20±1℃", "热残余允许上限"]
    compact = re.sub(r"\s+", "", body)
    heat_values=[float(v) for v in re.findall(r'净热\s*([0-9.]+)\s*kJ',body)]
    arc_values=[float(v) for v in re.findall(r'弧燃\s*([0-9.]+)\s*s',body)]
    if not any(abs(v-p['nominal_arc_time_s'])<0.05 for v in arc_values):
        raise ValueError('当前正文关键数值与计算不一致：名义弧燃时间')
    if not any(abs(v-p['net_energy_kJ'])<0.005 for v in heat_values):
        raise ValueError('当前正文关键数值与计算不一致：名义总净热')
    if any(re.sub(r"\s+", "", value) not in compact for value in required):
        raise ValueError("当前正文关键数值与计算不一致，必须同步论证后再发布")
    layout,process=baseline['weld_layout'],baseline['final_GTAW']
    length=layout['segment_count']*layout['segment_length_mm']*layout['pass_count']
    effective=layout['segment_length_mm']-layout['start_allowance_mm']-layout['end_allowance_mm']
    if abs(length-layout['total_arc_length_mm'])>1e-8:
        raise ValueError('主方案实际路径与基准输入不一致')
    if abs(effective-layout['effective_segment_length_mm'])>1e-8:
        raise ValueError('主方案有效焊长未扣除起止过渡')
    if abs(layout['segment_count']*effective-layout['effective_length_per_pass_mm'])>1e-8:
        raise ValueError('主方案焊缝组有效长度未闭合')
    if abs(length*process['nominal_net_energy_J_mm']/1000-process['net_energy_kJ'])>1e-8:
        raise ValueError('主方案含起停的热量未闭合')
    for key in ('root','cover'):
        if abs(process['pass_feed_mm_s'][key]-revision['revision'][key+'_feed_mm_s'])>1e-8:
            raise ValueError('分道送丝与本轮有限解析计算不一致')
    wire=layout['length_per_pass_mm']/process['travel_speed_mm_s']*sum(process['pass_feed_mm_s'].values())
    if abs(wire-process['nominal_wire_consumption_length_mm'])>1e-8 or abs(wire-revision['nominal']['total_consumed_wire_mm'])>1e-8:
        raise ValueError('分道耗丝守恒未闭合')
    for value in (f"{length:.0f} mm",f"{effective:.0f} mm",f"{layout['effective_length_per_pass_mm']:.0f} mm",f"{process['net_energy_kJ']:.1f} kJ"):
        if re.sub(r'\s+','',value) not in compact:
            raise ValueError('主方案正文数值缺失：'+value)



def main() -> int:
    global OUT
    if '--competition-entry' in sys.argv:
        # A design-report submission is not an assertion that a production
        # process has passed verification. Default engineering release keeps
        # every existing physical gate below. The report itself states the
        # remaining measured/calculated deficiencies in sections0 and4.
        OUT=ROOT/REPORT_CONFIG.get('manual_pdf','output/pdf/焊接工艺设计说明书-含工艺卡.pdf')
    elif '--review' in sys.argv:
        OUT=ROOT/'output/pdf/焊接工艺设计说明书-修订审阅稿.pdf'
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
    validate_report_numbers()
    graph = yaml.safe_load((ROOT / "evidence/evidence_graph.yaml").read_text(encoding="utf-8"))
    errors = validate_evidence_graph(graph, ROOT)
    if errors:
        raise ValueError("证据登记校验失败：" + "; ".join(errors))
    register_project_fonts(ROOT)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = ManualDocTemplate(str(OUT), pagesize=A4, leftMargin=25 * mm, rightMargin=25 * mm,
                            topMargin=25 * mm, bottomMargin=23 * mm,
                            title="QT450-10主轴承座与Q235B壳体焊接工艺设计",author="")
    if '--competition-entry' in sys.argv:
        paper_doc = ManualDocTemplate(str(PAPER), pagesize=A4, leftMargin=25*mm, rightMargin=25*mm,
                        topMargin=25*mm, bottomMargin=23*mm,
                        title='QT450-10主轴承座与Q235B壳体焊接工艺设计', author='')
        paper_doc.multiBuild(cover_and_contents()+build_story(),onFirstPage=on_page,onLaterPages=on_page)
        print(f'参赛正文已生成：{PAPER}')
    # 工艺卡与正文使用同一套字体、表格和页码样式。
    story = cover_and_contents() + build_story()
    # The workshop cards belong in the readable manual, not only in loose attachments.
    appendix_style=ParagraphStyle('AppendixTitle',fontName=BOLD_FONT,fontSize=14,leading=22,
                                  spaceAfter=12,keepWithNext=True,textColor=INK,wordWrap='CJK')
    story += [PageBreak(),Paragraph('附录A 工艺规程与检验卡',appendix_style)]
    for card_index,card in enumerate(("manufacturing-and-inspection-card.md", "independent-precoat-design-card.md", "first-layer-input-card.md", "precoat-tolerance-and-feed-card.md", "joint-process-card.md", "copper-shield-card.md", "fixture-load-and-transfer-card.md", "NDT-inspection-card.md", "cleanliness-inspection-card.md", "bore-compensation-and-finish-card.md", "clean-shield-engineering-detail.md", "pilot-production-and-resource-card.md", "shell-datum-and-cmm-execution-card.md", "gas-water-fault-execution-card.md", "calculation-index.md")):
        story += ([] if card_index==0 else [PageBreak()]) + build_story(ROOT / "deliverables/process" / card)
    if "--include-research-status" in sys.argv:
        generated_status = write_status_artifacts(ROOT)
        story += [PageBreak()]+build_story(generated_status)
    doc.multiBuild(story,onFirstPage=on_page,onLaterPages=on_page)
    print(f"说明书与工艺卡已生成：{OUT}")
    if '--with-drawings' in sys.argv:
        if '--review' not in sys.argv and '--competition-entry' not in sys.argv:
            raise ValueError('--with-drawings仅用于统一审阅稿；正式包按build_submission发布')
        from pypdf import PdfReader, PdfWriter
        drawings=ROOT/REPORT_CONFIG.get('drawing_pdf','cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf')
        manifest_path=ROOT/REPORT_CONFIG.get('drawing_manifest',(drawings.parent/'pdf-exports.json').relative_to(ROOT).as_posix())
        manifest=json.loads(manifest_path.read_text(encoding='utf8'))
        if len(PdfReader(drawings).pages)!=manifest['sheet_count'] or {sheet['number'] for sheet in manifest['sheets']} != set(range(1,manifest['sheet_count']+1)):
            raise ValueError('先生成连续图号的当前图集')
        # The main drawing set uses one frozen eight-wing object and its tooling.
        # Complete-ring comparison drawings remain in the separate history archive.
        import fitz
        drawing_out=drawings
        # Merge duplicate embedded fonts from independently exported sheets.
        # This preserves page content while keeping the downloadable package compact.
        def compact_pdf(path):
            tmp=path.with_suffix('.compact.pdf')
            with fitz.open(path) as pdf:pdf.save(tmp,garbage=4,deflate=True)
            tmp.replace(path)
        bundle=PdfWriter();bundle.append(OUT);bundle.append(drawing_out)
        bundle.add_metadata({'/Title':'QT450-10/Q235B 工艺设计说明书与工程图（修订审阅稿）',
                             '/Author':'','/Subject':f"当前MMA首层候选、工艺规程与{manifest['sheet_count']}张工程图"})
        combined=ROOT/'output/pdf/焊接工艺设计说明书与工程图-修订审阅稿.pdf'
        if '--competition-entry' in sys.argv:
            combined=ROOT/REPORT_CONFIG.get('combined_pdf','output/pdf/焊接工艺设计说明书与工程图.pdf')
            bundle.add_metadata({'/Title':'QT450-10主轴承座与Q235B壳体焊接工艺设计说明书与工程图','/Author':'',
                                 '/Subject':f"8P-R2-t15柔顺槽主方案、工艺规程及{manifest['sheet_count']}张工程图"})
        with combined.open('wb') as stream:bundle.write(stream)
        compact_pdf(combined)
        print(f'说明书与工程图合订本已生成：{combined}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
