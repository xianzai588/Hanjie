"""Rebuild the R2 ring-specific UT method sheet and report section figure.

Outputs are candidate geometry, not measured UT coverage or qualification.
Dependencies: scipy, Inkscape, Poppler, and the repository Noto Sans SC font.
"""
from pathlib import Path
import math,os,subprocess,tempfile
from xml.sax.saxutils import escape
from scipy.optimize import brentq
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/report/figures/publication';OUT.mkdir(parents=True,exist_ok=True)
p=['<svg xmlns="http://www.w3.org/2000/svg" width="420mm" height="297mm" viewBox="0 0 1400 990">','<defs><marker id="ar" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto-start-reverse"><path d="M0 0 L7 3.5 L0 7 Z" fill="#315D83"/></marker><pattern id="blind" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="9" height="9" fill="#B35648" fill-opacity="0.10"/><line x1="0" y1="0" x2="0" y2="9" stroke="#B35648" stroke-width="2" stroke-opacity="0.55"/></pattern></defs>','<rect width="1400" height="990" fill="white"/><g font-family="Noto Sans SC,sans-serif" fill="#27384A" stroke-linejoin="round">']
def line(x1,y1,x2,y2,color='#27384A',width=1.4,dash=None):p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
def text(x,y,t,size=16,color='#27384A',anchor='start'):p.append(f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{escape(str(t))}</text>')
def rect(x,y,w,h,fill='none',color='#27384A'):p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{color}" stroke-width="1.2"/>')
def poly(pts,fill,color='#27384A'):p.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in pts)+f'" fill="{fill}" stroke="{color}" stroke-width="1.2"/>')
def circle(x,y,r,color='#27384A',fill='none',width=1.4):p.append(f'<circle cx="{x}" cy="{y}" r="{r}" stroke="{color}" fill="{fill}" stroke-width="{width}"/>')
def arrow(x1,y1,x2,y2,color='#315D83',dash=None):p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2.3" marker-end="url(#ar)"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
rect(30,30,1340,930);text(60,77,'HJ-Q-S01 方法示意 | 圆环UT探入、声路与未确认区',28);text(60,112,'SUBMISSION-RING-20261008-R2 | 几何与材料输入用于方法设计；目标反射体资格矩阵另行记录',16)
line(30,140,1370,140);line(30,927,1370,927);text(60,953,'图中射线为候选主声路；薄层、曲面折射、双晶接收交叠和几何回波由同工艺对比块确认',14)
text(60,172,'A  局部径向剖面与候选纵波声路',20)
text(60,199,'图示局部R61～80 / z110～125；完整QT座体R20～74.98、z100～115',14)
X=lambda r:90+(r-61)*30;Y=lambda z:210+(125-z)*30
# Full seat clipped at z110, with true R1.5 local pocket removed.
poly([(X(61),Y(110)),(X(74.98),Y(110)),(X(74.98),Y(115)),(X(61),Y(115))],'#EADAC2')
rect(X(75),Y(125),150,450,'#CBD5DF')
def pocket(inner,bottom,radius,fill):
 d=f'M {X(inner)},{Y(115)} L {X(74.98)},{Y(115)} L {X(74.98)},{Y(bottom)} L {X(70.48)},{Y(bottom)} A {radius*30},{radius*30} 0 0 1 {X(inner)},{Y(115)} Z'
 p.append(f'<path d="{d}" fill="{fill}" stroke="#315D83" stroke-width="1.8"/>')
pocket(68.98,113.5,1.5,'#8FB4B3');pocket(69.68,114.2,.8,'#E8C46B')
poly([(X(71.5),Y(115)),(X(75),Y(115)),(X(75),Y(118.5))],'#D89768')
# Explicit qualification gap overlay, not a measured blind-zone result.
rect(X(68.98),Y(115),6*30,1.5*30,'url(#blind)',color='#B35648')
text(X(62),Y(112),'QT450-10',17);text(X(77.5),Y(113),'Q235B',17,anchor='middle')
text(X(77.5),Y(111.8),'t5 / h200',13,anchor='middle')
# Top slender-footprint design envelope (2D radial projection).
rect(X(64.5),Y(115)-21,4*30,21,'#E9EDF0');text(X(66.5),Y(115)-31,'T：R66.5 / 足迹4×6',14,anchor='middle')
# 60-degree pure-QT extrapolation to flat-depth level does not certify the window.
ar=math.radians(60);r60=66.5+1.5*math.tan(ar)
arrow(X(66.5),Y(115),X(r60),Y(113.5),'#315D83','6 4');text(X(64.3),Y(113.4),'60°延伸',13)
# 75-degree ray terminates on the actual curved first interface.
a=math.radians(75);f=lambda r:math.sqrt(1.5**2-(r-70.48)**2)-(r-66.5)/math.tan(a)
rhit=brentq(f,68.98001,70.4799);zhit=115-(rhit-66.5)/math.tan(a)
arrow(X(66.5),Y(115),X(rhit),Y(zhit));circle(X(rhit),Y(zhit),3,'#315D83','#315D83');text(X(69.3),Y(111.7),'75°先遇R1.5圆角',13,color='#315D83')
# Two exterior candidates: solid only while traversing reference steel.
rect(X(80)+4,Y(120.75)-20,32,40,'#E9EDF0');text(X(80)+22,Y(123.2),'S45',15,anchor='middle')
arrow(X(80),Y(120.75),X(75),Y(115.75));text(X(77.8),Y(120.6),'钢中L45°',14,anchor='middle')
ends=[]
for c in (5000,6200):
 b=math.asin(c/5890*math.sin(math.pi/4));rr=75-.75/math.tan(b);ends.append(rr)
 arrow(X(75),Y(115.75),X(rr),Y(115),'#BB8038','5 4')
text(X(71.8),Y(120.1),'NiFe55后段',13,color='#996B30');text(X(71.8),Y(119.3),'声速待校准',13,color='#996B30')
arrow(X(80),Y(116.75),X(75),Y(116.75));text(X(80)+12,Y(116.75)-10,'S0',14)
text(X(76),Y(118.3),'T4',15,color='#315D83');line(X(74.15),Y(115),X(75.7),Y(114.0),'#315D83');text(X(75.8),Y(113.7),'T3',15,color='#315D83')
# Target and layer leaders.
line(X(70.7),Y(113.5),X(70.7)-16,672,'#B35648');text(70,678,'T1平底/圆角/端壁；T2薄层交叠及近表面：分辨与传播未确认',14,color='#994D43')
text(X(76),Y(110.4),'0.02气隙非声路',12,color='#994D43')
# Right design inputs and qualification map.
x=825;text(x,172,'B  输入、目标与方法资格',20)
rows=[('参考钢L / S','5890 / 3240 m/s（1020钢代理）'),('PMMA纵波','2730 m/s'),('QT纵波参考','5600 m/s（本批需校准）'),('Ni焊态传播','CI-A1 / Ni99 / NiFe55逐层校准'),('频率候选','2 / 5 MHz，按同块SNR和分辨筛选'),('钢中L45 / L60','楔入射19.132° / 23.666°')]
for i,(a,b) in enumerate(rows):
 yy=211+i*30;text(x,yy,a,14);text(x+163,yy,b,14)
line(x,391,1325,391);text(x,423,'薄层与曲率筛查',18)
for i,t in enumerate(['两周期/正常入射假设：2 / 5 MHz → 2.80 / 1.12 mm','斜入射按局部法向投影；实际脉宽/死区要测','壳外R80，周向6 mm弦弓高0.0563 mm','局部法向周向变化±2.149°，曲面楔按实测研配']):text(x,458+i*29,t,14)
line(x,556,1325,556);text(x,589,'专用对比块人工反射体',18)
for i,t in enumerate(['相同QT/CI-A1/Ni99/NiFe55/Q235B全过程','完整环优先；≥60°环段需排除截断边界影响','T1平底/圆角/两端、T2层间、T3根部/弧坑','T4钢侧近根/近趾；按三种面法向分别设置','槽深0.5×长3、宽≤0.2：项目资格目标','逐姿态记录SNR≥12 dB、重复幅度差≤2 dB','宏观/金相证实首次熔合、层厚及重熔','PT补表面开口裂纹；内部未确认区另发展方法']):text(x,625+i*28,t,14)
# Full ring top plan, actual eight windows and effective segment angles.
text(60,720,'C  周向逐段扫描与端部登记',20)
cx,cy,sc=225,820,.85
circle(cx,cy,74.98*sc);circle(cx,cy,20*sc);circle(cx,cy,80*sc,'#8799AA')
def arc(radius,angle0,angle1,color,width):
 a,b=math.radians(angle0),math.radians(angle1)
 p.append(f'<path d="M {cx+radius*sc*math.cos(a)},{cy-radius*sc*math.sin(a)} A {radius*sc},{radius*sc} 0 0 0 {cx+radius*sc*math.cos(b)},{cy-radius*sc*math.sin(b)}" fill="none" stroke="{color}" stroke-width="{width}"/>')
for i in range(8):
 center=i*45;arc(71.98,center-9.55195,center+9.55195,'#D9B365',6)
 arc(74.98,center-6.87733,center+6.87733,'#D89768',3)
 arc(85,center-10,center+10,'#315D83',2)
 a=math.radians(center);text(cx+85*math.cos(a),cy-85*math.sin(a)+5,str(i+1),13,anchor='middle')
for i,t in enumerate(['金色：24 mm预制窗 / 19.1039°','橙色：18 mm有效连接 / 13.7547°','蓝色：各段中心±10°候选扫查','步距≤1 mm，按实际入射面弧长登记','T1两端壁与弧坑逐项记录，不靠段中替代']):text(375,755+i*29,t,14)
text(825,892,'来源：Evident技术说明/材料表；ISO 22825:2017',13)
text(375,908,'材料典型值、候选射线和资格目标为不同证据；完整依据及计算见 ring-ut-coverage-design.md',13)
p.append('</g></svg>');svg=OUT/'ring-ut-coverage.svg';svg.write_text('\n'.join(p),encoding='utf8')
with tempfile.TemporaryDirectory(prefix='ring-ut-fonts-') as d:
 conf=Path(d)/'fonts.conf';conf.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'+f'<dir>{escape(str(ROOT/"assets/fonts"))}</dir><cachedir>{escape(d)}</cachedir></fontconfig>')
 env={**os.environ,'FONTCONFIG_FILE':str(conf)}
 subprocess.run(['inkscape',str(svg),'--export-type=pdf',f'--export-filename={svg.with_suffix(".pdf")}'],env=env,check=True,stdout=subprocess.DEVNULL)
 subprocess.run(['pdftoppm','-singlefile','-scale-to','2100','-png',str(svg.with_suffix('.pdf')),str(svg.with_suffix(''))],check=True,stdout=subprocess.DEVNULL)
print(svg)

# Compact report figure: the radial section uses larger type instead of
# shrinking the complete A3 sheet into the report's single text column.
p=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="950" viewBox="0 0 1200 950">',
   '<defs><marker id="ar" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto-start-reverse"><path d="M0 0 L7 3.5 L0 7 Z" fill="#315D83"/></marker><pattern id="blind" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="12" height="12" fill="#B35648" fill-opacity="0.10"/><line x1="0" y1="0" x2="0" y2="12" stroke="#B35648" stroke-width="2" stroke-opacity="0.55"/></pattern></defs>',
   '<rect width="1200" height="950" fill="white"/><g font-family="Noto Sans SC,sans-serif" fill="#27384A" stroke-linejoin="round">']
