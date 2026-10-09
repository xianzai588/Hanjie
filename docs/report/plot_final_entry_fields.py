"""Read saved 8P fields only; export 300 dpi engineering figures."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, colors
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT=Path(__file__).resolve().parents[2]
CASE='8p-thermal-tool-bore008-h1125-dt025-s05'
SOURCE=ROOT/'simulation/competition-r4/results'/CASE
OUT=ROOT/'docs/report/figures/final-entry'


def surface(x,e,m):
    allfaces=np.vstack([e[:,[0,1,2]],e[:,[0,1,3]],e[:,[0,2,3]],e[:,[1,2,3]]])
    owner=np.tile(np.arange(len(e)),4)
    _,indices,counts=np.unique(np.sort(allfaces,axis=1),axis=0,return_index=True,return_counts=True)
    indices=indices[counts==1]
    faces,owners=allfaces[indices],owner[indices]
    centre=x[faces].mean(axis=1)
    keep=(m[owners]!=0)|(centre[:,1]>=0)
    return faces[keep],owners[keep]


def view(ax,x,faces,owners,values,cmap,norm):
    keep=(x[faces].mean(axis=1)[:,2]>=80)&(x[faces].mean(axis=1)[:,2]<=140)
    faces,owners=faces[keep],owners[keep]
    poly=Poly3DCollection(x[faces],facecolors=cmap(norm(values[owners])),edgecolors='none',rasterized=True)
    ax.add_collection3d(poly)
    ax.set(xlim=(-82,82),ylim=(-82,82),zlim=(80,140),xlabel='X / mm',ylabel='Y / mm',zlabel='Z / mm')
    ax.view_init(elev=38,azim=-63)
    ax.set_box_aspect((164,164,75))
    ax.tick_params(labelsize=7,pad=0)
    for axis in (ax.xaxis,ax.yaxis,ax.zaxis):axis.set_pane_color((1,1,1,0))


def export(fig,name):
    fig.savefig(OUT/(name+'.png'),dpi=300,facecolor='white')
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    font_manager.fontManager.addfont(str(ROOT/'assets/fonts/NotoSansSC-Regular.ttf'))
    plt.rcParams.update({'font.family':'Noto Sans SC','font.size':9,'axes.unicode_minus':False,
        'axes.spines.top':False,'axes.spines.right':False})
    with np.load(SOURCE/'fields.npz') as f:
        x,e,m=f['x'],f['e'],f['material']
        snapshots=f['temperature_snapshots']
        index=int(np.argmax(snapshots.max(axis=1)))
        temp=snapshots[index].astype(float)
        alltime_nodal_peak=float(f['peak_nodal_temperature'].max())
    eq=np.loadtxt(SOURCE/'equilibrium-history.csv',delimiter=',',skiprows=1)
    saved_time=float(eq[10*index+9,0])
    faces,owners=surface(x,e,m)
    fig=plt.figure(figsize=(7.1,5.5))
    fig.subplots_adjust(left=.01,right=.76,bottom=.20,top=.87)
    ax=fig.add_subplot(111,projection='3d')
    norm=colors.Normalize(20,float(temp.max()));cmap=plt.get_cmap('turbo')
    view(ax,x,faces,owners,temp,cmap,norm)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=fig.add_axes([.86,.28,.025,.43]),label='单元平均温度 / ℃')
    ax.text2D(.01,.95,'Q235B壳体／QT450-10座体／八段焊缝',transform=ax.transAxes,fontsize=8)
    hot=int(np.argmax(temp));point=x[e[hot]].mean(axis=0)
    ax.scatter(*point,color='#222222',s=16)
    ax.text2D(.01,.89,f'快照焊段峰值 {temp.max():.0f}℃（黑点）',transform=ax.transAxes,fontsize=8)
    fig.suptitle(f'终焊温度场：保存快照最高温时刻 t={saved_time:.2f} s',fontsize=11)
    fig.text(.5,.035,f'h=1.125 mm，dt=0.25 s；壳体局部剖开（Z=80—140 mm）；几何×1\n全时程节点峰值{alltime_nodal_peak:.0f}℃；色阶为该快照单元温度',ha='center',fontsize=8)
    export(fig,'temperature-snapshot')
    with np.load(SOURCE/'free-release-fields.npz') as f:
        u=f['u'];stress=f['stress']
    dev=stress.copy();dev[:,:3]-=stress[:,:3].mean(axis=1)[:,None]
    vm=np.sqrt(1.5*np.sum(dev**2,axis=1))
    centre=x[e].mean(axis=1);radius=np.linalg.norm(centre[:,:2],axis=1)
    region={'焊趾邻域':(radius>69)&(centre[:,2]>113)&(centre[:,2]<121),
            '槽根邻域':(m==1)&(radius>30)&(radius<61)}
    maxima={}
    fig=plt.figure(figsize=(7.1,5.5));fig.subplots_adjust(left=.01,right=.76,bottom=.20,top=.87)
    ax=fig.add_subplot(111,projection='3d')
    norm=colors.Normalize(0,float(vm.max()));cmap=plt.get_cmap('viridis')
    view(ax,x,faces,owners,vm,cmap,norm)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=fig.add_axes([.86,.28,.025,.43]),label='残余 von Mises 应力 / MPa')
    for label_index,(label,mask) in enumerate(region.items()):
        ids=np.flatnonzero(mask);k=int(ids[np.argmax(vm[ids])]);point=centre[k]
        maxima[label]=dict(element_index=k,value_MPa=float(vm[k]),location_mm=point.tolist())
        ax.scatter(*point,color='#ce553f',s=18)
        ax.text2D(.01,.96-label_index*.06,f'{label}峰值 {vm[k]:.0f} MPa（红点）',transform=ax.transAxes,fontsize=8)
    fig.suptitle('冷却并完全卸夹后的残余应力场',fontsize=11)
    fig.text(.5,.035,'h=1.125 mm，dt=0.25 s；局部剖开（Z=80—140 mm）；几何×1\n焊趾／槽根标记为所列邻域极值；应力直接读取现有场文件',ha='center',fontsize=8)
    export(fig,'residual-stress')
    measurement=json.loads((SOURCE/'measurement.json').read_text(encoding='utf8'))
    fit=measurement['fit'];samples=np.asarray(measurement['measurement_samples_mm']['bore'])
    frame=np.asarray(fit['datum_frame']);origin=np.asarray(fit['datum_A_origin_mm'])
    local=(samples-origin)@frame
    local[:,:2]-=np.asarray(fit['datum_B_center_in_A_frame_mm'])
    sections=local.reshape(33,384,3)
    centres=np.asarray(fit['section_centres_relative_B_mm'])
    bore=np.abs(np.linalg.norm(x[:,:2],axis=1)-20.004)<1e-5
    angle=np.degrees(np.arctan2(x[bore,1],x[bore,0]))%360
    ur=np.sum(u[bore,:2]*x[bore,:2],axis=1)/20.004*1000
    fig,axes=plt.subplots(1,2,figsize=(7.1,3.8),layout='constrained',gridspec_kw={'width_ratios':[1.3,1]})
    import matplotlib.tri as tri
    triang=tri.Triangulation(angle,x[bore,2])
    clim=max(abs(ur.min()),abs(ur.max()))
    artist=axes[0].tripcolor(triang,ur,shading='gouraud',cmap='coolwarm',vmin=-clim,vmax=clim)
    fig.colorbar(artist,ax=axes[0],shrink=.8,label='节点径向位移 / μm')
    axes[0].set(xlabel='孔壁周向角 / °',ylabel='Z / mm',title='a  孔壁径向位移展开（尺寸×1）',xlim=(0,360))
    z=np.linspace(100,115,33)
    axes[1].plot(centres[:,0]*1000,z,color='#315d77',label='X方向偏移')
    axes[1].plot(centres[:,1]*1000,z,color='#b5573f',label='Y方向偏移')
    axes[1].axvline(0,color='0.65',lw=.7);axes[1].grid(alpha=.15)
    axes[1].set(xlabel='相对A/B基准的偏移 / μm',ylabel='Z / mm',title='b  截面孔中心偏移')
    axes[1].legend(frameon=False,fontsize=8)
    fig.suptitle(f'完全卸夹孔变形与孔轴位置度：直径{fit["position_diameter_mm"]*1000:.1f} μm',fontsize=11)
    fig.supxlabel('h=1.125 mm，dt=0.25 s；位移按μm直接绘制，无几何放大\n左图为原坐标节点径向位移；右图为独立A/B基准的33截面拟合结果',fontsize=8)
    export(fig,'bore-displacement')
    manifest=dict(case=CASE,mesh=dict(h_mm=1.125,dt_s=.25,nodes=len(x),tetrahedra=len(e)),
        source_fields=[str((SOURCE/n).relative_to(ROOT)) for n in ['fields.npz','free-release-fields.npz','measurement.json']],
        saved_hottest_snapshot_index=index,saved_hottest_time_s=saved_time,
        saved_snapshot_element_max_C=float(temp.max()),alltime_nodal_peak_C=alltime_nodal_peak,
        maximum_residual_von_mises_MPa=float(vm.max()),labelled_region_maxima=maxima,
        region_scope='Weld-toe vicinity: r>69,z113..121; slot-root vicinity: QT r30..61. Labels are region maxima, not extrapolated notch stresses.',
        position_diameter_um=fit['position_diameter_mm']*1000,
        files=['temperature-snapshot.png','residual-stress.png','bore-displacement.png'],
        dpi=300,physical_simulations_run=0)
    (OUT/'field-figure-data.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(manifest,ensure_ascii=False))


if __name__=='__main__':main()
