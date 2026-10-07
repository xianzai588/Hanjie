"""Engineering plots from accepted startup histories, with no synthetic fields."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mma_literature_profile import ROOT
from audit_mma_startup_check import BASE,CASES


if __name__=='__main__':
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,
        'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,2,figsize=(11.2,7.4),layout='constrained')
    labels=['基准 h0.65 / Δt0.125','时间减半 Δt0.0625','局部加密 h0.45']
    colors=['#225b80','#d16b38','#4c8065']
    folder=BASE/CASES[0]
    mass=np.loadtxt(folder/'deposition-history.csv',delimiter=',',skiprows=1,ndmin=2)
    axes[0,0].plot(np.r_[0,mass[:,0]],np.r_[0,mass[:,4]],color='#333333',ls='--',label='pWPS 0.17 g/s')
    axes[0,0].scatter(mass[:,0],mass[:,5],s=22,facecolors='none',edgecolors=colors[0],label='实际累计沉积')
    axes[0,0].set(title='a  逐步质量闭合',xlabel='起弧时间 / s',ylabel='累计沉积质量 / g',xlim=(0,1.03),ylim=(0,.18))
    axes[0,0].legend(frameon=False,fontsize=8)
    for name,label,color in zip(CASES,labels,colors):
        data=np.loadtxt(BASE/name/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
        axes[0,1].plot(np.r_[0,data[:,0]],np.r_[300,data[:,4]],label=label,color=color,lw=1.6)
    axes[0,1].axhline(2800,color='#9c3434',ls=':',lw=1.1,label='模型温度上限2800℃')
    axes[0,1].set(title='b  规定的时间与空间对照',xlabel='起弧时间 / s',ylabel='活动金属最高温度 / ℃',xlim=(0,1.03),ylim=(250,2950))
    axes[0,1].legend(frameon=False,fontsize=7.5,loc='lower right')
    heat=np.loadtxt(folder/'source-partition-history.csv',delimiter=',',skiprows=1,ndmin=2)
    data=np.loadtxt(folder/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
    for column,label,color in [(10,'直接净热→QT',colors[0]),(11,'直接净热→镍池',colors[1]),(4,'新金属进入焓',colors[2])]:
        axes[1,0].plot(heat[:,0],heat[:,column]/heat[:,1],color=color,label=label,lw=1.5)
    axes[1,0].plot(data[:,0],data[:,9]/data[:,1],color='#777777',ls='--',label='对流与辐射损失')
    axes[1,0].set(title='c  每步输入分配及损失（总净输入2024 W）',xlabel='起弧时间 / s',ylabel='平均功率 / W',xlim=(0,1.03),ylim=(0,1800))
    axes[1,0].legend(frameon=False,fontsize=8)
    inp=json.loads((folder/'input.json').read_text())
    with np.load(folder/'thermal-fields.npz') as f:
        x,e,m,T,faces=f['x'],f['e'],f['material'],f['temperature'],f['interface_nodes']
    bary=np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
    points=np.einsum('qj,fjk->fqk',bary,x[faces])
    phi=np.arctan2(x[:,1],x[:,0])+inp['growth_rise_length_mm']/inp['tracks'][0]['radius_mm']*(x[:,2]-inp['growth_floor_z_mm'])/(inp['growth_top_z_mm']-inp['growth_floor_z_mm'])
    present=phi[faces]@bary.T<=mass[-1,7]
    points=points[present];values=(T[faces]@bary.T)[present]
    radius=np.linalg.norm(points[:,:2],axis=1)
    arc=71.98*np.arctan2(points[:,1],points[:,0])
    sc=axes[1,1].scatter(arc,radius,c=values,cmap='inferno',s=9,vmin=300,vmax=2500,linewidths=0)
    axes[1,1].set(title='d  t=1 s已出生QT/镍界面温度积分点',xlabel='s=71.98θ / mm',ylabel='半径 / mm',xlim=(-10.5,-5.5),ylim=(68.8,75.2))
    fig.colorbar(sc,ax=axes[1,1],label='当前温度 / ℃',shrink=.8,pad=.02)
    for ax in axes.flat:ax.grid(alpha=.15)
    fig.suptitle('CI-A1单连续轨迹起弧接口核验：供料、热平衡与离散精度',fontsize=13)
    dest=ROOT/'output/review/mma-startup-20261007';dest.mkdir(parents=True,exist_ok=True)
    for ext in ['png','pdf','svg']:
        fig.savefig(dest/('startup-physical-check.'+ext),dpi=300)
    print(dest/'startup-physical-check.png')
