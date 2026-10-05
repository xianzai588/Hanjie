"""Engineering figures from finished first-track fields and phase results."""
from pathlib import Path
import csv,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

ROOT=Path(__file__).resolve().parents[2]
RES=ROOT/'simulation/competition-r4/results'
FIG=ROOT/'docs/report/figures'


def main():
    a=json.loads((RES/'route4-reselection/route4-audit.json').read_text(encoding='utf8'))
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False,'font.size':10})
    candidates=[r for r in a['cases'] if r['case'] in [f'route4-P{T}-Ni0-GTAW-equivalent-first' for T in [20,150,350]]]
    if len(candidates)!=3:raise ValueError('all three cooled first-track outputs required')
    fig,axes=plt.subplots(2,3,figsize=(13.4,7.8),layout='constrained',gridspec_kw={'height_ratios':[1,1.15]})
    colours=['#0072B2','#D55E00','#009E73']
    for i,(r,color) in enumerate(zip(candidates,colours)):
        case=RES/r['case'];h=np.loadtxt(case/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
        on=h[:,3]>0
        axes[0,0].plot(h[on,0],h[on,5],color=color,label=f"{r['initial_QT_C']:.0f}℃初温")
        axes[0,1].plot([t['threshold_C'] for t in r['threshold_response']],[t['root_area_mm2'] for t in r['threshold_response']],'-o',ms=3,color=color)
        base=0
        for key,c in [('wire_entering_J','#0072B2'),('intercepted_surface_J','#E69F00'),('uncaptured_J','#9ca3af')]:
            value=r[key]/1000;axes[0,2].bar(i,value,bottom=base,color=c,label={'wire_entering_J':'焊丝进入焓','intercepted_surface_J':'表面截获','uncaptured_J':'未截获'}[key] if i==0 else None);base+=value
        with np.load(case/'thermal-fields.npz',allow_pickle=False) as f:
            x,e,m=f['x'],f['e'],f['material'];fa=f['interface_nodes'];temp=f['interface_peak_C'];active=f['thermal_active']
        bary=np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
        xyz=np.einsum('qj,fjk->fqk',bary,x[fa]);rad=np.linalg.norm(xyz[:,:,:2],axis=2);s=74.98*np.arctan2(xyz[:,:,1],xyz[:,:,0])
        floor=x[np.unique(e[m==3]),2].min()
        born={tuple(sorted(tet[list(idx)])) for tet in e[(m==3)&active] for idx in [(0,1,2),(0,1,3),(0,2,3),(1,2,3)]}
        deposited=np.array([tuple(sorted(row)) in born for row in fa])
        pick=(abs(xyz[:,:,2]-floor)<1e-5)&(rad>=72.2)&(abs(s)<=9)&deposited[:,None]
        im=axes[1,i].scatter(s[pick],rad[pick],c=temp[pick],s=16,cmap='viridis',norm=Normalize(650,1650),edgecolors='none')
        hit=pick&(temp>=1450.85)
        axes[1,i].scatter(s[hit],rad[hit],facecolors='none',edgecolors='#dc2626',s=27,linewidths=.6)
        axes[1,i].set(title=f"{r['initial_QT_C']:.0f}℃初温 / 槽底真实积分点峰温",xlabel='焊程 s / mm',ylabel='半径 R / mm',xlim=(-9,2),ylim=(72.2,75))
    axes[0,0].axhline(1450.85,color='#6b7280',ls='--',lw=1,label='纯Ni熔化起点')
    axes[0,0].set(title='(a) 相同净源：QT温度历程',xlabel='弧燃时间 / s',ylabel='QT最高节点温度 / ℃');axes[0,0].legend(fontsize=8)
    axes[0,1].set(title='(b) 已沉积根道的阈值响应',xlabel='检出阈值 / ℃',ylabel='超过阈值的面积 / mm²');axes[0,1].axvline(1450.85,color='#6b7280',ls='--',lw=1)
    axes[0,2].set(title='(c) 相同弧燃输入的能量分配',xticks=[0,1,2],xticklabels=['20℃','150℃','350℃'],ylabel='能量 / kJ');axes[0,2].legend(fontsize=8)
    for ax in axes.ravel():ax.grid(alpha=.15)
    fig.colorbar(im,ax=axes[1,:],label='实际数值峰温 / ℃',shrink=.9)
    fig.suptitle('独立预制温度制度比较：350 W、v6、纯Ni端元；红圈≥1450.85℃\n只绘制真实已沉积足迹，不插值补出连续熔合',fontsize=12)
    FIG.mkdir(parents=True,exist_ok=True)
    fig.savefig(FIG/'r4-route4-preheat-comparison.png',dpi=260);fig.savefig(FIG/'r4-route4-preheat-comparison.svg');plt.close(fig)
    phase=RES/'route4-filler-phase-gibbs-checked'
    summary=json.loads((phase/'phase-summary.json').read_text());rows=list(csv.DictReader((phase/'phase-fractions.csv').open(encoding='utf8')))
    if not summary['Gibbs_branch_audit']['nested_phase_feasibility_pass']:raise ValueError('phase branch audit required')
    fig,(ax,bx)=plt.subplots(1,2,figsize=(11.6,4.6),layout='constrained')
    for name,color,label in [('bare_Ni99-QT20',colours[0],'裸Ni99，C0.01%'),('Pascual2009_Ni97p6-QT20',colours[1],'文献SMAW，C0.30%'),('RepTecCast1_typical-QT20',colours[2],'供方典型，C0.70%')]:
        for limit,style in [('graphite_allowed','-'),('graphite_suppressed','--')]:
            q=[r for r in rows if r['case']==name and r['limit']==limit and float(r['T_C'])>=1100]
            ax.plot([float(r['T_C']) for r in q],[float(r['LIQUID_mass_fraction']) for r in q],ls=style,color=color,label=label if style=='-' else None)
        q=[r for r in rows if r['case']==name and r['limit']=='graphite_suppressed' and float(r['T_C']) in [25,350,500]]
        bx.plot([float(r['T_C']) for r in q],[100*float(r['CEMENTITE_mass_fraction']) for r in q],'-o',color=color,label=label)
    ax.set(title='(a) 20%QT配混情景的液相比例',xlabel='温度 / ℃',ylabel='平衡液相质量分数');ax.legend(fontsize=8)
    ax.text(.02,.95,'实线：允许石墨；虚线：抑制石墨',transform=ax.transAxes,va='top',fontsize=8)
    bx.set(title='(b) 抑制石墨极限的碳化物负担',xlabel='温度 / ℃',ylabel='渗碳体平衡质量百分数 / %')
    for q in [ax,bx]:q.grid(alpha=.2)
    fig.suptitle('替代焊材必须重算：给定20%QT配混的Fe-Ni-C情景\n成分是输入；相平衡不代替PMZ冷却组织或连接容量',fontsize=11)
    fig.savefig(FIG/'r4-route4-filler-phase.png',dpi=260);fig.savefig(FIG/'r4-route4-filler-phase.svg');plt.close(fig)


if __name__=='__main__':main()
