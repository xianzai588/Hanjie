"""Five physically scaled A3 drawings from the frozen geometry and fixture dimensions."""
from pathlib import Path
import math, json, sys
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from OCP.BRep import BRep_Builder
from OCP.BRepTools import BRepTools
from OCP.TopoDS import TopoDS_Shape, TopoDS
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.BRepAdaptor import BRepAdaptor_Curve

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'cad/generated/final-entry-drawings'
pdfmetrics.registerFont(TTFont('CN',str(ROOT/'assets/fonts/NotoSansSC-Regular.ttf')))
C=None

def line(x,y,X,Y,w=.35,dash=None):
    C.setLineWidth(w*mm);C.setDash(dash or []);C.line(x*mm,y*mm,X*mm,Y*mm);C.setDash([])
def text(x,y,s,size=2.6,align='left'):
    C.setFont('CN',size*mm)
    getattr(C,{'left':'drawString','center':'drawCentredString','right':'drawRightString'}[align])(x*mm,y*mm,s)
def poly(points,fill=None,w=.5,close=False):
    C.setLineWidth(w*mm);p=C.beginPath();p.moveTo(points[0][0]*mm,points[0][1]*mm)
    for x,y in points[1:]:p.lineTo(x*mm,y*mm)
    if close:p.close()
    if fill is not None:C.setFillGray(fill)
    C.drawPath(p,stroke=1,fill=fill is not None);C.setFillGray(0)
def rect(x,y,w,h,shade=None):poly([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],shade,close=True)
def circle(x,y,r,w=.35):C.setLineWidth(w*mm);C.circle(x*mm,y*mm,r*mm,stroke=1,fill=0)
def arrow(x,y,X,Y):
    line(x,y,X,Y,.18);a=math.atan2(Y-y,X-x);d=2.5
    poly([(X,Y),(X-d*math.cos(a)+.65*math.sin(a),Y-d*math.sin(a)-.65*math.cos(a)),
          (X-d*math.cos(a)-.65*math.sin(a),Y-d*math.sin(a)+.65*math.cos(a))],0,.18,True)
def leader(x,y,X,Y,s):arrow(x,y,X,Y);text(x,y+1.5,s)
def dh(x,X,y,fromy,s):
    line(x,fromy,x,y+2,.18);line(X,fromy,X,y+2,.18)
    arrow((x+X)/2,y,x,y);arrow((x+X)/2,y,X,y);text((x+X)/2,y+1.5,s,align='center')
def dv(y,Y,x,fromx,s):
    line(fromx,y,x+2,y,.18);line(fromx,Y,x+2,Y,.18)
    arrow(x,(y+Y)/2,x,y);arrow(x,(y+Y)/2,x,Y)
    C.saveState();C.translate((x-1.7)*mm,(y+Y)/2*mm);C.rotate(90);text(0,0,s,align='center');C.restoreState()
def center(x,y,w,h):line(x-w/2,y,x+w/2,y,.18,[10,2,2,2]);line(x,y-h/2,x,y+h/2,.18,[10,2,2,2])
def notes(x,y,items):
    for i,s in enumerate(items):text(x,y-i*5.2,f'{i+1}. {s}',2.55)
def frame(number,title,scale,material):
    rect(20,10,390,277);text(25,277,title,5);text(405,279,f'HJ-F0{number}',3.5,'right')
    rect(230,10,180,35);line(230,25,410,25);line(230,17,410,17);line(330,10,330,25);line(365,10,365,25)
    text(320,31,title,4,'center');text(233,20,'材料 / 配置：'+material,2.5)
    text(233,12,'图号 HJ-F0'+str(number),2.7);text(347,20,'比例 '+scale,2.6,'center')
    text(347,12,'单位 mm',2.6,'center');text(387,20,'2026.10',2.6,'center');text(387,12,f'第{number}张 / 共5张',2.6,'center')
    text(25,14,'工艺设计图；第一角投影；尺寸以标注为准；图签匿名',2.4)

