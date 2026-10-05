"""Local connection design section, independent of the formal drawing set."""
from pathlib import Path
import sys
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))


def build():
    out=ROOT/'output/cloud-20261005';out.mkdir(parents=True,exist_ok=True)
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">',
        '<style>text{font-family:sans-serif;font-size:18px;fill:#1e3448}.title{font-size:28px;font-weight:700}.small{font-size:16px}.section{font-size:21px;font-weight:700}</style>']
    def line(a,b,c,d,color='#1e3448',dash=None):
        parts.append(f'<line x1="{a}" y1="{b}" x2="{c}" y2="{d}" stroke="{color}" stroke-width="1.5"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
    def rect(x,y,w,h,color):parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" stroke="#1e3448"/>')
    def text(x,y,s,cls='small'):parts.append(f'<text x="{x}" y="{y}" class="{cls}">{escape(s)}</text>')
    def poly(points,color):parts.append(f'<polygon points="{points}" fill="{color}" stroke="#1e3448"/>')
    rect(20,20,1160,760,'#ffffff');text(45,64,'Ni99预制层、首次QT熔合边界与两道组焊连接剖面','title')
    text(1040,64,'HJ-017','section');text(45,99,'云端设计审阅 / NTS / 尺寸按HJ-W-00及HJ-W-01-C285；PMZ宽度未赋定值')
    # Finished pocket and layers: nominal1.5, first0.65, second0.85.
    rect(105,347,345,225,'#efd18b');rect(270,347,180,25.5,'#8bb5ad');rect(270,372.5,180,19.5,'#bed4ce')
    rect(461,178,150,394,'#cbd5e1')
    poly('341,347 461,347 461,227','#db9681')
    poly('377,347 461,347 461,263','#bd6b54')
    line(270,392,450,392,'#b91c1c','5,3')
    text(135,548,'QT450-10，座体t15');text(466,599,'Q235B，壳体t5')
    text(82,175,'局部截面（层厚示意放大）','section')
    line(461,227,611,227);text(486,217,'总焊脚4.0')
    line(377,347,377,305);line(377,305,195,305);text(112,295,'根道目标2.8')
    line(270,347,236,244);text(110,234,'第二层加工后≥0.50')
    line(292,392,206,450);text(78,476,'首次Ni99/QT熔合线')
    text(78,504,'PMZ/HAZ位于QT侧；宽度由热循环/组织定位')
    line(290,362,186,616);text(66,642,'加工后总Ni99≥1.20；残层≥0.80')
    line(450,440,450,470);line(461,440,461,470);line(450,462,461,462)
    text(349,492,'装配径向间隙0.01～0.04')
    text(270,676,'浅槽：18×6；深1.50±0.10；端部R1.5')
    notes=[
        '1 先预制Ni99两层、PT、加工后清洗，再组焊。',
        '2 图示首层0.65/第二层0.85为名义工序截面；',
        '   实际厚度按三级截面记录，不把示意厚度当测量。',
        '3 根道Ni99重熔设计上限0.30；两道并集≤0.40。',
        '   完整第二层余厚≥0.10；不以总层厚替代检验。',
        '4 NiFe/Ni99与NiFe/Q235两侧须连续有效熔合；',
        '   熔敷面积、总能量或峰温不单独证明连接。',
        '5 首次QT侧PMZ不能借用QT母材或纯镍许用值。',
        '   记录局部最大主拉、三轴度与塑性路径。',
        '6 Ni99采用完整三维弹塑性应力状态；受约束层',
        '   的静水拉应力不会被J2屈服自动截断。',
        '7 当前整件候选仍为三实体+弹性薄层连接模型。',
        '   显式层/PMZ替换及整件反馈尚未完成。',
        '8 根层塑性、双侧熔合和QT侧失效参数核验后，',
        '   重新计算完全卸夹孔形和同残余状态承载。',
        '9 正常产品禁腔内打磨；NDT/微珩防护分别按',
        '   HJ-015/HJ-016，排液干燥后闭合撤出。']
    for i,note in enumerate(notes):text(650,159+29*i,note)
    line(45,714,1155,714);text(45,745,'单位mm / 比例NTS / 设计审阅C1 / 未作为完整连接强度通过证据')
    text(45,771,'仅标注工序控制尺寸；PMZ、熔合轮廓及材料失效依据待对应工艺核验')
    parts.append('</svg>');p=out/'HJ-017-connection-section.svg';p.write_text('\n'.join(parts),encoding='utf8')
    sys.path.insert(0,str(ROOT/'cad/parametric'))
    from export_drawing_pdfs import parse_css,export_sheet,register_fonts
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import A4,landscape
    import xml.etree.ElementTree as ET
    register_fonts();root=ET.parse(p).getroot();css=root.find('{http://www.w3.org/2000/svg}style').text
    pdf=out/'HJ-017-connection-section.pdf';c=Canvas(str(pdf),pagesize=landscape(A4),author='',title='局部冶金连接设计剖面 / 审阅C1')
    export_sheet(p,c,*landscape(A4),parse_css(css));c.showPage();c.save()
    return pdf


if __name__=='__main__':print(build())