rect(25,20,1150,910)
text(55,68,'HJ-Q-S01 圆环局部径向断面：候选声路与未确认区',30)
text(55,112,'完整QT座体R20～74.98、z100～115；钢壳R75～80、高200',24)
X=lambda r:100+(r-61)*38
Y=lambda z:145+(125-z)*38
poly([(X(61),Y(110)),(X(74.98),Y(110)),(X(74.98),Y(115)),(X(61),Y(115))],'#EADAC2')
rect(X(75),Y(125),5*38,15*38,'#CBD5DF')
def compact_pocket(inner,bottom,radius,fill):
    d=f'M {X(inner)},{Y(115)} L {X(74.98)},{Y(115)} L {X(74.98)},{Y(bottom)} L {X(70.48)},{Y(bottom)} A {radius*38},{radius*38} 0 0 1 {X(inner)},{Y(115)} Z'
    p.append(f'<path d="{d}" fill="{fill}" stroke="#315D83" stroke-width="2"/>')
compact_pocket(68.98,113.5,1.5,'#8FB4B3')
compact_pocket(69.68,114.2,.8,'#E8C46B')
poly([(X(71.5),Y(115)),(X(75),Y(115)),(X(75),Y(118.5))],'#D89768')
rect(X(68.98),Y(115),6*38,1.5*38,'url(#blind)',color='#B35648')
text(X(62),Y(110.45),'QT450-10',26)
text(X(77.5),Y(112.3),'Q235B',26,anchor='middle')
text(X(77.5),Y(111.2),'t5 mm',24,anchor='middle')
rect(X(64.5),Y(115)-31,4*38,31,'#E9EDF0')
text(X(66.5),Y(115)-65,'T：R66.5 / 总足迹4×6',24,anchor='middle')
arrow(X(66.5),Y(115),X(r60),Y(113.5),'#315D83','8 5')
arrow(X(66.5),Y(115),X(rhit),Y(zhit))
circle(X(rhit),Y(zhit),4,'#315D83','#315D83')
text(110,624,'60°虚线：纯QT延伸',24,color='#315D83')
text(110,665,'75°实线：先遇R1.5界面',24,color='#315D83')
rect(X(80)+4,Y(120.75)-27,44,54,'#E9EDF0')
arrow(X(80),Y(120.75),X(75),Y(115.75))
text(X(77.3),Y(121.7),'钢中L45°',24,anchor='middle')
text(X(80)+58,Y(120.75)+9,'S45',24)
for rr in ends:
    arrow(X(75),Y(115.75),X(rr),Y(115),'#BB8038','6 5')
