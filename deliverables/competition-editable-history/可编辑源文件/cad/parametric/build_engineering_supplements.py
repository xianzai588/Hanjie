"""Vector tolerance, UT access and manufacturing BOM sheets from current design."""
import json,math,sys
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape,A3
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
import fitz
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from hanjie.reporting.fonts import register_project_fonts
OUT=ROOT/'cad/generated/engineering-supplements-20261007'
W,H=landscape(A3)


def text(c,x,y,t,size=11,color='#24384a'):
    c.setFillColor(HexColor(color));c.setFont('HanjieCN',size);c.drawString(x,y,str(t))


def line(c,x,y,xx,yy,color='#506579',width=1):
    c.setStrokeColor(HexColor(color));c.setLineWidth(width);c.line(x,y,xx,yy)


def begin(number,title,subtitle):
    file=OUT/f'HJ-DRW-{number:03d}.pdf'
    c=canvas.Canvas(str(file),pagesize=(W,H));c.setTitle(f'HJ-{number:03d} {title}');c.setAuthor('')
    c.setStrokeColor(HexColor('#24384a'));c.rect(22,22,W-44,H-44)
    text(c,42,H-58,title,23);text(c,W-140,H-58,f'HJ-{number:03d}',18)
    text(c,42,H-84,subtitle,11)
    line(c,40,66,W-40,66)
    text(c,42,45,'工艺设计工程图 | 单位mm | NTS，不按比例量图 | 2026-10-08 | 技术文件匿名',10)
    return c,file


def poly(c,points,fill,stroke='#506579'):
    p=c.beginPath();p.moveTo(*points[0])
    for q in points[1:]:p.lineTo(*q)
    p.close();c.setFillColor(HexColor(fill));c.setStrokeColor(HexColor(stroke));c.drawPath(p,fill=1,stroke=1)


def notes(c,items,x,y,step=22,size=11):
    for i,t in enumerate(items):text(c,x,y-step*i,t,size)


def column_notes(c,items,x,y,width,step=18,size=10.5):
    for item in items:
        row=''
        for char in item:
            if row and pdfmetrics.stringWidth(row+char,'HanjieCN',size)>width:
                text(c,x,y,row,size);y-=step;row=char
            else:row+=char
        text(c,x,y,row,size);y-=step
    return y


def pocket(depth,offset):
    cr,cz,R=70.48,115-depth+1.5,1.5-offset
    end=-math.pi if cz<=115 else -math.pi+math.asin((cz-115)/R)
    roof=cr-R if cz<=115 else cr-math.sqrt(R*R-(115-cz)**2)
    arc=[(cr+R*math.cos(-math.pi/2+(end+math.pi/2)*i/80),cz+R*math.sin(-math.pi/2+(end+math.pi/2)*i/80)) for i in range(81)]
    return [(roof,115),(74.98,115),(74.98,cz-R),*arc,(roof,115)]