def outline(cx,cy,s=1):
    shape=TopoDS_Shape();BRepTools.Read_s(shape,str(ROOT/'simulation/competition-r4/geometry/8P-R2-t15.brep'),BRep_Builder())
    ex=TopExp_Explorer(shape,TopAbs_EDGE);seen=set()
    while ex.More():
        c=BRepAdaptor_Curve(TopoDS.Edge_s(ex.Current()));a,b=c.FirstParameter(),c.LastParameter()
        pts=[c.Value(a+(b-a)*i/40) for i in range(41)]
        xy=[(round(p.X(),5),round(p.Y(),5)) for p in pts]
        key=min(tuple(xy),tuple(reversed(xy)))
        if key not in seen and len(set(xy))>1:
            poly([(cx+s*x,cy+s*y) for x,y in xy],w=.45);seen.add(key)
        ex.Next()

def fillet_symbol(x,y,target):
    # GB/T 324 reference line, arrow side fillet triangle, dashed secondary line.
    arrow(x,y,*target);line(x,y,x+68,y,.35);line(x+4,y+4,x+57,y+4,.18,[3,1.5])
    poly([(x+20,y),(x+20,y-5),(x+25,y)],w=.35,close=True)
    text(x+5,y-6,'z4',3);text(x+28,y-6,'16',3)
    line(x+68,y,x+74,y+4,.35);line(x+68,y,x+74,y-4,.35)
    text(x+75,y+1,'8处，45°均布',2.6);text(x+75,y-4,'根/盖两道，实际长18',2.6)

def seat():
    frame(1,'八翼柔顺槽座体零件图','1:1','QT450-10')
    outline(110,180);center(110,180,172,172)
    dh(35.02,184.98,94,180,'外圆 Ø149.94～149.98')
    dh(90,130,268,180,'最终孔 Ø40.000～40.025')
    leader(28,251,70,189,'8槽宽4.00，槽端R2.00')
    leader(143,259,151,180,'中心连续环 Ø82.00')
    leader(30,115,68,130,'槽内端R39.00；32处过渡R2')
    text(110,85,'俯视图（按真实R2实体投影）',3,'center')
    # Section through opposite wings: circular bore interrupts the central ring.
    for a,b in [(-74.98,-20),(20,74.98)]:
        pts=[(290+a,210),(290+b,210),(290+b,225),(290+a,225)]
        if a>0:pts=[(310,210),(364.98,210),(364.98,223.5),(358.98,223.5),(358.98,225),(310,225)]
        else:pts=[(215.02,210),(270,210),(270,225),(221.02,225),(221.02,223.5),(215.02,223.5)]
        poly(pts,.90,close=True)
    center(290,217.5,170,45);dv(210,225,382,365,'15.00');dh(358.98,364.98,238,224,'6.00')
    leader(250,250,360,223.5,'两端预制槽深1.50±0.10；槽底R1.50±0.10')
    text(290,196,'A—A 剖视（两相对翼中心）',3,'center')
    notes(225,173,['外缘浅槽沿八翼全宽贯通；所有槽口去毛刺。',
        '首层修整后法向留层0.70±0.05；修整圆角R0.65～0.95。',
        '两层覆盖后总厚1.50±0.10；连接外圆按标注精加工。',
        '预制后孔留成形余量；最终孔径在入壳装夹态一次成形。',
        '最终孔不得迁移轴线；卸夹后按装配图独立A/B验收位置度。',
        '未注线性尺寸公差±0.10；未注倒角0.5×45°；孔壁Ra≤0.8。'])

