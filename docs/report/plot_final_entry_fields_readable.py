"""Exact saved-field sections and magnified bore-centre schematic; no new solve."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, colors
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
ROOT=Path(__file__).resolve().parents[2]
CASE='8p-thermal-tool-bore008-h1125-dt025-s05'
SOURCE=ROOT/'simulation/competition-r4/results'/CASE
OUT=ROOT/'docs/report/figures/final-entry'
CMAP=colors.LinearSegmentedColormap.from_list('engineering',['#f3f6f9','#82b4d3','#2775ad','#ffe08b','#ef743d','#bd2326'])

def surface(x,e,m):
    f=np.vstack([e[:,[0,1,2]],e[:,[0,1,3]],e[:,[0,2,3]],e[:,[1,2,3]]]);o=np.tile(np.arange(len(e)),4)
    _,idx,n=np.unique(np.sort(f,axis=1),axis=0,return_index=True,return_counts=True);idx=idx[n==1]
    f,o=f[idx],o[idx];c=x[f].mean(axis=1);keep=((m[o]!=0)|(c[:,1]>=0))&(c[:,2]>=90)&(c[:,2]<=122)
    return f[keep],o[keep]

def view(ax,x,f,o,v,norm):
    ax.add_collection3d(Poly3DCollection(x[f],facecolors=CMAP(norm(v[o])),edgecolors=(.45,.55,.60,.12),linewidths=.12,rasterized=True))
    ax.set(xlim=(-82,82),ylim=(-82,82),zlim=(90,122));ax.view_init(38,-65);ax.set_box_aspect((164,164,58));ax.set_axis_off()

def section(ax,x,e,v,point,half=10,norm=None,label=''):
    radial=np.array([point[0],point[1],0.]);radial/=np.linalg.norm(radial);tangent=np.cross([0.,0.,1.],radial)
    xx=x[e]-point;d=xx@tangent;rr=xx@radial;zz=xx[:,:,2]
    ids=np.flatnonzero((d.min(axis=1)<=0)&(d.max(axis=1)>=0)&(rr.min(axis=1)<half)&(rr.max(axis=1)>-half)&(zz.min(axis=1)<half)&(zz.max(axis=1)>-half))
    polys=[];values=[]
    for k in ids:
        pts=[]
        for a,b in [(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)]:
            if d[k,a]*d[k,b]<0:
                t=d[k,a]/(d[k,a]-d[k,b]);q=xx[k,a]+t*(xx[k,b]-xx[k,a]);pts.append([q@radial,q[2]])
        if len(pts)<3:continue
        pts=np.asarray(pts);cc=pts.mean(axis=0);order=np.argsort(np.arctan2(pts[:,1]-cc[1],pts[:,0]-cc[0]))
        polys.append(pts[order]);values.append(v[k])
    artist=PolyCollection(polys,array=np.asarray(values),cmap=CMAP,norm=norm,edgecolors='none',rasterized=True)
    ax.add_collection(artist);ax.set(xlim=(-half,half),ylim=(-half,half),aspect='equal',xlabel='径向距离 / mm',ylabel='高度差 / mm')
    ax.scatter(0,0,s=65,facecolors='none',edgecolors='#202124',linewidths=1.2);ax.plot([0],[0],'+',color='#202124',ms=5)
    ax.set_title(label,fontsize=10);ax.grid(alpha=.12);return artist

def export(fig,name):fig.savefig(OUT/(name+'.png'),dpi=300,facecolor='white');plt.close(fig)

def main():
    OUT.mkdir(exist_ok=True);font_manager.fontManager.addfont(str(ROOT/'assets/fonts/NotoSansSC-Regular.ttf'))
    plt.rcParams.update({'font.family':'Noto Sans SC','font.size':10,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,'xtick.labelsize':8,'ytick.labelsize':8})
    with np.load(SOURCE/'fields.npz') as f:
        x,e,m=f['x'],f['e'],f['material'];snap=f['temperature_snapshots'];idx=int(np.argmax(snap.max(axis=1)));temp=snap[idx].astype(float);peak=float(f['peak_nodal_temperature'].max())
    eq=np.loadtxt(SOURCE/'equilibrium-history.csv',delimiter=',',skiprows=1);t=float(eq[10*idx+9,0])
    faces,owners=surface(x,e,m);centres=x[e].mean(axis=1);hot=centres[np.argmax(temp)]
    fig=plt.figure(figsize=(7.1,4.35));gs=fig.add_gridspec(1,2,left=.01,right=.84,bottom=.27,top=.84,width_ratios=[1,1.12],wspace=.28)
    norm=colors.PowerNorm(.55,20,float(temp.max()));ax=fig.add_subplot(gs[0,0],projection='3d');view(ax,x,faces,owners,temp,norm)
    ax.scatter(*hot,s=32,color='#202124');ax.set_title('a  座体、壳体与焊段（壳体剖开）',fontsize=10,pad=-2)
    ax=fig.add_subplot(gs[0,1]);artist=section(ax,x,e,temp,hot,norm=norm,label='b  峰值焊段 20×20 mm 剖切')
    fig.colorbar(artist,cax=fig.add_axes([.86,.30,.018,.49]),label='温度 / ℃',ticks=[20,200,500,900,1200,float(temp.max())])
    fig.suptitle(f'终焊温度场：t={t:.2f} s；h=1.125 mm，dt=0.25 s',fontsize=11)
    fig.text(.5,.055,f'几何×1；圈点为该快照峰值 {temp.max():.0f}℃；全时程节点峰值 {peak:.0f}℃\n剖切穿过峰值单元中心；色阶上限为快照实际峰值（低温段展开显示）',ha='center',fontsize=9);export(fig,'temperature-snapshot')
    with np.load(SOURCE/'free-release-fields.npz') as f:u,stress=f['u'],f['stress']
    dev=stress.copy();dev[:,:3]-=stress[:,:3].mean(axis=1)[:,None];vm=np.sqrt(1.5*np.sum(dev**2,axis=1));radius=np.linalg.norm(centres[:,:2],axis=1)
    masks={'焊趾邻域':(radius>69)&(centres[:,2]>113)&(centres[:,2]<121),'槽根邻域':(m==1)&(radius>30)&(radius<61)};maxima={}
    for label,mask in masks.items():
        ids=np.flatnonzero(mask);k=int(ids[np.argmax(vm[ids])]);maxima[label]=dict(element_index=k,value_MPa=float(vm[k]),location_mm=centres[k].tolist())
    fig=plt.figure(figsize=(7.1,6.0));gs=fig.add_gridspec(2,2,left=.09,right=.87,bottom=.14,top=.90,hspace=.68,wspace=.50)
    toe=maxima['焊趾邻域'];ax=fig.add_subplot(gs[0,:]);artist=section(ax,x,e,vm,np.asarray(toe['location_mm']),half=165,norm=colors.Normalize(0,vm.max()),label='a  穿过焊趾峰值的整体径向剖切')
    ax.set_ylim(-28,16);ax.set_xlim(-160,10);ax.set_ylabel('相对焊趾高度 / mm');ax.set_xlabel('相对焊趾径向距离 / mm')
    fig.colorbar(artist,ax=ax,fraction=.03,pad=.04,label='MPa',ticks=[0,100,200,300,float(vm.max())])
    for j,(label,entry) in enumerate(maxima.items()):
        ax=fig.add_subplot(gs[1,j]);vmax=entry['value_MPa'];artist=section(ax,x,e,vm,np.asarray(entry['location_mm']),half=6,norm=colors.Normalize(0,vmax),label=f'{"b" if j==0 else "c"}  {label}：{vmax:.1f} MPa')
        fig.colorbar(artist,ax=ax,fraction=.047,pad=.03,ticks=[0,vmax/2,vmax])
    fig.suptitle('冷却并完全卸夹残余 von Mises 应力；h=1.125 mm，dt=0.25 s',fontsize=11)
    fig.text(.5,.025,'几何×1；局部视窗12×12 mm；圈点为区域最大值的单元中心\n焊趾与槽根分别使用所标色标上限；有限元单元场直接剖切，无节点外推',ha='center',fontsize=9);export(fig,'residual-stress')
    data=json.loads((SOURCE/'measurement.json').read_text(encoding='utf8'));fit=data['fit'];cc=np.asarray(fit['section_centres_relative_B_mm'])
    bore=np.abs(np.linalg.norm(x[:,:2],axis=1)-20.004)<1e-5;angle=np.degrees(np.arctan2(x[bore,1],x[bore,0]))%360;ur=np.sum(u[bore,:2]*x[bore,:2],axis=1)/20.004*1000
    fig=plt.figure(figsize=(7.1,5.6));gs=fig.add_gridspec(2,2,left=.09,right=.91,bottom=.14,top=.88,wspace=.50,hspace=.57)
    import matplotlib.tri as tri
    ax=fig.add_subplot(gs[:,0]);clim=max(abs(ur.min()),abs(ur.max()));artist=ax.tripcolor(tri.Triangulation(angle,x[bore,2]),ur,shading='gouraud',cmap='coolwarm',vmin=-clim,vmax=clim)
    ax.set(xlabel='孔壁周向角 / °',ylabel='Z / mm',title='a  孔壁径向位移 / μm',xlim=(0,360));ax.set_xticks([0,90,180,270,360])
    fig.colorbar(artist,ax=ax,orientation='horizontal',pad=.13,fraction=.035,label='径向位移 / μm')
    ax=fig.add_subplot(gs[0,1]);z=np.linspace(100,115,33);ax.plot(cc[:,0]*1000,z,color='#2775ad',label='X');ax.plot(cc[:,1]*1000,z,color='#bd2326',label='Y');ax.axvline(0,color='.65',lw=.7)
    ax.set(xlabel='孔中心偏移 / μm',ylabel='Z / mm',title='b  独立A/B下轴线偏移');ax.legend(frameon=False,fontsize=8);ax.grid(alpha=.15)
    ax=fig.add_subplot(gs[1,1]);k=int(np.argmax(np.linalg.norm(cc,axis=1)));shift=cc[k]*500;a=np.linspace(0,2*np.pi,250)
    ax.plot(20*np.cos(a),20*np.sin(a),color='.4',ls='--',lw=1);ax.plot(20*np.cos(a)+shift[0],20*np.sin(a)+shift[1],color='#bd2326',lw=1.4)
    ax.plot(0,0,'+',color='.2',ms=8);ax.plot(*shift,'+',color='#bd2326',ms=8);ax.annotate('',xy=shift,xytext=(0,0),arrowprops=dict(arrowstyle='->',color='#bd2326',lw=1.3))
    ax.set(aspect='equal',xlim=(-25,25),ylim=(-25,25),title='c  孔中心偏移示意 ×500');ax.set_axis_off();ax.text(0,-28,f'真实偏移 {np.linalg.norm(cc[k])*1000:.1f} μm',ha='center',fontsize=9)
    fig.suptitle(f'完全卸夹孔区：位置度直径 {fit["position_diameter_mm"]*1000:.1f} μm；h=1.125 mm',fontsize=11)
    fig.text(.5,.025,'dt=0.25 s；a、b按μm直接绘制，无几何放大\nc仅将中心偏移放大500倍，Ø40孔轮廓保持原尺寸比例；虚线圆中心为独立A/B轴',ha='center',fontsize=9);export(fig,'bore-displacement')
    manifest=dict(case=CASE,mesh=dict(h_mm=1.125,dt_s=.25,nodes=len(x),tetrahedra=len(e)),saved_hottest_time_s=t,saved_snapshot_element_max_C=float(temp.max()),alltime_nodal_peak_C=peak,
        maximum_residual_von_mises_MPa=float(vm.max()),labelled_region_maxima=maxima,section_method='Exact tetrahedron/plane intersections, piecewise constant saved element field',
        position_diameter_um=fit['position_diameter_mm']*1000,bore_schematic_centre_amplification=500,dpi=300,physical_simulations_run=0,
        files=['temperature-snapshot.png','residual-stress.png','bore-displacement.png'])
    (OUT/'field-figure-data.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':main()