def section():
    audit=json.loads((ROOT/'cad/generated/precoat-tolerance-family-20261007/geometry-and-feed-audit.json').read_text())
    c,file=begin(19,'R1.5预制槽、真实公差与法向修整截面','与HJ-017及HJ-W-00C/00D/00E关联；材料分区来自8P座体真实CAD')
    def xy(r,z):return (64+(r-68.5)*87,390+(z-113.25)*108)
    poly(c,[xy(68.5,113.25),xy(75.05,113.25),xy(75.05,115),xy(68.5,115)],'#d9dee2')
    poly(c,[xy(*p) for p in pocket(1.5,0)],'#a9c9ba')
    poly(c,[xy(*p) for p in pocket(1.5,.7)],'#bfd8ea')
    notes(c,['QT450-10','首层CI-A1：按槽底法向0.70±0.05','第二层：齐平总层1.40～1.60'],65,352,size=11)
    text(c,380,580,'连接面 z115.00',12)
    text(c,183,520,'圆心(R70.48,z115.00)',11)
    text(c,135,450,'QT R1.50；修整名义R0.80',11)
    text(c,420,540,'平直区第二层≥0.65',11)
    text(c,640,497,'R74.98',10)
    text(c,68,598,'局部放大剖面（径向/高度比例不同，尺寸以标注为准）',11)
    text(c,735,598,'实际公差实体 / 每翼体积mm³',13)
    notes(c,['D / R / N    槽体积     首层存留    第二层存留'],735,570,size=10)
    for i,r in enumerate(audit['cases']):
        text(c,735,544-21*i,f'{r["pocket_depth_mm"]:.2f}/{r["QT_radius_mm"]:.2f}/{r["retained_normal_mm"]:.2f}   {r["actual_pocket_volume_one_wing_mm3"]:.3f}    {r["retained_first_volume_one_wing_mm3"]:.3f}    {r["final_second_volume_one_wing_mm3"]:.3f}',10)
    notes(c,['九个实体：第二层/QT直接共享面均为0。',
             'D<R时刀具圆被原顶面裁边；D>R时增加直壁。',
             '各公差件按实测槽底定圆心，不独立固定z115。',
             'R槽1.50±0.10；R修整=R槽−N，范围0.65～0.95。'],735,339,step=20,size=10)
    notes(c,['1. 首层表面轮廓覆盖最大0.75法向保留包络，局部欠填/夹渣/裂纹不得进入保留层。',
             f'2. 实际最大槽{audit["maximum_actual_pocket_volume_one_wing_mm3"]:.6f} mm³/翼，设计密度下填槽至少{audit["maximum_pocket_fill_mass_g"]:.6f} g；100 mm/min保留为pWPS基线。',
             f'3. 120 mm/min、0.15 g/s情景欠填{-audit["feed_scenarios"][2]["mass_margin_g"]:.6f} g；0.17 g/s、速度+2%情景欠填{-audit["feed_scenarios"][4]["mass_margin_g"]:.6f} g。',
             '4. 本图为加工公差实体；带残余应力的实际去料/重平衡须接续有效冷态制造状态。'],65,244,size=12)
    c.save();return file


def ut():
    c,file=begin(20,'异种接头专用UT可达与覆盖设计','与HJ-Q-01配套；直线射线为几何可达预检，声束折射/衰减/盲区由同材料对比块资格确定')
    X=lambda r:90+(r-65)*35
    Y=lambda z:360+(z-110)*12
    poly(c,[(X(65),Y(110)),(X(75),Y(110)),(X(75),Y(115)),(X(65),Y(115))],'#d9dee2')
    poly(c,[(X(75),Y(110)),(X(80),Y(110)),(X(80),Y(138)),(X(75),Y(138))],'#c5d7e7')
    poly(c,[(X(71),Y(115)),(X(75),Y(115)),(X(75),Y(119))],'#dccbad')
    line(c,X(68.98),Y(113.5),X(74.98),Y(113.5),'#af442b',2)
    text(c,100,720,'径向-轴向局部示意 / 座体底部省略，壳体R75～80',12)
    target=(74.5,113.5)
    for angle,col in [(45,'#176b7b'),(60,'#b37a25')]:
        entry=target[1]+(80-target[0])*math.tan(math.radians(angle))
        line(c,X(80),Y(entry),X(target[0]),Y(target[1]),col,2)
        text(c,X(80)+8,Y(entry)-3,f'{angle}°外侧入射',11,col)
    line(c,X(68.4),Y(115),X(68.4+1.5*math.tan(math.pi/3)),Y(113.5),'#176b7b',2)
    text(c,105,339,'QT顶面入射受焊趾和探头足迹限制',11)
    notes(c,['检查目标分区：',
             '① 首次QT/CI-A1界面、圆角及两端；',
             '② 首层/第二层及分道重熔边界；',
             '③ 最终镍侧、钢侧熔合面与弧坑。',
             '',
             '外壳扫查带设计：z114～135，R80外侧；',
             '按段号1～8逐段，覆盖18mm及两端各2mm。',
             '探头入射点沿轴向/周向两方向记录。'],720,630,size=12)
    notes(c,['几何核查：45/60°外侧直线路径到R68.98～74.98、z113.5～115的目标，入射带z118.52～134.09。',
             '最远几何声程22.04mm；5mm钢壁段10.00mm（60°情景）。不能按该直线代替实际折射声程。',
             '顶面探头足迹径向4mm、中心R≤69时，60°到深1.5mm的最大径向位置R71.60；',
             '外侧约3.38mm不能仅靠顶面45/60°扫查覆盖，因此设置外壳扫查和两侧交叉入射。',
             '起点方案：2/5MHz双晶纵波、45/60°对比筛选；记录实际孔径、楔块外形、声速及曲率。',
             '同材料对比块：首次/最终两侧0.5深×3长×≤0.2宽平面反射体，段中、两端、圆角均配置。',
             '资格目标：最远路径SNR≥12dB、重复幅度差≤2dB；记录覆盖图，几何回波不得代替缺陷检出。',
             '近表层0.65～0.75mm与分层1.40～1.60mm需专门证实盲区；未覆盖的区域先修改检测可达性。'],60,262,step=22,size=11)
    c.save();return file


