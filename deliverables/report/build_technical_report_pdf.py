"""排版匿名工艺设计说明书及配套工艺卡、工程图合订本。"""
from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
import json
import math
import re
import sys

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph as ReportLabParagraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether, CondPageBreak

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
CARD_FILES = ("manufacturing-and-inspection-card.md", "independent-precoat-design-card.md", "first-layer-input-card.md", "precoat-tolerance-and-feed-card.md", "joint-process-card.md", "copper-shield-card.md", "fixture-load-and-transfer-card.md", "NDT-inspection-card.md", "cleanliness-inspection-card.md", "bore-compensation-and-finish-card.md", "clean-shield-engineering-detail.md", "pilot-production-and-resource-card.md", "shell-datum-and-cmm-execution-card.md", "gas-water-fault-execution-card.md", "calculation-index.md")


def navigation_paragraph(text, style, key, level):
    paragraph=Paragraph(inline(text),style)
    paragraph.navigation=dict(key=key,title=paragraph.getPlainText(),level=level)
    return paragraph


def navigation_catalog(story):
    result=[]
    for flowable in story:
        if hasattr(flowable,'navigation'):result.append(flowable.navigation)
        if isinstance(flowable,KeepTogether):result.extend(navigation_catalog(flowable._content))
    return result


def external_catalog():
    manifest=json.loads((ROOT/REPORT_CONFIG['drawing_manifest']).read_text(encoding='utf8'))
    names=['八翼柔顺槽座体零件图','异种连接角焊缝详图','八翼座体焊接装配图','定位承力与退出工装总装图','首批试制焊接工作站布置图']
    entries=[dict(key='appendix-b',title='附录B 按比例工程图 HJ-F01～05',level=0,external=True,offset=0)]
    entries += [dict(key=f'drawing-{i+1}',title=f'HJ-F{i+1:02d} {name}',level=1,external=True,offset=i) for i,name in enumerate(names)]
    entries.append(dict(key='appendix-c',title='附录C 工艺与工装功能示意（NTS）',level=0,external=True,offset=manifest['sheet_count']))
    illustrations=json.loads((ROOT/REPORT_CONFIG['illustration_pdf']).with_name('illustrations.json').read_text(encoding='utf8'))
    entries += [dict(key=f'illustration-{item["number"]}',title=f'附图I{item["number"]:02d} {item["title"]}',level=1,external=True,
                     offset=manifest['sheet_count']+item['number']-1) for item in illustrations['items']]
    for entry in entries:
        entry['title']=Paragraph(inline(entry['title']),ParagraphStyle('NavigationTitle',fontName=REGULAR_FONT,wordWrap='CJK')).getPlainText()
    return entries


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


class FormTable(Table):
    """Identify workshop tables for balanced form endings."""
    pass


def flowable_height(flowable):
    if isinstance(flowable,KeepTogether):return sum(flowable_height(f) for f in flowable._content)
    if isinstance(flowable,(PageBreak,CondPageBreak)):return 0
    return flowable.wrap(TEXT_WIDTH,245*mm)[1]+flowable.getSpaceBefore()+flowable.getSpaceAfter()


def keep_form_closing(story):
    height=0
    for index in range(len(story)-1,-1,-1):
        flowable=story[index]
        item_height=flowable_height(flowable)
        if isinstance(flowable,FormTable) and item_height+height>210*mm:
            # Preserve all rows and repeat the header on the closing page.
            reserve=max(0,120*mm-height)
            pieces=flowable.split(TEXT_WIDTH,item_height-reserve)
            if len(pieces)==2 and flowable_height(pieces[0])<=210*mm:
                story[index:index+1]=[pieces[0],PageBreak(),pieces[1]]
            break
        height+=item_height
        if height>=115*mm:
            if height<=210*mm:story[index:]=[KeepTogether(story[index:])]
            break


