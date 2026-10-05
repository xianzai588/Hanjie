"""从参赛配置及真实座体BREP生成五张设计图；尺寸要求与能力验证分开。"""
import json
import math
from pathlib import Path
import sys
from xml.sax.saxutils import escape
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.GeomAbs import GeomAbs_Line

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from hanjie.domain.competition_design import read_spec, current_assessment
from hanjie.domain.tooling_access import read_brep


def text(x,y,value,cls="note"):
    return f'<text x="{x}" y="{y}" class="{cls}">{escape(str(value))}</text>'


def line(x,y,xx,yy,color="#334155",width=1.5):
    return f'<line x1="{x}" y1="{y}" x2="{xx}" y2="{yy}" stroke="{color}" stroke-width="{width}"/>'


def box(x,y,w,h,fill="#ffffff"):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="#334155"/>'


def circle(x,y,r,fill="none",stroke="#334155"):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}"/>'


def polygon(points,fill):
    return '<polygon points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in points)+f'" fill="{fill}" stroke="#334155"/>'


def sheet(title,number,subtitle):
    return ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">',
            '<style>text{font-family:"Microsoft YaHei";font-size:17px;fill:#183247}.title{font-size:28px;font-weight:700}.small{font-size:14px}.section{font-size:21px;font-weight:700;fill:#176b7b}</style>',
            box(0,0,1200,800),box(25,25,1150,750),text(50,68,title,"title"),
            text(50,99,subtitle,"small"),text(1020,65,number,"section")]


def finish(parts,material="装配材料见明细"):
    # 视图注明NTS；制造按标注尺寸和公差取值。
    return parts+[line(50,719,1150,719),
                  line(560,719,560,775),line(760,719,760,775),line(950,719,950,775),
                  text(50,742,"工艺设计图 · 单位mm · 未注公差±0.10","small"),
                  text(50,764,"关键配合按尺寸；检验按说明书§7执行","small"),
                  text(572,742,"比例：NTS（不按比例）","small"),
                  text(572,764,"视图NTS；不得量图取值","small"),
                  text(772,742,f"材料：{material}","small"),
                  text(772,764,"工序与零件见明细","small"),
                  text(962,742,"工艺设计图 / 修订5","small"),
                  text(962,764,"试制检验按说明书执行","small"),'</svg>']


