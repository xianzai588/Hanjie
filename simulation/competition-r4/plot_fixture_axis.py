"""Actual y=0 sections of the converged independent fixture solid FE."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

ROOT=Path(__file__).resolve().parents[2]
folder=Path(__file__).parent/'results'/'fixture-axis-solid-core-h1.5'
f=np.load(folder/'fields.npz');x,e,u,s=(f[k] for k in ('x','e','u','stress'))
xx=x[e];selected=np.flatnonzero((xx[:,:,1].min(axis=1)<0)&(xx[:,:,1].max(axis=1)>0))
normal=s[:,:3].mean(axis=1);dev=s.copy();dev[:,:3]-=normal[:,None]
vm=np.sqrt(1.5*np.sum(dev*dev,axis=1))
polygons=[];displacement=[];stress=[]
for cell in selected:
    points=[];values=[]
    for a,b in ((0,1),(0,2),(0,3),(1,2),(1,3),(2,3)):
        pa,pb=xx[cell,a],xx[cell,b]
        if pa[1]*pb[1]<0:
            t=-pa[1]/(pb[1]-pa[1])
            points.append((pa+t*(pb-pa))[[0,2]])
            values.append((u[e[cell,a],0]+t*(u[e[cell,b],0]-u[e[cell,a],0]))*1000)
    if len(points)<3:continue
    points=np.array(points);centre=points.mean(axis=0)
    order=np.argsort(np.arctan2(points[:,1]-centre[1],points[:,0]-centre[0]))
    polygons.append(points[order]);displacement.append(np.mean(values));stress.append(vm[cell])
plt.rcParams['font.sans-serif']=['Microsoft YaHei'];plt.rcParams['axes.unicode_minus']=False
fig,axes=plt.subplots(1,3,figsize=(11,5),layout='constrained')
for ax,values,label,cmap in zip(axes[:2],(displacement,stress),('径向位移 u_x / μm','von Mises / MPa'),('viridis','magma')):
    coll=PolyCollection(polygons,array=np.asarray(values),cmap=cmap,edgecolors='none')
    ax.add_collection(coll);ax.autoscale();ax.set_aspect('equal');ax.set(xlabel='x / mm',ylabel='z / mm',title=label)
    fig.colorbar(coll,ax=ax,shrink=.8)
envelope=json.loads((ROOT/'output/review/carrier-design-envelope.json').read_text(encoding='utf8'))
components=envelope['radial_axis_deflection_components_mm']
labels={'bolt_root':'螺栓根部','flange_bending':'法兰弯曲','flange_transverse_shear':'法兰剪切',
        'bulk_solid_FE':'实体有限元','microscopic_face_axis_allowance':'界面轴移分配'}
axes[2].barh([labels[k] for k in components],[v*1000 for v in components.values()],color='#548e9b')
axes[2].axvline(6.5,color='#a45b3f',ls='--',label='夹紧径向预算6.5 μm')
axes[2].set(xlabel='径向轴移 / μm',title='全链容量包络');axes[2].legend(fontsize=8)
fig.suptitle('实心固定反锥承力验证：5 kN侧向力＋支承矩＋双头轻击；E=180 GPa',fontsize=12)
target=ROOT/'docs/report/figures/fixture-axis-solid-fe.png';fig.savefig(target,dpi=240);plt.close(fig)
print(target)