def weld():
    frame(2,'异种连接角焊缝详图','5:1','QT450-10 / Ni / Q235B')
    ox,oy,s=150,105,5
    def p(x,z):return ox+s*x,oy+s*z
    poly([p(-22,0),p(0,0),p(0,13.5),p(-6,13.5),p(-6,15),p(-22,15)],.92,close=True)
    rect(ox,oy-25,25,145,.82)
    rect(ox-30,oy+67.5,30,3.5,.62);rect(ox-30,oy+71,30,4,.96)
    poly([p(0,15),p(-4,15),p(0,19)],.45,close=True)
    line(*p(-2.8,15),*p(0,17.8),.25,[3,1.5]);center(ox+12.5,oy+60,65,185)
    dh(ox,ox+25,248,oy+100,'壳壁5.00');dv(oy,oy+75,30,40,'座体15.00')
    dh(ox-30,ox,195,oy+75,'槽宽6.00');dv(oy+67.5,oy+75,185,150,'总留层1.50±0.10')
    leader(28,209,*p(-3.5,13.85),'CI-A1高镍首层：法向0.70±0.05')
    leader(26,227,*p(-3.5,14.6),'低碳Ni99覆盖：最薄≥0.65')
    leader(208,145,*p(-1.0,17.0),'NiFe55根/盖共同形成一个角焊缝')
    fillet_symbol(208,229,p(-2,17))
    notes(210,203,['焊接符号按GB/T 324—2008；实线侧为箭头侧。',
       '总名义焊脚4.00；最小3.80；最短喉厚≥2.69。',
       '每段实际18，扣除两端各1后有效16；共8段。',
       '脉冲GTAW：100/50 A，50%，20 Hz，参考12 V。',
       '焊速1.65±2%；根道供丝3.42±0.05 mm/s。',
       '盖道供丝3.78±0.05 mm/s；NiFe55丝Ø1.60±0.01。',
       '最终重熔≤0.40；第二层存留≥0.25；段端无弧坑裂纹。',
       '接头pWPS及PQR组织见说明书第3、9章。'])
    text(100,77,'截面材料分区；虚线为根道参考轮廓；几何5:1',2.7,'center')
    text(210,151,'截面坐标：x向孔内，z向上；尺寸及层厚按实物测量。',2.5)

def assembly():
    frame(3,'八翼座体焊接装配图','1:1','明细见表')
    cx,y0=113,58
    rect(cx-80,y0,5,200,.86);rect(cx+75,y0,5,200,.86)
    for a,b in [(-74.98,-20),(20,74.98)]:rect(cx+a,y0+100,b-a,15,.94)
    for sign in [-1,1]:poly([(cx+sign*74.98,y0+115),(cx+sign*70.98,y0+115),(cx+sign*74.98,y0+119)],.5,close=True)
    center(cx,y0+100,180,215);dv(y0,y0+200,27,cx-80,'200.00');dv(y0,y0+100,202,cx+80,'100.00')
    dh(cx-80,cx+80,48,y0,'壳体外径 Ø160.00');leader(151,237,cx+75,y0+185,'内径 Ø150.00～150.02')
    # Datum symbols and position tolerance frame.
    arrow(57,66,57,y0);rect(46,67,15,7);text(53.5,69,'A',3.2,'center')
    for z in [25,175]:line(cx+73,y0+z,cx+80,y0+z,.7)
    leader(141,95,cx+75,y0+25,'B：两内壁带共同圆柱轴线')
    rect(62,198,93,9);line(75,198,75,207);line(125,198,125,207);line(140,198,140,207)
    circle(68.5,202.5,2,.25);line(65.5,202.5,71.5,202.5,.25);line(68.5,199.5,68.5,205.5,.25)
    text(100,200,'Ø0.05',3,'center');text(132.5,200,'A',3,'center');text(147.5,200,'B',3,'center')
    arrow(106,198,cx,y0+110)
    leader(46,216,cx-20,y0+115,'成品孔 Ø40.000～40.025；Ra≤0.8')
    circle(309,184,80);circle(309,184,75);outline(309,184);center(309,184,177,177)
    for i in range(8):
        a=i*math.pi/4;half=18/74.98/2
        pts=[(309+74.98*math.cos(a-half+2*half*j/30),184+74.98*math.sin(a-half+2*half*j/30)) for j in range(31)]
        poly(pts,w=1);text(309+85*math.cos(a),184+85*math.sin(a),str(i+1),2.7,'center')
    text(309,92,'八段按45°均布；图中粗线为实际18 mm弧段',2.6,'center')
    rows=[('序号','名称','材料','数量'),('1','壳体 Ø160×200','Q235B','1'),('2','8P-R2-t15 座体','QT450-10','1'),('3','首次界面留层','CI-A1','8处'),('4','低碳覆盖层','Ni99','8处'),('5','两道短角焊缝','NiFe55','8段')]
    for i,row in enumerate(rows):
        y=83-i*5.7;line(223,y-1,401,y-1,.18)
        for xx,ss in zip([226,243,334,382],row):text(xx,y,ss,2.45)
    text(30,33,'最终孔在闭底接液盘内装夹态成形；完全卸夹后建立独立A/B，位置度以本图验收。',2.55)
    text(30,25,'A平面度≤0.002；B带z20～30、170～180，圆度≤0.003，共同圆柱度≤0.004。',2.55)