text(480,246,'NiFe55后段声速待校准',24,color='#996B30')
line(657,266,X(74.3),Y(115.15),'#996B30')
arrow(X(80),Y(116.75),X(75),Y(116.75))
text(X(80)+19,Y(116.75)-13,'S0',24)
line(X(75),Y(117.7),X(75)+24,Y(119.35),'#315D83')
text(X(75)+25,Y(119.8),'T4 钢侧',24,color='#315D83')
line(X(74.2),Y(115),X(75)+22,Y(113.6),'#315D83')
text(X(75)+25,Y(113.4),'T3 最终镍侧',24,color='#315D83')
line(X(70.8),Y(113.5),500,741,'#B35648')
text(60,772,'T1：QT/CI-A1首次界面平底、R1.5圆角和两端壁',24,color='#994D43')
line(X(73.3),Y(114.2),645,781,'#B35648')
text(60,813,'T2：CI-A1/Ni99层间；0.70 / 0.80 mm薄层分辨未确认',24,color='#994D43')
text(60,856,'z115以下0.02 mm装配气隙不计传声；最小最终等脚3.50 mm',24)
text(60,899,'2 / 5 MHz候选；材料声速、脉宽、曲面折射与接收声路由对比块确认',24)
p.append('</g></svg>')
compact=OUT/'ring-ut-section.svg'
compact.write_text('\n'.join(p),encoding='utf8')
with tempfile.TemporaryDirectory(prefix='ring-ut-section-fonts-') as d:
    conf=Path(d)/'fonts.conf'
    conf.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'+f'<dir>{escape(str(ROOT/"assets/fonts"))}</dir><cachedir>{escape(d)}</cachedir></fontconfig>')
    env={**os.environ,'FONTCONFIG_FILE':str(conf)}
    subprocess.run(['inkscape',str(compact),'--export-type=png','--export-width=2000',f'--export-filename={compact.with_suffix(".png")}'],env=env,check=True,stdout=subprocess.DEVNULL)
print(compact)
