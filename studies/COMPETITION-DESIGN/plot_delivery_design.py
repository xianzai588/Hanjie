"""Plots from the current arc integrals and the frozen bore-axis budget."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/report/figures/delivery'
OUT.mkdir(parents=True,exist_ok=True)
font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':font.get_name(),'axes.unicode_minus':False,'font.size':10,
                    'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':220})
data=json.loads((ROOT/'studies/COMPETITION-DESIGN/results/delivery-joint-capacity-20261008.json').read_text(encoding='utf-8'))
def save(fig,name):
    fig.savefig(OUT/f'{name}.png',bbox_inches='tight',facecolor='white')
    fig.savefig(OUT/f'{name}.pdf',bbox_inches='tight',metadata={'Author':''})
    plt.close(fig)

fig,ax=plt.subplots(1,2,figsize=(10.0,3.5),layout='constrained')
keys=['6P_16mm_leg_3.8','8P_leg_3.8','Continuous_leg_3.8']
labels=['6段×16 mm','8段×16 mm\n主设计','全周连续']
colors=['#9cabb6','#177c87','#9cabb6']
for a,key,title,unit in [(ax[0],'required_nominal_static_capacity_MPa','静承载资格需求','名义等效应力 / MPa'),
                         (ax[1],'required_reference_range_MPa_at_2e6','疲劳资格需求','2×10^6 次参考应力范围 / MPa')]:
    vals=[data['rows'][k][key] for k in keys]
    a.bar(labels,vals,color=colors,width=.6)
    for i,v in enumerate(vals):a.text(i,v+.7,f'{v:.2f}',ha='center',fontsize=10)
    a.set_title(title,fontweight='bold',loc='left');a.set_ylabel(unit)
    a.set_ylim(0,max(vals)*1.24);a.grid(axis='y',alpha=.18);a.set_axisbelow(True)
ax[1].axhline(30,color='#bd7046',ls='--',lw=1.2)
ax[1].text(2.35,30.6,'30 MPa资格目标',ha='right',color='#995d3c',fontsize=9)
fig.suptitle('相同设计载荷、稳定焊脚3.80 mm；有效喉部及材料资格分别验证',fontsize=11)
save(fig,'joint-capacity')

fig,ax=plt.subplots(figsize=(9.5,3.2),layout='constrained')
labels=['内部设计目标','完整允许分配','历史组焊算例']
values=[(28,2,6.5,12),(28,2,6.5,13.5),(28,2,6.5,15.583947)]
names=['制造/装配/定心','测量U','有限微珩轴线变化','焊接热残余']
colors=['#7f98aa','#b8ccd5','#ccd2b1','#21828b']
left=[0.,0.,0.]
for j,(name,color) in enumerate(zip(names,colors)):
    vals=[v[j] for v in values]
    ax.barh(labels,vals,left=left,color=color,label=name,height=.54)
    for i,v in enumerate(vals):
        if v>4:ax.text(left[i]+v/2,i,f'{v:g}',ha='center',va='center',fontsize=9,color='white' if j in (0,3) else '#243948')
    left=[x+y for x,y in zip(left,vals)]
for i,v in enumerate(left):ax.text(v+.5,i,f'{v:.3f}',va='center',color='#a45134' if i==2 else '#243948')
ax.axvline(50,color='#ac5e3e',ls='--',lw=1.3)
ax.set_xlim(0,58);ax.set_xlabel('孔轴位置度预算（直径） / μm')
ax.set_title('保持Ø50 μm上限；历史结果超差2.084 μm，当前新制造链仍需收敛验证',loc='left',fontsize=11)
ax.invert_yaxis();ax.legend(loc='lower left',bbox_to_anchor=(0,-.48),ncol=4,frameon=False,fontsize=9)
save(fig,'position-budget')
print('Saved current capacity and position-budget figures')
