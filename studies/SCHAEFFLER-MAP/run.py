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
MATERIALS=yaml.safe_load((ROOT/'project/materials.yaml').read_text(encoding='utf8'))['materials']
COMPOSITIONS={name:{key:float(MATERIALS[material]['composition_nominal_wt_pct'].get(key,0))
 for key in ('C','Si','Mn','Cr','Ni','Mo','Nb')}
 for name,material in (('Q235B','q235b'),('QT450-10','qt450_10'),('NiFe-55','ernife_ci'))}
COMPOSITIONS['Ni99']=dict(C=.01,Si=.05,Mn=.17,Cr=0,Ni=99.62,Mo=0,Nb=0)
def blend(components):
 return {k:sum(weight*composition[k] for weight,composition in components) for k in COMPOSITIONS['Ni99']}
def transition_cases():
 """Track carbon inherited from QT into both butter layers and the final pool."""
 rows=[]
 for d1 in (.1,.2,.3):
  for d2 in (.1,.15,.2):
   first=blend([(1-d1,COMPOSITIONS['Ni99']),(d1,COMPOSITIONS['QT450-10'])])
   second=blend([(1-d2,COMPOSITIONS['Ni99']),(d2,first)])
   for dnickel,dsteel in ((.1,.05),(.15,.1),(.2,.1)):
    final=blend([(1-dnickel-dsteel,COMPOSITIONS['NiFe-55']),(dnickel,second),(dsteel,COMPOSITIONS['Q235B'])])
    rows.append(dict(first_QT_dilution=d1,second_first_layer_remelt=d2,final_Ni_layer_dilution=dnickel,final_steel_dilution=dsteel,
     first_composition_wt_pct=first,second_composition_wt_pct=second,final_composition_wt_pct=final,
     final_cr_eq=equivalents(final)[0],final_ni_eq=equivalents(final)[1],
     meets_selected_dilution_envelope=d1<=.2 and d2<=.15 and dnickel<=.2 and dsteel<=.1))
 return rows
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
   source='供方典型成分，按批次证书复核' if k in ('NiFe-55','Ni99') else '工程成分假设，按来料化学分析替换；牌号不等于固定化学成分') for k,v in COMPOSITIONS.items()]
 return dict(version='SCHAEFFLER-R4',formula=dict(cr_eq='Cr+Mo+1.5Si+0.5Nb',ni_eq='Ni+30C+0.5Mn'),
  original_diagram=dict(url='https://www.kobelco-welding.jp/images/education-center/pdf/Specific_4Ed.pdf',page='3-7',figure='2.3',plot_extent=[0,40,0,30],
   tracing_accuracy_equivalent_units=.4,role='读图重绘，非热力学数据库；不对图外点分类'),
  base_metals=base,dilution_sweep=dict(design_rows=rows[:7],conservative_rows=rows[7:]),
  transition_layer_sweep=transition_cases(),
  Ni99_source=dict(url='https://www.weldwire.net/wp-content/uploads/2013/08/ERNi-CI.pdf',product='WWNA99 / ERNi-CI',basis='typical deposited chemistry, not a batch certificate',processes=['GTAW','GMAW']),
  metallurgy_reference=dict(doi='10.1007/s11661-024-07399-4',scope='EN-GJS-500-14 / GMAW-MCAW；机理参考，非本件合格评定',
   conclusion='NiFe与纯Ni均有奥氏体主枝晶；NiFe枝晶间可析出渗碳体，纯Ni促进石墨，HAZ仍可出现马氏体'),
  design_decision='QT侧两层Ni99过渡层，QT稀释≤20%、第二层重熔首层≤15%；加工后第二层≥0.5 mm，最终熔深≤0.4 mm只重熔第二层；最终Ni层稀释≤20%、钢侧≤10%；厚度与稀释独立控制，总残层≥0.8 mm；首次QT/Ni99界面的PMZ与HAZ仍按冷焊裂纹控制程序管理')
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
 valid=[a for a in r['transition_layer_sweep'] if a['meets_selected_dilution_envelope']]
 z.scatter([a['final_cr_eq'] for a in valid],[a['final_ni_eq'] for a in valid],s=18,color='#059669',label='两层Ni99后最终熔池（设计窗口）')
 for a in r['base_metals']:
  z.scatter(a['cr_eq'],a['ni_eq'],marker='*',s=70);z.annotate(f'{a["material"]} ({a["cr_eq"]:.2f},{a["ni_eq"]:.2f})',(a['cr_eq'],a['ni_eq']),xytext=(4,2),textcoords='offset points',fontsize=7)
 z.axhline(30,color='#94a3b8',ls='--');z.text(.1,31,'原图Ni_eq上限30；上方点不作相区外推',fontsize=8)
 z.set(xlim=(0,5),ylim=(0,122),xlabel='Cr_eq',ylabel='Ni_eq',title='真实成分当量及稀释轨迹（含图外点）');z.legend(fontsize=8)
 for a in (ax,z):a.grid(alpha=.2)
 fig.savefig(FIG/'schaeffler-map.png',dpi=220);fig.savefig(OUT/'schaeffler-map.svg');plt.close(fig)
 temps=np.array([20,100,150,200,500]);delta=temps-20
 fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
 spec=yaml.safe_load((ROOT/'project/competition-design.yaml').read_text(encoding='utf8'))
 manifest=json.loads((ROOT/spec['geometry_manifest']).read_text(encoding='utf8'))
 mass=manifest['geometry']['calculated_mass_kg']
 tab=yaml.safe_load((ROOT/'project/materials.yaml').read_text(encoding='utf8'))['materials']['qt450_10']['temperature_dependent']
 knots=np.array(tab['temperatures_c']);values=np.array(tab['specific_heat_j_kgk'])
 heat=[]
 for top in temps:
  grid=np.unique(np.r_[20,knots[(knots>20)&(knots<top)],top])
  heat.append(mass*np.trapezoid(np.interp(grid,knots,values),grid)/1000)
 axes[0].bar(temps.astype(str),heat,color='#0284c7');axes[0].set(ylabel='座体蓄热 kJ',xlabel='均匀温度 ℃',title='15 mm实际座体：温变比热积分')
 axes[1].bar(temps.astype(str),74.98*1.05e-5*delta,color='#059669');axes[1].set(ylabel='自由半径增量 mm',xlabel='均匀温度 ℃',title='自由热胀（不等于孔轴偏移或残余量）')
 fig.savefig(FIG/'cold-weld-regime.png',dpi=220);fig.savefig(OUT/'cold-weld-regime.svg');plt.close(fig)
def main():
 OUT.mkdir(exist_ok=True);FIG.mkdir(exist_ok=True,parents=True);r=build()
 (OUT/'schaeffler-mapping.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
 with (OUT/'schaeffler-mapping.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['cast_iron_share','dilution','Ni_wt_pct','C_wt_pct','Cr_eq','Ni_eq','within_original_domain'])
  for rows in r['dilution_sweep'].values():
   for a in rows:w.writerow([a['cast_iron_share'],a['dilution'],a['composition_wt_pct']['Ni'],a['composition_wt_pct']['C'],a['cr_eq'],a['ni_eq'],a['within_schaeffler_plot']])
 plot(r);print('原图域、14组直接稀释对照及27组两层过渡配混已生成')
if __name__=='__main__':main()