class ManualDocTemplate(SimpleDocTemplate):
    def beforeDocument(self):
        self.navigation_pages = {}
        # The declared page margins are the text margins, without Frame's
        # implicit six-point padding on each side.
        for template in self.pageTemplates:
            for frame in template.frames:
                frame._leftPadding=frame._rightPadding=0
                frame._topPadding=frame._bottomPadding=0
                frame._geom()
                frame._reset()

    def afterFlowable(self, flowable):
        if hasattr(flowable, 'navigation'):
            entry = flowable.navigation
            self.navigation_pages[entry['key']] = self.page
            self.canv.bookmarkPage(entry['key'])
            self.canv.addOutlineEntry(entry['title'], entry['key'], entry['level'], closed=False)


def cover_and_contents(catalog, pages):
    center = ParagraphStyle("CoverCN", fontName=REGULAR_FONT, fontSize=14,
                            leading=24, alignment=TA_CENTER, wordWrap="CJK", textColor=INK)
    title = ParagraphStyle("CoverTitle", parent=center, fontName=BOLD_FONT,
                           fontSize=20, leading=31, spaceAfter=12)
    contents_title = ParagraphStyle("ContentsTitle", parent=center, fontName=BOLD_FONT,
                                    fontSize=16, leading=25, spaceAfter=15)
    toc_styles = [ParagraphStyle(f'ContentsLevel{i}', fontName=BOLD_FONT if i==0 else REGULAR_FONT,
        fontSize=11, leading=16, wordWrap='CJK', alignment=TA_LEFT,
        leftIndent=i*7*mm, firstLineIndent=0, spaceBefore=0, spaceAfter=0) for i in range(2)]
    page_style=ParagraphStyle('ContentsPage',fontName=REGULAR_FONT,fontSize=11,leading=16,alignment=TA_RIGHT)
    rows=[]
    for entry in catalog:
        label=escape(entry['title'])
        if not entry.get('external'):
            label=f'<link href="#{entry["key"]}" color="#000000">{label}</link>'
        rows.append([Paragraph(label,toc_styles[entry['level']]),
                     Paragraph(str(pages.get(entry['key'],'—')),page_style)])
    table_style=TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
        ('TOPPADDING',(0,0),(-1,-1),1),('BOTTOMPADDING',(0,0),(-1,-1),1)])
    heights=Table(rows,colWidths=[TEXT_WIDTH-13*mm,13*mm],style=table_style).wrap(TEXT_WIDTH,245*mm)[1]
    count=max(1,int(math.ceil(heights/(225*mm))))
    # Balance the contents pages rather than spilling a single final entry.
    chunks=[];start=0
    for page in range(count):
        end=round(len(rows)*(page+1)/count)
        while end<len(rows) and catalog[end-1]['level']==0 and catalog[end]['level']==1:
            end-=1
        chunk=rows[start:end];start=end
        chunks += [Paragraph('目录' if page==0 else '目录（续）',contents_title),
                   Table(chunk,colWidths=[TEXT_WIDTH-13*mm,13*mm],style=table_style),PageBreak()]
    review = [Spacer(1, 8*mm), Paragraph('修订审阅稿', center)] if '--review' in sys.argv else []
    return [Spacer(1, 25*mm),
            Paragraph("第一届辽宁省大学生材料焊接与铸造工艺设计大赛", center),
            Spacer(1, 32*mm),
            Paragraph("QT450-10主轴承座与Q235B壳体<br/>焊接工艺设计", title),
            Spacer(1, 14*mm), Paragraph("参赛赛道：焊接工艺设计赛道·固定题目", center),
            Paragraph("作品类型：工艺设计说明书（含 pWPS 与工程图）", center),
            Spacer(1, 38*mm), Paragraph("2026年10月", center),
            *review, PageBreak(), *chunks]


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
    # Keep Chinese punctuation and Latin/number spacing consistent in prose.
    text=re.sub(r'(?<=[\u4e00-\u9fff])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[\u4e00-\u9fff])',' ',text)
    text=re.sub(r'(?<=\d)\s*(?=μm|µm|mm(?:/s|/min)?|MPa|GPa|kPa|kN|kJ|kg|J/mm|L/min|℃|°C|[AVWsgh](?![A-Za-z]))',' ',text)
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
        nodes[index]=re.sub(r'位置度|焊脚|焊趾|槽根|孔径|孔轴|热输入|层间温度',lambda m:'<nobr>'+m[0]+'</nobr>',nodes[index])
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


