"""Condensation-domain evidence from actual post-arc saved thermal states."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mma_literature_profile import ROOT


def run():
    report=ROOT/'simulation/competition-r4/results/mma-continuous-end80-r12-20261007/phase-resolved-cooling-verification.json'
    d=json.loads(report.read_text())
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':9,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,3,figsize=(12.7,4),layout='constrained')
    labels=['h0.65 / 冷却Δt0.125','h0.65 / 冷却Δt0.0625','局部h0.45 / 冷却Δt0.125']
    for case,label,col in zip(d['cases'],labels,['#245b78','#d17a42','#498363']):
        history=np.loadtxt(ROOT/case['source']/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
        arc_end=json.loads((ROOT/case['source']/'input.json').read_text())['tracks'][0]['arc_duration_s']
        selected=(history[:,0]>=arc_end)&(history[:,0]<=arc_end+16)
        axes[0].plot(history[selected,0]-arc_end,history[selected,4],label=label,color=col,lw=1.3)
        probes=case['probes'];times=[row['delay_s'] for row in probes]
        axes[1].plot(times,[row['Ni_coherent_volume_mm3'] for row in probes],'-o',ms=3,color=col)
        axes[2].plot(times,[row['qualified_coherent_face_area_mm2']/case['qualified_reference_area_mm2']*100 for row in probes],'-o',ms=3,color=col)
    axes[0].set(title='a  收弧后的实际温度',xlabel='收弧后时间 / s',ylabel='活动金属最高温度 / ℃',ylim=(900,2800));axes[0].legend(frameon=False,fontsize=7)
    axes[1].set(title='b  镍层连续固体体积',xlabel='收弧后时间 / s',ylabel='出生域与固相域交集 / mm³')
    axes[2].set(title='c  已热连接界面的固体覆盖',xlabel='收弧后时间 / s',ylabel='完整三角面均已凝固 / %',ylim=(-2,102))
    for ax in axes:ax.grid(alpha=.15)
    fig.suptitle('CI-A1连续首层：凝固阶段离散检查\n相同弧末温度、质量与前沿；冷却过程中温度与材料状态连续传递',fontsize=11)
    output=ROOT/'output/review/mma-continuous-end80-r12-20261007'
    for ext in ['png','pdf','svg']:fig.savefig(output/('first-layer-coherent-cooling.'+ext),dpi=300)
    print(output/'first-layer-coherent-cooling.png')


if __name__=='__main__':run()
