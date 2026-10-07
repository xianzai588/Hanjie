"""Read-only phase-interface diagnosis; elastic probe is not manufacturing state."""
import json
from pathlib import Path
import numpy as np
import yaml
from scipy.sparse import coo_matrix
from threadpoolctl import threadpool_limits
import pypardiso
from mma_literature_profile import ROOT
from run_calculix_one_wing import history
from run_candidate_solver import operators

OUT = ROOT/'output/review/phase-interface-diagnosis-20261007'
RUN = ROOT/'simulation/competition-r4/results/calculix-one-wing-native-gauss-coldref-cold-20261007'


def frd_vector(name):
    lines=(RUN/'onewing.frd').read_text().splitlines()
    start=next(i for i,s in enumerate(lines) if s.startswith(' -4  '+name))
    values={}
    for s in lines[start+1:]:
        if s.startswith(' -3'):break
        if s.startswith(' -1'):
            values[int(s[3:13])]=[float(s[13+12*j:25+12*j]) for j in range(3)]
    return values


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    data=np.load(RUN/'mesh.npz');x,e,m,V=[data[k] for k in ['x','e','material','volume_mm3']]
    source=ROOT/'simulation/competition-r4/results/mma-first-end80-r12-phase-front-dt0125-20261007'
    inp=json.loads((source/'input.json').read_text(encoding='utf8'))
    _,T,_,_=next(q for q in history(source) if abs(q[0]-.25)<1e-9)
    Ts=inp['materials'][1]['fusion_enthalpy']['solidus_C']
    active=(m==1)&(T[e].mean(axis=1)<=Ts)
    signed=np.linalg.det((x[e[:,1:]]-x[e[:,:1]]).transpose(0,2,1))/6
    g,vol,B,dof=operators(x,e[active],True)
    ref=yaml.safe_load((ROOT/'project/precoat-mechanical-reference.yaml').read_text(encoding='utf8'))['QT_reference']
    te=T[e[active]].mean(axis=1)
    E=1000*np.interp(te,ref['temperatures_C'],ref['E_GPa']);nu=ref['poisson']
    mu=E/(2*(1+nu));bulk=E/(3*(1-2*nu))
    pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3
    C=2*mu[:,None,None]*(np.eye(6)-pv)+3*bulk[:,None,None]*pv
    ke=np.einsum('eji,ejk,ekl->eil',B,C,B)*vol[:,None,None]
    K=coo_matrix((ke.ravel(),(np.repeat(dof,12,axis=1).ravel(),np.tile(dof,(1,12)).ravel())),shape=(3*len(x),3*len(x))).tocsr()
    alpha=np.interp(te,ref['temperatures_C'],ref['mean_alpha_20C_per_K'])
    eps=(alpha*(te-20))[:,None]*np.array([1,1,1,0,0,0])
    fe=np.einsum('eji,ejk,ek->ei',B,C,eps)*vol[:,None]
    f=np.bincount(dof.ravel(),weights=fe.ravel(),minlength=3*len(x))
    occupied=np.unique(dof)
    fixed=np.array([3*196,3*196+1,3*196+2,3*1413+1,3*1413+2,3*1399+2])
    free=np.setdiff1d(occupied,fixed)
    engine=pypardiso.PyPardisoSolver(mtype=11)
    u=np.zeros(3*len(x));u[free]=engine.solve(K[free][:,free],f[free]);engine.free_memory(everything=True)
    residual=K@u-f
    probe=dict(purpose='elastic stiffness/topology probe at actual thermal0.25s; no yield capacity or accepted manufacturing state',
               active_QT_volume_mm3=float(V[active].sum()),positive_tetrahedra=int((signed>0).sum()),
               negative_tetrahedra=int((signed<0).sum()),minimum_signed_volume_mm3=float(signed.min()),
               minimum_active_E_MPa=float(E.min()),maximum_displacement_mm=float(np.linalg.norm(u.reshape(-1,3),axis=1).max()),
               free_force_residual_norm_N=float(np.linalg.norm(residual[free])),
               free_force_relative_residual=float(np.linalg.norm(residual[free])/np.linalg.norm(f[free])),
               accepted_manufacturing_state=False)
    disp=frd_vector('DISP');force=frd_vector('FORC')
    ids=np.array(list(disp));norm=np.array([np.linalg.norm(disp[k]) for k in ids])
    worst=[]
    for node in ids[np.argsort(norm)[-8:][::-1]]:
        touched=active&np.any(e==node-1,axis=1)
        worst.append(dict(node=int(node),x_mm=x[node-1].tolist(),native_unsuccessful_displacement_mm=disp[node],
                          native_unsuccessful_force_N=force.get(node),active_incident_tetrahedra=int(touched.sum()),
                          active_incident_volume_mm3=float(V[touched].sum()),
                          active_incident_mean_temperature_C=T[e[touched]].mean(axis=1).tolist(),
                          elastic_probe_displacement_mm=u.reshape(-1,3)[node-1].tolist()))
    partition=np.genfromtxt(source/'source-partition-history.csv',delimiter=',',names=True)
    audit=dict(actual_failure_time_s=.25,last_accepted_actual_time_s=.125,elastic_probe=probe,unsuccessful_native_tip_diagnostics=worst,
               heat_account=dict(command_J=float(partition['command_J'].sum()),entering_filler_J=float(partition['wire_J'].sum()),
                                 absorbed_arc_QT_J=float(partition['arc_to_QT_J'].sum()),absorbed_arc_Ni_J=float(partition['arc_to_Ni_J'].sum())),
               interpretation='An elastic probe can reject a gross disconnected/negative-volume hypothesis, but cannot prove a unique nonlinear failure cause or actual process adequacy.',
               manufacturing_chain_passed=False)
    (OUT/'diagnosis.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=='__main__':
    with threadpool_limits(limits=1):main()
