"""Load/unload the actual cold state, retaining stress, plastic strain and ties.

This extends the existing bulk J2 model for the declared mounting condition.
The elastic Ni-side ties remain an explicit limitation; this solve cannot
certify Ni99 or the PMZ, nor may it overwrite the manufacturing free shape.
"""
from pathlib import Path
import argparse,json,time
import numpy as np
from scipy.sparse import coo_matrix,diags,triu
from threadpoolctl import threadpool_limits
from run_verified import operators
from welded_strength import recover_residual_interface,vm

OUT=Path(__file__).parent/'results'


def run(case):
    folder=OUT/case;started=time.perf_counter()
    inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    with np.load(folder/'free-release-fields.npz') as src:f={k:src[k] for k in src.files}
    with np.load(folder/'service-area-fields.npz') as src:service={k:src[k] for k in src.files}
    with np.load(folder/'interface-service-demand.npz') as src:demand={k:src[k] for k in src.files}
    x,e,m=f['x'],f['e'],f['material'];nn=len(x);nd=3*nn
    _,vol,B,dof=operators(x,e);tables=inp['materials']
    E=np.array([np.interp(20,t['temperature_dependent']['temperatures_c'],t['temperature_dependent']['elastic_modulus_gpa'])*1000 for t in tables])[m]
    Y=np.array([np.interp(20,t['temperature_dependent']['temperatures_c'],t['temperature_dependent']['yield_strength_mpa']) for t in tables])[m]
    nu=np.array([t['nominal_properties_20c']['poisson_ratio'] for t in tables])[m]
    G=E/(2*(1+nu));K=E/(3*(1-2*nu));H=.005*E
    pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3;pd=np.eye(6)-pv
    elastic=3*K[:,None,None]*pv+2*G[:,None,None]*pd
    def body(stress):
        fi=np.einsum('eji,ej,e->ei',B,stress,vol)
        return np.bincount(dof.ravel(),weights=fi.ravel(),minlength=nd)
    nodes,weights=f['link_nodes'],f['link_weights']
    L=coo_matrix((weights.ravel(),(np.repeat(np.arange(len(nodes)),nodes.shape[1]),nodes.ravel())),shape=(len(nodes),nn)).tocsr()
    residual_force,recovery=recover_residual_interface(f,folder)
    density=np.where(demand['is_QT_interface'],75000/1.2,160000/inp['h_mm'])
    stiffness=density*demand['area_mm2'];scalar=(L.T@diags(stiffness)@L).tocoo()
    tie=coo_matrix((np.tile(scalar.data,3),(np.concatenate([3*scalar.row+a for a in range(3)]),
        np.concatenate([3*scalar.col+a for a in range(3)]))),shape=(nd,nd)).tocsr()
    # Reconstruct exactly the service load from its saved linear stress and
    # spring force. This avoids a second, subtly different traction protocol.
    linear_u=service['u_combined'].ravel()
    external=body(service['service_stress_Mandel_MPa'])+tie@linear_u
    bottom=np.flatnonzero(x[:,2]<1e-5);fixed=(3*bottom[:,None]+np.arange(3)).ravel()
    free=np.setdiff1d(np.arange(nd),fixed)
    initial=body(f['stress'])
    for axis in range(3):initial.reshape(nn,3)[:,axis]+=L.T@residual_force[:,axis]
    rr=np.repeat(dof,12,axis=1).ravel();cc=np.tile(dof,(1,12)).ravel()
    import pypardiso
    solver=pypardiso.PyPardisoSolver(mtype=2)
    stress=f['stress'].copy();eqp=f['eqp'].copy();plastic=f['plastic'].copy()
    u=np.zeros(nd);current_force=residual_force.copy();history=[];loaded={}
    for load in np.r_[np.linspace(.1,1.5,15),np.linspace(1.4,0,15)]:
        old_stress=stress.copy();old_eqp=eqp.copy();delta=np.zeros(nd)
        base=body(old_stress)
        for axis in range(3):base.reshape(nn,3)[:,axis]+=L.T@current_force[:,axis]
        def assemble(value,tangent=True):
            strain=np.einsum('eij,ej->ei',B,value[dof])
            trial=old_stress+np.einsum('eij,ej->ei',elastic,strain)
            deviator=trial-trial@pv;q=vm(trial)
            dl=np.maximum(0,(q-Y-H*old_eqp)/(3*G+H))
            direction=1.5*deviator/np.maximum(q[:,None],1e-20)
            beta=1-3*G*dl/np.maximum(q,1e-20)
            s=trial@pv+deviator*beta[:,None]
            force=base+body(s-old_stress)+tie@value-load*external
            matrix=None
            if tangent:
                D=3*K[:,None,None]*pv+2*G[:,None,None]*beta[:,None,None]*pd
                correction=1/(3*G+H)-dl/np.maximum(q,1e-20)
                D-=np.where(dl>0,4*G*G*correction,0)[:,None,None]*direction[:,:,None]*direction[:,None,:]
                ke=np.einsum('eji,ejk,ekl,e->eil',B,D,B,vol,optimize=True)
                matrix=coo_matrix((ke.ravel(),(rr,cc)),shape=(nd,nd)).tocsr()+tie
            return force,matrix,s,dl,direction
        for iteration in range(40):
            force,matrix,stress,dl,direction=assemble(delta)
            residual=float(np.linalg.norm(force[free]))
            if residual<.001:break
            matrix=matrix[free][:,free].tocsr()
            answer=pypardiso.spsolve(triu(matrix,format='csr'),-force[free],solver=solver)
            if np.linalg.norm(matrix@answer+force[free])>.001:raise RuntimeError('service linear solve residual')
            for power in range(12):
                candidate=delta.copy();candidate[free]+=answer*.5**power
                if np.linalg.norm(assemble(candidate,False)[0][free])<residual:delta=candidate;break
            else:raise RuntimeError('stateful service line search stagnated')
        else:raise RuntimeError('stateful service Newton did not converge')
        u+=delta;eqp=old_eqp+dl;plastic+=dl[:,None]*direction
        current_force+=stiffness[:,None]*(L@delta.reshape(nn,3))
        history.append(dict(load_factor=float(load),iterations=iteration+1,residual_N=residual,
            maximum_added_eqp=float((eqp-f['eqp']).max()),maximum_displacement_mm=float(np.linalg.norm(u.reshape(nn,3),axis=1).max())))
        print(case,'service load',round(load,2),'iterations',iteration+1,'residual',residual,flush=True)
        if abs(load-1.5)<1e-8:
            loaded=dict(stress=stress.copy(),eqp=eqp.copy(),plastic=plastic.copy(),u=u.copy(),interface_force=current_force.copy())
    np.savez_compressed(folder/'stateful-service-fields.npz',
        loaded_stress_Mandel_MPa=loaded['stress'],loaded_eqp=loaded['eqp'],loaded_plastic=loaded['plastic'],
        loaded_u_increment_mm=loaded['u'].reshape(nn,3),loaded_interface_force_N=loaded['interface_force'],
        unloaded_stress_Mandel_MPa=stress,unloaded_eqp=eqp,unloaded_u_increment_mm=u.reshape(nn,3))
    result=dict(case=case,input_snapshot=inp,load_factor=1.5,history=history,
        bulk_material_model='same cold J2 isotropic hardening H=0.005E as manufacturing solve; retained eqp and plastic tensor',
        mounting='clamp actual deformed lower rim; zero incremental motion at mount; free manufacturing shape is not reset',
        maximum_added_eqp=float((eqp-f['eqp']).max()),interface_force_recovery_residual_N=recovery,
        equilibrium_design_pass=max(h['residual_N'] for h in history)<.001,
        elapsed_s=time.perf_counter()-started,
        scope='bulk load/unload response on inherited state; original elastic ties do not certify Ni99/PMZ capacity')
    (folder/'stateful-service-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',required=True)
    with threadpool_limits(limits=1):
        result=run(p.parse_args().case)
    print(json.dumps({k:v for k,v in result.items() if k not in ('input_snapshot','history')},ensure_ascii=False,indent=2))
