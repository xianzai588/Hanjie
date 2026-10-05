"""Cold service stresses on the full assembly, separate from welding residual stress."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu
from threadpoolctl import threadpool_limits
from run_verified import operators,fit_position_diameter
ROOT=Path(__file__).resolve().parents[2]
def run(folder,h_override=None):
 data=np.load(folder/'mesh.npz');x=data['x'];e=data['e'];m=data['material'];weld_top=float(x[np.unique(e[m==2]),2].min())
 inp=json.loads((folder/'input.json').read_text(encoding='utf8')) if (folder/'input.json').exists() else {}
 g,vol,B,dof=operators(x,e);N=3*len(x)
 E=np.array([210000,170000,160000])[m];nu=np.array([.28,.27,.3])[m]
 if inp.get('materials'):
  # Same cold constitutive constants as the retained manufacturing state.
  E=np.array([np.interp(20,t['temperature_dependent']['temperatures_c'],t['temperature_dependent']['elastic_modulus_gpa'])*1000 for t in inp['materials']])[m]
  nu=np.array([t['nominal_properties_20c']['poisson_ratio'] for t in inp['materials']])[m]
 pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3;pd=np.eye(6)-pv
 G=E/(2*(1+nu));K=E/(3*(1-2*nu));D=3*K[:,None,None]*pv+2*G[:,None,None]*pd
 ke=np.einsum('eji,ejk,ekl,e->eil',B,D,B,vol,optimize=True)
 matrix=coo_matrix((ke.ravel(),(np.repeat(dof,12,axis=1).ravel(),np.tile(dof,(1,12)).ravel())),shape=(N,N)).tocsr()
 ln=data['link_nodes'];lw=data['link_weights']
 if (folder/'input.json').exists():
  inp=json.loads((folder/'input.json').read_text(encoding='utf8'));h=inp['h_mm'];bore_radius=inp['initial_bore_diameter_mm']/2
 elif h_override is not None:h=h_override;bore_radius=20.007
 else:raise ValueError('input.json or explicit mesh h is required')
 # Use the saved interface geometry and the same area-scaled mechanics.
 bd=data['boundary'];weld_faces=bd[np.isin(bd[:,0],np.unique(e[m==2]))]
 area=np.linalg.norm(np.cross(x[weld_faces[:,1]]-x[weld_faces[:,0]],x[weld_faces[:,2]]-x[weld_faces[:,0]]),axis=1)/2
 rr=np.linalg.norm(x[weld_faces,:2],axis=2);is_cast=np.isin(ln[:,1],np.unique(e[m==1]))
 picks=[np.all(abs(rr-75)<1e-4,axis=1),np.all(abs(x[weld_faces,2]-weld_top)<1e-4,axis=1)]
 aa=[np.bincount(weld_faces.ravel(),weights=np.repeat(area*mask/3,3),minlength=len(x)) for mask in picks]
 stiffness=np.where(is_cast,75000/1.2,160000/h)*np.where(is_cast,aa[1][ln[:,0]],aa[0][ln[:,0]])
 for ax in range(3):
  ld=3*ln+ax;blocks=np.einsum('li,lj,l->lij',lw,lw,stiffness)
  matrix+=coo_matrix((blocks.ravel(),(np.repeat(ld,ln.shape[1],axis=1).ravel(),np.tile(ld,(1,ln.shape[1])).ravel())),shape=(N,N)).tocsr()
 bottom=np.flatnonzero(x[:,2]<1e-5);fixed=(3*bottom[:,None]+np.arange(3)).ravel();free=np.setdiff1d(np.arange(N),fixed)
 radius=np.linalg.norm(x[:,:2],axis=1);bn=np.flatnonzero((abs(radius-bore_radius)<1e-4)&(x[:,2]>=100)&(x[:,2]<=weld_top))
 bore_faces=bd[np.all(abs(np.linalg.norm(x[bd,:2],axis=2)-bore_radius)<1e-4,axis=1)]
 if len(bn)==0 or len(bore_faces)==0:raise ValueError('输入孔径与实际载荷孔壁网格不一致')
 bore_area=np.linalg.norm(np.cross(x[bore_faces[:,1]]-x[bore_faces[:,0]],x[bore_faces[:,2]]-x[bore_faces[:,0]]),axis=1)/2
 weight=np.bincount(bore_faces.ravel(),weights=np.repeat(bore_area/3,3),minlength=len(x))[bn]
 weight/=weight.sum()
 F=np.zeros((N,3));F[3*bn,0]=5000*weight;F[3*bn+2,1]=5000*weight
 xy=x[bn,:2]-weight@x[bn,:2]
 couple=np.c_[xy[:,1],-xy[:,0]]
 # Normalize both moment components. An irregular mesh can otherwise add
 # a small unintended y moment to the prescribed x-axis pure couple.
 coefficient=np.linalg.solve(couple.T@(weight[:,None]*couple),[250000.,0.])
 F[3*bn+2,2]=weight*(couple@coefficient)
 factor=splu(matrix[free][:,free].tocsc());U=np.zeros_like(F);U[free]=factor.solve(F[free])
 strain=np.einsum('eij,ejk->eik',B,U[dof]);s=np.einsum('eij,ejk->eik',D,strain)
 stress=np.sum(s,axis=2);vm=np.sqrt(1.5*np.sum((stress-stress@pv)**2,axis=1))
 cyc=s[:,:,0]*.1+s[:,:,1]*.04+s[:,:,2]*.1;dr=2*np.sqrt(1.5*np.sum((cyc-cyc@pv)**2,axis=1))
 c=x[e].mean(axis=1);r=np.linalg.norm(c[:,:2],axis=1)
 zones={'QT_slot_root':(m==1)&(r>35)&(r<47),'QT_body':m==1,'NiFe_weld':m==2,'Q235_shell':m==0}
 res={'mesh_h_mm':h,'initial_bore_diameter_mm':2*bore_radius,'nodes':len(x),'tetrahedra':len(e),'load_conditions':{'Fr_N':5000,'Fa_N':5000,'Mx_Nmm':250000,'continuous_amplitudes_N_N_Nmm':[500,200,25000]},
  'boundary':'cold service: shell lower rim rigidly attached to base; weld interfaces interpolated; no mandrel support',
  'pure_couple_components_normalized':True,
  'load_distribution':'area-weighted bore-wall tractions, each prescribed resultant normalized exactly; moment is a zero-resultant force couple about weighted centre; this is a design load-transfer envelope, not a measured bearing contact distribution',
  'stress_method':'linear elastic geometric notch resolution; reported peak and element-count p95; no claim of a local weld-toe singularity fatigue class',
  'elastic_yield_screen':{'safety_factor':1.5,'allowable_MPa':{'QT':310/1.5,'NiFe':290/1.5,'Q235':235/1.5},'scope':'incremental cold service stress, separate from weld residual stress; local metal yield checks do not determine PMZ brittle fracture'},
  'zones':{name:{'peak_service_VM_MPa':float(vm[z].max()),'continuous_peak_range_MPa':float(dr[z].max()),
    'p95_service_VM_MPa':float(np.quantile(vm[z],.95))} for name,z in zones.items()}}
 bp=np.flatnonzero((abs(radius-75)<1e-4)&((x[:,2]<35)|(x[:,2]>165)))
 disp=U.sum(axis=1).reshape(-1,3)
 np.savez_compressed(folder/'service-area-fields.npz',service_VM=vm,continuous_range=dr,u_combined=disp,
     service_stress_Mandel_MPa=stress,continuous_amplitude_stress_Mandel_MPa=cyc)
 res['combined_service_axis_fit']=fit_position_diameter(x[bottom]+disp[bottom],x[bp]+disp[bp],x[bn]+disp[bn])
 res['maximum_combined_displacement_mm']=float(np.linalg.norm(disp,axis=1).max())
 res['axis_fit_scope']='elastic service deflection relative to deformed shell, separate from the unloaded welding position tolerance'
 (folder/'service-area-result.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(res,ensure_ascii=False))
 from extract_interface_demand import evaluate as interface_demand
 interface_demand(folder.name)
if __name__=='__main__':
 with threadpool_limits(limits=1):run(Path(sys.argv[1]),float(sys.argv[2]) if len(sys.argv)>2 else None)