def fixture():
    frame(4,'定位承力与退出工装总装图','1:3','45钢 / 17-4PH / C11000')
    cx,y0,s=114,97,1/3
    def R(x,z,w,h,shade=.90):rect(cx+x*s,y0+z*s,w*s,h*s,shade)
    R(-220,-160,440,140,.83);R(-72,-20,144,100);R(-36,80,72,14);R(-30,59.8,60,40,.78)
    poly([(cx-19.074*s,y0+100.2*s),(cx+19.074*s,y0+100.2*s),(cx+16.5*s,y0+114.8*s),(cx-16.5*s,y0+114.8*s)],.7,close=True)
    for a in [-80,75]:R(a,0,5,200,.96)
    for a in [-74.98,20]:R(a,100,54.98,15,.96)
    for a in [-20,19.2]:R(a,100.2,.8,45.2,.6)
    R(-35,155.4,23,244.6,.90);R(12,155.4,23,244.6,.90)
    R(-50,155.4,100,10,.72)
    for a in [-220,140]:R(a,-160,80,560,.94)
    R(-230,400,460,100,.83);R(-55,400,110,100,1)
    R(-74,87.59,148,1,.55);R(-74.8,90.5,3,9,.65);R(71.8,90.5,3,9,.65)
    # Independent pressure feet at R37 and ring from R37 to R52.
    R(-52,116,15,12,.55);R(37,116,15,12,.55)
    center(cx,y0+170*s,165,235)
    dh(cx-220*s,cx+220*s,34,y0-160*s,'法兰 Ø440 ×140；12-M36 / PCD360')
    dv(y0-160*s,y0+500*s,26,cx-230*s,'总高660.00');dh(cx-180*s,cx+180*s,272,y0+500*s,'门架净跨360.00')
    leader(160,76,cx+40*s,y0+10*s,'整体承力柱 Ø144×100')
    leader(162,127,cx+19*s,y0+108*s,'反向10°锥芯 / 六指胀套')
    leader(165,156,cx+45*s,y0+161*s,'Ø100机械止挡；打开后穿Ø110孔')
    leader(164,198,cx+30*s,y0+300*s,'承力筒 Ø70/Ø24，长244.60')
    # Separate upper interface enlarged 2:1, explicitly indicated.
    text(300,257,'退出顺序及行程（按1:3画出）',3,'center')
    rx,ry=303,94
    rect(rx-80*s,ry,5*s,200*s,.96);rect(rx+75*s,ry,5*s,200*s,.96)
    line(rx-85*s,ry+340*s,rx+85*s,ry+340*s,.25,[3,2])
    arrow(rx+35,ry+150*s,rx+35,ry+290*s);text(rx+38,ry+210*s,'壳体↑140',2.6)
    arrow(rx-35,ry+145*s,rx-35,ry+405*s);text(rx-33,ry+335*s,'芯组↑260',2.6)
    arrow(rx,ry+120*s,rx,ry+270*s);text(rx+3,ry+240*s,'压环↑150',2.6)
    notes(231,76,['枪丝↑150 → 压环↑150并锁止 → 张开上止挡。',
       '胀套主动退1.00；铜瓣径向退1.10±0.05。',
       '芯组↑260；四抽头退15到R93；壳体连托环↑140。',
       '孔内预载≤100 N；压环500±20 N；热反力额定5 kN。',
       '固定盘始终朝上；工具退位全过程持续气幕与抽吸。'])
    text(30,25,'总装几何与行程按既有工装尺寸；水气、密封和副压环接口详见工艺附图。',2.5)