_STYLE_CACHE = {}


def report_styles(is_card):
    if is_card in _STYLE_CACHE:return _STYLE_CACHE[is_card]
    body = ParagraphStyle("CardBodyCN" if is_card else "BodyCN", fontName=REGULAR_FONT,
                          fontSize=9.5 if is_card else 12, leading=12.5 if is_card else 17.6,
                          wordWrap="CJK", alignment=TA_LEFT if is_card else TA_JUSTIFY,
                          firstLineIndent=0 if is_card else 24, spaceAfter=3 if is_card else 4,
                          textColor=INK, allowOrphans=0, allowWidows=0)
    no_indent = ParagraphStyle("NoIndentCN",parent=body,firstLineIndent=0)
    cell = ParagraphStyle("CellCN", parent=body, fontName=REGULAR_FONT,
                          fontSize=9 if is_card else 10.5, leading=11.8 if is_card else 14,
                          firstLineIndent=0, alignment=TA_LEFT, spaceAfter=0)
    header_cell = ParagraphStyle("HeaderCellCN", parent=cell, fontName=BOLD_FONT, textColor=INK)
    table_caption = ParagraphStyle("TableCaptionCN", parent=body, fontName=REGULAR_FONT,
                                   fontSize=10.5, leading=15, alignment=TA_CENTER, firstLineIndent=0,
                                   keepWithNext=True, spaceBefore=5, spaceAfter=4)
    figure_caption = ParagraphStyle("FigureCaptionCN", parent=table_caption,
                                    keepWithNext=False, spaceBefore=4, spaceAfter=5)
    reference = ParagraphStyle("ReferenceCN", parent=body, fontSize=10.5, leading=14.5,
                               firstLineIndent=0, alignment=TA_LEFT, spaceAfter=3)
    abstract_title = ParagraphStyle("AbstractTitle",parent=no_indent,fontName=BOLD_FONT,
                                    fontSize=14,leading=22,alignment=TA_CENTER,
                                    spaceBefore=7,spaceAfter=10,keepWithNext=True)
    references_title = ParagraphStyle("ReferencesTitle",parent=abstract_title,alignment=TA_LEFT)
    keyword = ParagraphStyle("KeywordCN",parent=body,firstLineIndent=0,alignment=TA_LEFT,
                             spaceBefore=5,spaceAfter=10)
    headings = {i: ParagraphStyle(f"CardH{i}" if is_card else f"H{i}", parent=no_indent,
                fontName=BOLD_FONT,fontSize=(12 if i<=2 else 11) if is_card else (14 if i<=2 else 12),
                leading=(17 if i<=2 else 15) if is_card else (21 if i<=2 else 18),spaceBefore=8,spaceAfter=5,
                textColor=INK,keepWithNext=True) for i in range(1,7)}
    result=dict(body=body,no_indent=no_indent,cell=cell,header_cell=header_cell,
        table_caption=table_caption,figure_caption=figure_caption,reference=reference,
        abstract_title=abstract_title,references_title=references_title,keyword=keyword,headings=headings)
    _STYLE_CACHE[is_card]=result
    return result


