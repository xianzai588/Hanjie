"""Vector tolerance, UT access and manufacturing BOM sheets from current design."""
import json,math,sys
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape,A3
from reportlab.lib.colors import HexColor
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
    text(c,42,45,'工艺设计工程图 | 单位mm | NTS，不按比例量图 | 2026-10-07 | 技术文件匿名',10)
    return c,file


def poly(c,points,fill,stroke='#506579'):
    p=c.beginPath();p.moveTo(*points[0])
    for q in points[1:]:p.lineTo(*q)
    p.close();c.setFillColor(HexColor(fill));c.setStrokeColor(HexColor(stroke));c.drawPath(p,fill=1,stroke=1)


def notes(c,items,x,y,step=22,size=11):
    for i,t in enumerate(items):text(c,x,y-step*i,t,size)


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
        ('02','壳体','1','Q235B','Ø160×200，t5；内径150.00～150.02','HJ-001'),
        ('03','一体反锥芯/柱/法兰','1','45钢调质','半角10°；Ø60颈；无过盈拼接；Ra≤0.2','HJ-004/005/012'),
        ('04','六指胀套','1','17-4PH H900','缩态Ø39.94；机械最大Ø40.04；弹颈t0.80/L30','HJ-006/009'),
        ('05','上承力筒及止挡头','1','按HJ-F-01','Ø70/Ø24×244.6；止挡头Ø100×20','HJ-012'),
        ('06','门架横板/立柱','1/4','45钢结构件','板460×460×100；4柱Ø80；柱位置(±180,±180)','HJ-012'),
        ('07','机械上止挡','2','按HJ-F-01','26×30×20；独立径退20；接触宽≥7','HJ-012'),
        ('08','基座连接螺钉','12','ISO4762-8.8','M36×200；PCD360；预紧90±9kN；啮合≥55','HJ-F-01'),
        ('09','独立A基准托环','1','45钢','OD180/ID150.20±0.04×20；六个正向承托槽','HJ-013'),
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
    notes(c,['A：壳体下端实际安装面；B：壳体内壁双轴向带的独立拟合轴线，按A法向定向。孔轴自身为被测对象。',
             '工装锥芯轴线相对A/B转移、轴线与定心各2μm径向；A托环等高/热差按HJ-F-01，不以胀套作B基准。',
             '锥芯与胀套为配锥研合；增量柔度≤0.05μm/kN为装机资格目标。M36预紧以张力/伸长核验，不能只靠扭矩。',
             '水/气路及密封槽按实物测径配作；上圈径向压缩0.415～0.425，最小壁厚/盲孔封底按HJ-C-02验收。',
             '采购焊材按实际药皮/裸棒分类及批次证书；主体/工装不得以未注±0.10替代微米级定位与密封配合。'],48,181,step=21,size=11)
    c.save();return file


def main():
    OUT.mkdir(parents=True,exist_ok=True);register_project_fonts(ROOT)
    paths=[section(),ut(),bom()]
    for p in paths:
        with fitz.open(p) as f:f[0].get_pixmap(dpi=120).save(p.with_suffix('.png'))
    manifest=ROOT/'cad/generated/engineering-drawings/drawing-manifest.json'
    data=json.loads(manifest.read_text(encoding='utf8'))
    existing=[r for r in data.get('external_pdf_sheets',[]) if r['number'] not in [19,20,21]]
    for number,p,title in zip([19,20,21],paths,['真实公差与法向修整截面','异种接头专用UT可达与覆盖','关键零件明细与制造配合']):
        existing.append(dict(number=number,pdf=p.relative_to(ROOT).as_posix(),title=f'HJ-{number:03d} {title}'))
    data['external_pdf_sheets']=existing
    manifest.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps([str(p) for p in paths],ensure_ascii=False))


if __name__=='__main__':main()