def bom():
    c,file=begin(21,'关键零件明细、制造配合及独立基准','与HJ-001～018关联；装配尺寸与能力验收要求分别执行；材料批次和热处理记录随夹具')
    rows=[
        ('01','座体','1','QT450-10','8P-R2-t15；Ø40候选孔；D1.50±0.10/R1.50','HJ-001/017/019'),
        ('02','壳体','1','Q235B','Ø160×200，t5；A/B及焊前加工按HJ-022','HJ-001/022'),
        ('03','一体反锥芯/柱/法兰','1','45钢调质','半角10°；Ø60颈；无过盈拼接；Ra≤0.2','HJ-004/005/012'),
        ('04','六指胀套','1','17-4PH H900','缩态Ø39.94；机械最大Ø40.04；弹颈t0.80/L30','HJ-006/009'),
        ('05','上承力筒及止挡头','1','按HJ-F-01','Ø70/Ø24×244.6；独立浮动压环接口见HJ-023','HJ-012/023'),
        ('06','门架横板/立柱','1/4','45钢结构件','板460×460×100；4柱Ø80；柱位置(±180,±180)','HJ-012'),
        ('07','机械上止挡','2','按HJ-F-01','26×30×20；独立径退20；接触宽≥7','HJ-012'),
        ('08','基座连接螺钉','12','ISO4762-8.8','M36×200；PCD360；预紧90±9kN；啮合≥55','HJ-F-01'),
        ('09','独立A基准托环','1','45钢','OD180/ID150.20±0.04×20；夹钩/外耳见HJ-022','HJ-013/022'),
        ('10','水冷铜瓣','4','C11000','OD149.60/ID143.60×9；三层真空钎焊水道','HJ-007/010/011'),
        ('11','滑动桥片','4','316L','厚0.50；固定/滑动搭接4；袋槽6','HJ-010'),
        ('12','上闭合密封圈','1','低析出FFKM','自由ID145.85±0.10；截径2.47～2.53；配槽','HJ-010'),
        ('13','下连续座/闭合圈','1/1','17-4PH/FFKM','座厚1.50；圈截径0.99～1.01；压缩0.28～0.29','HJ-007/010'),
        ('14','刚性盘/加强环','1/1','按HJ-C-01','Ø148×1；底环厚6；盘封底连续气密','HJ-003/007'),
        ('15','穿盘水块','4','316L','12径×16切向；穿盘连接气密；四路独立','HJ-011'),
        ('16','微管/转向块/压紧接头','16/16/32','PFA/Cu/316L','OD2/ID1；实装R≥12；接头包络Ø5×8','HJ-011'),
        ('17','后序独立接液盘','1','按HJ-Q-02','OD149.40±0.05；底厚2；密闭撤出筒ID152','HJ-015'),
        ('18','微珩上下罩/下杯','1套','按HJ-Q-03','密封接触R27端面；下杯ID44±0.20；液深16','HJ-016/018'),
    ]
    xs=[48,78,270,335,465,1005]
    heads=['序','零件','数量','材料/供货','关键制造尺寸与接口','关联图/卡']
    for x,h in zip(xs,heads):text(c,x,735,h,12)
    line(c,44,722,W-44,722)
    for i,row in enumerate(rows):
        y=700-i*27
        for x,t in zip(xs,row):text(c,x,y,t,10)
        line(c,44,y-10,W-44,y-10,'#d0d8df',.5)
    notes(c,['A：z0壳底全周端面；B1：z20～30、B2：z170～180；同装夹加工及独立提取按HJ-022。',
             '工装锥芯轴线相对A/B转移、轴线与定心各2μm径向；A托环等高/热差按HJ-F-01，不以胀套作B基准。',
             '锥芯与胀套为配锥研合；增量柔度≤0.05μm/kN为装机资格目标。M36预紧以张力/伸长核验，不能只靠扭矩。',
             '水/气路及密封槽按实物测径配作；上圈径向压缩0.415～0.425，最小壁厚/盲孔封底按HJ-C-02验收。',
             '采购焊材按实际药皮/裸棒分类及批次证书；主体/工装不得以未注±0.10替代微米级定位与密封配合。'],48,181,step=21,size=11)
    c.save();return file


