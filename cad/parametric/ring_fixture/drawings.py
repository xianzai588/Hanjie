"""Three A3 sheets: real fixture, interfaces and staged clean withdrawal."""
from pathlib import Path
import os
import subprocess
import tempfile
from xml.sax.saxutils import escape
from pypdf import PdfReader, PdfWriter

ROOT=Path(__file__).resolve().parents[3]
INK="#27384A"; STEEL="#E9EDF0"; CU="#E9C797"; PART="#F4EEE4"; BLUE="#315D83"


class Sheet:
    def __init__(self,number,title):
        self.number=number
        self.p=['<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 1400 990">',
                '<defs><marker id="arr" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto-start-reverse"><path d="M0 0 L7 3.5 L0 7 Z" fill="#27384A"/></marker><pattern id="hatch" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="10" height="10" fill="#EDF0F2"/><line x1="0" x2="0" y1="0" y2="10" stroke="#BBC4CB" stroke-width="1"/></pattern></defs>',
                '<rect width="1400" height="990" fill="white"/>',
                '<g font-family="Noto Sans SC,sans-serif" fill="#27384A" stroke-linejoin="round">']
        self.rect(30,30,1340,930,fill="none")
        self.text(60,78,title,28)
        self.text(60,112,"完整圆环专属工装 | 单位:mm | A3 | 所列尺寸为设计选定",16)
        self.line(30,135,1370,135)
        self.line(30,875,1370,875)
        self.text(60,906,"HJ-F-S01-R2 | 圆环固定题基础站 | 设计/解析与实测分项记录",16)
        self.text(60,938,"材料与热处理按BOM；配锥/基准共同精磨；未注锐边去毛刺，内腔接触处圆滑",14)
        self.text(1110,906,f"比例:NTS | 第{number}/3页",16)
        self.text(1110,938,"严禁按图量取尺寸",14)
    def line(self,x1,y1,x2,y2,color=INK,width=1.4,dash=None):
        self.p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
    def rect(self,x,y,w,h,fill=STEEL,color=INK):
        self.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{color}" stroke-width="1.4"/>')
    def circle(self,x,y,r,fill="none",color=INK):
        self.p.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{color}" stroke-width="1.4"/>')
    def text(self,x,y,value,size=16,color=INK,anchor="start"):
        self.p.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{escape(str(value))}</text>')
    def poly(self,points,fill=STEEL):
        self.p.append(f'<polygon points="'+" ".join(f"{x},{y}" for x,y in points)+f'" fill="{fill}" stroke="{INK}" stroke-width="1.4"/>')
    def dim(self,x1,y1,x2,y2,label,offset=-9):
        self.p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{INK}" marker-start="url(#arr)" marker-end="url(#arr)"/>')
        self.text((x1+x2)/2,(y1+y2)/2+offset,label,14,anchor="middle")
    def arrow(self,x1,y1,x2,y2,color=BLUE):
        self.p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.5" marker-end="url(#arr)"/>')
    def save(self,path):
        path.write_text("\n".join(self.p+['</g></svg>']),encoding="utf8")


def assembly(s,cx,base_y,scale,lift=False):
    X=lambda x:cx+x*scale;Y=lambda z:base_y-z*scale
    R=lambda a,b,z0,z1,fill=STEEL:s.rect(X(a),Y(z1),(b-a)*scale,(z1-z0)*scale,fill)
    R(-230,230,-200,-100,"url(#hatch)");R(-230,230,-100,-20,"url(#hatch)")
    R(-72,72,-20,80,"url(#hatch)");R(-48,48,80,99.8,"url(#hatch)")
    s.poly([(X(-19.1449),Y(99.8)),(X(19.1449),Y(99.8)),(X(18.3378),Y(115.2)),(X(-18.3378),Y(115.2))],"url(#hatch)")
    for a,b in [(-175,-105),(105,175)]:R(a,b,-20,400)
    for a,b in [(-170,-55),(55,170)]:R(a,b,400,480,"url(#hatch)")
    for a,b in [(-74,-48),(48,74)]:R(a,b,83.59,84.59,CU)
    for a,b in [(-74.8,-71.8),(71.8,74.8)]:R(a,b,88.9,99.5,CU)
    h=140 if lift else 0;u=260 if lift else 0
    for a,b in [(-80,-75),(75,80)]:R(a,b,h,200+h,"none")
    for a,b in [(-74.98,-20),(20,74.98)]:R(a,b,100+h,115+h,PART)
    for a,b in [(-90,-75.1),(75.1,90)]:R(a,b,-20+h,h,"url(#hatch)")
    for a,b in [(-19.97,-18.34),(18.34,19.97)]:R(a,b,99.8+u,145.4+u,STEEL)
    for a,b in [(-23,-19.17),(19.17,23)]:R(a,b,145.4+u,155.4+u,STEEL)
    for a,b in [(-35,-12),(12,35)]:R(a,b,155.4+u,440+u)
    for a,b in [(-50,-12),(12,50)]:R(a,b,440+u,460+u)
    for a,b in [(-50,-24),(24,50)]:R(a,b,115+u,123+u)
    for a,b in [(-50,-36),(36,50)]:R(a,b,123+u,175+u)
    if lift:
        for a,b in [(-98,-72),(72,98)]:R(a,b,460,480)
        R(-90,90,117.5,119.5,CU)
    else:
        for a,b in [(-68,-42),(42,68)]:R(a,b,460,480)
    s.line(X(0),Y(-215),X(0),Y(740 if lift else 505),BLUE,1,"14 4 2 4")
    return X,Y


def sheet1(manifest,result):
    s=Sheet(1,"HJ-F-S01 工装总装与载荷闭环")
    X,Y=assembly(s,390,630,.80)
    s.text(80,169,"A-A 剖视（安装状态）",18)
    s.dim(X(-230),822,X(230),822,"460")
    s.dim(120,Y(-200),120,Y(-20),"180",-10)
    s.text(80,855,"RF02钢床座100 + RF01基板80；基板顶z−20",14)
    s.arrow(X(-100),Y(115.2),X(-22),Y(115.2));s.text(80,Y(115.2)-20,"5 kN + 170 kN·mm",15)
    s.text(80,192,"侧向反力: 孔→3°反锥→Ø96颈→Ø144柱→底座/床座",14)
    s.text(80,217,"轴向反力: 胀套/压环→承力筒→双止挡→上桥→双柱",14)
    s.text(690,165,"基板俯视（轴向钻孔位置以BOM/STEP为准）",17)
    cx,cy,sc=1015,365,.63
    s.rect(cx-230*sc,cy-200*sc,460*sc,400*sc,"none")
    for dia,color in [(180,INK),(160,BLUE),(144,INK)]:s.circle(cx,cy,dia/2*sc,color=color)
    for x in (-140,140):s.circle(cx+x*sc,cy,35*sc,STEEL)
    for x,y in result["anchors"]["coordinates_mm"]:s.circle(cx+x*sc,cy-y*sc,16.5*sc,"white")
    s.line(cx-160,cy,cx+160,cy,BLUE,1,"12 3 2 3");s.line(cx,cy-150,cx,cy+150,BLUE,1,"12 3 2 3")
    s.dim(cx-230*sc,520,cx+230*sc,520,"460")
    s.text(760,565,"18-M30×140 / Ø33通孔；100±10 kN/只",16)
    s.text(760,592,"18孔坐标: 主排y=±150，x=0/±55/±110/±165",14)
    s.text(760,617,"侧排x=±185，y=±75；床座啮合≥60",14)
    s.text(760,662,"双柱Ø70，中心(±140,0)，长420",16)
    s.text(760,692,"上桥340×220×80，桥底z400，中央孔Ø110",16)
    s.text(760,722,"桥孔削弱后有效条带b110纳入弯曲和剪切",14)
    s.text(760,752,"上桥4-M16×110；双止挡26×30×20",16)
    s.text(760,782,"止挡外退30后，Ø100上头可穿Ø110通孔",14)
    s.text(760,828,"RF01/RF02全底面贴合；机台余量见第3页",15)
    return s


def sheet2(manifest,result):
    s=Sheet(2,"HJ-F-S02 孔内胀套、铜屏障与气水接口")
    cx,sc,by=380,4.0,775
    X=lambda x:cx+x*sc;Y=lambda z:by-(z-80)*sc
    R=lambda a,b,z0,z1,fill=STEEL:s.rect(X(a),Y(z1),(b-a)*sc,(z1-z0)*sc,fill)
    s.text(80,168,"B-B 近孔区放大剖视",18)
    R(-48,48,80,99.8,"url(#hatch)")
    s.poly([(X(-19.1449),Y(99.8)),(X(19.1449),Y(99.8)),(X(18.3378),Y(115.2)),(X(-18.3378),Y(115.2))],"url(#hatch)")
    for a,b in [(-74.98,-20),(20,74.98)]:R(a,b,100,115,PART)
    for a,b in [(-50,-24),(24,50)]:R(a,b,115,123)
    for a,b in [(-50,-36),(36,50)]:R(a,b,123,175)
    for a,b in [(-35,-12),(12,35)]:R(a,b,155.4,180)
    for a,b in [(-23,-19.17),(19.17,23)]:R(a,b,145.4,155.4)
    for a,b in [(-19.97,-19.17),(19.17,19.97)]:R(a,b,115.4,145.4)
    for a,b in [(-19.97,-18.34),(18.34,19.97)]:R(a,b,99.8,115.4)
    s.line(X(0),Y(77),X(0),Y(184),BLUE,1,"12 4 2 4")
    s.dim(X(-48),810,X(48),810,"Ø96上颈")
    s.text(80,842,"图示接触按名义位；最大胀开Ø40.04为行程限位",14)
    s.text(760,170,"制造与配合要求",20)
    items=["固定反锥: 3°半角，z99.8～115.2",f"下Ø38.2898 / 上Ø{result['inputs']['cone_top_diameter_mm']:.4f}",
           "有效配锥带z100.2～114.8，Ra≤0.2", "胀套: 17-4PH H900；六槽宽0.8",
           "弹性颈L30、t0.80；根部Ø46/38.34×10", "塌缩Ø39.94；孔Ø40名义径向间隙0.03",
           "正向上退1.5，3°锥释放0.0786径向", "µ>tan3°可自锁；禁止只靠弹簧松脱",
           "独立压环OD100/ID48，轴压500 N", "气缸/驱动径向浮动，推力经球面座传递"]
    for i,t in enumerate(items):s.text(760,215+i*31,t,16 if i in (0,3,5,8) else 14)
    s.line(730,545,1320,545)
    s.text(760,585,"屏障与气水分区",20)
    details=["铜瓣工作顶z99.5，距座底0.5；径退1.10±0.05", "固定盘外径148、底z83.59；中央口Ø96连续气密焊",
             "水块最小R49，Ø96颈R48，名义净隙1.00", "16水孔Ø4，4块各4路；立管OD4/ID2.5",
             "水路z−40/−30分层径向出侧面，气路z−55独立", "2气孔Ø6位于x±62；固定反锥保持实心",
             "软管16根OD3，弯曲半径按空间路径记录", "铜水路泄漏信号→停弧；盘和回收水路固定在站内"]
    for i,t in enumerate(details):s.text(760,622+i*29,t,14)
    return s


def sheet3(manifest,result):
    s=Sheet(3,"HJ-F-S03 受控退出、质量范围与刚度分配")
    s.text(70,171,"C-C 安装 → 完全退出（名义位置）",18)
    assembly(s,250,700,.57,False);assembly(s,625,700,.57,True)
    s.text(140,217,"安装/施焊",16);s.text(535,217,"产品上升140 + 上工具260",16)
    s.text(70,251,"RF20无孔盖：在z116.7从+y200横插至轴心，再上升0.8",15)
    s.text(70,279,"横插时锥顶净隙1.5、垫顶至托环0.8、盖至柱内缘15",14)
    s.arrow(405,405,470,405)
    s.text(70,844,"盘/铜/下反锥原位；产品从其外侧抬离，封底后沿+y横移",14)
    x=925
    s.text(x,170,"退出操作与净隙",20)
    notes=["1. 停弧≥120 s且最高温<55℃", "2. 压环卸载；双止挡外退30", "3. 胀套主动上退1.5，确认收拢", "4. 铜瓣径退1.10；上工具升260",
           "5. A托环接管；壳体+托环升140", "6. 盖底z116.7，从+y200横插至轴心",
           "   盖+密封上升0.8，贴合锁定", "7. 封底反馈后，产品+y横移360",
           "壳上口z340 → 桥底z400: 60", "上胀套底z359.8 → 壳上口: 19.8",
           "托环底z120 → 反锥顶115.2: 4.8", "底盖下表面117.5 → 反锥顶: 2.3"]
    for i,t in enumerate(notes):s.text(x,211+i*23,t,14)
    s.line(x,492,1325,492)
    s.text(x,527,"冷态径向解析分配 / μm",20)
    vals=[("实际下柱/颈/锥（含气水孔）",result["lower_arbor_axis_displacement_um"]),
          ("基板与钢床座",result["base_block_axis_displacement_um"]+result["steel_bed_axis_displacement_um"]),
          ("预紧螺栓弹性转角",result["anchor_elastic_axis_displacement_um"]),
          ("上筒/桥/柱/止挡轴压折算",result["upper_axial_path"]["radial_equivalent_um"]),
          ("接触坐实增量分配",.25),
          ("合计（径向分配6.5）",result["cold_structural_plus_seating_allocation_um"]),
          ("机台摇摆剩余分配",result["remaining_foundation_and_seating_budget_um"])]
    for i,(label,value) in enumerate(vals):s.text(x,566+28*i,label,14);s.text(1320,566+28*i,f"{value:.3f}",14,anchor="end")
    s.text(x,781,f"制件 {manifest['mass_summary_kg']['fabricated_fixture_components']:.2f} kg + 床座 {manifest['mass_summary_kg']['supplied_steel_machine_bed']:.2f} kg",14)
    s.text(x,809,"标准件包络质量另列；采购件非实心质量",13)
    s.text(x,837,"热态、机台和坐实资格按工装卡执行",14)
    return s


def create(out,manifest,result):
    docs=[]
    with tempfile.TemporaryDirectory(prefix="ring-fixture-fonts-") as d:
        config=Path(d)/"fonts.conf"
        config.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'+f'<dir>{escape(str(ROOT / "assets/fonts"))}</dir><cachedir>{escape(d)}</cachedir></fontconfig>',encoding="utf8")
        env={**os.environ,"FONTCONFIG_FILE":str(config)}
        for i,s in enumerate((sheet1(manifest,result),sheet2(manifest,result),sheet3(manifest,result)),1):
            svg=out/f"HJ-F-S0{i}-ring-fixture.svg";s.save(svg)
            pdf=svg.with_suffix(".pdf");png=svg.with_suffix(".png")
            subprocess.run(["inkscape",str(svg),"--export-type=pdf",f"--export-filename={pdf}"],env=env,check=True,stdout=subprocess.DEVNULL)
            subprocess.run(["pdftoppm","-singlefile","-scale-to","1800","-png",str(pdf),str(png.with_suffix(''))],check=True,stdout=subprocess.DEVNULL)
            docs.append(pdf)
    writer=PdfWriter()
    for pdf in docs:writer.append(PdfReader(pdf))
    with (out/"HJ-F-S01-ring-fixture-drawings.pdf").open("wb") as f:writer.write(f)
