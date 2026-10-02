"""Cold service stresses on the full assembly, separate from welding residual stress."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import splu
from threadpoolctl import threadpool_limits
from run_full_part import mesh,operators
ROOT=Path(__file__).resolve().parents[2]
def run(folder):
 data=np.load(folder/'fields.npz');x=data['x'];e=data['e'];m=data['material'];_,_,_,_,links=mesh(8,2.)
 g,vol,B,dof=operators(x,e);N=3*len(x)
 E=np.array([210000,170000,160000])[m];nu=np.array([.28,.27,.3])[m]
 pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3;pd=np.eye(6)-pv
 G=E/(2*(1+nu));K=E/(3*(1-2*nu));D=3*K[:,None,None]*pv+2*G[:,None,None]*pd
 ke=np.einsum('eji,ejk,ekl,e->eil',B,D,B,vol,optimize=True)
 matrix=coo_matrix((ke.ravel(),(np.repeat(dof,12,axis=1).ravel(),np.tile(dof,(1,12)).ravel())),shape=(N,N)).tocsr()
 ln=np.array([[a,*b] for a,b,c in links]);lw=np.array([[1,*[-d for d in c]] for a,b,c in links])
 for ax in range(3):
  ld=3*ln+ax;blocks=1e6*np.einsum('li,lj->lij',lw,lw)
  matrix+=coo_matrix((blocks.ravel(),(np.repeat(ld,5,axis=1).ravel(),np.tile(ld,(1,5)).ravel())),shape=(N,N)).tocsr()
 bottom=np.flatnonzero(x[:,2]<1e-5);fixed=(3*bottom[:,None]+np.arange(3)).ravel();free=np.setdiff1d(np.arange(N),fixed)
 radius=np.linalg.norm(x[:,:2],axis=1);bn=np.flatnonzero((abs(radius-20)<1e-4)&(x[:,2]>=100)&(x[:,2]<=112))
 F=np.zeros((N,3));F[3*bn,0]=5000/len(bn);F[3*bn+2,1]=5000/len(bn)
 yy=x[bn,1]-x[bn,1].mean();F[3*bn+2,2]=250000*yy/np.dot(yy,yy)
 factor=splu(matrix[free][:,free].tocsc());U=np.zeros_like(F);U[free]=factor.solve(F[free])
 strain=np.einsum('eij,ejk->eik',B,U[dof]);s=np.einsum('eij,ejk->eik',D,strain)
 stress=np.sum(s,axis=2);vm=np.sqrt(1.5*np.sum((stress-stress@pv)**2,axis=1))
 cyc=s[:,:,0]*.1+s[:,:,1]*.04+s[:,:,2]*.1;dr=2*np.sqrt(1.5*np.sum((cyc-cyc@pv)**2,axis=1))
 c=x[e].mean(axis=1);r=np.linalg.norm(c[:,:2],axis=1)
 zones={'QT_slot_root':(m==1)&(r>35)&(r<47),'QT_body':m==1,'NiFe_weld':m==2,'Q235_shell':m==0}
 res={'load_conditions':{'Fr_N':5000,'Fa_N':5000,'Mx_Nmm':250000,'continuous_amplitudes_N_N_Nmm':[500,200,25000]},
  'boundary':'cold service: shell lower rim rigidly attached to base; weld interfaces interpolated; no mandrel support',
  'stress_method':'linear elastic geometric notch resolution; reported peak and volume weighted p95; no claim of a local weld-toe singularity fatigue class',
  'zones':{name:{'peak_service_VM_MPa':float(vm[z].max()),'continuous_peak_range_MPa':float(dr[z].max()),
    'p95_service_VM_MPa':float(np.quantile(vm[z],.95))} for name,z in zones.items()}}
 np.savez_compressed(folder/'service-fields.npz',service_VM=vm,continuous_range=dr)
 (folder/'service-result.json').write_text(json.dumps(res,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(res,ensure_ascii=False))
if __name__=='__main__':
 with threadpool_limits(limits=1):run(Path(sys.argv[1]))
