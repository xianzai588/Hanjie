"""Build cloud review documents; never touch the formal submission paths."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'deliverables/report'))
sys.path.insert(0,str(ROOT/'src'))
from build_technical_report_pdf import build_story,REGULAR_FONT
from hanjie.reporting.fonts import register_project_fonts
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate,PageBreak,Image,Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
import io,fitz


def footer(canvas,doc):
    canvas.setFont(REGULAR_FONT,8)
    canvas.drawString(20*mm,11*mm,'云端工程审阅C1 · 完整验证未完成 · 正式提交包未替换')
    canvas.drawRightString(A4[0]-20*mm,11*mm,str(doc.page))


def document(path,story,title):
    doc=SimpleDocTemplate(str(path),pagesize=A4,leftMargin=20*mm,rightMargin=20*mm,
        topMargin=18*mm,bottomMargin=22*mm,title=title,author='')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)


def build():
    out=ROOT/'output/cloud-20261005';out.mkdir(parents=True,exist_ok=True)
    register_project_fonts(ROOT)
    record=ROOT/'docs/review/2026-10-05-云端实际恢复与工程设计.md'
    card=ROOT/'deliverables/process/cloud-candidate-pWPS.md'
    document(out/'candidate-WPS-C285.pdf',build_story(card),'HJ-W-01-C285 候选工艺设计审阅')
    story=build_story(record)
    heading=ParagraphStyle('CloudFigureTitle',fontName=REGULAR_FONT,fontSize=14,leading=20)
    story += [PageBreak(),Paragraph('实际部分制造状态与局部本构诊断',heading)]
    p=out/'partial-state/partial-state-cloud.png';fig=Image(str(p));width,height=fig.imageWidth,fig.imageHeight
    fig.drawWidth=170*mm;fig.drawHeight=height/width*170*mm
    story += [fig,Paragraph('32.909091 s提交状态；顶面采用真实QT三角形，截面采用保存单元值。不是冷态孔形或实测资料。',ParagraphStyle('CloudCaption',parent=heading,fontSize=9,leading=14))]
    p=out/'connection/layer-response.png';fig=Image(str(p));width,height=fig.imageWidth,fig.imageHeight
    fig.drawWidth=170*mm;fig.drawHeight=height/width*170*mm
    story += [PageBreak(),Paragraph('镍层三维塑性及侧向拘束敏感性',heading),fig,
        Paragraph('规定诊断张开30 μm/滑移10 μm、回零位移；Ni200轧材比较参数。受约束静水拉应力不会被J2屈服限制。不是接头资格或零载卸载。',ParagraphStyle('CloudCaption2',parent=heading,fontSize=9,leading=14))]
    document(out/'cloud-calculation-record.pdf',story,'云端实际恢复与工程设计记录')
    # Current review body and relevant workshop cards; obsolete 300 J/mm final
    # joint cards are not attached as the current candidate execution card.
    story=build_story(ROOT/'deliverables/report/technical-report-v4-unified.md')
    for name in ('Ni99-transition-pWPS.md','cloud-candidate-pWPS.md','copper-shield-card.md',
            'fixture-load-and-transfer-card.md','NDT-inspection-card.md','cleanliness-inspection-card.md',
            'bore-compensation-and-finish-card.md'):
        story += [PageBreak()]+build_story(ROOT/'deliverables/process'/name)
    document(out/'cloud-manual-review.pdf',story,'工艺设计说明书 云端工程审阅')
    drawings=fitz.open(ROOT/'cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf')
    if len(drawings)!=16:raise ValueError('expected the existing HJ001..016 drawing set')
    revised=fitz.open()
    for i in range(14):
        replacement=out/f'HJ-{i+1:03}-cloud-review.pdf'
        if replacement.exists():
            with fitz.open(replacement) as d:revised.insert_pdf(d)
        else:revised.insert_pdf(drawings,from_page=i,to_page=i)
    for name in ('HJ-015-cloud-review.pdf','HJ-016-cloud-review.pdf','HJ-017-connection-section.pdf'):
        with fitz.open(out/name) as d:revised.insert_pdf(d)
    for page in revised:
        overlay=io.BytesIO();c=Canvas(overlay,pagesize=(page.rect.width,page.rect.height),author='')
        c.setFont(REGULAR_FONT,7);c.drawString(20,7,'工程审阅C1 / 连接、控形、承载及实物洁净资格尚未完成 / 不作生产放行图');c.save()
        with fitz.open(stream=overlay.getvalue(),filetype='pdf') as d:page.show_pdf_page(page.rect,d,0)
    revised.set_metadata(dict(title='HJ001..017 云端工程图审阅C1',author=''))
    revised.save(out/'cloud-engineering-drawings.pdf')
    combined=fitz.open()
    for name in ('cloud-calculation-record.pdf','cloud-manual-review.pdf','cloud-engineering-drawings.pdf'):
        with fitz.open(out/name) as d:combined.insert_pdf(d)
    combined.set_metadata(dict(title='焊接工艺设计说明书、WPS及工程图 云端审阅C1',author=''))
    combined.save(out/'cloud-welding-design-review.pdf')
    stats={p.name:len(fitz.open(p)) for p in out.glob('*.pdf')}
    (out/'pdf-build-manifest.json').write_text(json.dumps(dict(pages=stats,formal_submission_replaced=False),ensure_ascii=False,indent=2),encoding='utf8')
    return stats


if __name__=='__main__':print(json.dumps(build(),ensure_ascii=False,indent=2))