def rectangle(c,x,y,w,h,fill='#edf2f5'):
    poly(c,[(x,y),(x+w,y),(x+w,y+h),(x,y+h)],fill)


def arrow(c,x,y,xx,yy,color='#176b7b',width=1.5):
    line(c,x,y,xx,yy,color,width)
    a=math.atan2(yy-y,xx-x)
    for da in [-.48,.48]:
        line(c,xx,yy,xx-8*math.cos(a+da),yy-8*math.sin(a+da),color,width)


def manufacturing_interfaces():
    c,file=begin(22,'壳体焊前基准加工与保基准夹持接口','配套HJ-001/005/013/014/021；保持原承托槽、门架、反锥及铜盘，焊后禁止加工平移孔轴')
    text(c,60,720,'A  壳体轴向剖面与指定测量带',15)
    # Drawing represents the given 200 mm shell height at one point per mm.
    x0,y0=133,468
    rectangle(c,x0,y0,12,200,'#c5d7e7');rectangle(c,x0+192,y0,12,200,'#c5d7e7')
    for z,col in [(20,'#a8cec0'),(170,'#a8cec0'),(100,'#eed5ae')]:
        h=20 if z==100 else 10
        rectangle(c,x0,y0+z,12,h,col);rectangle(c,x0+192,y0+z,12,h,col)
    line(c,235,452,235,695,'#909ba5',.8)
    line(c,124,y0,349,y0,'#b45d36',2);text(c,130,445,'A：z0全周环端面',11)
    arrow(c,365,494,340,y0+25);text(c,370,490,'B1：z20～30',11)
    arrow(c,365,644,340,y0+175);text(c,370,640,'B2：z170～180',11)
    arrow(c,365,579,340,y0+110);text(c,370,575,'连接带：z100～120',11)
    text(c,152,682,'H200 / OD160 / t5',11)
    notes(c,['两带全周各宽10；正式测线：',
             'z22/25/28及172/175/178。',
             'B1/B2/连接带：Ø150.00～150.02。',
             '其他内腔通径≥150.00，无台阶毛刺。'],60,409,step=20,size=11)
    text(c,620,720,'B  随行托环、外部长压钩与正向锁止',15)
    # One of three hold-downs in the radial/axial section; none touches the bore.
    rectangle(c,671,469,166,18,'#e1e7eb');rectangle(c,708,487,12,192,'#c5d7e7')
    rectangle(c,821,465,78,8,'#d9dee2');rectangle(c,869,473,12,221,'#d9dee2')
    rectangle(c,713,679,168,9,'#d9dee2');rectangle(c,708,670,16,9,'#a8cec0')
    c.setStrokeColor(HexColor('#b45d36'));c.circle(879,683,4,fill=0)
    arrow(c,717,711,717,680);text(c,685,695,'75±5 N',11)
    text(c,673,446,'原A托环：OD180 / ID150.20±0.04 / t20',11)
    column_notes(c,['触点R77.5 / z200；压钩30°/150°/270°。',
             '外耳30径×24切×8，2-M6；孔中心R84、切向±6。',
             '立杆Ø12，中心R100；上钩臂25×12×8。',
             '钩片接触脚径宽4×切宽10，圆滑无压痕。',
             '气动摆入/开钩，Ø6弹簧插销正向锁止；',
             '锁销弹簧插入、气动拔出；断气保持。'],926,672,220,step=18,size=10.5)
    text(c,60,287,'焊前加工与精度交接',14)
    notes(c,['板筒成形及纵缝完成 → 去应力/稳定化 → 软爪同装夹精加工A、B1/B2及连接带 → 去毛刺、清洗。',
             '来料留足焊前加工量；成品保持题定Ø160/t5/H200，壁厚逐区检验；不以焊后镗孔修正轴线。',
             'A：平面度0.002、Ra≤0.8 μm。B：圆度≤0.003、两带共同圆柱度≤0.004、Ra≤0.8 μm。',
             '先用两带自由拟合轴检查A垂直度0.002/有效跨距150；再以A法向约束提取正式B。',
             'A的2 μm/150 mm倾斜投影到z115约1.53 μm；基准转移径向2 μm分配以装机复测验收。'],60,263,step=22,size=11)
    text(c,60,139,'转运许可',13)
    notes(c,['六承托指按原0°起每60°进入R87槽；宽≤8、高≤1.8、单指≤100 N，六只均有到位与锁销反馈。',
             '六指全锁止＋三只壳体压钩仍锁止 → 才释放定位窝三锁；随托环上提140，固定铜盘保持朝上。',
             '20±1℃前不得开壳体压钩；CMM前钩、孔内和全部外部约束解除。销位用实到位信号，不读气阀指令。'],60,116,step=20,size=11)
    # A supplier interface is specified explicitly; force targets are checked on installation.
    column_notes(c,['每只压钩装机用力计设定75±5 N。',
             '弹簧压头有效行程≥2，工作刚度≤10 N/mm；',
             '机械销锁住摆臂，弹簧压头维持端面力。',
             '总轴向225±15 N；端面受压≤2 MPa。',
             '夹钩/立杆/外耳45钢调质；M6-8.8。',
             'M6啮合≥9、盲深≤12，托环底余厚≥8。',
             '先在端面上方≥2摆入，再轴压；不刮擦壳口。'],926,468,220,step=18,size=10.5)
    c.save();return file


