"""Figures of the actual load, heat and cycle calculations."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
D=json.loads((Path(__file__).parent/'results/engineering-checks-r3.json').read_text(encoding='utf8'))
OUT=ROOT/'docs/report/figures'
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False})
fig,axes=plt.subplots(1,3,figsize=(12,4),layout='constrained')
rows=D['layout_checks'];labels=[r['layout'].replace('-FAIR_B','') for r in rows]
for ax,key,title,ylabel in zip(axes,['static_equivalent_MPa','heat_kJ','arc_s'],['同一设计静载荷','两道累计净热','两道弧燃'],['等效应力 MPa','kJ','s']):
 values=[r[key] for r in rows];ax.bar(labels,values,color=['#94a3b8','#0284c7','#059669'])
 ax.set(title=title,ylabel=ylabel)
 for i,v in enumerate(values):ax.text(i,v,f'{v:.2f}',ha='center',va='bottom',fontsize=9)
fig.savefig(OUT/'layout-engineering-comparison.png',dpi=220);plt.close(fig)
fig,ax=plt.subplots(figsize=(7,4),layout='constrained')
scales=np.linspace(.7,1.5,161)
for row in rows:ax.plot(scales,row['miner_damage']*scales**3,label=row['layout'].replace('-FAIR_B',''))
ax.axhline(1,color='#dc2626',ls='--',label='设计曲线累计损伤1')
ax.axvline(1,color='#94a3b8',ls=':');ax.set(xlabel='相同比例载荷倍率',ylabel='Miner计算损伤',title='假定同谱、同资格目标曲线下的敏感性')
ax.legend();ax.grid(alpha=.2);fig.savefig(OUT/'fatigue-load-sensitivity.png',dpi=220);plt.close(fig)
print('已生成三布局热量/承载/弧燃对比和假定载荷敏感性图')
