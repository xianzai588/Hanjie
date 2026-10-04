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
for row in rows:ax.plot(scales,row['required_reference_range_MPa_at_2e6']*scales,label=row['layout'].replace('-FAIR_B',''))
ax.axhline(30,color='#dc2626',ls='--',label='拟定资格目标30 MPa')
ax.axvline(1,color='#94a3b8',ls=':');ax.set(xlabel='相同比例载荷倍率',ylabel='所需参考应力范围 MPa（200万次，m=3）',title='假定同谱下的疲劳资格需求')
ax.legend();ax.grid(alpha=.2);fig.savefig(OUT/'fatigue-load-sensitivity.png',dpi=220);plt.close(fig)
print('已生成三布局热量/承载/弧燃对比和假定载荷敏感性图')
