"""Plot actual material-interface quadrature peaks without invented contours."""
from pathlib import Path
import argparse,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def plot(case,output):
    case=Path(case);summary=json.loads((case/'interface-thermal-history-summary.json').read_text())
    inp=json.loads((case/'input.json').read_text(encoding='utf8'))
    with np.load(case/'material-interface-thermal.npz',allow_pickle=False) as f:
        xyz=f['quadrature_xyz_mm'];pair=f['material_pairs'];peak=f['peak_quadrature_C'];seg=f['segment'];live=f['thermally_active']
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(9,6),layout='constrained',sharex=True)
    for row,(ids,name,ts) in enumerate([((2,4),'Ni99 / NiFe',1435),((0,2),'Steel / NiFe',1474.85)]):
        for col,j in enumerate([0,4]):
            pick=np.all(pair==ids,axis=1)&(seg==j)&live
            q=xyz[pick].reshape(-1,3);T=peak[pick].ravel()
            theta=np.arctan2(q[:,1],q[:,0])-j*np.pi/4
            along=74.98*np.arctan2(np.sin(theta),np.cos(theta))
            height=np.linalg.norm(q[:,:2],axis=1) if row==0 else q[:,2]
            ax=axes[row,col]
            dots=ax.scatter(along,height,c=T,cmap='inferno',vmin=20,vmax=2100,s=9,linewidths=0,rasterized=True)
            fused=T>=ts
            ax.scatter(along[fused],height[fused],s=17,facecolors='none',edgecolors='#2bc4df',linewidths=.65)
            ax.set_title(f'{name}, segment {j+1}'+(' (+5%)' if j==0 else ''),loc='left',fontsize=10)
            ax.set_ylabel('Radius r (mm)' if row==0 else 'Height z (mm)')
            ax.set_xlim(-9.2,9.2);ax.grid(alpha=.12)
            if row==0:ax.set_ylim(70.8,75.1)
            else:ax.set_ylim(114.9,119.2);ax.set_xlabel('Along segment s (mm)')
            ax.text(.03,.05 if row==0 else .90,f'Both-solidus threshold: {ts:g} C',transform=ax.transAxes,fontsize=8)
    fig.colorbar(dots,ax=axes.ravel().tolist(),label='Actual peak interface temperature (C)',shrink=.85)
    fig.suptitle(f"285 J/mm per head; source z={inp['source_root_z_mm']:g} mm; cold Ni99 stack {inp['explicit_layer_geometry']['total_layer_mm']:g} mm",fontsize=11)
    fig.supxlabel('Cyan rings: actual quadrature point exceeded both solidus temperatures. Root pair only; precoat and cap states assessed separately.',fontsize=8)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(output,dpi=260);fig.savefig(output.with_suffix('.pdf'));plt.close(fig)
    return dict(case=str(case),partial=summary['partial'],time_s=summary['t_s'],plot=str(output),scope='native face quadrature values; no grid interpolation or experimental fields')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(plot(a.case,a.output),indent=2))
