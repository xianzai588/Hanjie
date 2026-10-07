"""Two continuous low-carbon Ni tracks on the actual retained first layer.

This one frozen thermal case preserves the machined seat geometry and cold
temperature. Preheat/interpass uses furnace boundary exchange. Constant wire
feed drives exact P1 domain volumes, and molten-wire enthalpy is deducted from
the495 W net budget once. It supplies temperatures for retained-state replay.
"""
import argparse
import copy
import json
import time
import numpy as np
import yaml
from scipy.sparse import coo_matrix,diags
from scipy.spatial import cKDTree
import pypardiso
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT
from mma_conservative_birth import ConservativeBirth
from run_candidate_solver import operators
from ni99_local_thermal import tables
from ni99_physics_bounds import apply_bounds
from second_layer_surface import surface


def run(geometry,output,dt_arc=.125):
    if output.exists():raise ValueError('Preserve previous second-layer evidence')
    audit=json.loads((geometry/'geometry-state-audit.json').read_text())
    cut_source=ROOT/audit['source'];mechanical_source=ROOT/json.loads((cut_source/'input.json').read_text())['source']
    first_source=ROOT/json.loads((mechanical_source/'input.json').read_text())['source']
    tab=json.loads((first_source/'input.json').read_text())['materials']
    pure=apply_bounds(tables(1300.,.75),'pure_Ni_endmember')[3]
    pure['name']='Low-carbon bare Ni99: pure-Ni thermal reference before solved mixing'
    pure['composition_scope']='JANAF/Nickel200 thermal end member; no actual dilution or strength envelope assigned'
    tab[4]=copy.deepcopy(pure);tab.append(copy.deepcopy(pure))
    with np.load(geometry/'mesh.npz') as f:x,e,m,volume,total_mass=f['x'],f['e'],f['material'],f['volume_mm3'],f['material_mass_kg']
    with np.load(geometry/'inherited-state.npz') as f:T=f['temperature_C'].copy();occupation=f['occupation'].copy()
    card=yaml.safe_load((ROOT/'project/precoat-process-design.yaml').read_text(encoding='utf8'))['second']
    power=card['current_A']*card['voltage_V_reference']*card['efficiency_for_design_accounting'];speed=card['travel_mm_s']
    tracks=audit['continuous_track_geometry'];width=1.75;depth=1.;entry=1470.;liquid_factor=3.
    g,_,_,_=operators(x,e,False);gram=np.einsum('eik,ejk->eij',g,g);n=len(x)
    rr=np.repeat(e,4,axis=1).ravel();cc=np.tile(e,(1,4)).ravel()
    rho=total_mass/volume
    faces=np.sort(np.vstack([e[:,q] for q in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1)
    owners0=np.tile(np.arange(len(e)),4)
    faces,first,inverse,count=np.unique(faces,axis=0,return_index=True,return_inverse=True,return_counts=True)
    last=np.zeros(len(count),int);np.maximum.at(last,inverse,np.arange(len(owners0)))
    owners=owners0[first];neighbours=np.where(count==2,owners0[last],-1);safe=np.maximum(neighbours,0)
    xyz=x[faces];area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)/2
    pending=(count==2)&(m[owners]!=m[safe])&((m[owners]>=4)|(m[safe]>=4))
    interface=faces[pending];interface_area=area[pending];interface_owners=np.c_[owners[pending],neighbours[pending]]
    interface_old=np.any(m[interface_owners]==3,axis=1);interpass_nodes=np.unique(interface[interface_old])
    if not len(interpass_nodes):raise ValueError('Actual first/second interface not found')
    if np.any(pending&((m[owners]==1)|(m[safe]==1))):raise ValueError('New Ni directly bypasses the retained first layer')
    output.mkdir(parents=True);trace_dir=output/'nodal-thermal-history';trace_dir.mkdir()
    np.savez_compressed(output/'mesh.npz',x=x,e=e,material=m)
    input_data=dict(mesh=str(geometry),materials=tab,initial_state_path=str(geometry/'inherited-state.npz'),
        preexisting_material_ids=[1,3],deposition_material_ids=[4,5],cold_start_C=float(T.mean()),
        arc_power_W=power,net_line_energy_J_mm=power/speed,travel_mm_s=speed,dt_s=dt_arc,
        wire_feed_mm_s=card['feed_mm_s'],wire_diameter_mm=card['diameter_mm'],
        deposition_efficiency_design_case=audit['deposition_efficiency_design_case'],entering_Ni_C=entry,
        source_width_mm=width,source_depth_mm=depth,liquid_transport_factor=liquid_factor,
        source_parameter_scope='effective volume-source dimensions from3.5mm coverage/1mm deposition demand; engineering source hypothesis, no gun-distance or physical calibration assigned',
        thermal_reference_scope='source CI-A1 Gibbs enthalpy and original QT; new low-carbon Ni pure-Ni thermal reference, no dilution inferred',
        power_policy='net495W split into incoming molten wire and normalized occupied-medium Gaussian; no second interception efficiency',
        birth_policy='separate exact P1 track domains dosed in proportion to real CAD arc length, constant wire rate; fraction/4 capacity/source requires response check',
        boundary='15W/m2K plus emissivity0.7;300C furnace conditioning until actual first/second interface200..300C,20C free cooling between arcs',
        initial_state_transfer='actual machined cold geometry and nonuniform temperature; surviving residual tensors provided for separate mechanical replay',
        growth_rise_length_mm=width,deposition_regions=[dict(material_id=j,radius_mm=row['radius_mm'],
            growth_rise_length_mm=width,angle_offset_rad=0.) for j,row in zip([4,5],tracks)],
        tracks=tracks,geometry_state_audit=audit,full_manufacturing_verified=False,PMZ_capacity_assigned=False)
    (output/'input.json').write_text(json.dumps(input_data,ensure_ascii=False,indent=2),encoding='utf8')
    def constitutive(local):
        values=np.empty_like(local);capacity=np.empty_like(local)
        for j in np.unique(m):
            row=tab[j];select=m==j;q=local[select]
            if 'enthalpy_table' in row:
                knots=np.array(row['enthalpy_table']['temperature_C']);h=np.array(row['enthalpy_table']['relative20C_J_kg']);slopes=np.diff(h)/np.diff(knots)
                pos=np.clip(np.searchsorted(knots,q,side='right')-1,0,len(slopes)-1)
                values[select]=np.interp(q,knots,h);capacity[select]=slopes[pos]
            else:
                curve=row['temperature_dependent'];knots=np.array(curve['temperatures_c']);cp=np.array(curve['specific_heat_j_kgk'])
                prefix=np.r_[0,np.cumsum(np.diff(knots)*(cp[1:]+cp[:-1])/2)]
                pos=np.clip(np.searchsorted(knots,q,side='right')-1,0,len(knots)-2);d=np.minimum(q,knots[-1])-knots[pos]
                values[select]=prefix[pos]+cp[pos]*d+.5*np.diff(cp)[pos]/np.diff(knots)[pos]*d*d+np.maximum(q-knots[-1],0)*cp[-1]
                capacity[select]=np.interp(q,knots,cp)
                fusion=row['fusion_enthalpy'];s,l,h=fusion['solidus_C'],fusion['liquidus_C'],fusion['latent_heat_J_kg']
                values[select]+=h*np.clip((q-s)/(l-s),0,1);capacity[select]+=h/(l-s)*((q>s)&(q<l))
        return values,capacity
    incoming,_=constitutive(np.full((len(e),4),entry));wire_specific=incoming.mean(axis=1)
    def conductivity(means):
        answer=np.empty(len(e))
        for j in np.unique(m):
            curve=tab[j]['temperature_dependent'];select=m==j;f=tab[j]['fusion_enthalpy']
            liquid=np.clip((means[select]-f['solidus_C'])/(f['liquidus_C']-f['solidus_C']),0,1)
            answer[select]=np.interp(means[select],curve['temperatures_c'],curve['thermal_conductivity_w_mk'])/1000*(1+(liquid_factor-1)*liquid)
        return answer
    history=[];deposition=[];chunks=[];trace=[];cycle_times=[];cycles=[];stages=[]
    deposit_indices=np.flatnonzero(m>=4);peak=T.copy();clock=time.perf_counter();t=0.;step=0
    engine=pypardiso.PyPardisoSolver(mtype=11);moments=np.repeat((occupation/4)[:,None],4,axis=1)
    accepted_state=None;trial_end=None
    def save(partial,error=None):
        if trace:
            filename='chunk-%04d.npz'%len(chunks)
            np.savez_compressed(trace_dir/filename,time_s=np.array([q[0] for q in trace]),temperature_C=np.array([q[1] for q in trace]),
                deposit_fraction=np.array([q[2] for q in trace]),deposit_element_indices=deposit_indices)
            chunks.append(dict(file=filename,first_s=trace[0][0],last_s=trace[-1][0],steps=len(trace)));trace.clear()
            (trace_dir/'manifest.json').write_text(json.dumps(dict(chunks=chunks)),encoding='utf8')
        np.savez_compressed(output/'thermal-fields.npz',x=x,e=e,material=m,temperature=T,peak_nodal_temperature=peak,
            volume_mm3=volume,material_mass_kg=total_mass,thermal_active=moments.sum(axis=1)>1e-14,deposited_P1_moments=moments)
        np.savez_compressed(output/'interface-cycles.npz',time_s=np.array(cycle_times),face_nodes=interface,
            nodal_temperature_C=np.array(cycles,dtype=np.float64),face_area_mm2=interface_area)
        np.savetxt(output/'thermal-history.csv',history,delimiter=',',comments='',header='t_s,dt_s,track,arc_on,environment_C,max_C,min_C,command_J,wire_J,surface_outflow_J,balance_J')
        np.savetxt(output/'deposition-history.csv',deposition,delimiter=',',comments='',header='t_s,track,target_track_g,actual_track_g,step_g,wire_J,arc_to_QT_J,arc_to_CI_J,arc_to_Ni_J')
        final=dict(partial=partial,error=error,time_s=t,stages=stages,maximum_temperature_C=float(peak.max()),
            final_max_C=float(T.max()),final_min_C=float(T.min()),full_manufacturing_verified=False,
            second_layer_continuous_connection_verified=False,PMZ_capacity_assigned=False,elapsed_s=time.perf_counter()-clock)
        (output/('failure.json' if error else 'result.json')).write_text(json.dumps(final,indent=2),encoding='utf8')
        return final
    try:
        for track_id,(material_id,track) in enumerate(zip([4,5],tracks),1):
            birth=ConservativeBirth(x,e,np.where(m<4,1,0),volume,rho,radius=track['radius_mm'],rise_length=width,
                deposit_mask=m==material_id,initial_moments=moments)
            front=float(birth.lo.min()-1e-9);local=0.;duration=track['arc_length_mm']/speed;conditioning=0.;cooling=0.;start=None
            mass_rate=birth.total_mass_kg/duration
            expected_rate=8890e-9*np.pi*(card['diameter_mm']/2)**2*card['feed_mm_s']*audit['deposition_efficiency_design_case']
            if abs(mass_rate-expected_rate)>expected_rate*1e-8:raise ValueError('Actual track domain and wire mass/time differ')
            while local<duration-1e-9 or T[np.unique(e[moments.sum(axis=1)>1e-14])].max()>500:
                precondition=start is None and (T[interpass_nodes].min()<200 or T[interpass_nodes].max()>300+1e-6)
                on=local<duration-1e-9 and not precondition
                ambient=300. if precondition and T[interpass_nodes].min()<200 else 20.
                dt=min(dt_arc,duration-local) if on else 10. if precondition else 2.
                accepted_state=(T.copy(),moments.copy(),peak.copy(),t);trial_end=t+dt
                if on and start is None:start=t
                old=T.copy();old_mom=moments.copy();old_fraction=old_mom.sum(axis=1)
                if on:
                    _,moments,delta,fraction,centres,front=birth.advance(min(mass_rate*(local+dt),birth.total_mass_kg))
                else:
                    fraction=moments.sum(axis=1);delta=np.zeros_like(moments);centres=x[e].mean(axis=1)
                present=np.unique(e[old_fraction>=1-1e-12]);supported=np.unique(e[fraction>1e-14])
                if on:present=np.union1d(present,supported[birth.nodal_values[supported]<=front])
                if not len(present):raise ValueError('No physical thermal support')
                mapping=np.arange(n);ghost=np.setdiff1d(np.arange(n),present)
                if len(ghost):mapping[ghost]=present[cKDTree(x[present]).query(x[ghost])[1]]
                dofs,inverse=np.unique(mapping,return_inverse=True)
                R=coo_matrix((np.ones(n),(np.arange(n),inverse)),shape=(n,len(dofs))).tocsr();T=R@T[dofs]
                nodal_area=surface(x,e,faces,owners,neighbours,area,birth,front,fraction)
                if nodal_area.min()<-1e-10:raise RuntimeError('Exposed area became negative')
                mass=total_mass*fraction/4;old_mass=total_mass*old_fraction/4
                values,_=constitutive(old[e]);old_H=np.bincount(e.ravel(),weights=(old_mass[:,None]*values).ravel(),minlength=n)
                q=np.zeros(n);entering=float((total_mass*wire_specific)@delta.sum(axis=1));command=power*dt if on else 0.
                parts=np.zeros(3)
                if on:
                    _,source_fraction,source_centres,source_front=birth.at_mass(mass_rate*(local+dt/2))
                    theta=track['angular_offsets_rad'][0]+speed*(local+dt/2)/track['radius_mm']
                    z=birth.floor+(birth.top-birth.floor)*(source_front-theta)*track['radius_mm']/width
                    point=np.array([track['radius_mm']*np.cos(theta),track['radius_mm']*np.sin(theta),min(birth.top,max(birth.floor,z))])
                    d=source_centres-point;weight=np.exp(-np.sum(d[:,:2]**2,axis=1)/width**2-(d[:,2]/depth)**2)*volume*source_fraction*(d[:,2]<=0)
                    remaining=power-entering/dt
                    if remaining<=0 or weight.sum()<=0:raise RuntimeError('Wire or geometry exceeds the actual net source budget')
                    per_cell=remaining*weight/weight.sum();q=np.bincount(e.ravel(),weights=np.repeat(per_cell/4,4),minlength=n)
                    parts=np.array([per_cell[m==1].sum(),per_cell[m==3].sum(),per_cell[m>=4].sum()])*dt
                    q+=np.bincount(e.ravel(),weights=np.repeat(total_mass*wire_specific*delta.sum(axis=1)/(4*dt),4),minlength=n)
                def enthalpy(values):
                    h,cp=constitutive(values[e])
                    return (np.bincount(e.ravel(),weights=(mass[:,None]*h).ravel(),minlength=n),
                        np.bincount(e.ravel(),weights=(mass[:,None]*cp).ravel(),minlength=n))
                def conduction(values,tangent=False):
                    means=values[e].mean(axis=1);k=conductivity(means)
                    K=coo_matrix(((gram*(k*volume*fraction)[:,None,None]).ravel(),(rr,cc)),shape=(n,n)).tocsr()
                    if not tangent:return K
                    dk=(conductivity(means+.01)-conductivity(means-.01))/.02
                    grad=np.einsum('eik,ei->ek',g,values[e]);extra=np.einsum('eik,ek->ei',g,grad)*(dk*volume*fraction/4)[:,None]
                    return K,K+coo_matrix((np.repeat(extra[:,:,None],4,axis=2).ravel(),(rr,cc)),shape=(n,n)).tocsr()
                def loss(values,derivative=False):
                    if derivative:return nodal_area*(15e-6+4*.7*5.670374419e-14*(values+273.15)**3)
                    return nodal_area*(15e-6*(values-ambient)+.7*5.670374419e-14*((values+273.15)**4-(ambient+273.15)**4))
                def residual(values):
                    H,_=enthalpy(values);return R.T@(H-old_H+dt*(conduction(values)@values+loss(values)-q))
                for iteration in range(45):
                    H,C=enthalpy(T);K,J=conduction(T,True);r=R.T@(H-old_H+dt*(K@T+loss(T)-q))
                    if np.linalg.norm(r)<1e-5:break
                    A=(R.T@(diags(C+dt*loss(T,True))+dt*J)@R).tocsr()
                    correction=pypardiso.spsolve(A,-r,solver=engine)
                    if np.linalg.norm(A@correction+r)>.001:raise RuntimeError('Second-layer linear residual exceeds0.001J')
                    for power_index in range(12):
                        trial=T+(R@correction)*.5**power_index
                        if trial.min()>20-1e-4 and np.linalg.norm(residual(trial))<np.linalg.norm(r):T=trial;break
                    else:raise RuntimeError('Second-layer thermal Newton line search failed')
                else:raise RuntimeError('Second-layer thermal Newton did not converge')
                if T.max()>=2800:raise RuntimeError('Second-layer temperature exceeds model interval; no clipping or evaporation assumed')
                t+=dt;step+=1
                if on:local+=dt
                elif precondition:conditioning+=dt
                else:cooling+=dt
                peak=np.maximum(peak,T);outflow=dt*float(loss(T).sum());balance=float((H-old_H).sum())+outflow-command
                history.append([t,dt,track_id,on,ambient,float(T.max()),float(T.min()),command,entering,outflow,balance])
                if on:deposition.append([t,track_id,mass_rate*local*1000,float((total_mass[m==material_id]*fraction[m==material_id]).sum())*1000,
                    float(total_mass@delta.sum(axis=1))*1000,entering,*parts])
                present_face=np.ones_like(interface,dtype=bool)
                for side in range(2):
                    owner=interface_owners[:,side];full=fraction[owner]>=1-1e-12;absent=fraction[owner]<=1e-14
                    present_face&=full[:,None]|((~absent[:,None])&(birth.nodal_values[interface]<=front))
                cycle_times.append(t);cycles.append(np.where(present_face,T[interface],20.));trace.append((t,T.copy(),fraction[deposit_indices].copy()))
                if step%25==0:
                    save(True);print('second',step,round(t,3),track_id,on,round(T.max(),2),round(time.perf_counter()-clock,1),flush=True)
                if conditioning>10800 or cooling>1800:raise RuntimeError('Independent second-layer temperature cycle exceeds frozen station budget')
            stages.append(dict(track=track_id,start_s=start,arc_s=duration,conditioning_s=conditioning,cool_s=cooling,end_s=t))
        print(json.dumps(save(False),indent=2))
    except Exception as error:
        np.savez_compressed(output/'failed-trial.npz',temperature_C=T,deposited_P1_moments=moments,
            trial_end_s=trial_end,last_accepted_s=t)
        if accepted_state is not None and t==accepted_state[3]:T,moments,peak,t=accepted_state
        save(True,str(error));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--geometry',type=lambda s:ROOT/s,required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True);p.add_argument('--dt',type=float,default=.125)
    a=p.parse_args()
    with threadpool_limits(limits=1):run(a.geometry,a.output,a.dt)