def station():
    frame(5,'首批试制焊接工作站布置图','1:20','单头GTAW机器人 / 隔离工位')
    ox,oy,s=64,65,.05
    def R(x,y,w,h,label):
        rect(ox+x*s,oy+y*s,w*s,h*s,.95);text(ox+(x+w/2)*s,oy+(y+h/2)*s,label,2.8,'center')
    rect(ox,oy,6000*s,4000*s);dh(ox,ox+300,274,oy+200,'设计占地6000');dv(oy,oy+200,49,ox,'4000')
    R(0,0,6000,800,'主通道宽800（保持净空）')
    R(200,1000,800,1000,'装载 / 清洁封存');R(4800,1000,1000,800,'闭底湿检 / 孔成形')
    R(4800,2200,1000,800,'CMM / 干态内窥');R(200,2600,700,700,'PLC / HMI')
    R(1200,2900,700,700,'GTAW电源');R(1200,2000,700,600,'水冷 / 氩歧管')
    circle(ox+3200*s,oy+2350*s,1200*s,.18);circle(ox+3200*s,oy+2350*s,300*s,.5)
    text(ox+3200*s,oy+2350*s,'机器人',2.8,'center')
    R(3000,1100,600,600,'定位窝 / 工装')
    line(ox+4700*s,oy+800*s,ox+4700*s,oy+3900*s,.6,[5,2]);text(ox+4100*s,oy+3650*s,'隔离围护',2.6)
    arrow(ox+1100*s,oy+1400*s,ox+2900*s,oy+1400*s);arrow(ox+3650*s,oy+1400*s,ox+4750*s,oy+1400*s)
    text(25,47,'工件流：壳外预制 → 清洁封存 → 焊接 → 装夹态孔成形 → 卸夹几何 / 检测',2.7)
    notes(25,38,['配置尺寸为布置设计包络；采购时以实际设备接口和机器人可达范围复核。',
       '焊接侧与湿检侧隔离；集液、抽吸和收集筒留独立维护空间。',
       '首批单头，量产对向双头增配按同一位置度和洁净判据定型。'])

def main():
    global C
    OUT.mkdir(parents=True,exist_ok=True)
    names=['seat-part','weld-detail','weld-assembly','fixture-assembly','station-layout']
    sheets=[]
    for i,(name,draw) in enumerate(zip(names,[seat,weld,assembly,fixture,station]),1):
        C=canvas.Canvas(str(OUT/(name+'.pdf')),pagesize=(420*mm,297*mm))
        C.setTitle('HJ-F0'+str(i)+' '+name);C.setAuthor('');draw();C.showPage();C.save()
        sheets.append(dict(number=i,pdf=name+'.pdf',title=name,scale=['1:1','5:1','1:1','1:3','1:20'][i-1]))
    import fitz
    with fitz.open() as doc:
        for name in names:
            with fitz.open(OUT/(name+'.pdf')) as part:doc.insert_pdf(part)
        doc.set_metadata({'title':'八翼座体按比例工程图 HJ-F01～05','author':''})
        doc.save(OUT/'HJ-F-drawing-set.pdf',garbage=4,deflate=True)
        for i,page in enumerate(doc):page.get_pixmap(matrix=fitz.Matrix(1.25,1.25)).save(OUT/(names[i]+'.png'))
    (OUT/'pdf-exports.json').write_text(json.dumps(dict(sheet_count=5,sheets=sheets,page_size_mm=[420,297],unit='mm',
        geometry_source='simulation/competition-r4/geometry/8P-R2-t15.brep',fixture_source='project/competition-design.yaml',
        station_scope='Design layout envelopes; verify purchased equipment interfaces'),ensure_ascii=False,indent=2),encoding='utf8')
    print('Generated five scaled A3 drawings:',OUT)
if __name__=='__main__':main()
