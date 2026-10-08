"""从当前参赛正文构建设计说明书；历史文件名保留以兼容已有入口。"""
from __future__ import annotations

from html import escape
from pathlib import Path
import json
import hashlib
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
from hanjie.reporting.publication import fingerprints, image_dependencies, validate_ring_production_release
from hanjie.domain.competition_design import current_assessment
import yaml

REGULAR_FONT = "HanjieCN"
BOLD_FONT = "HanjieCN-Bold"
SANS_FONT = "HanjieCN-Sans"
PAPER = ROOT / "output/pdf/焊接工艺设计论文-正文.pdf"
NAVY = colors.HexColor("#24364B")


class ManualDocTemplate(SimpleDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            title = flowable.getPlainText()
            if flowable.style.name == "CardH1" or (flowable.style.name == "H2" and re.match(r'^[0-9] ',title)) or (flowable.style.name == "H1" and
                    title.startswith(("HJ-S01", "HJ-W-S01", "HJ-M-01", "计算依据索引", "当前候选", "主轴承座—", "HJ-W-00", "HJ-W-02", "HJ-C-01", "HJ-C-02", "HJ-Q-01", "HJ-Q-02", "HJ-Q-03", "HJ-F-01"))):
                self.notify("TOCEntry", (0, title, self.page))


def cover_and_contents():
    center = ParagraphStyle("CoverCN", fontName=REGULAR_FONT, fontSize=16,
                            leading=26, alignment=1, wordWrap="CJK")
    title = ParagraphStyle("CoverTitle", parent=center, fontName=BOLD_FONT,
                           fontSize=24, leading=37, spaceAfter=16)
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("ContentsCN", fontName=REGULAR_FONT,
                                     fontSize=10.5, leading=20, wordWrap="CJK")]
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
    body = ParagraphStyle("BodyCN", fontName=REGULAR_FONT, fontSize=9.5 if is_card else 10.5,
                          leading=13.5 if is_card else 16.5, wordWrap="CJK", spaceAfter=4 if is_card else 6,
                          allowOrphans=0, allowWidows=0)
    cell = ParagraphStyle("CellCN", parent=body, fontName=SANS_FONT, fontSize=8.3, leading=12.5)
    header_cell = ParagraphStyle("HeaderCellCN", parent=cell, fontName=BOLD_FONT, textColor=NAVY)
    table_caption = ParagraphStyle("TableCaptionCN", parent=body, fontName=BOLD_FONT,
                                   keepWithNext=True, spaceBefore=4, spaceAfter=5)
    reference = ParagraphStyle("ReferenceCN", parent=body, fontSize=9, leading=13, spaceAfter=4)
    headings = {i: ParagraphStyle(f"CardH{i}" if is_card else f"H{i}", parent=body, fontName=BOLD_FONT,
                fontSize=19 if i == 1 else 14 if i == 2 else 11,
                leading=25 if i == 1 else 19, spaceBefore=12, spaceAfter=7, textColor=NAVY,
                keepWithNext=True) for i in range(1, 7)}
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
        widths=[170*mm/n]*n
        if n==2:widths=[40*mm,130*mm]
        if n==3 and table_rows[0][0]=='项目':widths=[30*mm,70*mm,70*mm]
        if n==3 and table_rows[0][0]=='工序':widths=[25*mm,48*mm,97*mm]
        if n==3 and table_rows[0][1]=='当前设计输入及用途':widths=[30*mm,90*mm,50*mm]
        if n==4 and table_rows[0][0]=='输入':widths=[25*mm,35*mm,35*mm,75*mm]
        table = Table(rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEABOVE", (0, 0), (-1, 0), 0.9, NAVY),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, NAVY),
            ("LINEBELOW", (0, -1), (-1, -1), 0.9, NAVY),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        height=table.wrap(170*mm,250*mm)[1]
        opening=table.split(170*mm,70*mm) if height>190*mm else []
        if len(opening)>1:
            first=[pending_caption,opening[0]] if pending_caption is not None else [opening[0]]
            story.append(KeepTogether(first))
            story.extend(opening[1:])
            pending_caption=None
        elif pending_caption is not None:
            if height<=200*mm:
                story.append(KeepTogether([pending_caption,table]))
            else:
                story.extend([pending_caption,table])
            pending_caption=None
        else:
            story.append(KeepTogether([table]) if len(rows)<=7 and height<=90*mm else table)
        story.append(Spacer(1, 6))
        table_rows.clear()

    source_lines=source.read_text(encoding="utf-8").splitlines()
    consumed_captions=set()
    for line_index,line in enumerate(source_lines):
        if line_index in consumed_captions:continue
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
            image_path = ROOT / illustration[2]
            if not image_path.is_file():
                image_path = (source.parent / illustration[2]).resolve()
            figure = Image(str(image_path))
            ratio = min(170*mm/figure.imageWidth, 99*mm/figure.imageHeight)
            figure.drawWidth = figure.imageWidth*ratio
            figure.drawHeight = figure.imageHeight*ratio
            caption=illustration[1]
            for next_index in range(line_index+1,len(source_lines)):
                following=source_lines[next_index].strip()
                if not following:continue
                if re.match(r'^图\s*\d+',following):
                    caption=following
                    consumed_captions.add(next_index)
                break
            story.extend([KeepTogether([figure,Paragraph(inline(caption),cell)]),Spacer(1,6)])
            continue
        if not line or line in {"---", "$$"} or line.startswith("```"):
            continue
        heading = re.match(r"^(#{1,6}) (.*)$", line)
        if heading:
            if source==SOURCE and len(heading[1])==1:
                continue  # The full document title is already on the cover.
            story.append(Paragraph(inline(heading[2]), headings[len(heading[1])]))
        else:
            style = table_caption if re.match(r'^表\s*\d+',line) else reference if re.match(r'^\[\d+\]',line) else body
            paragraph=Paragraph(inline(line.removeprefix("> ")), style)
            if style is table_caption:
                pending_caption=paragraph
            else:
                story.append(paragraph)
    flush_table()
    if pending_caption is not None:story.append(pending_caption)
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
                f"{p['fixed_feed_mm_s']:.2f}±0.05",
                "20±1℃", "热残余允许上限"]
    compact = re.sub(r"\s+", "", body)
    heat_values=[float(v) for v in re.findall(r'净热\s*([0-9.]+)\s*kJ',body)]
    if not any(abs(v-p['total_net_heat_j']/1000)<0.005 for v in heat_values):
        raise ValueError('当前正文关键数值与计算不一致：名义总净热')
    if any(re.sub(r"\s+", "", value) not in compact for value in required):
        raise ValueError("当前正文关键数值与计算不一致，必须同步论证后再发布")
    ring=json.loads((ROOT/'deliverables/process/ring-final-welding-card.json').read_text(encoding='utf8'))
    baseline=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text(encoding='utf8'))
    length=ring['segments']*ring['passes']*ring['actual_path_per_segment_per_pass_mm']
    if abs(length-baseline['weld_layout']['total_arc_length_mm'])>1e-8:
        raise ValueError('圆环实际路径与基准输入不一致')
    if abs(length*ring['nominal_net_line_energy_J_mm']/1000-ring['nominal_net_heat_kJ'])>1e-8:
        raise ValueError('圆环含起停热量未闭合')
    for value in (f"{length:.0f} mm",f"{ring['nominal_net_heat_kJ']:.1f} kJ",f"{ring['arc_on_time_s']:.2f} s"):
        if re.sub(r'\s+','',value) not in compact:raise ValueError('圆环正文数值缺失：'+value)
    if '--competition-entry' in sys.argv:
        structure=json.loads((ROOT/'simulation/ring-baseline-structure/results/assessment.json').read_text())
        manufacture=json.loads((ROOT/'simulation/ring-baseline-manufacturing/results/assessment.json').read_text())
        current_values=[f"{structure['combined']['axis_diameter_envelope_um']:.3f}",
                        f"{structure['combined']['elastic_strain_energy_N_mm']:.3f}",
                        f"{structure['combined']['raw_quadrature_stress_by_material']['5']['von_mises_max_MPa']:.2f}",
                        *[f"{manufacture['cold_response_summary'][mode]['position_diameter_um']:.4f}" for mode in
                          ('first_harmonic_final_shrink','first_harmonic_precoat_redistribution')]]
        heat=manufacture['thermal_result']
        current_values += [f"{heat['tooling_exit']['time_s']:.3f}",
                           f"{heat['tooling_exit']['part_max_C']:.3f}",
                           f"{heat['end_s']:.3f}", f"{heat['final_max_C']:.4f}",
                           f"{heat['material_peak_C']['4']:.3f}",
                           f"{heat['material_peak_C']['2']:.3f}"]
        if any(value not in compact for value in current_values):
            raise ValueError('当前圆环计算改变，须同步正文数值及解释后再渲染')


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
        write_status_artifacts(ROOT)
        state=json.loads((ROOT/'deliverables/report/generated/current-status.json').read_text(encoding='utf8'))
        baseline=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text(encoding='utf8'))
        validate_ring_production_release(state, baseline['version'])
    if '--competition-entry' in sys.argv:
        write_status_artifacts(ROOT)  # Standalone PDF entry must not bypass active-object identity.
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
    if '--competition-entry' in sys.argv:
        paper_doc = ManualDocTemplate(str(PAPER), pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                        topMargin=18*mm, bottomMargin=22*mm,
                        title='QT450-10主轴承座与Q235B壳体焊接工艺设计', author='')
        paper_doc.multiBuild(cover_and_contents()+build_story(),onFirstPage=on_page,onLaterPages=on_page)
        print(f'参赛正文已生成：{PAPER}')
    # 工艺卡与正文使用同一套字体、表格和页码样式。
    story = cover_and_contents() + build_story()
    # The workshop cards belong in the readable manual, not only in loose attachments.
    for card in ("ring-baseline-design-card.md", "ring-final-welding-card.md", "ring-fixture-design-card.md", "ring-automation-card.md", "manufacturing-and-inspection-card.md", "NDT-inspection-card.md", "ring-ut-coverage-design.md", "cleanliness-inspection-card.md", "bore-compensation-and-finish-card.md", "ring-production-resource-card.md", "calculation-index.md"):
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
        # HJ-S01 is the complete-ring baseline. HJ-001..021 retain their
        # original eight-wing candidate identity and are preceded by a scope page.
        import fitz
        ring=ROOT/'cad/generated/ring-baseline/HJ-S01-ring-baseline.pdf'
        ringdoc=fitz.open();page=ringdoc.new_page(width=A4[1],height=A4[0])
        page.insert_image(fitz.Rect(15,15,A4[1]-15,A4[0]-15),
                          filename=str(ring.with_suffix('.png')),keep_proportion=True)
        page=ringdoc.new_page(width=A4[1],height=A4[0])
        page.insert_image(fitz.Rect(15,15,A4[1]-15,A4[0]-15),
                          filename=str(ring.parent/'HJ-S02-ring-precoat-section.png'),keep_proportion=True)
        ringdoc.set_metadata({'title':'HJ-S01/S02 完整圆环总装与局部预制断面','author':''})
        ringdoc.save(ring,garbage=4,deflate=True);ringdoc.close()
        scope=ROOT/'output/pdf/工程图对象说明.pdf'
        scope_doc=SimpleDocTemplate(str(scope),pagesize=A4,leftMargin=20*mm,rightMargin=20*mm,
                                   title='工程图对象说明',author='')
        scope_style=ParagraphStyle('Scope',fontName=REGULAR_FONT,fontSize=12,leading=21,wordWrap='CJK')
        scope_doc.build([
            Paragraph('工程图对象与使用顺序',ParagraphStyle('ScopeTitle',parent=scope_style,fontName=BOLD_FONT,fontSize=20,leading=30)),
            Spacer(1,12*mm),
            Paragraph('HJ-F-S01～S03：圆环专属紧凑载荷环、实体屏障与受控退出。HJ-S01：完整圆环座体与Q235B壳体的名义母件总装。HJ-S02：圆环局部预制窗口、存留层及加工断面。八段短焊位置与实际电弧行程分别标注，过渡层与槽加工按基准卡执行。',scope_style),
            Spacer(1,8*mm),
            Paragraph('HJ-001至HJ-021：已建立的八翼开口结构创新候选及其夹具、洁净防护、预制公差和检测图。图中的翼形、预制用量和工位数量保留原对象身份，作为候选比较与工程细化依据。',scope_style),
            Spacer(1,8*mm),
            Paragraph('图纸按对象使用：完整环的环向载荷通道与开口八翼的柔顺槽不同，不能通过改图名互换；相同的焊段布局可共用焊长与送丝守恒核算，热史、残余变形和刚度另按对应实体评价。',scope_style)
        ],onFirstPage=on_page,onLaterPages=on_page)
        fixture=ROOT/'cad/generated/ring-fixture/HJ-F-S01-ring-fixture-drawings.pdf'
        if not fixture.is_file():raise FileNotFoundError('先生成圆环专属工装图：'+str(fixture))
        drawing_bundle=PdfWriter();drawing_bundle.append(scope);drawing_bundle.append(ring);drawing_bundle.append(fixture);drawing_bundle.append(drawings)
        drawing_bundle.add_metadata({'/Title':'完整圆环基准与八翼创新候选工程图集','/Author':''})
        drawing_out=ROOT/'output/pdf/基准与候选工程图集.pdf'
        with drawing_out.open('wb') as stream:drawing_bundle.write(stream)
        # Merge duplicate embedded fonts from independently exported sheets.
        # This preserves page content while keeping the downloadable package compact.
        def compact_pdf(path):
            tmp=path.with_suffix('.compact.pdf')
            with fitz.open(path) as pdf:pdf.save(tmp,garbage=4,deflate=True)
            tmp.replace(path)
        compact_pdf(drawing_out)
        bundle=PdfWriter();bundle.append(OUT);bundle.append(drawing_out)
        bundle.add_metadata({'/Title':'QT450-10/Q235B 工艺设计说明书与工程图（修订审阅稿）',
                             '/Author':'','/Subject':f"当前MMA首层候选、工艺规程与{manifest['sheet_count']}张工程图"})
        combined=ROOT/'output/pdf/工艺设计说明书与工程图-修订审阅稿.pdf'
        if '--competition-entry' in sys.argv:
            combined=ROOT/'output/pdf/工艺设计说明书与工程图-参赛设计稿.pdf'
            bundle.add_metadata({'/Title':'QT450-10/Q235B 焊接工艺设计说明书与工程图','/Author':'',
                                 '/Subject':'完整圆环设计基准、八翼创新候选、工艺卡与工程图'})
        with combined.open('wb') as stream:bundle.write(stream)
        compact_pdf(combined)
        print(f'统一审阅稿已生成：{combined}')
    if '--competition-entry' in sys.argv and '--with-drawings' in sys.argv:
        source_paths=[SOURCE,ROOT/'project/submission-baseline.yaml',ROOT/'project/report.yaml',
                      *[ROOT/'deliverables/process'/name for name in (
                        'ring-baseline-design-card.md','ring-final-welding-card.md','ring-fixture-design-card.md',
                        'ring-automation-card.md','manufacturing-and-inspection-card.md','NDT-inspection-card.md',
                        'cleanliness-inspection-card.md','bore-compensation-and-finish-card.md',
                        'ring-ut-coverage-design.md',
                        'ring-production-resource-card.md','calculation-index.md')],
                      ROOT/'cad/generated/ring-fixture/HJ-F-S01-ring-fixture-drawings.pdf']
        source_paths += image_dependencies(ROOT,[p for p in source_paths if p.suffix=='.md'])
        source_paths += [ROOT/name for name in (
            'cad/generated/ring-baseline/geometry-quality-and-mass.json',
            'cad/generated/ring-baseline/ring-precoat-design.json',
            'cad/generated/ring-baseline/HJ-S01-ring-baseline.png',
            'cad/generated/ring-baseline/HJ-S02-ring-precoat-section.png',
            'deliverables/process/ring-final-welding-card.json',
            'studies/COMPETITION-DESIGN/results/ring-fixture-feasibility.json',
            'studies/COMPETITION-DESIGN/results/ring-production-resources.json',
            'simulation/ring-baseline-structure/results/assessment.json',
            'simulation/ring-baseline-manufacturing/results/assessment.json',
            'automation/app/results/demo-summary.json',
            'automation/app/results/complete-weld-replay-summary.json',
            'automation/path-planning/results/weld-path.json',
            'deliverables/report/generated/current-status.json',
            'cad/generated/ring-baseline/ring-assembly-QT450-10-Q235B.step',
            'cad/generated/ring-baseline/ring-seat-QT450-10.step',
            'cad/generated/ring-baseline/ring-precoat-eight-windows-17solids.step',
            'cad/generated/ring-fixture/ring-fixture-assembly.step',
            'cad/generated/ring-fixture/geometry-quality-and-bom.json',
            'simulation/ring-baseline-structure/results/medium/mesh.npz',
            'docs/report/figures/publication/ring-ut-coverage.pdf',
            'scripts/generate-ring-ut-coverage.py',
            'cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf',
            'deliverables/report/build_technical_report_pdf.py',
            'src/hanjie/reporting/fonts.py',
            'src/hanjie/reporting/current_status.py',
            'simulation/ring-baseline-structure/model_inputs.py',
            'src/hanjie/reporting/publication.py')]
        source_paths += [p for p in (ROOT/'assets/fonts').iterdir() if p.is_file()]
        outputs=[OUT,PAPER,ROOT/'output/pdf/基准与候选工程图集.pdf',combined]
        state={'process_version':yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text())['version'],
               'sources':fingerprints(ROOT,source_paths),
               'outputs':fingerprints(ROOT,outputs)}
        (ROOT/'output/pdf/ring-publication-build.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