def float_and_utilities():
    c,file=begin(23,'浮动设置、独立压环与气水抽吸接口','配套HJ-003/006/007/011/013/022；M12只作设置/正向回退，5 kN热反力沿原止挡—门架力链')
    text(c,60,720,'A  M12径向浮动 / 副压紧局部验算',14)
    rectangle(c,104,649,208,12,'#d9dee2');rectangle(c,156,678,106,12,'#a8cec0')
    rectangle(c,171,663,76,12,'#edf2f5');rectangle(c,203,630,12,80,'#c5d7e7')
    c.setStrokeColor(HexColor('#b45d36'));c.arc(193,690,226,710,startAng=180,extent=180)
    arrow(c,327,688,440,688);text(c,330,705,'XY各±0.30',11)
    text(c,104,628,'原门架顶面z500；热反力不经浮动板',10)
    notes(c,['滑板80×80×12；上下盖板限位，轴向间隙0.02～0.04。',
             '中心通孔Ø18，M12杆；四肩销导向长孔6.5×7.1。',
             '限位允许XY各±0.30；复位力≤10 N，接触面精磨。',
             '球面座R20 / 接触Ø24，倾转±0.2°；限位不锁死球面。',
             '副压环先独立升150并销锁，胀套上退1后芯组升260。'],60,606,step=18,size=10.2)
    notes(c,['500 N副载与5 kN原止挡反力分开；45钢调质、屈服≥355 MPa。',
             '三外驱动净轴力146.45 / 207.11 / 146.45 N，ΣMx=ΣMy=0。',
             'Ø25理想压0.2983 / 0.4219 / 0.2983 MPa；实装扣重力/摩擦调压。',
             '用三足力计调到各166.7±5 N、合计500±20 N，不用同压等力。',
             '横臂L280，40×20截面（内端R60～90收为3.0×20）：',
             '按最大207.11 N，根部σ21.75 MPa；分段梁端挠度≤0.36 mm。',
             '环最大支承弧93.2，保守500 N单点简支：σ32.4 MPa、δ21.7 μm。',
             'Ø8杆L98：Euler约37.2 kN；径浮0.30副径向分力≤1.54 N。',
             '上述为副压紧局部手算；原5 kN热态拘束力链及有限元保持。'],60,518,step=14,size=10)
    text(c,625,720,'B  固定外驱动 / 独立退出150 / 真实包络',14)
    # Radial section through one driver: original core and gate remain unchanged.
    X=lambda r:675+r*.62
    Y=lambda z:547+(z-115)*.30
    rectangle(c,X(12),Y(155.4),23*.62,(400-155.4)*.30,'#c5d7e7')
    rectangle(c,X(12),Y(380),38*.62,20*.30,'#c5d7e7')
    rectangle(c,X(55),Y(400),175*.62,100*.30,'#d9dee2')
    rectangle(c,X(37),Y(115.3),15*.62,11.7*.30,'#a8cec0')
    line(c,X(60),Y(127),X(60),Y(225),'#506579',4)
    rectangle(c,X(60),Y(225),30*.62,20*.30,'#9badbb')
    rectangle(c,X(90),Y(225),250*.62,20*.30,'#9badbb')
    rectangle(c,X(325),Y(430),30*.62,210*.30,'#d9dee2')
    line(c,X(340),Y(430),X(340),Y(245),'#506579',3)
    c.setDash(4,3)
    rectangle(c,X(37),Y(265.3),15*.62,11.7*.30,'#edf2f5')
    line(c,X(60),Y(277),X(60),Y(375),'#506579',2)
    line(c,X(60),Y(395),X(340),Y(395),'#506579',1)
    c.setDash();arrow(c,930,Y(125),930,Y(265));text(c,944,Y(207),'独退150',10)
    text(c,635,675,'头Ø100：z380～400',9.5)
    text(c,731,705,'板460方 / 孔Ø110 / z400～500',9.5)
    text(c,779,566,'臂下z225→375，上限395',9.5)
    line(c,825,586,842,577)
    text(c,629,537,'环115～127→265～277；不随原芯组升260',9.5)
    notes(c,['3×DSNU-25-150-P-A；轴R340，角22.5°/157.5°/292.5°。',
             '官方D30、前螺母KV32、杆Ø10、ZJ+行程247.5（目录2025/05 p15）。',
             '2×Ø16外导轨/组，衬套长30、两层跨100；横臂反矩约58 N·m。',
             '导轨杆16h8/硬化钢；KPE-16(178467)静保持1000 N，独立气释≥0.3 MPa。',
             '外组整体包络径向−40～+90、切向±60；固定柱60×60×4，4-M8。',
             'R60/Ø8杆L98；两端球座±0.30径浮，臂端球座最大Ø14。',
             '环ID74 +0.05/0，OD104±0.05/t12；下表面非触点退让0.30。',
             '三足R37、0°/120°/240°，径2×切6，R36～38，定位±0.03。',
             '动态制动：Mayr linearstop气动Brake unit Size20，Ø16/OD46，5 bar。',
             '订型750 N、≥0.35 J/停、停止≤1；m≤5 kg/组、v≤50 mm/s。',
             '端位正向销/反馈；静锁1000 N另设，外副架不在原门架钻孔。'],625,519,step=11,size=9.0)
    text(c,60,386,'C  气、水及干式抽吸管路（与产品内腔分隔）',14)
    # Utility diagram uses separately labelled routes instead of suggesting a combined fluid circuit.
    for x,label,w in [(62,'氩源/调压',96),(194,'流量/阀',88),(319,'气幕12×Ø1',128),(487,'开放腔',95)]:
        rectangle(c,x,336,w,27,'#edf2f5');text(c,x+7,345,label,10)
    for a,b in [(158,194),(282,319),(447,487)]:arrow(c,a,349,b,349)
    text(c,62,313,'气幕10～15；枪保护8～12；上口扩散补氩0～12 L/min',10.5)
    for x,label,w in [(62,'4个抽吸口',111),(207,'捕集/预滤',108),(348,'H13滤器',95),(483,'受控抽气',99)]:
        rectangle(c,x,266,w,27,'#edf2f5');text(c,x+6,275,label,10)
    for a,b in [(173,207),(315,348),(443,483)]:arrow(c,a,280,b,280)
    text(c,62,244,'口R78/z210，45°起每90°；Ø4喉→ID6支管→ID12总管',10.5)
    text(c,62,224,'朝下向内15°；各5.5～7，总22～28；转运前四口径退15',10.5)
    text(c,62,204,'滤器置工位外；监测总流量/压差，禁止滤后气体回到氩保护',10.5)
    for x,label,w in [(62,'冷水源/常闭阀',124),(220,'8路流量',104),(359,'铜瓣8水路',119),(513,'回水',69)]:
        rectangle(c,x,157,w,27,'#edf2f5');text(c,x+6,166,label,10)
    for a,b in [(186,220),(324,359),(478,513)]:arrow(c,a,171,b,171)
    text(c,62,133,'各路0.075～0.07875 L/min；总≥0.60；供回水独立，见HJ-011',10.5)
    text(c,62,112,'入口20±2℃ / 出口≤35℃ / 漏水关供水；微管不随工件转动',10.5)
    text(c,62,99,'动态：5 bar→Mayr释放；ID4、管长≤0.5 m快速排气，失电先施制动。',9.4)
    text(c,62,87,'静锁：4 bar→止回→有效≥50 mL→KPE；Ø0.20(+0.01)限流排气。',9.4)
    text(c,62,75,'失电静夹延时≥1.3 s；停稳才开常闭旁通；UPS失效仍被动延时。',9.4)
    text(c,625,386,'D  净隙、许可、保持及故障动作',14)
    notes(c,['装配末段前吹30 s；各流量稳定≥5 s且段位/温度/锁止齐全才起弧。',
             '每次停弧枪保护≥15 s；末弧气幕/抽吸/必要补氩保持≥120 s。',
             '退位另须温度<55℃、颗粒检查合格；枪丝先升150，再副环升150。',
             '副环升锁→开上止挡/胀套退1/铜瓣退1.10→芯组升260；',
             '关补氩→四口径退15确认→壳/托环升140；完整退出按HJ-C-03。',
             '四口退位反馈齐全才上提140；气幕保持至上提结束后关闭。',
             '停弧清盘用独立干式细口回收，不能用流量证明飞溅已吸净。',
             '计±0.30浮动/足±0.03/筒OD70+0.10：最小过筒净0.62。',
             '足外角含误差≤R38.45＜最深槽根R38.95；有效12 mm²/足。',
             '外组对方板边净24.2；内杆头对原头径净≥2.5；臂对板净≥4。',
             '退环对上提座最高255净≥9.5；枪丝提升名义0.9156、扣差后≥0.25。',
             '段间枪丝升150后转位：全工具z≥265.2～370，越工作臂顶245。',
             '缺气/失吸/堵水：停弧停运动、锁/盘保持；漏水关供水。',
             '失电气阀关闭、弹簧夹持；健康水路有电续流，泵停按缺水。',
             '24 V控制/测温备用≥15 min；复核阀位/温度后人工标准撤出。',
             '急停动态制动→停稳反馈→KPE静夹；PLC重启不得自动续焊。'],625,359,step=17,size=10.2)
    c.save();return file


def main():
    OUT.mkdir(parents=True,exist_ok=True);register_project_fonts(ROOT)
    paths=[section(),ut(),bom(),manufacturing_interfaces(),float_and_utilities()]
    for p in paths:
        with fitz.open(p) as f:f[0].get_pixmap(dpi=120).save(p.with_suffix('.png'))
    manifest=ROOT/'cad/generated/engineering-drawings/drawing-manifest.json'
    data=json.loads(manifest.read_text(encoding='utf8'))
    existing=[r for r in data.get('external_pdf_sheets',[]) if r['number'] not in [19,20,21,22,23]]
    for number,p,title in zip([19,20,21,22,23],paths,['真实公差与法向修整截面','异种接头专用UT可达与覆盖','关键零件明细与制造配合','壳体基准加工与保基准接口','浮动压紧与气水抽吸管路']):
        existing.append(dict(number=number,pdf=p.relative_to(ROOT).as_posix(),title=f'HJ-{number:03d} {title}'))
    data['external_pdf_sheets']=existing
    manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps([str(p) for p in paths],ensure_ascii=False))


if __name__=='__main__':main()
