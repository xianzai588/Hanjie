"""Cold precoat residual-stress/shape evidence from the completed actual state."""
import argparse
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mma_literature_profile import ROOT
from run_first_layer_machining import datum_frame


def run(source,output):
    result=json.loads((source/'result.json').read_text())
    if result['partial']:raise ValueError('Require the completed cold mechanical state')
    with np.load(source/'fields.npz') as f:
        x,e,m=f['x'],f['e'],f['material'];u=f['u'];stress=f['stress'];eqp=f['eqp']
        T=f['temperature_C'];occupation=f['occupation']
    if T.max()>20.05 or occupation.min()<1-1e-10:raise ValueError('Use the cold completed layer before tool cutting')
    registered,datum=datum_frame(x,u,e,m);delta=registered-x
    dev=stress.copy();dev[:,:3]-=stress[:,:3].mean(axis=1)[:,None]
    vm=np.sqrt(1.5*np.sum(dev*dev,axis=1))
    faces=np.sort(np.vstack([e[:,q] for q in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1)
    owners=np.tile(np.arange(len(e)),4);face,first,count=np.unique(faces,axis=0,return_index=True,return_counts=True)
    exterior=count==1;face=face[exterior];owner=owners[first[exterior]]
    xyz=registered[face];centre=registered[e[owner]].mean(axis=1)
    cross=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]);normal=cross*np.sign(np.einsum('ij,ij->i',cross,xyz.mean(axis=1)-centre))[:,None]
    top=normal[:,2]>1e-8
    polys=xyz[top,:,:2];parents=owner[top]
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':9,'svg.fonttype':'none'})
    fig,axes=plt.subplots(1,3,figsize=(13.2,4.5),layout='constrained')
    values=[vm[parents],eqp[parents]*100,delta[face[top],2].mean(axis=1)*1000]
    titles=['a  冷态残余等效应力','b  存留等效塑性应变','c  A/B基准下端面轴向偏移']
    labels=['等效应力 / MPa','等效塑性应变 / %','轴向偏移 / μm']
    for ax,field,title,label in zip(axes,values,titles,labels):
        colour='RdBu_r' if '偏移' in title else 'viridis'
        limits=(-abs(field).max(),abs(field).max()) if colour=='RdBu_r' else (0,float(field.max()))
        pc=PolyCollection(polys,array=field,cmap=colour,clim=limits,edgecolors='none',rasterized=True)
        ax.add_collection(pc);ax.set(xlim=(-78,78),ylim=(-78,78),aspect='equal',title=title,xlabel='x / mm',ylabel='y / mm')
        fig.colorbar(pc,ax=ax,label=label,shrink=.8)
    fig.suptitle('独立CI-A1首层：实际沉积、凝固与规定炉冷后的制造需求\n参考材料本构；切削前状态，后续精密组焊孔形另行核验',fontsize=11)
    output.mkdir(parents=True,exist_ok=True)
    for extension in ['png','pdf','svg']:fig.savefig(output/('first-layer-cold-demand.'+extension),dpi=300)
    summary=dict(source=str(source),datum=datum,maximum_residual_equivalent_stress_MPa=float(vm.max()),
        maximum_equivalent_plastic_strain=float(eqp.max()),registered_z_range_mm=[float(delta[:,2].min()),float(delta[:,2].max())],
        cold_maximum_C=float(T.max()),full_manufacturing_verified=False)
    (output/'first-layer-cold-demand.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(output/'first-layer-cold-demand.png')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=lambda s:ROOT/s,required=True);p.add_argument('--output',type=lambda s:ROOT/s,required=True)
    a=p.parse_args();run(a.source,a.output)
