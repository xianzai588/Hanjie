"""Actual first-layer process timing for the WPS and furnace-capacity design."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mma_literature_profile import ROOT


def run():
    source=ROOT/'simulation/competition-r4/results/mma-eight-wing-phase-front-t4-end80-r12-20261007'
    result=json.loads((source/'result.json').read_text())
    if result['partial']:raise ValueError('Require the completed actual eight-wing history')
    history=np.loadtxt(source/'thermal-history.csv',delimiter=',',skiprows=1)
    boundary=np.loadtxt(source/'boundary-history.csv',delimiter=',',skiprows=1)
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,
        'font.size':9,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,1,figsize=(10.4,6.1),layout='constrained',sharex=True,
        gridspec_kw={'height_ratios':[1.35,1]})
    axes[0].plot(history[:,0]/60,history[:,4],color='#a64b37',lw=1.1,label='实际活动金属最高温度')
    axes[0].plot(history[:,0]/60,history[:,5],color='#315d77',lw=1,label='QT最高温度')
    axes[0].set(ylabel='温度 / ℃',title='a  八翼顺序沉积及真实冷却')
    axes[0].legend(frameon=False,fontsize=8,loc='upper right')
    labels=[str(stage['wing']) for stage in result['stages']]
    for k,stage in enumerate(result['stages']):
        start=stage['start_s'];arc=stage['arc_s'];end=stage['end_s']
        axes[1].broken_barh([(start/60,arc/60)],(k-.33,.66),facecolors='#a64b37')
        axes[1].broken_barh([((start+arc)/60,(end-start-arc)/60)],(k-.33,.66),facecolors='#bdd0db')
        select=(boundary[:,3]==stage['wing'])&(boundary[:,5]==1)
        for row in boundary[select]:
            axes[1].broken_barh([((row[0]-row[1])/60,row[1]/60)],(k-.33,.66),facecolors='#e6be6b')
        axes[1].text(start/60,k+.40,f"{stage['initial_max_C']:.1f}℃",fontsize=7,color='#315d77')
    from matplotlib.patches import Patch
    axes[1].legend(handles=[Patch(color='#a64b37',label='电弧'),Patch(color='#bdd0db',label='冷却'),
        Patch(color='#e6be6b',label='炉边界复温')],frameon=False,ncol=3,loc='upper left',fontsize=8)
    axes[1].set(yticks=range(8),yticklabels=labels,ylabel='实际翼号',xlabel='首道起弧后时间 / min',
        title='b  工序占用及道前温度',ylim=(-1.2,7.8),xlim=(0,result['time_s']/60+.35))
    axes[1].invert_yaxis()
    for ax in axes:ax.grid(axis='x',alpha=.17)
    fig.suptitle('独立CI-A1首层：八翼实际热史与节拍\n电弧92.55 s；至入炉28.24 min；翼间复温7.00 min；随后独立保温缓冷',fontsize=11)
    fig.supxlabel('时间包含模型内冷却和复温；人工装卸、清渣与选配轻击另计。图中数据为设计计算。',fontsize=8)
    output=ROOT/'output/review/mma-continuous-end80-r12-20261007'
    for ext in ('png','pdf','svg'):fig.savefig(output/('actual-eight-wing-first-layer-cycle.'+ext),dpi=300)
    print(output/'actual-eight-wing-first-layer-cycle.png')


if __name__=='__main__':run()
