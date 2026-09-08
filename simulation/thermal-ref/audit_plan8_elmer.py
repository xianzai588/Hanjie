"""离线重装配FE材料反力与两侧梯度热流；不参与Elmer求解。"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from scipy.special import erf
from threadpoolctl import threadpool_limits

import elmer_reference as ref
from assess_reference import read, nonlinear_check
from run_plan7 import heat, materials
from run_plan8 import RESULTS


def shapes(points):
    signs=2*ref.CORNERS-1
    factors=(1+points[:,None,:]*signs[None,:,:])/2
    values=factors.prod(axis=2)
    gradients=np.stack([signs[None,:,d]/2*np.prod(factors[:,:,np.arange(3)!=d],axis=2) for d in range(3)],axis=2)
    return values,gradients


def longitudinal(lo,hi,center,source):
    lo,hi=lo-center,hi-center
    af,ar,ff,fr=[source[k] for k in ("a_front_mm","a_rear_mm","front_fraction","rear_fraction")]
    return (fr*ar*(erf(np.sqrt(3)*np.minimum(hi,0)/ar)-erf(np.sqrt(3)*np.minimum(lo,0)/ar))+
            ff*af*(erf(np.sqrt(3)*np.maximum(hi,0)/af)-erf(np.sqrt(3)*np.maximum(lo,0)/af)))/(ff*af+fr*ar)


class FEAudit:
    def __init__(self,out):
        self.out=out; self.record=read(out/"run-inputs.json")
        self.config=self.record["config"]; spec=self.record["specification"]
        self.g=ref.geometry(self.config,ref.load(ref.ROOT/spec["process_input"]),self.record["mesh"])
        self.b,self.bnodes=ref.boundaries(self.g,self.config); self.bnodes-=1
        self.conn=self.g["conn"]-1; self.ids=self.g["ids"]; self.nn=len(self.g["nodes"])
        self.mats=materials(); self.constant=self.record["constant_properties"]
        if self.constant:
            for m in self.mats:
                m["cp"]=np.full_like(m["cp"],np.interp(150.,m["knots"],m["cp"]))
                m["k"]=np.full_like(m["k"],np.interp(150.,m["knots"],m["k"])); m["latent"]=0.
        self.dt=spec["solver"]["time_step_s"]
        self.N,self.D=shapes(np.array([[a,b,c] for a in (-1.,1.) for b in (-1.,1.) for c in (-1.,1.)])/np.sqrt(3.))
        self.face_mass=np.array([[4,2,1,2],[2,4,2,1],[1,2,4,2],[2,1,2,4]])/36
        support=np.zeros((3,self.nn),bool)
        for m in (1,2,3):
            support[m-1,np.unique(self.conn[self.ids==m])]=True
        if np.any(support.sum(axis=0)>2):
            raise ValueError("三材料共节点反力无法唯一拆成二体交换，必须显式处理")
        self.interfaces={m:support[m-1]&support[2] for m in (1,2)}
        self.support=support
        self.faces=[]
        for e in np.flatnonzero(self.ids==3):
            idx=self.g["index"][e]
            for axis in range(3):
                for sign in (-1,1):
                    neighbour=idx.copy(); neighbour[axis]+=sign
                    if np.any(neighbour<0) or np.any(neighbour>=self.g["lattice"].shape):
                        continue
                    p=self.g["lattice"][tuple(neighbour)]
                    if p>=0 and self.ids[p] in (1,2):
                        self.faces.append([e,p,axis,sign,self.ids[p]])
        self.faces=np.asarray(self.faces,int)

    def fill(self,t):
        if self.constant:
            return np.ones(len(self.ids))
        path=self.config["heat_source_path"]; speed=self.config["process"]["travel_speed_mm_s"]
        left=self.g["nodes"][self.conn[:,0],0]
        value=np.clip((min(path["source_end_s_mm"],path["source_start_s_mm"]+speed*t)-left)/self.g["dims"][:,0],0,1)
        value[value<1.e-10]=0.; value[value>1-1.e-10]=1.
        return np.where(self.ids==3,value,1.)

    def source_loss(self,t,old,rawfill):
        b=self.b; owner=b[:,0].astype(int)-1; neighbour=b[:,1].astype(int)-1
        other=np.where(neighbour>=0,rawfill[np.maximum(neighbour,0)],0.)
        exposure=np.where(b[:,2]==1,((rawfill[owner]>0)&(other<=0)).astype(float),np.maximum(rawfill[owner]-other,0))*b[:,5]
        p=self.config["process"]; path=self.config["heat_source_path"]; src=self.config["heat_source"]
        center=path["source_start_s_mm"]+p["travel_speed_mm_s"]*(t-self.dt/2)
        left=self.g["nodes"][self.conn[owner,0],0]; right=left+self.g["dims"][owner,0]
        lo=np.maximum(left,path["source_start_s_mm"])
        hi=np.maximum(lo,np.minimum(right,path["source_end_s_mm"] if self.constant else min(center,path["source_end_s_mm"])))
        whole=longitudinal(left,right,center,src); deposited=longitudinal(lo,hi,center,src)
        power=p["net_power_w"]*((whole-deposited)*b[:,6]+deposited*b[:,7])
        if t-self.dt>=(path["source_end_s_mm"]-path["source_start_s_mm"])/p["travel_speed_mm_s"]-1.e-10:
            power*=0.
        temp=old[self.bnodes]; ambient=p["cooling_environment_c"]
        flux=exposure[:,None]*(p["convection_coefficient_w_m2k"]*(temp-ambient)/1.e6+
                              p["emissivity"]*5.670374419e-14*((temp+273.15)**4-(ambient+273.15)**4))
        nodal=self.dt*(power[:,None]/4-b[:,4,None]*(flux@self.face_mass))
        source=np.bincount(self.ids[owner],weights=power*self.dt,minlength=4)[1:4]
        loss=np.bincount(self.ids[owner],weights=flux.mean(axis=1)*b[:,4]*self.dt,minlength=4)[1:4]
        return nodal,source,loss

    def gradient_flows(self,new,knodal,fill):
        result=np.zeros((2,2))
        for axis in range(3):
            for sign in (-1,1):
                rows=self.faces[(self.faces[:,2]==axis)&(self.faces[:,3]==sign)]
                if not len(rows):
                    continue
                points=np.zeros((4,3)); points[:,axis]=sign
                points[:,np.arange(3)!=axis]=np.array([[a,b] for a in (-1.,1.) for b in (-1.,1.)])/np.sqrt(3.)
                for side in (0,1):
                    points[:,axis]=sign if side==0 else -sign
                    N,D=shapes(points); e=rows[:,side]
                    gradient=new[self.conn[e]]@D[:,:,axis].T*2/self.g["dims"][e,axis,None]
                    k=knodal[e]@N.T*fill[e,None]
                    area=self.g["volume"][rows[:,0]]/self.g["dims"][rows[:,0],axis]
                    flux=-sign*np.mean(k*gradient,axis=1)*area*self.dt
                    for index,parent in enumerate((2,1)):
                        result[index,side]+=flux[rows[:,4]==parent].sum()
        return result.ravel()

    def step(self,t,old,new):
        raw=self.fill(t); fill=np.maximum(1.e-8,raw); prior=np.maximum(1.e-8,self.fill(t-self.dt))
        delta=new[self.conn]-old[self.conn]; residual=np.zeros((3,self.nn))
        knodal=np.zeros_like(delta); H=np.zeros(3); mix=np.zeros(3); born=np.zeros(3)
        for index,m in enumerate(self.mats):
            selected=self.ids==index+1; conn=self.conn[selected]
            oldh,newh=heat(old[conn],m),heat(new[conn],m)
            mid=(old[conn]+new[conn])/2
            cp=np.interp(mid,m["knots"],m["cp"])+m["latent"]/(m["tl"]-m["ts"])*((mid>=m["ts"])&(mid<m["tl"]))
            np.divide(newh-oldh,delta[selected],out=cp,where=np.abs(delta[selected])>1.e-7)
            k=np.interp(old[conn],m["knots"],m["k"]); knodal[selected]=k
            capq=cp@self.N.T
            diagonal=capq@(self.N**2)/8
            diagonal*= (capq.mean(axis=1)/diagonal.sum(axis=1))[:,None]
            weight=m["rho"]*self.g["volume"][selected]*fill[selected]
            mass_force=weight[:,None]*diagonal*delta[selected]
            mix[index]=np.sum(mass_force-weight[:,None]*(newh-oldh)/8)
            H[index]=np.sum(weight[:,None]*newh/8)
            born[index]=np.sum(m["rho"]*self.g["volume"][selected]*(fill[selected]-prior[selected])*heat(20.,m))
            invdims=2/self.g["dims"][selected]
            gradient=np.einsum("en,qnd->eqd",new[conn],self.D)*invdims[:,None,:]
            force=self.dt*self.g["volume"][selected,None]/8*np.einsum("eq,eqd,qnd->en",(k@self.N.T)*fill[selected,None],gradient*invdims[:,None,:],self.D)
            birth_force=m["rho"]*self.g["volume"][selected,None]*(fill[selected]-prior[selected])[:,None]*(heat(20.,m)-oldh)/8
            np.add.at(residual[index],conn.ravel(),(mass_force+force-birth_force).ravel())
        boundary,source,loss=self.source_loss(t,old,raw)
        for index in range(3):
            selected=self.ids[self.b[:,0].astype(int)-1]==index+1
            np.add.at(residual[index],self.bnodes[selected].ravel(),-boundary[selected].ravel())
        q=[float(residual[p-1,self.interfaces[p]].sum()) for p in (2,1)]
        imbalance=[float(np.sum(residual[p-1,self.interfaces[p]]+residual[2,self.interfaces[p]])) for p in (2,1)]
        pure=[float(residual[i,self.support[i]&(self.support.sum(axis=0)==1)].sum()) for i in range(3)]
        gradient=self.gradient_flows(new,knodal,fill)
        return [t,*H,*source,*loss,*born,*q,*mix], [t,*imbalance,*pure,*gradient], raw


def audit(out):
    engine=FEAudit(out); record=engine.record; dt=engine.dt; offset=record["restart_time_s"]
    rows=[]; checks=[]; fields=[]; fractions=[]; times=[]
    old=np.loadtxt(out/f"field-{round((18.-dt-offset)/dt):05d}.dat")[:,0]
    for step in range(round((18.-offset)/dt),round((26.-offset)/dt)+1):
        t=offset+step*dt; new=np.loadtxt(out/f"field-{step:05d}.dat")[:,0]
        row,check,fraction=engine.step(t,old,new)
        if not rows:
            row[4:]=[0.]*(len(row)-4); check[1:]=[0.]*(len(check)-1)
        rows.append(row); checks.append(check); fields.append(new); fractions.append(fraction); times.append(t); old=new
    header="time_s,H_q235_j,H_qt_j,H_weld_j,source_q235_j,source_qt_j,source_weld_j,loss_q235_j,loss_qt_j,loss_weld_j,birth_q235_j,birth_qt_j,birth_weld_j,weld_to_qt_j,weld_to_q235_j,mix_q235_j,mix_qt_j,mix_weld_j"
    np.savetxt(out/"partition.csv",rows,delimiter=",",comments="",header=header,fmt="%.15g")
    np.savetxt(out/"interface-audit.csv",checks,delimiter=",",comments="",header="time_s,qt_pair_residual_j,q235_pair_residual_j,q235_interior_residual_j,qt_interior_residual_j,weld_interior_residual_j,qt_weld_side_gradient_j,qt_parent_side_gradient_j,q235_weld_side_gradient_j,q235_parent_side_gradient_j",fmt="%.15g")
    np.savez_compressed(out/"window-fields.npz",times=times,temperature=fields,fraction=fractions)
    checks=np.array(checks)
    sensors=np.loadtxt(out/"sensors.dat")
    result=dict(complete=read(out/"execution.json")["returncode"]==0 and len(sensors)==record["local_steps"],
                nonlinear_convergence=nonlinear_check((out/"solver.log").read_text(encoding="utf-8"),1.e-8,record["local_steps"]),
                maximum_interface_pair_residual_j=float(np.max(np.abs(checks[:,1:3]))),
                maximum_interior_residual_j=float(np.max(np.abs(checks[:,3:6]))),
                interface_definition="Sum of independently assembled material nodal reactions on shared interface nodes; includes shared-node load/storage partition. Face-gradient estimates are reported separately and are not conservative numerical fluxes.")
    if not record["constant_properties"]:
        original=np.loadtxt(ref.HERE/"results/REF-C/sensors.dat")
        result["replay_temperature_difference_c"]=float(max(np.max(abs(sensors[:,j]-np.interp(sensors[:,0],original[:,0],original[:,j]))) for j in range(1,6)))
    ref.write_json(out/"partition-assessment.json",result)
    print(out.name,result,flush=True)
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("mode",choices=["dynamic","constant"])
    parser.add_argument("--output-dir",type=Path)
    args=parser.parse_args()
    with threadpool_limits(limits=1):
        audit(args.output_dir or RESULTS/f"elmer-{args.mode}")
