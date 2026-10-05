"""Release the remaining shell datum clamp at the actual cold measurement state.

The weld history is retained. Reconstruct interface force resultants from the
saved equilibrated stress, then perform an incremental J2 equilibrium solve.
Only six rigid-body coordinate gauges remain; no bottom-face shape is prescribed.
"""
from pathlib import Path
import argparse, json, time
import numpy as np
from scipy.sparse import coo_matrix, diags, triu
from scipy.sparse.linalg import lsmr
from threadpoolctl import threadpool_limits
from run_verified import operators


def release(folder, threads=1):
    started=time.perf_counter()
    inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    result=json.loads((folder/'result.json').read_text(encoding='utf8'))
    if not result['released'] or result['final_max_C']>20.5:
        raise ValueError('completed cold, released seat state required')
    with np.load(folder/'fields.npz') as src:
        fields={key:src[key] for key in src.files}
    x,e,m,bd=fields['x'],fields['e'],fields['material'],fields['boundary']
    nn=len(x);nd=3*nn
    _,vol,b,dof=operators(x,e)
    old_stress=fields['stress'];old_eqp=fields['eqp']
    te=fields['temperature'][e].mean(axis=1)
    tables=inp['materials']
    def prop(key):
        values=np.empty(len(e))
        for j,table in enumerate(tables):
            tab=table['temperature_dependent']
            values[m==j]=np.interp(te[m==j],tab['temperatures_c'],tab[key])
        return values
    E=1000*prop('elastic_modulus_gpa');Y=prop('yield_strength_mpa');H=.005*E
    nu=np.array([t['nominal_properties_20c']['poisson_ratio'] for t in tables])[m]
    G=E/(2*(1+nu));K=E/(3*(1-2*nu))
    pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3;pd=np.eye(6)-pv
    elastic=3*K[:,None,None]*pv+2*G[:,None,None]*pd
    def body_force(stress):
        fi=np.einsum('eji,ej,e->ei',b,stress,vol)
        return np.bincount(dof.ravel(),weights=fi.ravel(),minlength=nd)
    fint=body_force(old_stress)
    bottom=np.flatnonzero(x[:,2]<1e-5)
    anchors=[int(bottom[np.argmin(np.linalg.norm(x[bottom,:2]-[77.5*np.cos(a),77.5*np.sin(a)],axis=1))]) for a in (0,2*np.pi/3,4*np.pi/3)]
    old_fixed=np.r_[3*bottom+2,3*anchors[0],3*anchors[0]+1,3*anchors[1]+1]
    gauge=np.array(sorted([3*k+2 for k in anchors]+[3*anchors[0],3*anchors[0]+1,3*anchors[1]+1]))
    old_free=np.setdiff1d(np.arange(nd),old_fixed);free=np.setdiff1d(np.arange(nd),gauge)
    ln,lw=fields['link_nodes'],fields['link_weights']
    L=coo_matrix((lw.ravel(),(np.repeat(np.arange(len(ln)),ln.shape[1]),ln.ravel())),shape=(len(ln),nn)).tocsr()
    # A corner slave can have two interface rows. Recover all link resultants
    # together; assigning its entire force to each row would double-count it.
    initial=fint.copy();link_force=np.empty((len(ln),3));recovery=[]
    for axis in range(3):
        nodes=old_free[old_free%3==axis]//3
        A=L[:,nodes].T.tocsr();rhs=-fint.reshape(nn,3)[nodes,axis]
        answer=lsmr(A,rhs,atol=1e-13,btol=1e-13,maxiter=8000)
        link_force[:,axis]=answer[0]
        initial.reshape(nn,3)[:,axis]+=L.T@answer[0]
        recovery.append(dict(axis=axis,iterations=int(answer[2]),residual_N=float(np.linalg.norm(A@answer[0]-rhs))))
    initial_residual=float(np.linalg.norm(initial[old_free]))
    if initial_residual>.050001:
        raise RuntimeError(f'saved-state equilibrium recovery failed: {initial_residual} N')
    weld_nodes=np.unique(e[m==2]);weld_faces=bd[np.isin(bd[:,0],weld_nodes)]
    area=np.linalg.norm(np.cross(x[weld_faces[:,1]]-x[weld_faces[:,0]],x[weld_faces[:,2]]-x[weld_faces[:,0]]),axis=1)/2
    wr=np.linalg.norm(x[weld_faces,:2],axis=2);weld_top=float(x[weld_nodes,2].min())
    faces=[np.all(abs(wr-75)<1e-4,axis=1),np.all(abs(x[weld_faces,2]-weld_top)<1e-4,axis=1)]
    tributary=[np.bincount(weld_faces.ravel(),weights=np.repeat(area*pick/3,3),minlength=nn) for pick in faces]
    cast=np.isin(ln[:,1],np.unique(e[m==1]))
    h=result['h_mm'];density=np.where(cast,75000/1.2,160000/h)
    link_area=np.where(cast,tributary[1][ln[:,0]],tributary[0][ln[:,0]])
    if np.any(link_area<=0):raise RuntimeError('missing original interface tributary area')
    scalar=(L.T@diags(density*link_area)@L).tocoo()
    tie=coo_matrix((np.tile(scalar.data,3),
        (np.concatenate([3*scalar.row+a for a in range(3)]),
         np.concatenate([3*scalar.col+a for a in range(3)]))),shape=(nd,nd)).tocsr()
    srr=np.repeat(dof,12,axis=1).ravel();scc=np.tile(dof,(1,12)).ravel()
    import pypardiso
    solver=pypardiso.PyPardisoSolver(mtype=2)
    def direct(matrix,rhs):
        skew=matrix-matrix.T
        if skew.nnz and abs(skew.data).max()>1e-7*abs(matrix.data).max():
            raise RuntimeError('release tangent is not symmetric')
        answer=pypardiso.spsolve(triu(matrix,format='csr'),rhs,solver=solver)
        if np.linalg.norm(matrix@answer-rhs)>.001:raise RuntimeError('release linear residual failed')
        return answer
    def assemble(delta,tangent=True):
        strain=np.einsum('eij,ej->ei',b,delta[dof])
        trial=old_stress+np.einsum('eij,ej->ei',elastic,strain)
        s=trial-trial@pv;q=np.sqrt(1.5*np.sum(s*s,axis=1))
        dl=np.maximum(0,(q-Y-H*old_eqp)/(3*G+H))
        direction=1.5*s/np.maximum(q[:,None],1e-20)
        beta=1-3*G*dl/np.maximum(q,1e-20)
        stress=trial@pv+s*beta[:,None]
        force=initial+body_force(stress-old_stress)+tie@delta
        matrix=None
        if tangent:
            D=3*K[:,None,None]*pv+2*G[:,None,None]*beta[:,None,None]*pd
            corr=1/(3*G+H)-dl/np.maximum(q,1e-20)
            D-=np.where(dl>0,4*G*G*corr,0)[:,None,None]*direction[:,:,None]*direction[:,None,:]
            ke=np.einsum('eji,ejk,ekl,e->eil',b,D,b,vol,optimize=True)
            matrix=coo_matrix((ke.ravel(),(srr,scc)),shape=(nd,nd)).tocsr()+tie
        return force,matrix,stress,dl,direction
    delta=np.zeros(nd);history=[]
    with threadpool_limits(limits=threads):
        for iteration in range(35):
            force,matrix,stress,dl,direction=assemble(delta)
            residual=float(np.linalg.norm(force[free]));history.append(residual)
            print('cold shell release',folder.name,iteration,residual,flush=True)
            if residual<.001:break
            increment=direct(matrix[free][:,free].tocsr(),-force[free])
            for power in range(10):
                candidate=delta.copy();candidate[free]+=increment*.5**power
                if np.linalg.norm(assemble(candidate,False)[0][free])<residual:
                    delta=candidate;break
            else:raise RuntimeError('cold release Newton stagnation')
        else:raise RuntimeError('cold release Newton failed')
    audit=dict(source_fields='fields.npz',source_temperature_max_C=float(fields['temperature'].max()),
        scope='shell annular axial datum clamp retained during ambient cooling, removed before CMM; six coordinate gauges only',
        original_bottom_axially_fixed_nodes=len(bottom),remaining_gauge_dofs=gauge.tolist(),gauge_nodes=anchors,
        recovered_interface_equilibrium_residual_N=initial_residual,link_force_recovery=recovery,
        release_equilibrium_residual_N=residual,release_iterations=len(history),residual_history_N=history,
        maximum_incremental_displacement_mm=float(np.linalg.norm(delta.reshape(nn,3),axis=1).max()),
        maximum_incremental_equivalent_plastic_strain=float(dl.max()),
        bottom_face_displacement_range_mm=np.ptp((fields['u']+delta.reshape(nn,3))[bottom,2]).item(),
        retained_gauge_reaction_norm_N=float(np.linalg.norm(force[gauge])),
        elapsed_s=time.perf_counter()-started,
        free_shell_release_pass=bool(residual<.001 and initial_residual<=.050001 and np.linalg.norm(force[gauge])<.1))
    fields['u']=fields['u']+delta.reshape(nn,3);fields['stress']=stress
    fields['plastic']=fields['plastic']+dl[:,None]*direction;fields['eqp']=old_eqp+dl
    # The original file retains the complete time-history snapshots. The final
    # free shape needs the spatial fields, without duplicating those histories.
    final_fields={key:value for key,value in fields.items() if key not in ('temperature_snapshots','displacement_snapshots')}
    np.savez_compressed(folder/'free-release-fields.npz',**final_fields)
    # A converged cold release is a distinct mechanical phase, not a new
    # thermal-time increment. Keep its actual material-point updates explicit.
    yielded=np.flatnonzero(dl>0)
    cast_nodes=np.unique(e[m==1]);radius=np.linalg.norm(x[cast_nodes,:2],axis=1)
    bore=cast_nodes[abs(radius-inp['initial_bore_diameter_mm']/2)<1e-4]
    np.savez_compressed(folder/'free-release-path-increment.npz',
        phase=np.array('complete_cold_shell_datum_release'),
        plastic_element=yielded,delta_eqp=dl[yielded],
        delta_plastic_Mandel=dl[yielded,None]*direction[yielded],
        thermal_reset_element=np.array([],dtype=np.int64),
        bore_nodes=bore,mandrel_active=np.zeros(len(bore),dtype=bool),
        remaining_gauge_dofs=gauge,
        equilibrium_residual_N=np.array(residual),
        converged_free_release=np.array(audit['free_shell_release_pass']))
    (folder/'free-release-verification.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(audit,ensure_ascii=False,indent=2),flush=True)
    return audit


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--threads',type=int,default=1)
    a=p.parse_args();release(a.case,a.threads)
