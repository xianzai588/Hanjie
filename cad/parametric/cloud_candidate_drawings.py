"""Consistent candidate parameter/weld sequence/workstation review drawings."""
from pathlib import Path
import xml.etree.ElementTree as ET
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4,landscape
from export_drawing_pdfs import register_fonts,parse_css,export_sheet

ROOT=Path(__file__).resolve().parents[2];NS='{http://www.w3.org/2000/svg}'


def build():
    register_fonts();out=ROOT/'output/cloud-20261005'
    replacements={
        '脉冲100/50 A；50%占空；20 Hz；12 V':'候选95/47.5 A；50%/20 Hz/12 V；未标定',
        '每道顺序 1→5→3→7→2→6→4→8':'每道对向同时1/5→3/7→2/6→4/8',
        '每道净热300 J/mm；在线窗口250～350':'候选净热285 J/mm；η0.55设计假设',
        '本件净热输入86.40 kJ；弧燃时间174.5 s':'名义净热82.08 kJ；双头同时弧燃87.27 s',
        'QT侧双层Ni99：总厚≥1.2；表层≥0.5；熔深≤0.4':'QT侧Ni99总≥1.2/表层≥0.5；重熔并集≤0.4',
        '1头，站占用462.5 s':'双头；完整站占用待计算',
        '焊接站462.5 s；装配120；需微珩时CMM2×360 s（≥2站）＋微珩200 s（≥1站）':'末次停弧213.27 s；冷却/释放另计；微珩分支CMM共720 s、微珩200 s',
        '固定定位窝数按 N≥ceil[(120＋工装释放时刻＋60)/462.5]；环境缓冲位另计':'定位窝N≥ceil[(装夹120＋完全释放时刻＋转运60)/站间隔T]；T待验证',
        'PT单件33～68 min：≥9等待位；UT600 s/件：≥2工位；检测人员≥5当量':'PT等待、UT及CMM按ceil(占用/T)配置；实际检测能力及完整节拍待资格',
        '工艺设计图 / 修订5':'云端候选审阅C1 / 未冻结',
        '试制检验按说明书执行':'执行HJ-W-01-C285候选卡',
    }
    for number,name in [('HJ-002','joint-detail'),('HJ-005','inspection-and-release'),('HJ-008','workstation')]:
        source=(ROOT/f'cad/generated/engineering-drawings/{name}.svg').read_text()
        for old,new in replacements.items():source=source.replace(old,new)
        root=ET.fromstring(source)
        if number=='HJ-005':
            for element in list(root):
                tag=element.tag.removeprefix(NS);a=element.attrib
                if ((tag=='circle' and a.get('cy')=='235') or
                    (tag=='text' and a.get('y')=='242') or
                    (tag=='line' and a.get('y1')==a.get('y2')=='235') or
                    (tag=='polygon' and ',235.00' in a.get('points',''))):root.remove(element)
            for i,pair in enumerate(('1 / 5','3 / 7','2 / 6','4 / 8')):
                x=65+i*145
                ET.SubElement(root,NS+'rect',dict(x=str(x),y='205',width='100',height='60',fill='#d7eef0',stroke='#176b7b'))
                ET.SubElement(root,NS+'text',dict(x=str(x+19),y='243',**{'class':'section'})).text=pair
                if i<3:
                    ET.SubElement(root,NS+'line',dict(x1=str(x+103),y1='235',x2=str(x+140),y2='235',stroke='#176b7b',**{'stroke-width':'2'}))
                    ET.SubElement(root,NS+'polygon',dict(points=f'{x+140},235 {x+132},230 {x+132},240',fill='#176b7b',stroke='#176b7b'))
            ET.SubElement(root,NS+'text',dict(x='630',y='242',**{'class':'small'})).text='每框为两头同时；根道/盖面同序'
        svg=out/f'{number}-cloud-review.svg';ET.ElementTree(root).write(svg,encoding='unicode')
        css=root.find(NS+'style').text;pdf=out/f'{number}-cloud-review.pdf'
        c=Canvas(str(pdf),pagesize=landscape(A4),author='',title=f'{number}候选审阅C1')
        export_sheet(svg,c,*landscape(A4),parse_css(css));c.showPage();c.save()


if __name__=='__main__':build()
