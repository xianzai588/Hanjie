"""Continue the actual deposited seat in the prescribed hold and cooling furnace.

No temperature or residual state is replaced by a uniform furnace temperature.
The controlled50 C/h ramp is a prospective process setting, not measured data.
"""
import argparse
import json
import time
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix, diags
import pypardiso
from threadpoolctl import threadpool_limits
from run_candidate_solver import operators
from mma_literature_profile import ROOT


def run(source, output):
    output.mkdir(parents=True,exist_ok=True)
    if (output/'input.json').exists():raise ValueError('Preserve existing cooling evidence')
    result=json.loads((source/'result.json').read_text())
    if result['partial'] or result['error']:raise ValueError('Require a completed deposited source state')
    inp=json.loads((source/'input.json').read_text())
    with np.load(source/'thermal-fields.npz') as f:
        x,e,m=f['x'].copy(),f['e'].copy(),f['material'].copy()
        T=f['temperature'].copy();volume=f['volume_mm3'].copy()
        fractions=f['deposited_P1_moments'].sum(axis=1)
    if np.min(fractions)<1-1e-10:raise ValueError('Furnace continuation requires complete actual deposition')
    np.savez_compressed(output/'mesh.npz',x=x,e=e,material=m)
    tab=inp['materials'];g,_,_,_=operators(x,e,False)
    gram=np.einsum('eik,ejk->eij',g,g)
    n=len(x);rr=np.repeat(e,4,axis=1).ravel();cc=np.tile(e,(1,4)).ravel()
    mass=np.array([row['nominal_properties_20c']['density_kg_m3'] for row in tab])[m]*1e-9*volume/4
    faces=np.sort(np.vstack([e[:,q] for q in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1)
    unique,count=np.unique(faces,axis=0,return_counts=True)
    free=unique[count==1];xyz=x[free]
    area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)/2
    surface=np.bincount(free.ravel(),weights=np.repeat(area/3,3),minlength=n)
    def properties(temperatures,key):
        out=np.empty_like(temperatures)
        for j in (1,3):
            curve=tab[j]['temperature_dependent']
            out[m==j]=np.interp(temperatures[m==j],curve['temperatures_c'],curve[key])
        return out
    def enthalpy(temperature):
        local=temperature[e];values=np.empty_like(local);cp=np.empty_like(local)
        for j in (1,3):
            select=m==j;row=tab[j]
            if 'enthalpy_table' in row:
                knots=np.array(row['enthalpy_table']['temperature_C'])
                totals=np.array(row['enthalpy_table']['relative20C_J_kg'])
                slopes=np.diff(totals)/np.diff(knots)
                pos=np.clip(np.searchsorted(knots,local[select],side='right')-1,0,len(slopes)-1)
                values[select]=np.interp(local[select],knots,totals)
                cp[select]=slopes[pos]
            else:
                knots=np.array(row['temperature_dependent']['temperatures_c'])
                capacity=np.array(row['temperature_dependent']['specific_heat_j_kgk'])
                prefix=np.r_[0,np.cumsum(np.diff(knots)*(capacity[1:]+capacity[:-1])/2)]
                pos=np.clip(np.searchsorted(knots,local[select],side='right')-1,0,len(knots)-2)
                d=local[select]-knots[pos]
                values[select]=prefix[pos]+capacity[pos]*d+.5*np.diff(capacity)[pos]/np.diff(knots)[pos]*d*d
                cp[select]=np.interp(local[select],knots,capacity)
        return (np.bincount(e.ravel(),weights=(values*mass[:,None]).ravel(),minlength=n),
                np.bincount(e.ravel(),weights=(cp*mass[:,None]).ravel(),minlength=n))
    source_end=float(result['time_s']);hold=7200.;ramp=180/50*3600
    input_data=dict(source_run=str(source),source_end_s=source_end,materials=tab,
        hold_environment_C=200.,hold_duration_s=hold,controlled_environment_cooling_C_h=50.,
        ramp_duration_s=ramp,final_environment_C=20.,cold_stop_max_C=20.05,
        furnace_boundary_h_W_m2K=15.,emissivity=.7,
        cooling_rate_basis='prospective controlled furnace setting selected before calculation; two-hour200C hold follows the stated same-family process source',
        state_transfer='exact saved nodal temperature, complete deposition and CAD-corrected material volumes; no uniform temperature replacement',
        mechanical_history_reset=False)
    (output/'input.json').write_text(json.dumps(input_data,indent=2),encoding='utf8')
    trace_dir=output/'nodal-thermal-history';trace_dir.mkdir()
    chunks=[];trace=[];history=[];clock=time.perf_counter();local_time=0.;max_error=0.;max_increment=0.
    engine=pypardiso.PyPardisoSolver(mtype=11)
    def flush():
        if not trace:return
        filename='chunk-%04d.npz'%len(chunks)
        np.savez_compressed(trace_dir/filename,time_s=np.array([q[0] for q in trace]),
            temperature_C=np.array([q[1] for q in trace]),deposit_fraction=np.ones((len(trace),np.sum(m==3))),
            deposit_element_indices=np.flatnonzero(m==3))
        chunks.append(dict(file=filename,first_s=trace[0][0],last_s=trace[-1][0],steps=len(trace)))
        trace.clear()
        (trace_dir/'manifest.json').write_text(json.dumps(dict(chunks=chunks,scope='actual furnace continuation of the saved source state')),encoding='utf8')
        np.savetxt(output/'thermal-history.csv',history,delimiter=',',comments='',
            header='t_s,local_s,dt_s,environment_C,max_C,min_C,surface_outflow_J,balance_J,maximum_step_temperature_change_C')
    while local_time<hold+ramp or T.max()>20.05:
        dt=60.
        for endpoint in (hold,hold+ramp):
            if endpoint>local_time+1e-8:dt=min(dt,endpoint-local_time)
        # The first transient uses shorter steps until the previous accepted
        # change falls below10C. Later60s steps resolve a0.833C furnace ramp.
        if local_time<600:dt=10.
        environment=200. if local_time+dt<=hold else max(20.,200.-50*(local_time+dt-hold)/3600)
        old=T.copy();old_H,_=enthalpy(old)
        def stiffness(values,tangent=False):
            means=values[e].mean(axis=1);k=properties(means,'thermal_conductivity_w_mk')/1000
            K=coo_matrix(((gram*(k*volume)[:,None,None]).ravel(),(rr,cc)),shape=(n,n)).tocsr()
            if not tangent:return K
            dk=(properties(means+.01,'thermal_conductivity_w_mk')-properties(means-.01,'thermal_conductivity_w_mk'))/20
            gradient=np.einsum('eik,ei->ek',g,values[e])
            extra=np.einsum('eik,ek->ei',g,gradient)*(dk*volume/4)[:,None]
            return K,K+coo_matrix((np.repeat(extra[:,:,None],4,axis=2).ravel(),(rr,cc)),shape=(n,n)).tocsr()
        def losses(values,derivative=False):
            if derivative:return surface*(15e-6+4*.7*5.670374419e-14*(values+273.15)**3)
            return surface*(15e-6*(values-environment)+.7*5.670374419e-14*((values+273.15)**4-(environment+273.15)**4))
        def residual(values):
            H,_=enthalpy(values)
            return H-old_H+dt*(stiffness(values)@values+losses(values))
        for iteration in range(30):
            H,C=enthalpy(T);K,J=stiffness(T,True);r=H-old_H+dt*(K@T+losses(T))
            if np.linalg.norm(r)<1e-5:break
            A=diags(C+dt*losses(T,True))+dt*J
            delta=pypardiso.spsolve(A,-r,solver=engine)
            for power in range(12):
                candidate=T+delta*.5**power
                if candidate.min()>20.-1e-4 and np.linalg.norm(residual(candidate))<np.linalg.norm(r):
                    T=candidate;break
            else:raise RuntimeError('Furnace Newton line search failed')
        else:raise RuntimeError('Furnace Newton did not converge')
        local_time+=dt
        loss=dt*float(losses(T).sum());balance=float((H-old_H).sum())+loss
        max_error=max(max_error,abs(balance));increment=float(abs(T-old).max());max_increment=max(max_increment,increment)
        history.append([source_end+local_time,local_time,dt,environment,float(T.max()),float(T.min()),loss,balance,increment])
        trace.append((source_end+local_time,T.copy()))
        if len(history)%25==0:
            flush()
            (output/'progress.json').write_text(json.dumps(dict(local_s=local_time,environment_C=environment,max_C=float(T.max()),min_C=float(T.min()),elapsed_s=time.perf_counter()-clock)),encoding='utf8')
            print('furnace',round(local_time),round(environment,2),round(T.max(),3),flush=True)
        if local_time>hold+ramp+14400:raise RuntimeError('Controlled furnace did not reach the cold metrology state')
    flush()
    np.savez_compressed(output/'thermal-fields.npz',x=x,e=e,material=m,temperature=T,volume_mm3=volume,
        thermal_active=np.ones(len(e),bool),deposited_P1_moments=np.full((len(e),4),.25))
    final=dict(partial=False,error=None,time_s=source_end+local_time,source_run=str(source),
        final_min_C=float(T.min()),final_max_C=float(T.max()),
        maximum_absolute_step_energy_balance_error_J=max_error,maximum_step_temperature_change_C=max_increment,
        elapsed_s=time.perf_counter()-clock,mechanical_residual_state_assigned=False)
    (output/'result.json').write_text(json.dumps(final,indent=2),encoding='utf8')
    print(json.dumps(final,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=lambda s:ROOT/s,required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True)
    a=p.parse_args()
    with threadpool_limits(limits=1):run(a.source,a.output)
