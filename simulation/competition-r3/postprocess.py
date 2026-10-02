import json,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.interpolate import LinearNDInterpolator
sys.path.insert(0,str(ROOT/'src')) if 'ROOT' in globals() else None
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'simulation/competition-r3/results';FIG=ROOT/'docs/report/figures'
sys.path.insert(0,str(ROOT/'src'))
from hanjie.simulation.structural_prep import fit_position_diameter
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False})
coarse=json.loads((OUT/'8p-coarse/result.json').read_text(encoding='utf8'));fine=json.loads((OUT/'8p-review/result.json').read_text(encoding='utf8'))
def fixed_measurement(folder,result):
    f=np.load(folder/'fields.npz');x=f['x'];u=f['u'];rad=np.linalg.norm(x[:,:2],axis=1)
    def surface_points(r,zs,count):
        mask=abs(rad-r)<1e-5
        th=np.arctan2(x[mask,1],x[mask,0]);coords=np.column_stack((th,x[mask,2]));values=u[mask]
        coords=np.vstack((coords-[2*np.pi,0],coords,coords+[2*np.pi,0]));values=np.vstack((values,values,values))
        interp=LinearNDInterpolator(coords,values)
        tt=np.tile(np.arange(count)*2*np.pi/count,len(zs));zz=np.repeat(zs,count)
        q=np.column_stack((tt,zz));du=interp(q)
        if not np.all(np.isfinite(du)):raise RuntimeError('fixed CMM sample interpolation outside surface')
        return np.column_stack((r*np.cos(tt),r*np.sin(tt),zz))+du
    aa=x[x[:,2]<1e-5]+u[x[:,2]<1e-5]
    bb=surface_points(75,[20,180],24);hole=surface_points(20,[100,106,112],12)
    result['fit_original_mesh_nodes']=result.get('fit_original_mesh_nodes',result['fit']);result['fit']=fit_position_diameter(aa,bb,hole)
    result['measurement_protocol']='same 36 bore samples and 48 independent shell samples for every mesh; periodic surface interpolation'
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result
coarse=fixed_measurement(OUT/'8p-coarse',coarse);fine=fixed_measurement(OUT/'8p-review',fine)
d=np.load(OUT/'8p-review/fields.npz');x=d['x'];e=d['e'];m=d['material'];c=x[e].mean(axis=1);u=d['u'];s=d['stress']
pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3
vm=np.sqrt(1.5*np.sum((s-s@pv)**2,axis=1));disp=np.linalg.norm(u[e].mean(axis=1),axis=1)*1000
position=np.array([coarse['fit']['position_diameter_mm'],fine['fit']['position_diameter_mm']])
delta=abs(position[1]-position[0]);relative=delta/max(position[1],1e-9);limit_relative=delta/.05
fields={'position_diameter_mm':fine['fit']['position_diameter_mm'],'mesh_difference_absolute_mm':delta,
 'mesh_difference_relative_to_response':relative,'mesh_difference_fraction_of_design_limit':limit_relative,
 'engineering_mesh_acceptance':'absolute difference ≤ 0.0025 mm (5% of design limit); also report response-relative difference, never hide it',
 'engineering_mesh_pass':bool(delta<=.0025),'max_stress_MPa':float(vm.max()),'max_displacement_mm':float(disp.max()/1000),
 'cold_measurement_temperature_pass':bool(fine['final_max_C']<=21),
 'full_part_result_valid':bool(fine['released'] and fine['max_equilibrium_residual_N']<.05 and abs(fine['energy_balance_relative'])<1e-5),
 'hotspot_QT_slot_root_residual_VM_MPa':float(vm[(m==1)&(np.linalg.norm(c[:,:2],axis=1)>35)&(np.linalg.norm(c[:,:2],axis=1)<47)].max())}
fields['position_budget_mm']=2*(.003+.003+.003+.002+.002+.0008)+position[1]+.002
fields['position_design_pass']=bool(fields['position_budget_mm']<=.05 and fields['engineering_mesh_pass'] and fields['full_part_result_valid'])
(OUT/'verification.json').write_text(json.dumps(fields,ensure_ascii=False,indent=2),encoding='utf8')
FIG.mkdir(exist_ok=True,parents=True)
fig,axes=plt.subplots(1,2,figsize=(11,5),layout='constrained')
mask=m!=0
for ax,val,title,label in zip(axes,[disp,vm],['冷却卸夹位移','冷却卸夹残余应力'],['位移 μm','von Mises MPa']):
 sc=ax.scatter(c[mask,0],c[mask,1],c=val[mask],s=3,cmap='turbo',rasterized=True);ax.set_aspect('equal');ax.set(xlabel='x mm',ylabel='y mm',title=title);fig.colorbar(sc,ax=ax,label=label)
fig.savefig(FIG/'r3-residual-fields.png',dpi=230);fig.savefig(OUT/'residual-fields.svg');plt.close(fig)
hist=np.loadtxt(OUT/'8p-review/thermal-history.csv',delimiter=',',skiprows=1)
eq=np.loadtxt(OUT/'8p-review/equilibrium-history.csv',delimiter=',',skiprows=1)
fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
axes[0].plot(hist[:,0],hist[:,1],label='全件最高节点温度');axes[0].plot(hist[:,0],hist[:,2],label='QT最高单元均温');axes[0].set(xlabel='t s',ylabel='℃',title='真实热历程（复核网格 3.0 mm）');axes[0].legend(fontsize=8)
axes[1].plot(eq[:,0],eq[:,3],label='胀套接触反力（复核网格，峰值614.2 N）');axes[1].set(xlabel='t s',ylabel='N',title='预载与热收缩反力分开校核（主网格峰值2008.3 N，见§4.2）');axes[1].axhline(5000,color='red',ls='--',label='止挡设计承载');axes[1].legend(fontsize=8)
fig.savefig(FIG/'r3-thermal-contact.png',dpi=220);plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
axes[0].bar(['主网格','复核网格'],position*1000,color=['#94a3b8','#0284c7']);axes[0].set(ylabel='位置度直径 μm',title=f'网格差值 {delta*1000:.3f} μm')
vals=[.006,.006,.006,.004,.004,.0016,float(position[1]),.002]
labels=['基准','工装轴','定心','装夹','释放','支点斜率','FE热残余','测量U']
axes[1].barh(labels,np.array(vals)*1000,color='#059669');axes[1].set(xlabel='直径口径 μm',title=f'保守合成 {fields["position_budget_mm"]*1000:.2f} μm ≤ 50')
fig.savefig(FIG/'r3-mesh-budget.png',dpi=220);plt.close(fig)
print(json.dumps(fields,ensure_ascii=False,indent=2))
