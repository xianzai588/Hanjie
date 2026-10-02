"""Composition accounting with a traceable Schaeffler diagram, without extrapolation.
Original diagram: KOBELCO Specific 4th edition, p.3-7 Fig.2.3.
No Ms extrapolation, invented horizontal phase lines or graphite subtraction.
"""
import json,csv,sys
from pathlib import Path
import numpy as np
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent/'results';FIG=ROOT/'docs/report/figures'
COMPOSITIONS={
 'Q235B':dict(C=.17,Si=.22,Mn=.5,Cr=.05,Ni=.05,Mo=.01,Nb=0),
 'QT450-10':dict(C=3.65,Si=2.60,Mn=.30,Cr=.05,Ni=.05,Mo=0,Nb=0),
 'NiFe-55':dict(C=.01,Si=.13,Mn=.70,Cr=0,Ni=55,Mo=0,Nb=0),
 'Ni99':dict(C=.02,Si=.1,Mn=.1,Cr=0,Ni=99,Mo=0,Nb=0)}
def equivalents(c):return c['Cr']+c['Mo']+1.5*c['Si']+.5*c['Nb'],c['Ni']+30*c['C']+.5*c['Mn']
def mix(d,r,filler='NiFe-55'):
 return {k:(1-d)*COMPOSITIONS[filler][k]+d*r*COMPOSITIONS['QT450-10'][k]+d*(1-r)*COMPOSITIONS['Q235B'][k] for k in COMPOSITIONS[filler]}
def build():
 rows=[]
 for r in (.3,.4):
  for d in (.1,.15,.2,.25,.3,.4,.5):
   c=mix(d,r);ce,ne=equivalents(c)
   rows.append(dict(dilution=d,cast_iron_share=r,composition_wt_pct=c,cr_eq=ce,ni_eq=ne,within_schaeffler_plot=0<=ce<=40 and 0<=ne<=30,
       constitution='图外；Ni-Fe体系文献支持奥氏体主枝晶，同时单独控制碳化物/HAZ'))
 base=[dict(material=k,composition_wt_pct=v,cr_eq=equivalents(v)[0],ni_eq=equivalents(v)[1],
   source='供方典型成分' if k=='NiFe-55' else '工程成分假设，按来料化学分析替换；牌号不等于固定化学成分') for k,v in COMPOSITIONS.items()]
 return dict(version='SCHAEFFLER-R3',formula=dict(cr_eq='Cr+Mo+1.5Si+0.5Nb',ni_eq='Ni+30C+0.5Mn'),
  original_diagram=dict(url='https://www.kobelco-welding.jp/images/education-center/pdf/Specific_4Ed.pdf',page='3-7',figure='2.3',plot_extent=[0,40,0,30],
   tracing_accuracy_equivalent_units=.4,role='读图重绘，非热力学数据库；不对图外点分类'),
  base_metals=base,dilution_sweep=dict(design_rows=rows[:7],conservative_rows=rows[7:]),
  metallurgy_reference=dict(doi='10.1007/s11661-024-07399-4',scope='EN-GJS-500-14 / GMAW-MCAW；机理参考，非本件合格评定',
   conclusion='NiFe与纯Ni均有奥氏体主枝晶；NiFe枝晶间可析出渗碳体，纯Ni促进石墨，HAZ仍可出现马氏体'),
  design_decision='QT侧预制Ni99隔离层，接头主体NiFe55；保证最终焊接不穿透隔离层，镍层制作在精加工孔之前完成；宏观金相确认剩余层厚≥0.8 mm')
