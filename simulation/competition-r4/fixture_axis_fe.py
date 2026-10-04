"""Static solid FE of the fixed reverse cone/column, independent of weld FE.

The lower column, guide body and solid cone are one machined steel part.
There is no press-fit or guide locking interface. E180 GPa throughout is a
lower bound including the steel column. No physical fixture measurements.
"""
from pathlib import Path
import argparse,json,math
import numpy as np
import gmsh,pypardiso
from scipy.sparse import coo_matrix,triu
from scipy.interpolate import LinearNDInterpolator
from threadpoolctl import threadpool_limits
from run_verified import operators
OUT=Path(__file__).parent/'results'
def solve(h):
 gmsh.initialize()
 try:
  gmsh.option.setNumber('General.Terminal',0);gmsh.model.add('fixed-core-axis')
  o=gmsh.model.occ
  shapes=[(3,o.addCylinder(0,0,-20,0,0,100,72)),(3,o.addCylinder(0,0,80,0,0,14,36)),
          (3,o.addCylinder(0,0,59.8,0,0,40,30)),
          (3,o.addCone(0,0,99.8,0,0,15.4,19.1449047,16.4294692))]
  solid,_=o.fuse([shapes[0]],shapes[1:]);o.synchronize()
  gmsh.option.setNumber('Mesh.MeshSizeMin',h/4);gmsh.option.setNumber('Mesh.MeshSizeMax',h*4)
  field=gmsh.model.mesh.field.add('Box');gmsh.model.mesh.field.setNumber(field,'VIn',h)
  gmsh.model.mesh.field.setNumber(field,'VOut',h*4)
  for key,val in [('XMin',-38),('XMax',38),('YMin',-38),('YMax',38),('ZMin',55),('ZMax',116),('Thickness',5)]:gmsh.model.mesh.field.setNumber(field,key,val)
  gmsh.model.mesh.field.setAsBackgroundMesh(field);gmsh.model.mesh.generate(3)
  tags,coords,_=gmsh.model.mesh.getNodes();x=coords.reshape(-1,3);mapping=np.full(tags.max()+1,-1,int);mapping[tags]=np.arange(len(x))
  _,_,blocks=gmsh.model.mesh.getElements(3);e=mapping[blocks[0].reshape(-1,4)]
 finally:gmsh.finalize()
 _,vol,b,dof=operators(x,e);nn=len(x);nd=3*nn
 E=180000;nu=.3;G=E/2/(1+nu);K=E/3/(1-2*nu)
 pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3;D=3*K*pv+2*G*(np.eye(6)-pv)
 ke=np.einsum('eji,jk,ekl,e->eil',b,D,b,vol,optimize=True)
 rr=np.repeat(dof,12,axis=1).ravel();cc=np.tile(dof,(1,12)).ravel()
 A=coo_matrix((ke.ravel(),(rr,cc)),shape=(nd,nd)).tocsr()
 faces=np.sort(np.vstack([e[:,[0,1,2]],e[:,[0,1,3]],e[:,[0,2,3]],e[:,[1,2,3]]]),axis=1)
 uf,cnt=np.unique(faces,axis=0,return_counts=True);bd=uf[cnt==1];centres=x[bd].mean(axis=1)
 area=np.linalg.norm(np.cross(x[bd[:,1]]-x[bd[:,0]],x[bd[:,2]]-x[bd[:,0]]),axis=1)/2
 force=np.zeros(nd)
 top=np.all(abs(x[bd,2]-115.2)<1e-5,axis=1)
 topweights=np.bincount(bd[top].ravel(),weights=np.repeat(area[top]/3,3),minlength=nn)
 force[0::3]+=5000*topweights/topweights.sum()
 disk=np.all(abs(x[bd,2]-94)<1e-5,axis=1)
 dw=np.bincount(bd[disk].ravel(),weights=np.repeat(area[disk]/3,3),minlength=nn)
 # Independent adverse bounds: 170 kN mm pad moment, full two-peener moment,
 # plus400 N lateral peening resultant. No cancellation credited.
 moment=170000+2*200*math.hypot(75,138)
 weights=dw*x[:,0];weights-=dw*weights.sum()/dw.sum()
 force[2::3]+=moment*weights/(weights@x[:,0]);force[0::3]+=400*dw/dw.sum()
 fixed=np.flatnonzero(np.repeat(abs(x[:,2]+20)<1e-5,3));free=np.setdiff1d(np.arange(nd),fixed)
 solver=pypardiso.PyPardisoSolver(mtype=2);u=np.zeros(nd)
 with threadpool_limits(limits=2):u[free]=pypardiso.spsolve(triu(A[free][:,free],format='csr'),force[free],solver=solver)
 residual=float(np.linalg.norm((A@u-force)[free]))
 disp=u.reshape(-1,3);r=np.linalg.norm(x[:,:2],axis=1)
 nominal=19.1449047-(x[:,2]-99.8)*math.tan(math.radians(10))
 mask=(abs(r-nominal)<1e-5)&(x[:,2]>=99.8-1e-5)&(x[:,2]<=115.2+1e-5)
 theta=np.arctan2(x[mask,1],x[mask,0]);coords=np.c_[theta,x[mask,2]];vals=disp[mask]
 interp=LinearNDInterpolator(np.vstack((coords-[2*np.pi,0],coords,coords+[2*np.pi,0])),np.vstack((vals,vals,vals)))
 z=np.repeat([100.2,107.5,114.8],24);tt=np.tile(np.arange(24)*2*np.pi/24,3)
 section=interp(np.c_[tt,z]).reshape(3,24,3)
 if not np.all(np.isfinite(section)):raise RuntimeError('axis samples outside bore surface')
 shifts=section[:,:,:2].mean(axis=1)
 stress=np.einsum('ij,ej->ei',D,np.einsum('eij,ej->ei',b,u[dof]));vm=np.sqrt(1.5*np.sum((stress-stress@pv)**2,axis=1))
 result=dict(h_local_mm=h,nodes=nn,tetrahedra=len(e),lateral_core_load_N=5000,
  adverse_pad_and_peening_moment_N_mm=moment,lateral_peening_force_N=400,
  axis_section_centres_mm=shifts.tolist(),maximum_radial_axis_shift_mm=float(np.linalg.norm(shifts,axis=1).max()),
  linear_equilibrium_residual_N=residual,max_von_mises_MPa=float(vm.max()),
  scope='integral solid reverse cone, fixed column root; flange/bolts and microscopic contact added separately; E180 GPa')
 folder=OUT/f'fixture-axis-solid-core-h{h:g}';folder.mkdir(parents=True,exist_ok=True)
 np.savez_compressed(folder/'fields.npz',x=x,e=e,u=disp,stress=stress)
 (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--h',type=float,required=True);solve(p.parse_args().h)
