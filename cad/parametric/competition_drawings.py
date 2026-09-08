"""从参赛配置及真实座体BREP生成四张设计图；尺寸要求与能力验证分开。"""
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


def finish(parts):
    return parts+[line(50,719,1150,719),text(50,746,"COMPETITION-R1 | 单位 mm | 设计图，未作制造签审 | 尺寸及能力要求不代表实测结果","small"),
                  text(50,768,"来源：project/competition-design.yaml；座体采用6P-FAIR_B真实BREP；工装柔性、热接触与生产设备未验证","small"),'</svg>']


def notes(parts,items,x=640,y=167,step=38):
    for i,item in enumerate(items):
        parts.append(text(x,y+i*step,item))


def seat_sheet(spec):
    parts=sheet("接头布局、座体尺寸与独立基准","HJ-R1-001","主设计：6P-FAIR_B，六段各18 mm；圆周段长来自真实圆柱界面测量")
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
    for i in range(6):
        angle=i*math.pi/3
        parts.append(text(cx+205*math.cos(angle)-5,cy-205*math.sin(angle)+5,str(i+1),"section"))
    notes(parts,["材料：QT450-10座体 / Q235B壳体",
                 "座体厚12；中心环外径82；槽根R2",
                 "外缘直径149.94～149.98（设计限值）",
                 "壳体内径150.00～150.02（设计限值）",
                 "径向装配间隙0.01～0.04，不能靠间隙定心",
                 "座体底面距壳体下端100（工序设计尺寸）",
                 "孔径40.000～40.025（自行分配公差）",
                 "A：壳体下端独立安装面",
                 "B：壳体内壁双测量带所建立的轴线",
                 "B定向按A法向约束；不以胀套轴冒充B",
                 "Ø40孔轴：位置度 Ø0.05，相对A、B",
                 "测量长度12；不默认扩展到整根主轴",
                 "C仅周向识别焊段，不加入位置度基准框"])
    return finish(parts)


def joint_sheet(spec,result):
    parts=sheet("四道焊接截面与工艺设计卡","HJ-R1-002","角焊缝：6×18；单段逐道焊；相邻段不同时起弧；本卡为工艺提案，不是评定合格WPS")
    parts += [box(435,185,50,360,"#cbd5e1"),box(115,485,320,60,"#efd18b"),
              polygon([(435,485),(235,485),(435,285)],"#e2a18b"),
              text(145,580,"QT450-10，t12"),text(410,165,"Q235B，t5"),
              text(140,230,"等效焊脚 z=3.50～3.80","section"),
              line(140,242,325,368,"#176b7b"),text(95,630,"图示为最终包络；四道面积不等于实际熔池形状"),
              text(95,663,"每道沉积目标1.531～1.801 mm²；总面积6.125～7.206 mm²","small")]
    notes(parts,["方法：自动TIG；直流正接（电极负极）",
                 "焊材：NiFe 55类TIG实心棒，Ø1.6",
                 "电流75 A；电压12 V；焊速1.5 mm/s",
                 f'固定送丝 {result["process"]["fixed_feed_mm_s"]:.3f} mm/s；共4道',
                 "沉积效率假设0.85～1.00，固定送丝计算",
                 "纯氩99.999%；名义10 L/min",
                 "预热名义150℃；起弧前各监测点≥130℃",
                 "层间最高温度<200℃；超温等待",
                 "每道顺序 1→4→3→6→2→5",
                 "每道净热输入330 J/mm；四道1320 J/mm",
                 "本件净热输入142.56 kJ；弧燃时间288 s",
                 "停弧后≥120 s且最高温度<55℃才松夹",
                 "冷却至20±1℃后独立测量并判定"])
    return finish(parts)


def fixture_sheet(spec,result):
    f=spec["fixture"]
    parts=sheet("胀套定位、端面夹紧与主动回退","HJ-R1-003","内部锥只驱动圆柱胀套；轴向500 N通过独立压环—座体—底部三支点承受")
    # 局部剖面放大，不将占位外包络伪装成加工细节。
    parts += [box(90,325,125,110,"#efd18b"),box(415,325,125,110,"#efd18b"),
              box(218,325,12,110,"#8cb6ae"),box(400,325,12,110,"#8cb6ae"),
              polygon([(230,422),(400,422),(370,295),(260,295)],"#b2c4cc"),
              box(302,160,26,150,"#b2c4cc"),box(155,295,320,30,"#8cb6ae"),
              box(150,435,42,90,"#9baeb7"),box(440,435,42,90,"#9baeb7"),
              box(140,525,355,30,"#9baeb7"),box(297,555,38,90,"#9baeb7"),
              text(125,140,"功能剖面：槽口及密封连接见技术要求","small"),
              text(80,220,"独立压环：500 N"),text(350,220,"内置拉杆／顶回肩"),
              text(100,593,"三支点位于R30，等间隔120°","small"),
              text(100,627,"支点端面极差≤0.003（制造要求）","small"),
              text(100,661,"承力柱Ø20；下托盘Ø72×4；支点Ø8","small")]
    notes(parts,["孔内接触件为开缝圆柱胀套，避免孔缘楔入",
                 "收拢外径39.94；最大撑开外径40.04",
                 "两接触带：z101～103、109～111",
                 "锥半角10°；锥不与工件孔直接接触",
                 "正向顶回肩＋拉杆；回退行程1.00",
                 f'覆盖全径差所需理想行程 {result["fixture"]["positive_return_stroke_required_mm"]:.3f}',
                 "μ=0.20仍可能自锁，禁止仅靠弹簧回位",
                 "径向合力标量上限100 N（机构设计要求）",
                 "摩擦未知时驱动力上限17.63 N，再限行程",
                 "0.221 MPa仅名义平均带压，不是峰值",
                 "上部压环／执行器包络R30，z112～220",
                 "温度满足→压环卸载→顶回→确认收拢",
                 "下部支承与接料盘同一组件向下退出"])
    return finish(parts)