def build_story(source: Path = SOURCE) -> list:
    is_card=source.parent==ROOT/'deliverables/process'
    styles=report_styles(is_card)
    body,no_indent,cell,header_cell,table_caption,figure_caption,reference,abstract_title,references_title,keyword,headings = (
        styles[key] for key in ('body','no_indent','cell','header_cell','table_caption','figure_caption','reference','abstract_title','references_title','keyword','headings'))
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
        # Use the same proportions for tables with the same engineering role.
        proportions={
            (3,'步骤'):(.15,.50,.35),
            (3,'分配项'):(.29,.17,.54),
            (3,'假设或项目'):(.25,.34,.41),
            (4,'排序及等级'):(.18,.17,.41,.24),
            (4,'编号'):(.09,.22,.40,.29),
            (4,'载荷级'):(.22,.20,.36,.22),
        }
        if (n,table_rows[0][0]) in proportions:
            widths=[TEXT_WIDTH*w for w in proportions[(n,table_rows[0][0])]]
        if n==2:widths=[TEXT_WIDTH*40/170,TEXT_WIDTH*130/170]
        if n==3 and table_rows[0][0]=='项目':widths=[TEXT_WIDTH*30/170,TEXT_WIDTH*70/170,TEXT_WIDTH*70/170]
        if n==3 and table_rows[0][0]=='工序':widths=[TEXT_WIDTH*25/170,TEXT_WIDTH*48/170,TEXT_WIDTH*97/170]
        if n==3 and table_rows[0][1]=='当前设计输入及用途':widths=[TEXT_WIDTH*30/170,TEXT_WIDTH*90/170,TEXT_WIDTH*50/170]
        if n==4 and table_rows[0][0]=='输入':widths=[TEXT_WIDTH*25/170,TEXT_WIDTH*35/170,TEXT_WIDTH*35/170,TEXT_WIDTH*75/170]
        table = (FormTable if is_card else Table)(rows, colWidths=widths, repeatRows=1, hAlign="CENTER")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (-1, 0), 0.9, NAVY),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY),
            ("LINEBELOW", (0, -1), (-1, -1), 0.9, NAVY),
            ("LINEBELOW", (0, "splitlast"), (-1, "splitlast"), 0.5, NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 2.3 if is_card else 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2.3 if is_card else 3),
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
            story.append(table)
        story.append(Spacer(1, 4))
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
            height = 145*mm if image_path.parent.name=='final-entry' else (105*mm if not is_card else 100*mm)
            figure = figure_image(image_path,max_height=height)
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
            story.extend([KeepTogether(figure_prefix+[figure,Paragraph(inline(caption),figure_caption)]),Spacer(1,4)])
            continue
        if not line or line in {"---", "$$"} or line.startswith("```"):
            continue
        heading = re.match(r"^(#{1,6}) (.*)$", line)
        if heading:
            level,title=len(heading[1]),heading[2]
            if is_card and level==1 and not title.startswith('HJ-'):
                identifier=re.search(r'规程号\s*(HJ-[A-Z0-9-]+)',source.read_text(encoding='utf8'))
                if identifier:title=identifier[1]+' '+title
            if source==SOURCE and level==1:
                continue
            normalized=re.sub(r'\s+','',title)
            if not is_card and normalized in ('摘要','设计概要'):
                paragraph=navigation_paragraph(title,abstract_title,f'body-{line_index}',0)
            elif not is_card and normalized in ('参考文献','参考资料'):
                if story and not isinstance(story[-1],PageBreak):story.append(PageBreak())
                paragraph=navigation_paragraph(title,references_title,f'body-{line_index}',0)
            else:
                paragraph=Paragraph(inline(title),headings[level])
                if (not is_card and level in (2,3)) or (is_card and level==1):
                    paragraph=navigation_paragraph(title,headings[level],f'{source.stem}-{line_index}',1 if is_card or level==3 else 0)
            story.append(paragraph)
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
    if is_card:keep_form_closing(story)
    return story


def page_furniture(canvas, number, width, height, cover=False):
    canvas.saveState()
    canvas.setFillColor(INK)
    canvas.setFont(REGULAR_FONT,8.5)
    canvas.drawCentredString(width/2,6*mm,f'轴承座焊接工艺设计 · {number}')
    if not cover:
        canvas.setStrokeColor(colors.HexColor('#767676'))
        canvas.setLineWidth(.35)
        canvas.line(25*mm,height-5*mm,width-25*mm,height-5*mm)
    canvas.restoreState()