def notes(parts,items,x=640,y=167,step=38):
    for i,item in enumerate(items):
        
        for j in range(0,len(item),32):
            parts.append(text(x,y+i*step+(j//32)*16,item[j:j+32],'small'))


def seat_sheet(spec):
    parts=sheet("接头布局、座体尺寸与独立基准","HJ-001","主设计：8P-R2-t15，八段各18 mm；焊后孔轴位置度在精整前检验")
    scale,cx,cy=3.0,310,395
    shape=read_brep(ROOT/spec["seat_brep"])
    edges=TopExp_Explorer(shape,TopAbs_EDGE)
    seen=set()
    while edges.More():
        curve=BRepAdaptor_Curve(TopoDS.Edge_s(edges.Current()))
        start,end=curve.FirstParameter(),curve.LastParameter()
        count=1 if curve.GetType()==GeomAbs_Line else 36
        points=[curve.Value(start+(end-start)*i/count) for i in range(count+1)]
        for a,b in zip(points,points[1:]):
            endpoints=tuple(sorted(((round(a.X(),5),round(a.Y(),5)),(round(b.X(),5),round(b.Y(),5)))))
            if endpoints in seen or endpoints[0]==endpoints[1]:
                continue
            seen.add(endpoints)
            parts.append(line(cx+scale*a.X(),cy-scale*a.Y(),cx+scale*b.X(),cy-scale*b.Y(),width=1))
        edges.Next()
    parts += [circle(cx,cy,75*scale,stroke="#7a939f"),circle(cx,cy,80*scale,stroke="#7a939f"),
              line(cx-260,cy,cx+260,cy,"#7a939f",.7),line(cx,cy-250,cx,cy+250,"#7a939f",.7),
              text(65,150,"俯视：真实BREP边界投影","section"),text(260,400,"Ø40","section"),
              text(115,671,"壳体 Ø160 / 内径名义 Ø150；H200；t5")]
    for i in range(8):
        angle=i*math.pi/4
        parts.append(text(cx+205*math.cos(angle)-5,cy-205*math.sin(angle)+5,str(i+1),"section"))
    notes(parts,["材料：QT450-10座体 / Q235B壳体",
                 "座体厚15；中心环外径82；32处转接R2",
                 "外缘直径149.94～149.98（设计限值）",
                 "壳体内径150.00～150.02（设计限值）",
                 "径向装配间隙0.01～0.04，不能靠间隙定心",
                 "座体底面距壳体下端100（工序设计尺寸）",
                 '焊前候选孔40.006～40.008；最终40.000～40.025',
                 "A：壳体下端独立安装面",
                 "B：壳体内壁双测量带所建立的轴线",
                 "B定向按A法向约束；不以胀套轴冒充B",
                 "Ø40孔轴：位置度 Ø0.05，相对A、B",
                 "测量长度15；不默认扩展到整根主轴",
                 "C仅周向识别焊段，不加入位置度基准框",
                 "八槽宽4±0.05，圆端R2，最深R39",
                 "槽位22.5°起，每45°；翼间其余区域留空"])
    # 位置度符号用圆与十字绘制，避免字体缺字符。
    gx,gy=95,588
    parts += [line(gx+18,gy,267,437,"#334155",1.2),
              box(gx,gy,32,32,"none"),box(gx+32,gy,80,32,"none"),box(gx+112,gy,36,32,"none"),box(gx+148,gy,36,32,"none"),
              circle(gx+16,gy+16,9),line(gx+3,gy+16,gx+29,gy+16),line(gx+16,gy+3,gx+16,gy+29),
              text(gx+42,gy+23,"Ø0.05"),text(gx+124,gy+23,"A"),text(gx+160,gy+23,"B"),
              text(gx,gy+46,"位置度公差框（GB/T 1182）","small")]
    return finish(parts,"QT450-10 / Q235B")


def joint_sheet(spec,result):
    parts=sheet("两道脉冲TIG截面与pWPS","HJ-002","8×18角焊缝；根道＋盖面；QT侧预制Ni99层在轴承孔精加工前完成")
    # 局部截面采用同一20px/mm绘制，镍层宽6大于焊脚4。
    parts += [box(435,175,100,445,"#cbd5e1"),box(115,320,320,300,"#efd18b"),
              box(315,320,120,24,"#bccfcb"),box(315,320,120,10,"#8cb6ae"),
              polygon([(435,320),(355,320),(435,240)],"#e2a18b"),
              text(145,580,"QT450-10，t15"),text(410,165,"Q235B，t5"),
              text(140,214,"焊脚 z≥3.50 / 可达包络4.30","section"),
              # GB/T 324 角焊缝符号：基准线＋箭头侧三角形＋焊脚尺寸与段数/段长/净距
              line(95,240,330,240,"#334155",1.2),line(330,240,395,280,"#334155",1.2),
              polygon([(130,242),(146,242),(130,258)],"#183247"),
              text(100,256,"z4.0"),text(154,256,"8×18(41)"),
              text(95,665,"焊缝符号按GB/T 324；段间净距≈41；浅槽宽6","small"),
              text(95,630,"QT侧双层Ni99：总厚≥1.2；表层≥0.5；熔深≤0.4","small"),
              text(95,688,"总面积7.326～8.760 mm²；高镍过渡残层≥0.8","small")]
    notes(parts,["方法：自动TIG；直流正接（电极负极）",
                 "NiFe55 TIG Ø1.6；第二镍层加工后≥0.50",
                 "脉冲100/50 A；50%占空；20 Hz；12 V",
                 f'固定送丝 {result["process"]["fixed_feed_mm_s"]:.3f} ±0.05 mm/s；共2道；焊速1.65±2%',
                 "Ø1.60±0.01；沉积效率0.90～0.98入边界",
                 "纯氩99.999%；名义10 L/min",
                 "不预热；起弧前工件温度15～35℃",
                 "层间温度≤100℃；超温等待",
                 "每道顺序 1→5→3→7→2→6→4→8",
                 "每道净热300 J/mm；在线窗口250～350",
                 "本件净热输入86.40 kJ；弧燃时间174.5 s",
                 "停弧后≥120 s且最高温度<55℃才松夹",
                 "冷却至20±1℃后独立测量并判定"])
    return finish(parts)


def fixture_sheet(spec,result):
    f=spec["fixture"]
    parts=sheet("胀套定位、端面夹紧与主动回退","HJ-003","整体固定反向锥；驱动胀套上退释放；轴向500 N通过独立压环—座体—底部三支点承受")
    # 局部剖面放大，不将占位外包络伪装成加工细节。
    parts += [box(90,325,125,110,"#efd18b"),box(415,325,125,110,"#efd18b"),
              box(218,325,12,110,"#8cb6ae"),box(400,325,12,110,"#8cb6ae"),
              polygon([(230,422),(400,422),(370,295),(260,295)],"#b2c4cc"),
              box(302,160,26,150,"#b2c4cc"),box(155,295,320,30,"#8cb6ae"),
              box(150,435,42,90,"#9baeb7"),box(440,435,42,90,"#9baeb7"),
              box(140,525,355,30,"#9baeb7"),box(249,555,134,90,"#9baeb7"),
              text(125,140,"功能剖面：槽口及密封连接见技术要求","small"),
              text(80,220,"独立压环：500 N"),text(350,220,"上部M12驱动／正向止挡"),
              text(100,593,"三支点位于R30，等间隔120°","small"),
              text(100,627,"托垫只受压允许脱离；制造端面极差≤0.0025；含热差≤0.003","small"),
              text(100,661,"固定承力柱Ø144×100；托盘Ø72×14；托垫Ø8×6","small")]
    notes(parts,["六指胀套套在固定反向锥上；上退释放",
                 "收拢外径39.94；最大撑开外径40.04",
                 "连续接触带：z100.2～114.8",
                 "锥10°：下端大、上端小；芯固定、套上退",
                 "正向顶回肩＋拉杆；回退行程1.00",
                 f'覆盖全径差所需理想行程 {result["fixture"]["positive_return_stroke_required_mm"]:.3f}',
                 "μ=0.20仍可能自锁，禁止仅靠弹簧回位",
                 "径向预载≤100 N；热反力由机械止挡承受",
                 "胀套6指：L30、t0.8、宽19；外圆同轴≤0.003",
                 "整体实心固定锥；胀套止挡设计承载5000 N",
                 "上承力筒Ø70/Ø24，z155.4～400；门架见HJ-013",
                 "M36-8.8，90±9 kN/只；基座啮合≥55、盲深≥70；柱不升降",
                 "45钢屈服≥355；法兰Ø440×140；12-M36×200/PCD360；详HJ-012"])
    return finish(parts,"17-4PH / 45钢")


def carrier_sheet(spec,result):
    f=spec['fixture'];r=f['carrier_post_radius_mm']
    flange_r=f['carrier_base_flange_radius_mm'];flange_h=f['carrier_base_flange_height_mm']
    bolt_r=f['carrier_base_bolt_radius_mm'];hole=f['carrier_base_clearance_hole_mm']
    length=f['carrier_disk_z_mm'][0]-f['carrier_post_bottom_z_mm']
    parts=sheet('下托承力柱、整体法兰与预紧连接','HJ-012',
                '三个托垫仅承压；刚度包含柱端横移、转角及根部柔度；尺寸为制造与装配要求')
    sc,cx,top=1.1,310,260
    parts += [text(70,145,'轴向剖面（NTS）','section'),
              box(cx-r*sc,top,2*r*sc,length*sc,'#9baeb7'),
              box(cx-flange_r*sc,top+length*sc,2*flange_r*sc,flange_h*sc,'#9baeb7'),
              box(cx-36*sc,top-14*sc,72*sc,14*sc,'#b2c4cc'),
              line(cx,top-70,cx,top+(length+flange_h)*sc+20,'#7a939f',.7),
              text(85,195,'托垫顶面z100；托盘顶面z94','small'),
              text(85,220,'托盘Ø72×14；柱顶z80、柱底z-20','small'),
              text(420,345,f'柱Ø{2*r:g}×{length:g}','small'),
              text(390,475,f'法兰Ø{2*flange_r:g}×{flange_h:g}','small')]
    # Bolts shown on the pitch-circle section; the plate is integral with the post.
    for sign in (-1,1):
        bx=cx+sign*bolt_r*sc
        parts += [box(bx-hole/2*sc,top+length*sc,hole*sc,flange_h*sc,'#ffffff'),
                  box(bx-f['carrier_base_bolt_diameter_mm']/2*sc,top+length*sc,f['carrier_base_bolt_diameter_mm']*sc,f['carrier_base_bolt_length_mm']*sc,'#c8d8e0'),
                  box(bx-30*sc,top+(length-36)*sc,60*sc,36*sc,'#c8d8e0')]
    parts += [text(75,590,'法兰下平面贴合机座；紧固后检托垫等高','small'),
              text(75,614,'整件45钢调质，材质证明屈服≥355 MPa','small'),
              text(75,638,'托垫Ø8×6：R30，0°/120°/240°；制造端面极差≤0.0025；含热差≤0.003','small'),
              text(75,662,'整体实心颈Ø60、z59.8～99.8；反锥见HJ-006','small'),
              text(75,686,'安装后工装轴线按2 μm径向分配验收','small')]
    pcx,pcy,ps=865,335,.75
    parts += [text(650,145,'法兰俯视（NTS）','section'),
              circle(pcx,pcy,flange_r*ps,'#edf2f5'),circle(pcx,pcy,r*ps,'#9baeb7'),
              circle(pcx,pcy,bolt_r*ps,stroke='#7a939f'),
              line(pcx-155,pcy,pcx+155,pcy,'#7a939f',.7),
              line(pcx,pcy-155,pcx,pcy+155,'#7a939f',.7)]
    for i in range(f['carrier_base_bolt_count']):
        angle=2*math.pi*i/f['carrier_base_bolt_count']
        parts.append(circle(pcx+bolt_r*ps*math.cos(angle),pcy-bolt_r*ps*math.sin(angle),hole/2*ps,'#ffffff'))
    notes(parts,[f'{f["carrier_base_bolt_count"]}×Ø{hole:g}通孔；PCD{2*bolt_r:g}，30°等分',
                 '12-M36×200 ISO4762内六角，8.8级',
                 '基座有效螺纹啮合≥55；盲孔深≥70',
                 '预紧90±9 kN/只，按对角分级紧固',
                 '螺栓头与柱根留工具净隙；装夹前完成紧固',
                 '托盘、柱和法兰为整体件，禁止松配拼接',
                 '5 kN侧向合力＋轻击；全链轴移计入6.5 μm预算'],x=650,y=525,step=26)
    return finish(parts,'45钢调质 / 8.8螺钉')


def shield_sheet(spec,result):
    parts=sheet("连续防护、承力组件与退出路径","HJ-004","下工装固定；胀套先上提260；壳体随A基准托环上提140；接料盘原位朝上")
    scale,cx,base=2.25,290,670
    x=lambda r:cx+r*scale
    y=lambda z:base-z*scale
    def rz(r0,r1,z0,z1,color):
        return box(x(r0),y(z1),(r1-r0)*scale,(z1-z0)*scale,color)
    for sign in (-1,1):
        lo,hi=sorted((75*sign,80*sign)); parts.append(rz(lo,hi,0,200,"#cbd5e1"))
        lo,hi=sorted((20*sign,74.98*sign)); parts.append(rz(lo,hi,100,115,"#efd18b"))
        lo,hi=sorted((26*sign,34*sign)); parts.append(rz(lo,hi,90,100,"#9baeb7"))
        lo,hi=sorted((71.8*sign,74.8*sign)); parts.append(rz(lo,hi,90.5,99.5,"#d9ad83"))
        lo,hi=sorted((74.8*sign,75.02*sign)); parts.append(rz(lo,hi,95.25,99,"#059669"))
        parts.append(circle(x(73.3*sign),y(92),.75*scale,"#ffffff","#2563eb"))
    for sign in (-1,1):
        lo,hi=sorted((71.8*sign,74.8*sign));parts.append(rz(lo,hi,88.9,90.4,"#8cb6ae"))
        lo,hi=sorted((66.5*sign,74*sign));parts.append(rz(lo,hi,81.59,87.59,"#4f9ea3"))
    f=spec['fixture']
    post_r=f['carrier_post_radius_mm'];upper_r=f['upper_envelope_radius_mm']
    parts += [rz(-74,74,87.59,88.59,"#4f9ea3"),rz(-36,36,80,94,"#9baeb7"),rz(-post_r,post_r,-20,80,"#9baeb7"),
              rz(-upper_r,upper_r,115,220,"#8cb6ae"),line(x(40),y(84),x(40),y(-10),"#176b7b",3),
              polygon([(x(37),y(-6)),(x(43),y(-6)),(x(40),y(-12))],"#176b7b"),
              text(65,155,"同轴工序剖面，翼片方向简化投影","small"),
              text(65,698,"铜瓣回缩1.10；胀套上提260；壳体托环上提140；盘不移动","small")]
    notes(parts,["刚性盘Ø148；底板1；底面z87.59",
                 "C11000四瓣铜环149.60/143.60，z90.5～99.5",
                 "上圈Ø2.50；独立整环下圈Ø1.00",
                 "水道Ø1.10/1.40，≥0.60 L/min；气水隔离",
                 "气道3×2；12孔Ø1.0向上；10～15 L/min",
                 "静态密封＋盘面截留；气幕辅助，不承诺悬浮全部颗粒",
                 "胀套上提后至抬起壳口净隙19.8；固定反锥不升降",
                 "焊枪30°弯头＋竖直枪体；喷嘴Ø10",
                 "送丝落点及独立随动轻击见HJ-009",
                 f'所建模焊枪／送丝最小间距 {result["geometry"]["torch_feed_clearance_mm"]:.2f}',
                 "执行互锁：防护在位、底口开放、轨迹确认",
                 "松夹→上止挡打开/胀套上退→上部上提→壳体连托环上提",
                 "内窥镜＋全表面颗粒检查，不以低飞溅免责"])
    return finish(parts,"C11000 / 304")


def inspection_sheet(spec, result):
    """把焊接顺序、测量基准和放行条件放在一张可执行的检查图中。"""
    parts=sheet("焊接顺序、测量基准与放行卡","HJ-005",
                "工序执行卡：按段序控制热输入；几何检验采用A、B独立基准与冷态复测")
    parts += [text(70,160,"一、焊接顺序与温度门控","section")]
    sequence=["1","5","3","7","2","6","4","8"]
    for i, item in enumerate(sequence):
        x=75+i*68
        parts.append(circle(x,235,25,fill="#d7eef0",stroke="#176b7b"))
        parts.append(text(x-7,242,item,"section"))
        if i < len(sequence)-1:
            parts.append(line(x+28,235,x+55,235,"#176b7b",2))
            parts.append(polygon([(x+55,235),(x+47,230),(x+47,240)],"#176b7b"))
    parts += [text(72,295,"起弧前：工件温度15～35℃", "small"),
              text(72,323,"层间温度≤100℃；超温等待", "small"),
              text(72,351,"停弧后≥120 s且最高温度<55℃才松夹", "small"),
              text(72,379,"冷却至20±1℃后进入独立测量", "small")]
    parts += [text(70,445,"二、基准与测量闭环","section"),
              box(75,500,205,70,"#eaf4f5"), box(365,500,205,70,"#eaf4f5"),
              box(655,500,205,70,"#eaf4f5"), box(945,500,150,70,"#eaf4f5"),
              text(95,540,"A：壳体下端安装面","small"),
              text(385,540,"B：内壁双测量带轴线","small"),
              text(675,540,"C：只识别周向焊段","small"),
              text(965,540,"冷态复测","small")]
    for x in (280,570,860):
        parts.append(line(x,535,x+70,535,"#176b7b",2))
        parts.append(polygon([(x+70,535),(x+62,530),(x+62,540)],"#176b7b"))
    parts += [text(70,625,"三、工序检验与处置条件","section"),
              text(90,660,"Ø40孔轴：位置度 Ø0.05，相对A、B；测量长度15 mm", "small"),
              text(90,686,"焊脚 z≥3.50；单段18；八段总长144 mm", "small"),
              text(630,660,"外缘 Ø149.94～149.98；壳体内径 Ø150.00～150.02", "small"),
              text(630,686,"检查记录需绑定图号、批次、温度曲线和复测结果", "small")]
    return finish(parts)


def sleeve_detail_sheet(spec,result):
    parts=sheet('固定反向锥—上退六指胀套制造详图','HJ-006',
        '反向锥实心、下大上小，与承力柱整体加工；胀套上退释放；上部止挡/门架见HJ-013')
    X=lambda r:240+6*r
    Y=lambda z:540-6*(z-100)
    parts += [text(70,155,'轴向剖面 B-B（局部，门架省略）','section'),
        polygon([(X(r),Y(z)) for r,z in [(-30,94),(30,94),(30,99.8),(19.1449,99.8),(16.4295,115.2),(-16.4295,115.2),(-19.1449,99.8),(-30,99.8)]],'#64748b'),
        text(385,Y(115.2)+5,'固定锥上端','small'),text(385,Y(100.2)+5,'接触段下端','small')]
    for sign in (-1,1):
        parts.append(polygon([(X(sign*r),Y(z)) for r,z in [(23,155.4),(23,145.4),(20.1,145.4),(19.3,145.4),(19.3,155.4)]],'#f2c94c'))
        parts.append(polygon([(X(sign*r),Y(z)) for r,z in [(20.1,145.4),(20.1,115.4),(20,115.2),(20,100.2),(19.0744,100.2),(16.5,114.8),(19.3,115.4),(19.3,145.4)]],'#f2c94c'))
    parts += [box(X(-35),Y(159.4),420,24,'#94a3b8'),
        text(390,Y(155.4)+4,'根部正向止挡','small'),line(240,175,240,560,'#64748b',1),
        text(75,594,'自由胀套上退1.00 → 收拢39.94 → 上提260','small'),
        text(75,623,'端视图：6指等分60°；固定锥位于中心','small'),
        circle(240,674,42,'#dbe7ee'),circle(240,674,35,'#f2c94c'),circle(240,674,24,'#64748b')]
    for i in range(6):
        a=i*math.pi/3;parts.append(line(240+35*math.cos(a),674-35*math.sin(a),240+42*math.cos(a),674-42*math.sin(a),'#dc2626',2))
    notes(parts,[
        '胀套17-4PH H900；外接触带Ra0.8',
        '6槽宽0.80，末端R1；根部不切穿',
        '弹性颈Ø40.20、t0.80±0.03、L30、宽≥19',
        '接触带z100.2～114.8，覆盖率90%',
        '固定锥10°±0.1°；下R19.074、上R16.50',
        '两端各延0.4，机加工z99.8～115.2',
        '实心锥与Ø60承力颈、柱及法兰整体加工',
        '锥/肩精研Ra≤0.2；根过渡R0.2',
        '胀套根环Ø46/Ø38.6×10，z145.4～155.4',
        '胀套向下设置；预载≤100 N；止挡承热反力',
        'M12只设置及回退；压环球铰独立500 N',
        '开上止挡→胀套上退1→上提260',
        '上承力筒Ø70/Ø24、长244.6，连接z400门架',
        '凝固轻击与变形检查不省略；不得依靠加工纠轴',
        '固定锥局部压缩及门架柔度见53号核算',
        '外圆同轴≤0.003，回程/重复性按HJ-F-01'],x=620,y=170,step=32)
    return finish(parts,'17-4PH胀套 / 45钢整体芯柱')


def gas_water_detail_sheet(spec,result):
    parts=sheet('四瓣铜环、闭合密封与独立气水路','HJ-007','接缝2.00±0.05；上圈滑动桥；下圈独立整环座；铜瓣先径向回缩；盘固定朝上，壳体上提回收')
    cx,cy=275,325
    parts += [circle(cx,cy,180,fill='#d9ad83'),circle(cx,cy,172.8,fill='#ffffff'),
              circle(cx,cy,181.5,stroke='#059669'),circle(cx,cy,176.4,stroke='#2563eb'),
              line(80,325,470,325,'#475569',2),line(275,135,275,515,'#475569',2),
              text(75,120,'俯视：四瓣水路各独立；外圈为闭合FFKM','small'),
              text(75,708,'OD149.60±0.02；ID143.60±0.05','small'),
              text(75,545,'剖面B-B：双水道与双静密封','small')]
    for i in range(12):
        a=2*math.pi*i/12
        parts.append(circle(cx+163*math.cos(a),cy+163*math.sin(a),3,fill='#059669'))
    for a in [math.pi/4+i*math.pi/2 for i in range(4)]:
        start=(cx+140*math.cos(a),cy+140*math.sin(a));end=(cx+110*math.cos(a),cy+110*math.sin(a))
        parts.append(line(*start,*end,'#dc2626',2))
    parts += [text(145,350,'八路等流量并联','small'),
              text(75,578,'上圈封钢壳；整环下圈封盘','small'),
              text(75,607,'12×Ø1.0气孔，等分30°','small'),
              text(75,638,'圈自由内径：上145.85/下144.60±0.10','small'),
              text(75,674,'四瓣先回缩1.10±0.05，盘固定，壳体上提','small')]
    # 10 px/mm剖面：铜瓣与整环座无金属接触；下密封静止。
    parts += [box(430,525,30,90,'#d9ad83'),box(462,525,50,140,'#cbd5e1'),
              box(441.25,530,18.75,37.5,'#ffffff'),
              '<ellipse cx="451.6" cy="548.75" rx="10.4" ry="15.1" fill="#059669" stroke="#334155"/>',
              circle(445,600,5.5,fill='#ffffff',stroke='#2563eb'),
              circle(445,580,7,fill='#ffffff',stroke='#2563eb'),
              box(430,616,30,15,'#8cb6ae'),box(433,627,14,4,'#ffffff'),
              '<ellipse cx="440" cy="631.5" rx="7" ry="3.55" fill="#059669" stroke="#334155"/>',
              box(377,634.1,75,10,'#4f9ea3'),box(377,644.1,75,60,'#4f9ea3'),box(449,631,3,3.1,'#4f9ea3')]
    notes(parts,[
      '铜环C11000；4×90°径向导轨＋正向回退',
      '上圈2.47～2.53；候选Kalrez 7075UP',
      '冷态实测压缩0.415～0.425；按圈配槽',
      '上槽深1.835～1.915按圈配作，宽3.75±0.02',
      '上圈滑动桥及铜瓣退位详见HJ-010',
      '下圈0.99～1.01；槽0.40±0.01×1.40±0.02',
      '下槽在连续密封座；实测压缩0.28～0.29',
      '水道下Ø1.10/上Ø1.40，+0.02/0',
      '水道距铜底1.50/3.50±0.02，R73.3',
      '上槽中心距铜底6.625±0.01',
      '最小铜壁0.50；每道84°＋两端3.5直道',
      '水≥0.60 L/min；入口20±2℃；出口≤35℃',
      '铜≤45℃；下座≤48℃；钢壳带≤180℃',
      '0.3 MPa水路检漏；密封装夹力≤1500 N',
      '气幕10～15；保护8～12；补氩0～12',
      '抽吸22～28 L/min；开口腔近大气压',
      '气幕歧管0.25～2.8 kPa；流量10～15',
      '四瓣径向退1.10±0.05，全周净隙≥0.10',
      '退位确认→上部上提→壳体托环上提→冷态测量',
      '水道在z92/z94分型加工半圆槽',
      '真空级Ag-Cu钎焊封道后精加工'],x=620,y=145,step=27)
    return finish(parts,'C11000 / FFKM')


def workstation_sheet(spec,result):
    sys.path.insert(0,str(ROOT/'studies/COMPETITION-DESIGN'))
    from inspection_capacity import evaluate as capacity_evaluate
    heads=spec['process'].get('simultaneous_heads',1)
    stages=len(spec['process']['sequence'])*spec['process']['pass_count']/heads
    station=result['process']['arc_on_time_s']/heads+stages*18
    pt_wait=math.ceil(4080/station);ut_stations=math.ceil(600/station)
    capacity=capacity_evaluate(station)
    operators=capacity['inspection_operator_equivalents'];clean_positions=capacity['cleanliness_parallel_positions']
    parts=sheet('自动焊接工作站与工装资源配置','HJ-008','孔内工装保持至温度释放门；上提转运后同一A托环保持至20±1℃，测量前再解除')
    positions=[60,275,490,705,920]
    for x,title in zip(positions,['装配','机器人焊接','带工装冷却','上提转运后冷却','独立检测']):
        parts += [box(x,240,200,140,'#e7f1f5'),text(x+15,280,title,'section')]
    parts += [text(75,320,'清洗、装夹120 s','small'),text(290,320,'两道8段','small'),
              text(290,347,f'{heads}头，站占用{station:.1f} s','small'),text(505,320,'保持胀套和压环','small'),
              text(720,320,'底座保持至20±1℃','small'),text(935,320,'CMM独立A/B','small'),
              text(935,347,'微珩前/后各CMM360 s','small'),
              text(75,178,'前工序：Ni99两层预制→24 h延迟PT→连接面与孔精加工→清洗封存→合格座体库存','small')]
    for x in positions[:-1]:parts.append(line(x+200,310,x+213,310,'#176b7b',3))
    resource_text=f'固定定位窝数按 N≥ceil[(120＋工装释放时刻＋60)/{station:.1f}]；环境缓冲位另计'
    verification=result.get('numerical_verification',{}).get('position')
    if verification and verification['position_design_pass']:
        rows=verification['records'];release=max(r['release_time_s'] for r in rows)
        final=max(r['final_time_s'] for r in rows)
        pallets=math.ceil((120+release+60)/station)
        buffers=math.ceil(max(0,final-release)/station)
        resource_text=f'计算较长释放{release:.1f} s / 冷态{final:.1f} s；配置≥{pallets}个固定定位窝、≥{buffers}个底座冷却位'
    parts += [box(345,430,500,95,'#f8fafc'),text(368,463,'机器人沿线移位；固定定位窝，工件/水管不旋转','small'),
              text(368,498,'安全PLC：防护门、夹紧、气幕、保护气、漏水、轨迹','small'),
              text(80,590,f'焊接站{station:.1f} s；装配120；需微珩时CMM2×360 s（≥{capacity["CMM_parallel_stations"]}站）＋微珩200 s（≥1站）','small'),
              text(80,625,resource_text,'small'),
              text(80,660,f'PT单件33～68 min：≥{pt_wait}等待位；UT600 s/件：≥{ut_stations}工位；检测人员≥{operators}当量','small'),
              text(80,691,f'逐件干态300 s：≥{clean_positions}位置；1800 s液体提取只用于牺牲样，独立实验室','small')]
    return finish(parts)


def following_peener_sheet(spec,result):
    parts=sheet('随动热态轻击、前侧送丝与退位时序','HJ-009','根道/盖面使用独立Z高度；轻击跟随已凝固焊道，停弧后快速扫尾')
    X=lambda r:60+(r-40)*11
    Y=lambda z:615-(z-110)*10
    parts += [text(65,145,'两剖面叠加示意，枪—锤周向错开','small'),
              box(X(75),Y(152),55,Y(102)-Y(152),'#dbe5ed'),
              box(X(40),Y(115),X(75)-X(40),Y(102)-Y(115),'#f2e5cc'),
              polygon([(X(72.2),Y(115)),(X(75),Y(115)),(X(75),Y(117.8))],'#eabe78'),
              box(X(45)-27.5,Y(118.5213)-25,X(71.4787)-X(45)+27.5,50,'#bdd2e2'),
              box(X(45)-27.5,Y(123),55,Y(118.5213)-Y(123),'#bdd2e2'),
              box(X(45)-55,Y(135),110,Y(123)-Y(135),'#c4dce0'),
              circle(X(71.4787),Y(118.5213),33,'#b7d9d1'),
              line(X(73.25),Y(119.465),X(69.25),Y(126.394),'#b16c37',5),
              polygon([(X(73.58),Y(128.894)),(X(64.92),Y(123.894)),
                       (X(52.42),Y(145.544)),(X(61.08),Y(150.544))],'#efe7dd'),
              text(66,346,'远置Ø10竖向气动驱动','small'),
              text(73,455,'R45；z123～135','small'),
              text(75,495,'Ø5 H13横臂，45±1 HRC','small'),
              text(290,605,'根道接触R73.6/z116.4','small'),
              text(65,652,'Ø6圆头；热态许用600 MPa，峰值≤200 N','small'),
              text(65,683,'退位：先升枪丝120，再升轻击头，禁止交叉抬升','small')]
    parts += [text(635,145,'俯视运动与段尾覆盖（NTS）','section'),
              line(665,340,1010,340,'#b16c37',4),
              circle(790,310,18,'#b7d9d1'),box(850,270,35,60,'#efe7dd'),
              line(985,250,860,318,'#6688a3',4),
              line(860,215,1030,215,'#176b7b',3),text(875,200,'焊接/送丝前侧 →','small'),
              line(790,372,868,372,'#334155',1),
              text(730,400,'未上提前枪—锤间距4.5～7.0','small'),
              text(669,368,'焊道','small')]
    notes(parts,[
        '根道枪74.5/117.3；丝73.2/116.0',
        '盖面枪74.0/118.0；丝72.7/116.7',
        '丝沿(-0.35,+0.93,+0.11225)延伸15后转竖直',
        '100 Hz；实测接触宽≥0.72，压痕深≤0.05',
        '扫尾≤18 mm/s、≤300 mm/s²，搭接≥75%',
        '表面400～500℃；测温/指令总延迟≤20 ms',
        '停弧0.20 s内枪丝升40，轻击轴继续扫尾',
        '气压0.2～0.4 MPa；驱动行程≤2，力另校准',
        '段两端各0.5及QT/焊趾/熔合线不施击',
        '坐标为热态R/z；枪/丝/锤各落点误差≤0.05'],x=625,y=447,step=28)
    return finish(parts,'H13 / 气动驱动')


def copper_retreat_sheet(spec,result):
    parts=sheet('铜瓣接缝、滑动桥及整环下密封座','HJ-010','本页为HJ-004/HJ-007配套装配详图；关键尺寸单独标注，不采用未注公差')
    parts += [text(65,155,'A：上槽接缝展开（NTS）','section'),
              box(75,210,185,80,'#d9ad83'),box(340,210,185,80,'#d9ad83'),
              box(185,228,220,35,'#8cb6ae'),circle(210,245,5,'#334155'),
              line(350,280,400,280,'#176b7b',3),text(355,312,'滑动端 →','small'),
              text(75,340,'接缝2.00±0.05；桥316L厚0.50±0.02','small'),
              text(75,370,'单端固定／另一端袋槽长6；初始搭接4','small'),
              text(75,400,'桥面按槽底配作；最小铜内壁0.510','small'),
              text(75,430,'退位最坏接缝0.324；搭接仍≥2.374','small'),
              text(65,487,'B：整环座与闭底盘（NTS）','section'),
              box(245,525,240,38,'#d9ad83'),box(245,574,240,20,'#8cb6ae'),
              box(355,589,58,10,'#ffffff'),circle(385,602,8,'#059669'),
              box(165,618,320,16,'#4f9ea3'),box(375,634,110,70,'#4f9ea3'),box(477,594,8,24,'#4f9ea3'),
              line(280,574,280,652,'#334155',3),
              text(65,545,'铜底z90.50','small'),text(65,577,'座顶90.40','small'),
              text(65,607,'下圈静封盘','small'),text(65,660,'闭底盲螺纹','small')]
    notes(parts,[
        '整环座17-4PH H900；149.60/143.60',
        '厚1.50±0.02；顶z90.40±0.02',
        '铜底z90.50±0.02；最小净隙0.06',
        '底槽R72.8；深0.40±0.01，宽1.40±0.02',
        '座底z88.90；盘顶名义z88.59（配作）',
        '受载状态实测下圈压缩0.28～0.29',
        '8内耳宽10、R65～72，22.5°＋45°等分',
        '8×ISO10642 M3×6：R69.00±0.05',
        '头齐平或凹0～0.02；锥座配作≤0.15',
        '含钻尖盲深≤5.5；底厚≥1.40/侧壁≥0.90',
        '盘底环内R66.50±0.05、厚6.00±0.02',
        '盘厚1.00±0.02；M3实测总长≤6.30',
        'R73.7～74整环止挡高0.31配作，旁路预紧',
        '每瓣2铜端口凸台2×4×6，距接缝3°',
        '水路84°弧＋两端各3.5直道；独立检漏',
        '桥袋槽径深0.53 +0.01/0；距水道≥0.50',
        '8柔性铜热带，合计导热≥0.75 W/K',
        '座≤48℃；附加2 W计入单瓣10 W包络',
        '铜瓣先退1.10±0.05；座与盘保持静止',
        '热带与软管固定留运动弯；禁止自由拖曳',
        '退位确认后壳体上提；盘固定朝上、颗粒留盘'],x=620,y=150,step=27)
    return finish(parts,'C11000 / 17-4PH')


def water_route_sheet(spec,result):
    from hanjie.domain.water_route import bends
    parts=sheet('密封穿盘分配块与铜瓣运动水路','HJ-011','俯视按安装中心线投影；固定水块随盘封底，16根柔性管容纳铜瓣1.15 mm回缩')
    cx,cy,scale=305,350,2.85
    point=lambda p:(cx+scale*p[0],cy-scale*p[1])
    parts += [circle(cx,cy,74.8*scale,fill='#d9ad83'),circle(cx,cy,71.8*scale,fill='#ffffff'),
              circle(cx,cy,36*scale,fill='#e8eef2'),text(65,125,'俯视：全16管与4固定块（NTS）','section'),
              text(cx-65,cy+5,'承力盘R36','small')]
    for i in range(4):
        a=math.radians(45+90*i)
        corners=[point((x*math.cos(a)-y*math.sin(a),x*math.sin(a)+y*math.cos(a)))
                 for x,y in [(49,-8),(61,-8),(61,8),(49,8)]]
        parts.append(polygon(corners,'#c3d5df'))
    for stroke in (1.15,0.):
        curves,_,_=bends(stroke,count=81)
        for i,c in enumerate(curves):
            colour='#bcc7cf' if stroke else ('#2563eb' if i<8 else '#059669')
            for a,b in zip(c,c[1:]):parts.append(line(*point(a),*point(b),colour,1 if stroke else 2))
            if not stroke:
                # Show the fixed metal inlet between the Cu boss and PFA exit.
                quarter=(i%8)//2;mirror=i%2;angle=quarter*math.pi/2
                rad=(math.cos(math.radians(3)),math.sin(math.radians(3)))
                xy=(71.8*rad[0],71.8*rad[1])
                if mirror:xy=(xy[1],xy[0])
                xy=(xy[0]*math.cos(angle)-xy[1]*math.sin(angle),xy[0]*math.sin(angle)+xy[1]*math.cos(angle))
                parts.append(line(*point(xy),*point(c[0]),'#b16c37',1.8))
    parts += [text(65,595,'蓝：下水道z92；绿：上水道z94；灰：回缩位','small'),
              text(65,622,'穿盘剖面（NTS）：水路独立，块周气密焊','small'),
              box(240,635,70,48,'#c3d5df'),box(130,674,110,5,'#4f9ea3'),box(310,674,110,5,'#4f9ea3'),
              line(253,643,265,643,'#2563eb',3),line(265,643,265,693,'#2563eb',3),
              line(297,653,286,653,'#059669',3),line(286,653,286,693,'#059669',3),
              text(330,660,'盘顶88.59','small'),text(330,691,'盘下独立供回水','small')]
    notes(parts,[
        '块体316L：12径向×16切向，R55',
        '45°起等分90°；底83.59、顶99.00',
        '盘板连续气密焊；不得留开放穿盘孔',
        '局部端口：x58/z92、x52/z94，y±8',
        '纵孔x52/58、y±3，侧帽齐平/流道隙≥0.5',
        '铜凸台上下口径向错开10；不直接开M5',
        '铜管OD1.80插入3；转向块5×5×5',
        '定制316L M4×0.5压紧接头≤Ø5×8',
        'PFA插入≥4；低析出卡套；铜管不循环弯折',
        '管OD2/ID1；有效ID≥0.95，实装包络Ø2.20',
        '管起点R66.8/56.8，沿3°切向偏置9',
        '自由运动弧长31.42/24.51，固定防擦',
        '每根名义总长≤100，极限≤105',
        '安装全行程弯曲R≥12；核算最小16.52',
        '管间计采样余量表面净隙≥3.85',
        '每支路0.075～0.07875 L/min，8路平衡',
        '支路压降设计上界53.45 kPa，压差≥80',
        '工作≤0.3 MPa/60℃；各路独立检漏',
        '首件循环确认回弹、耐压及颗粒',
        '铜瓣径退；胀套上提；壳体托环上提；盘不移动'],x=620,y=150,step=27)
    return finish(parts,'316L / Cu / PFA')


def portal_sheet(spec,result):
    parts=sheet('固定反锥、上止挡门架与A基准保持转运','HJ-013',
                '反锥、铜环和接料盘固定；打开上止挡→胀套上提260→壳体连托环上提140')
    cx,base,sc=285,540,.60
    xx=lambda r:cx+r*sc
    yy=lambda z:base-z*sc
    def rz(a,b,z0,z1,col):return box(xx(a),yy(z1),(b-a)*sc,(z1-z0)*sc,col)
    parts += [text(65,150,'装夹状态剖面（NTS）','section'),
              rz(-72,72,-20,80,'#9baeb7'),rz(-36,36,80,94,'#9baeb7'),
              rz(-30,30,94,99.8,'#9baeb7'),
              polygon([(xx(-19.145),yy(99.8)),(xx(19.145),yy(99.8)),
                       (xx(16.429),yy(115.2)),(xx(-16.429),yy(115.2))],'#7e9cad')]
    for sign in (-1,1):
        for a,b,z0,z1,col in [(75,80,0,200,'#cbd5e1'),(20,74.98,100,115,'#efd18b'),
                 (75.1,90,-20,0,'#6baeb4'),(19.2,20,100.2,115.4,'#91beb5'),
                 (19.3,20.1,115.4,145.4,'#91beb5'),(19.3,23,145.4,155.4,'#91beb5'),
                 (12,35,155.4,400,'#91beb5'),
                 (12,50,380,400,'#91beb5'),(42,68,400,420,'#cc9957'),
                 (55,230,400,500,'#aac1cc'),(140,220,-160,400,'#aac1cc')]:
            aa,bb=sorted((sign*a,sign*b));parts.append(rz(aa,bb,z0,z1,col))
    parts += [line(cx,yy(-25),cx,yy(520),'#7a939f',.7),
              text(70,667,'上下承力路径独立；上驱动径向浮动，500 N压环球铰传力','small'),
              text(70,690,'门架腿示意投影；实际四柱位于(±180,±180)，与底座同平面','small')]
    notes(parts,[
        '45钢整体实心反锥：下大、上小，半角10°',
        '有效接触z100.2～114.8；两端各延伸0.4',
        '上承力筒Ø70/Ø24，L244.6，z155.4～400',
        '止挡头Ø100×20，z380～400；门架孔Ø110',
        '门架板460×460×100，z400～500；四柱Ø80',
        '四柱z−160～400；按360净跨、120有效条带核算',
        '两止挡26×30×20，z400～420；径退20后放行',
        '止挡口袋x42～90及−90～−42；接触宽≥7',
        'M12只作设置/回退；热反力经止挡、筒和门架',
        '胀套先上退1，再上提260；固定锥保持原位',
        'A托环OD180/ID150.20±0.04/厚20保持壳底夹紧',
        '外侧6槽/60°与六点正向转运见HJ-014',
        '壳体连托环上提140：托环底至固定锥顶净隙4.8',
        '胀套底至抬起壳口净隙19.8；铜顶至壳底40.5',
        '完全冷态才松开A托环，独立CMM复测孔轴',
        '铜盘及水路不随转运升降；机器人移动至固定窝',
    ],x=590,y=152,step=35)
    return finish(parts,'45钢 / 17-4PH')


def datum_holder_sheet(spec,result):
    parts=sheet('A基准托环与六点正向转运详图','HJ-014',
        '壳底夹紧在转运时保持；托持托环外槽，禁止夹持轴承孔或以内腔承托')
    cx,cy,sc=300,350,2.0
    parts += [text(65,148,'俯视外槽位置投影；槽不贯穿A面','section'),
              circle(cx,cy,90*sc,'#dbe8eb'),circle(cx,cy,75.1*sc,'#ffffff'),
              circle(cx,cy,82.5*sc,stroke='#7a939f')]
    for i in range(6):
        theta=i*math.pi/3
        points=[]
        for r,t in ((87,-4.1),(91,-4.1),(91,4.1),(87,4.1)):
            points.append((cx+sc*(r*math.cos(theta)-t*math.sin(theta)),
                           cy-sc*(r*math.sin(theta)+t*math.cos(theta))))
        parts.append(polygon(points,'#91b8c0'))
        parts.append(text(cx+204*math.cos(theta)-6,cy-204*math.sin(theta)+5,str(i+1),'small'))
    parts += [text(240,345,'ID150.20±0.04','small'),text(254,372,'OD180 / H20','small'),
              text(65,552,'外槽径向剖面与承托指（NTS）','section'),
              box(200,566,89.28,120,'#dbe8eb'),
              box(271.28,624.8,18.0,14.4,'#ffffff'),
              box(271.28,624.8,68,10.8,'#cc9957'),
              text(346,633,'正向承托指：宽≤8、高≤1.8','small'),
              text(346,658,'向上承压，单点≤100 N；六点同时锁止','small'),
              text(65,707,'槽径向深3；槽高2.4；上缘距A面9.8；槽宽8.2；六槽60°等分','small')]
    h=result['datum_holder_transfer']
    notes(parts,[
        '45钢调质，屈服≥355 MPa；A面精磨',
        '独立托环z−20～0；孔150.20±0.04、外径180',
        '外侧6槽，60°等分；槽底R87，切向宽8.2',
        '槽z−12.2～−9.8，局部盲槽不切穿A面',
        '承托指宽≤8、高≤1.8，正向压住槽上面',
        '六点到位/锁止反馈齐全才上提；单点≤100 N',
        '六指接管后松定位窝锁止，壳体—环夹紧保留',
        f"六点展开跨{h['span_mm']:.3f}；削弱有效宽11.88",
        '按整周槽削弱、厚20、E180 GPa、单跨100 N',
        f"δ=PL³/(48EI)={h['elastic_deflection_bound_mm']*1000:.3f} μm",
        '托环平面/重复定位及永久变化按2 μm验收',
        '保留壳体两个平面定位约束及原A面夹紧',
        '托环随壳体上提140，固定锥和铜盘原位',
        '上提净隙见HJ-013；完全冷态才松开壳体',
        '微珩前后均独立CMM与内腔洁净复检',
    ],x=620,y=152,step=35)
    return finish(parts,'45钢调质')


def postweld_isolation_sheet(spec,result):
    parts=sheet('PT/UT独立接液盘与短孔微珩全收集装置','HJ-015',
        '冷态后序工具；进入NDT/微珩前先闭合隔离，液体/磨屑与不可清洗下腔隔开')
    # No seal is placed on fictitious wing land: the actual outer arc is 18 mm.
    parts += [text(60,148,'A：PT/UT座下整盘（径向剖面NTS）','section'),
        box(78,240,24,140,'#a9bdc9'),box(510,240,24,140,'#a9bdc9'),
        box(122,264,165,60,'#dbe6eb'),box(325,264,165,60,'#dbe6eb'),
        polygon([(110,338),(110,380),(502,380),(502,338),(484,338),(484,360),(128,360),(128,338)],'#eaf4f5'),
        box(102,334,16,25,'#ddba7d'),box(502,334,16,25,'#ddba7d'),
        line(306,380,306,439,'#176b7b',6),line(306,439,505,439,'#176b7b',3),
        text(80,184,'外缘翼片仅18：不设跨槽的虚构封口台面','small'),
        text(80,407,'整盘OD149.40±0.05；壁1/底2；盘面z96、唇z99','small'),
        text(80,466,'缩态密封OD≤149.6；20～30 kPa充气后贴合钢壁','small'),
        text(80,490,'无径向滑擦；膜应力界0.16 MPa，采购强度≥2 MPa','small'),
        text(80,514,'内径147.4/液深3，有效容量48.19 mL；Ø4密闭回液','small')]
    # Bore cup seals on the unbroken central annulus, with no sliding radial
    # seal in the precision bore and no interference with the bore wall.
    parts += [text(635,148,'B：微珩上下罩（轴向剖面NTS）','section'),
        box(650,290,185,70,'#dbe6eb'),box(925,290,185,70,'#dbe6eb'),
        box(715,210,330,60,'#eaf4f5'),box(828,205,104,80,'#ffffff'),
        box(862,160,36,188,'#a9bdc9'),
        polygon([(730,370),(730,435),(1030,435),(1030,370),(1005,370),(1005,410),(755,410),(755,370)],'#eaf4f5'),
        box(735,360,22,10,'#ddba7d'),box(1003,360,22,10,'#ddba7d'),
        line(880,435,880,483,'#176b7b',6),line(880,483,1060,483,'#176b7b',3),
        text(655,515,'下杯OD60/ID44/液深10；密封R27，压紧≤120 N','small'),
        text(655,541,'面圈Ø1.00±0.02；槽0.70±0.01/挡隙0.10±0.01','small'),
        text(655,567,'杯内占位扣3 mL后容量12.21；故障需7.10 mL','small'),
        text(655,593,'供液≤60 mL/min；Ø4下引排液；吸压−2～−5 kPa','small'),
        text(655,619,'失吸0.10 s停进给/供液；管内可回流量≤5 mL','small')]
    parts += [text(70,558,'整盘从壳底竖直装入：缩态→z96就位→充气→吸压/密封联锁','small'),
        text(70,586,'抽尽并原位干燥→壳底接密闭收集筒→保持盘朝上/抽吸→泄压下撤','small'),
        text(70,614,'PT/UT整盘与微珩下杯分工序装入，均从壳底撤出；禁止座下叠放','small'),
        text(70,650,'荧光液及5/10/25 μm颗粒覆盖正常、失吸、停机和撤出；牺牲件下腔未清洗检查','small'),
        text(70,680,'正常产品：过程记录＋干态内窥＋封存；过滤膜提取只用于退出产品流的牺牲件','small')]
    return finish(parts,'316L / 低析出FFKM')


def main():
    spec=read_spec(ROOT)
    result=current_assessment(ROOT)
    if result["spec"] != spec:
        raise ValueError("计算结果已过期，先重建COMPETITION-DESIGN")
    out=ROOT/"cad/generated/engineering-drawings"
    out.mkdir(parents=True,exist_ok=True)
    drawings={"bearing-seat.svg":seat_sheet(spec),"joint-detail.svg":joint_sheet(spec,result),
              "fixture-assembly.svg":fixture_sheet(spec,result),"protected-process-assembly.svg":shield_sheet(spec,result),
              "inspection-and-release.svg":inspection_sheet(spec,result),
              "sleeve-detail.svg":sleeve_detail_sheet(spec,result),
              "gas-water-detail.svg":gas_water_detail_sheet(spec,result),
              "workstation.svg":workstation_sheet(spec,result),
              "following-peener.svg":following_peener_sheet(spec,result),
              "copper-retreat.svg":copper_retreat_sheet(spec,result),
              "water-route.svg":water_route_sheet(spec,result),
              "carrier-detail.svg":carrier_sheet(spec,result),
              "portal-transfer.svg":portal_sheet(spec,result),
              "datum-holder-detail.svg":datum_holder_sheet(spec,result),
              "postweld-isolation.svg":postweld_isolation_sheet(spec,result)}
    for name,parts in drawings.items():
        (out/name).write_text("\n".join(parts),encoding="utf-8")
    core = [name for name in drawings if name != "sleeve-detail.svg"]
    (out/"drawing-manifest.json").write_text(json.dumps({"version":"COMPETITION-R4","source":"project/competition-design.yaml",
        "status":"competition design; not manufacturing release","drawings":core,"drawing_count":len(core),
        "supplemental_drawings":["sleeve-detail.svg"],
        "excluded":"本目录其他SVG/PDF为历史版本；补充详图与核心图集一并导出"},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"已同步{len(drawings)}张参赛设计图")


if __name__ == "__main__":
    main()