def shield_sheet(spec,result):
    parts=sheet("连续防护、承力组件与退出路径","HJ-R1-004","底口在焊接与回收工序均保持开放；内机件在本工序以后安装；底部预留120 mm操作空间")
    scale,cx,base=2.25,290,670
    x=lambda r:cx+r*scale
    y=lambda z:base-z*scale
    def rz(r0,r1,z0,z1,color):
        return box(x(r0),y(z1),(r1-r0)*scale,(z1-z0)*scale,color)
    for sign in (-1,1):
        lo,hi=sorted((75*sign,80*sign)); parts.append(rz(lo,hi,0,200,"#cbd5e1"))
        lo,hi=sorted((20*sign,74.98*sign)); parts.append(rz(lo,hi,100,112,"#efd18b"))
        lo,hi=sorted((26*sign,34*sign)); parts.append(rz(lo,hi,90,100,"#9baeb7"))
        points=[(72*sign,90.5),(75*sign,94),(75*sign,93.85),(72*sign,90.35)]
        parts.append(polygon([(x(r),y(z)) for r,z in points],"#4f9ea3"))
    parts += [rz(-74,74,90,91,"#4f9ea3"),rz(-36,36,86,90,"#9baeb7"),rz(-10,10,-20,86,"#9baeb7"),
              rz(-30,30,112,220,"#8cb6ae"),line(x(40),y(84),x(40),y(-10),"#176b7b",3),
              polygon([(x(37),y(-6)),(x(43),y(-6)),(x(40),y(-12))],"#176b7b"),
              text(65,155,"同轴工序剖面，翼片方向简化投影","small"),
              text(65,698,"盘面保持朝上，下撤全程贴壁，不折叠脏面","small")]
    notes(parts,["刚性盘Ø148；底板1；底面z90",
                 "连续薄裙：安装外缘Ø150，z94；t0.15",
                 "盘体—薄裙、穿盘支承均连续密封连接",
                 "薄裙径向顺应能力要求≥0.35",
                 "贴壁后覆盖R74.98落物路径；不留1 mm缝",
                 "名义接触不等于热态密封；磨损需验证",
                 "下撤不经过Ø40孔，不依赖收折倒渣",
                 "焊枪30°弯头＋竖直枪体；喷嘴Ø10",
                 "送丝管与焊枪周向错开，出口偏置y=-4",
                 f'所建模焊枪／送丝最小间距 {result["geometry"]["torch_feed_clearance_mm"]:.2f}',
                 "执行互锁：防护在位、底口开放、轨迹确认",
                 "冷却松夹→胀套顶回确认→组件下撤→封盖",
                 "内窥镜＋全表面颗粒检查，不以低飞溅免责"])
    return finish(parts)


def main():
    spec=read_spec(ROOT)
    result=current_assessment(ROOT)
    if result["spec"] != spec:
        raise ValueError("计算结果已过期，先重建COMPETITION-DESIGN")
    out=ROOT/"cad/generated/engineering-drawings"
    out.mkdir(parents=True,exist_ok=True)
    drawings={"bearing-seat.svg":seat_sheet(spec),"joint-detail.svg":joint_sheet(spec,result),
              "fixture-assembly.svg":fixture_sheet(spec,result),"protected-process-assembly.svg":shield_sheet(spec,result)}
    for name,parts in drawings.items():
        (out/name).write_text("\n".join(parts),encoding="utf-8")
    (out/"drawing-manifest.json").write_text(json.dumps({"version":"COMPETITION-R1","source":"project/competition-design.yaml",
        "status":"competition design; not manufacturing release","drawings":list(drawings),"drawing_count":len(drawings),
        "excluded":"本目录其他SVG/PDF为历史版本，当前导出仅读取此清单"},ensure_ascii=False,indent=2),encoding="utf-8")
    print("已同步四张参赛设计图")


if __name__ == "__main__":
    main()