def on_page(canvas, doc) -> None:
    page_furniture(canvas,doc.page,*A4,cover=doc.page==1)


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
    def content(include_cards):
        story=build_story()
        if include_cards:
            appendix_style=ParagraphStyle('AppendixTitle',fontName=BOLD_FONT,fontSize=14,leading=22,
                spaceAfter=10,keepWithNext=True,textColor=INK,wordWrap='CJK')
            story += [PageBreak(),navigation_paragraph('附录A 工艺规程与检验卡',appendix_style,'appendix-a',0)]
            for index,card in enumerate(CARD_FILES):
                story += ([] if index==0 else [PageBreak()])+build_story(ROOT/'deliverables/process'/card)
        if include_cards and '--include-research-status' in sys.argv:
            story += [PageBreak()]+build_story(write_status_artifacts(ROOT))
        return story

    def render(path,include_cards,include_external):
        catalog=navigation_catalog(content(include_cards))+(external_catalog() if include_external else [])
        pages={}
        for target in (BytesIO(),str(path)):
            doc=ManualDocTemplate(target,pagesize=A4,leftMargin=25*mm,rightMargin=25*mm,
                topMargin=25*mm,bottomMargin=23*mm,
                title='QT450-10主轴承座与Q235B壳体焊接工艺设计',author='')
            doc.build(cover_and_contents(catalog,pages)+content(include_cards),onFirstPage=on_page,onLaterPages=on_page)
            located=dict(doc.navigation_pages)
            for entry in catalog:
                if entry.get('external'):located[entry['key']]=doc.page+1+entry['offset']
            if pages and located!=pages:raise ValueError('目录页码在两次排版间发生变化')
            pages=located
        return catalog,pages

    if '--competition-entry' in sys.argv:
        render(PAPER,False,False)
        print(f'参赛正文已生成：{PAPER}')
    catalog,pages=render(OUT,True,'--with-drawings' in sys.argv)
    print(f'说明书与工艺卡已生成：{OUT}')
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
        bundle=PdfWriter();bundle.append(OUT)
        bundle.append(drawing_out)
        if REPORT_CONFIG.get('illustration_pdf'):
            bundle.append(ROOT/REPORT_CONFIG['illustration_pdf'])
        bundle.add_metadata({'/Title':'QT450-10/Q235B 工艺设计说明书与工程图（修订审阅稿）',
                             '/Author':'','/Subject':f"当前MMA首层候选、工艺规程与{manifest['sheet_count']}张工程图"})
        combined=ROOT/'output/pdf/焊接工艺设计说明书与工程图-修订审阅稿.pdf'
        if '--competition-entry' in sys.argv:
            combined=ROOT/REPORT_CONFIG.get('combined_pdf','output/pdf/焊接工艺设计说明书与工程图.pdf')
            bundle.add_metadata({'/Title':'QT450-10主轴承座与Q235B壳体焊接工艺设计说明书与工程图','/Author':'',
                                 '/Subject':f"8P-R2-t15柔顺槽主方案、工艺规程及{manifest['sheet_count']}张工程图"})
        with combined.open('wb') as stream:bundle.write(stream)
        with fitz.open(combined) as pdf:
            from reportlab.pdfgen import canvas as pdfcanvas
            footer_buffer=BytesIO()
            footer=pdfcanvas.Canvas(footer_buffer,pagesize=(420*mm,297*mm))
            manual_pages=len(PdfReader(OUT).pages)
            for index in range(manual_pages,len(pdf)):
                page_furniture(footer,index+1,pdf[index].rect.width,pdf[index].rect.height)
                footer.showPage()
            footer.save()
            with fitz.open(stream=footer_buffer.getvalue(),filetype='pdf') as overlay:
                for index in range(manual_pages,len(pdf)):
                    page=pdf[index]
                    for block in page.get_text('blocks'):
                        if '参赛工艺设计图集' in block[4]:page.add_redact_annot(fitz.Rect(block[:4]),fill=(1,1,1))
                    page.apply_redactions(images=0,graphics=0)
                    page.show_pdf_page(page.rect,overlay,index-manual_pages)
            pdf.set_toc([[entry['level']+1,entry['title'],pages[entry['key']]] for entry in catalog])
            contents_end=min(pages.values())-1
            for entry in catalog:
                if not entry.get('external'):continue
                for page in list(pdf)[1:contents_end]:
                    for rect in page.search_for(entry['title']):
                        page.insert_link({'kind':fitz.LINK_GOTO,'from':rect,'page':pages[entry['key']]-1,'to':fitz.Point(0,0)})
            revised=combined.with_suffix('.navigation.pdf')
            pdf.save(revised,garbage=4,deflate=True)
        revised.replace(combined)
        compact_pdf(combined)
        print(f'说明书与工程图合订本已生成：{combined}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