def plot(r):
 plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False})
 fig,(ax,z)=plt.subplots(1,2,figsize=(12,5.6),gridspec_kw={'width_ratios':[1.2,1]},layout='constrained')
 # Traced oblique boundaries from the actual published figure, within its original domain.
 for pts in ([(0,25.3),(26,4.3)],[(0,19.6),(20.5,3.1)],[(7.8,0),(34.5,30)],[(12,0),(40,9)],[(0,7),(2.8,0)]):
  xx,yy=zip(*pts);ax.plot(xx,yy,color='#475569',lw=1.2)
 for end,label in (((37,30),'5%'),((40,28.3),'10%'),((40,23),'20%'),((40,19.6),'40%'),((40,15.1),'80%')):
  # Ferrite lines start on the A/M boundary; digitized, labelled as diagram readouts.
  slope=(end[1])/(end[0]-8);xx=(25.3+8*slope)/(.81+slope);yy=25.3-.81*xx
  ax.plot([xx,end[0]],[yy,end[1]],color='#94a3b8',lw=.75)
 ax.text(8,24,'A',fontsize=12);ax.text(5,15,'A+M',fontsize=11);ax.text(5,8,'M',fontsize=11)
 ax.text(22,11,'A+F',fontsize=11);ax.text(19,5.5,'A+M+F',fontsize=9);ax.text(31,3,'F',fontsize=12)
 ax.text(12,2.1,'M+F',fontsize=9)
 ax.set(xlim=(0,40),ylim=(0,30),xlabel='Cr_eq',ylabel='Ni_eq',title='Schaeffler原图域及分区（读图重绘）')
 q=r['base_metals'][0];ax.scatter(q['cr_eq'],q['ni_eq'],s=35,color='#2563eb');ax.annotate('Q235B成分点\n不判母材供货组织',(q['cr_eq'],q['ni_eq']),xytext=(3,3),fontsize=8)
 for j,(tag,rows) in enumerate(r['dilution_sweep'].items()):
  z.plot([a['cr_eq'] for a in rows],[a['ni_eq'] for a in rows],'-o',label=f'铸铁熔入占比 {rows[0]["cast_iron_share"]:.0%}')
 for a in r['base_metals']:
  z.scatter(a['cr_eq'],a['ni_eq'],marker='*',s=70);z.annotate(f'{a["material"]} ({a["cr_eq"]:.2f},{a["ni_eq"]:.2f})',(a['cr_eq'],a['ni_eq']),xytext=(4,2),textcoords='offset points',fontsize=7)
 z.axhline(30,color='#94a3b8',ls='--');z.text(.1,31,'原图Ni_eq上限30；上方点不作相区外推',fontsize=8)
 z.set(xlim=(0,5),ylim=(0,122),xlabel='Cr_eq',ylabel='Ni_eq',title='真实成分当量及稀释轨迹（含图外点）');z.legend(fontsize=8)
 for a in (ax,z):a.grid(alpha=.2)
 fig.savefig(FIG/'schaeffler-map.png',dpi=220);fig.savefig(OUT/'schaeffler-map.svg');plt.close(fig)
 temps=np.array([20,100,150,200,500]);delta=temps-20
 fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
 axes[0].bar(temps.astype(str),.684571872*.460*delta,color='#0284c7');axes[0].set(ylabel='座体蓄热 kJ',xlabel='均匀温度 ℃',title='热容量核算')
 axes[1].bar(temps.astype(str),74.98*1.05e-5*delta,color='#059669');axes[1].set(ylabel='自由半径增量 mm',xlabel='均匀温度 ℃',title='自由热胀（不等于孔轴偏移或残余量）')
 fig.savefig(FIG/'cold-weld-regime.png',dpi=220);fig.savefig(OUT/'cold-weld-regime.svg');plt.close(fig)
def main():
 OUT.mkdir(exist_ok=True);FIG.mkdir(exist_ok=True,parents=True);r=build()
 (OUT/'schaeffler-mapping.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
 with (OUT/'schaeffler-mapping.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['cast_iron_share','dilution','Ni_wt_pct','C_wt_pct','Cr_eq','Ni_eq','within_original_domain'])
  for rows in r['dilution_sweep'].values():
   for a in rows:w.writerow([a['cast_iron_share'],a['dilution'],a['composition_wt_pct']['Ni'],a['composition_wt_pct']['C'],a['cr_eq'],a['ni_eq'],a['within_schaeffler_plot']])
 plot(r);print('真实相图与14例成分核算已生成，无自设相界与Ms外推')
if __name__=='__main__':main()
