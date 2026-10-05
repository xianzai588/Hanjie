"""Engineering sections from actual cold and inherited-state service fields."""
from pathlib import Path
import argparse, json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from welded_strength import vm

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent/'results'
FIG=ROOT/'docs/report/figures'


def section(x,e,nodal_value,element_value):
    polygons=[];cold=[];loaded=[]
    points=x[e];mask=(points[:,:,1].min(axis=1)<=0)&(points[:,:,1].max(axis=1)>=0)
    for k in np.flatnonzero(mask):
        p=points[k];cut=[];values=[]
        for a,b in ((0,1),(0,2),(0,3),(1,2),(1,3),(2,3)):
            if abs(p[a,1])<1e-10:
                cut.append(p[a,[0,2]]);values.append(nodal_value[e[k,a]])
            if p[a,1]*p[b,1]<0:
                ratio=-p[a,1]/(p[b,1]-p[a,1])
                cut.append((p[a]+ratio*(p[b]-p[a]))[[0,2]])
                values.append(nodal_value[e[k,a]]+ratio*(nodal_value[e[k,b]]-nodal_value[e[k,a]]))
            if abs(p[b,1])<1e-10:
                cut.append(p[b,[0,2]]);values.append(nodal_value[e[k,b]])
        if len(cut)<3:continue
        cut=np.array(cut);_,indices=np.unique(np.round(cut,9),axis=0,return_index=True)
        cut=cut[indices];values=np.array(values)[indices]
        if len(cut)<3:continue
        center=cut.mean(axis=0);order=np.argsort(np.arctan2(cut[:,1]-center[1],cut[:,0]-center[0]))
        polygons.append(cut[order]);cold.append(float(values.mean()));loaded.append(float(element_value[k]))
    return polygons,np.array(cold),np.array(loaded)


def main(case):
    folder=OUT/case
    with np.load(folder/'free-release-fields.npz') as f:
        x,e,u=f['x'],f['e'],f['u']
    with np.load(folder/'stateful-service-fields.npz') as f:
        s=f['loaded_stress_Mandel_MPa'];unloaded_u=f['unloaded_u_increment_mm']
    result=json.loads((folder/'stateful-service-result.json').read_text(encoding='utf8'))
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],
        'axes.unicode_minus':False,'font.size':10})
    polygons,cold,loaded=section(x,e,np.linalg.norm(u,axis=1)*1000,vm(s))
    fig,axes=plt.subplots(2,1,figsize=(11,6.5),layout='constrained')
    for ax,value,title,unit in zip(axes,(cold,loaded),
        ('完全冷却卸夹后的位移幅值','继承冷态应力与塑性后，1.5倍设定载荷的体材料VM应力'),('μm','MPa')):
        artist=PolyCollection(polygons,array=value,cmap='viridis',edgecolors='none',rasterized=True)
        artist.set_clim(0,float(value.max()));ax.add_collection(artist)
        ax.set(xlim=(-82,82),ylim=(90,123),xlabel='x / mm',ylabel='z / mm',title=title)
        ax.set_aspect('equal');fig.colorbar(artist,ax=ax,label=unit,shrink=.9)
    fig.suptitle('实际有限元剖面 y=0；Ø40.008 / h1.5 / Δt0.25',fontsize=12)
    FIG.mkdir(parents=True,exist_ok=True)
    fig.savefig(FIG/'r4-stateful-service-section.png',dpi=300);plt.close(fig)
    history=result['history'];step=np.arange(1,len(history)+1)
    fig,axes=plt.subplots(1,2,figsize=(10,3.2),layout='constrained')
    axes[0].plot(step,[h['load_factor'] for h in history],color='#0369a1',label='载荷系数')
    twin=axes[0].twinx();twin.plot(step,[h['maximum_added_eqp']*100 for h in history],color='#b45309',label='最大新增塑性')
    axes[0].set(xlabel='实际收敛载荷步',ylabel='设定载荷倍数',title='加载至1.5倍，再完全卸载')
    twin.set_ylabel('新增等效塑性应变 / %',color='#b45309')
    axes[1].plot(step,[h['residual_N'] for h in history],color='#0369a1')
    axes[1].axhline(.001,color='#b45309',ls='--',label='0.001 N收敛限')
    axes[1].set(xlabel='实际收敛载荷步',ylabel='自由自由度平衡残差 / N',title='30步实际平衡检验');axes[1].legend()
    fig.savefig(FIG/'r4-stateful-service-path.png',dpi=300);plt.close(fig)
    summary=dict(case=case,source_fields=['free-release-fields.npz','stateful-service-fields.npz'],
        section_plane='y=0; displacement interpolated along tetrahedron edges, cell stress held constant',
        maximum_unloaded_increment_displacement_mm=float(np.linalg.norm(unloaded_u,axis=1).max()),
        maximum_loaded_body_VM_MPa=float(vm(s).max()),
        maximum_added_eqp=result['maximum_added_eqp'],
        maximum_equilibrium_residual_N=max(h['residual_N'] for h in history),
        scope=result['scope'])
    (folder/'stateful-service-plot-evidence.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);main(p.parse_args().case)
