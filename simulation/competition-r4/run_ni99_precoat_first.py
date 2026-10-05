"""First Ni99 layer on the actual complete QT seat, four short non-weaving tracks.

The coating station has no steel shell. Exposed faces follow real element birth;
finite seat heat capacity replaces the earlier adiabatic local truncation.
"""
from pathlib import Path
import argparse,json,time,shutil
import numpy as np
from scipy.sparse import coo_matrix,diags,triu
import pypardiso
from threadpoolctl import threadpool_limits
from ni99_local_thermal import tables
from run_candidate_solver import operators


def run(a):
    out=a.output;out.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    if (out/'input.json').exists() or (out/'thermal-fields.npz').exists():
        raise ValueError('use a fresh output directory; saved physical evidence must not be overwritten')
    with np.load(a.mesh/'mesh.npz',allow_pickle=False) as f:x,e,m=f['x'],f['e'],f['material']
    centre=x[e].mean(axis=1);angle=np.arctan2(centre[:,1],centre[:,0])
    sector=np.round(angle/(np.pi/4)).astype(int)%8
    coating=(m==3)|((m==4)&(a.first_geometry=='full_pocket'))
    keep=(m==1)|(coating&(sector==0));e=e[keep];m=m[keep]
    if a.first_geometry=='full_pocket':m[m==4]=3
    used=np.unique(e);remap=np.full(len(x),-1,int);remap[used]=np.arange(len(used));x=x[used];e=remap[e]
    np.savez_compressed(out/'mesh.npz',x=x,e=e,material=m)
    g,volume,_,_=operators(x,e,mechanical=False);n=len(x);centre=x[e].mean(axis=1)
    radius=np.linalg.norm(centre[:,:2],axis=1);angle=np.arctan2(centre[:,1],centre[:,0])
    top=float(x[np.unique(e[m==3]),2].max());tab=tables(a.ni1_solidus,a.ni_k_scale)
    if a.phase_carbon_corner:
        from phase_thermal_tables import overrides
        for index,table in overrides(tab,a.phase_carbon_corner,a.phase_graphite_limit,a.phase_temperature_shift).items():tab[index]=table
    from ni99_physics_bounds import apply_bounds
    tab=apply_bounds(tab,a.thermal_bounds)
    if a.pure_filler_birth:
        if a.deposition_temperature<1458.85:raise ValueError('pure filler entering temperature below JANAF Ni liquidus plus4 K uncertainty')
        tab[3]['nominal_properties_20c']['density_kg_m3']=8890.
    if a.deposition_temperature<tab[3]['fusion_enthalpy']['liquidus_C']:raise ValueError('entering first-layer temperature is below its selected liquidus')
    rho=np.array([t['nominal_properties_20c']['density_kg_m3'] for t in tab])[m]*1e-9
    solidus=np.array([t['fusion_enthalpy']['solidus_C'] for t in tab])[m,None]
    liquidus=np.array([t['fusion_enthalpy']['liquidus_C'] for t in tab])[m,None]
    latent=np.array([t['fusion_enthalpy']['latent_heat_J_kg'] for t in tab])[m,None]
    curve=tab[3]['fusion_enthalpy'].get('liquid_fraction_curve')
    if curve:
        phase_T=np.asarray(curve['temperature_C']);phase_q=np.asarray(curve['liquid_mass_fraction']);phase_slope=np.diff(phase_q)/np.diff(phase_T)
        if np.any(np.diff(phase_T)<=0) or np.min(np.diff(phase_q))<-1e-7:raise ValueError('invalid actual liquid-fraction curve')
    def melting(T,derivative=False):
        result=latent/(liquidus-solidus)*((T>solidus)&(T<liquidus)) if derivative else latent*np.clip((T-solidus)/(liquidus-solidus),0,1)
        if curve:
            q=T[m==3]
            if derivative:
                k=np.clip(np.searchsorted(phase_T,q,side='right')-1,0,len(phase_slope)-1)
                fraction=np.where((q>phase_T[0])&(q<phase_T[-1]),phase_slope[k],0.)
            else:fraction=np.interp(q,phase_T,phase_q)
            result[m==3]=latent[m==3]*fraction
        return result
    def prop(T,key):
        answer=np.empty_like(T)
        for j in [1,3]:
            curve=tab[j]['temperature_dependent'];answer[m==j]=np.interp(T[m==j],curve['temperatures_c'],curve[key])
        return answer
    def integral(T):
        answer=np.empty_like(T)
        for j in [1,3]:
            curve=tab[j]['temperature_dependent'];knots=np.asarray(curve['temperatures_c']);cp=np.asarray(curve['specific_heat_j_kgk'])
            prefix=np.r_[0,np.cumsum(np.diff(knots)*(cp[1:]+cp[:-1])/2)]
            q=T[m==j];k=np.clip(np.searchsorted(knots,q,side='right')-1,0,len(knots)-2);d=np.minimum(q,knots[-1])-knots[k]
            answer[m==j]=prefix[k]+cp[k]*d+.5*np.diff(cp)[k]/np.diff(knots)[k]*d*d+np.maximum(q-knots[-1],0)*cp[-1]
        return answer+melting(T)
    rr=np.repeat(e,4,axis=1).ravel();cc=np.tile(e,(1,4)).ravel()
    faces=np.sort(np.vstack([e[:,q] for q in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1)
    owner=np.tile(np.arange(len(e)),4);order=np.lexsort(faces.T[::-1]);faces=faces[order];owner=owner[order]
    bounds=np.flatnonzero(np.r_[True,np.any(np.diff(faces,axis=0),axis=1),True]);count=np.diff(bounds);beg=bounds[:-1]
    face=faces[beg];oa=owner[beg];ob=np.full(len(beg),-1,int);two=count==2;ob[two]=owner[beg[two]+1]
    xyz=x[face];area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)/2
    cross=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0])/2
    face_centre=xyz.mean(axis=1)
    interface=two & (m[oa]!=m[np.maximum(ob,0)]);interface_peak=np.full((interface.sum(),3),20.)
    interface_face=face[interface];interface_area=area[interface]
    bary=np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
    tracks=[]
    layer_radius=np.linalg.norm(x[np.unique(e[m==3]),:2],axis=1)
    radial_edges=np.linspace(layer_radius.min(),layer_radius.max(),a.radial_tracks+1)
    if a.radial_tracks==2:radial_edges[1]=72.
    strip_indices=list(range(a.radial_tracks))
    if a.radial_order=='outer_first':strip_indices.reverse()
    for strip in strip_indices:
        sr=[70.5,73.5][strip] if a.radial_tracks==2 else float((radial_edges[strip]+radial_edges[strip+1])/2)
        part=(m==3)&(radius>=radial_edges[strip]-1e-8)&(radius<=radial_edges[strip+1]+1e-8)
        nodes=np.unique(e[part]);theta=np.arctan2(x[nodes,1],x[nodes,0]);lo=float(theta.min());hi=float(theta.max())
        overlap=a.half_overlap/sr
        if not 0<=overlap<min(-lo,hi):raise ValueError('short-track overlap exceeds half-track length')
        for half,(begin,end) in enumerate([(lo,overlap),(-overlap,hi)]):
            targets=part&((angle<=overlap) if half==0 else (angle>=-overlap));length=sr*(end-begin)
            if length>18:raise ValueError('precoat short track exceeds18 mm')
            tracks.append(dict(strip=strip+1,half=half+1,radius_mm=sr,angle_begin=begin,angle_end=end,
                length_mm=length,arc_duration_s=length/a.travel,targets=targets))
    input_data=dict(mesh=str(a.mesh),nodes=n,tetrahedra=len(e),QT_volume_mm3=float(volume[m==1].sum()),
        first_layer_volume_mm3=float(volume[m==3].sum()),materials=tab,
        arc_power_W=a.power,travel_mm_s=a.travel,source_width_mm=a.width,source_depth_mm=a.depth,
        source_z_mm=top-a.source_drop,
        source_depth_mm_effective=a.depth if a.source_model=='volume' else None,
        inactive_source_parameters=[] if a.source_model=='volume' else ['source_drop','depth'],
        source_parameter_scope='volume centroid/depth only; surface models use xy and planar width, not gun standoff or focal depth',
        entering_Ni99_C=a.deposition_temperature,dt_s=a.dt,cold_start_C=a.initial_temperature,interpass_C=90.,
        preheat_scope='uniform initial QT temperature, no shell; one-track comparison, no maintained furnace or stress relaxation assumed',
        half_track_overlap_each_end_mm=a.half_overlap,
        radial_tracks=a.radial_tracks,radial_order=a.radial_order,radial_strip_edges_mm=radial_edges.tolist(),
        start_ramp_s=a.start_ramp,end_ramp_s=a.end_ramp,start_power_fraction=a.start_fraction,end_power_fraction=.35,
        heat_source_model=a.source_model,thermal_bounds_case=a.thermal_bounds,
        surface_grid_step_mm=a.surface_grid_step if a.source_model=='visible_surface' else None,
        surface_normalization=('fixed pi*width^2; first upward ray/metal hit only; missed flux not redistributed' if a.source_model=='visible_surface' else 'fixed pi*width^2 upward facets; historical overlapping-projection model' if a.source_model=='surface' else 'legacy active-volume Gaussian normalization'),
        deposition_geometry='actual selected conforming coating volume born along track; deposited shape hypothesis, not measured contour',
        first_geometry=a.first_geometry,first_as_deposited_thickness_mm=top-float(x[np.unique(e[m==3]),2].min()),
        first_followup='remove top half to0.70 mm before second coating and before bearing-bore finishing; transfer surviving precoat state required' if a.first_geometry=='full_pocket' else 'retained first-layer geometry comparison',
        entering_enthalpy_basis='pure incoming Ni JANAF, density8890; coating constitutive thermal hypotheses separate from solved dilution' if a.pure_filler_birth else 'legacy diluted-coating enthalpy hypothesis',
        active_temperature_guard_C=2800.,temperature_guard_basis='conservative stop below pure-Ni JANAF boiling2883.434 C; no evaporation or mass-loss equation',
        tracks=[{k:v for k,v in item.items() if k!='targets'} for item in tracks],
        boundary='actual complete QT seat; evolving free faces15 W/m2K plus radiation0.7; no shell and no adiabatic local truncation',
        power_policy='same net power partitioned into entering molten first-layer enthalpy and parent/pool heat',
        scope='first-layer thermal candidate on one actual wing; no invented precoat stress or PMZ capacity')
    if a.resume_from:
        old_input=json.loads((a.resume_from/'input.json').read_text(encoding='utf8'))
        ignore={'scope','boundary','deposition_geometry','surface_normalization','active_temperature_guard_C','temperature_guard_basis',
                'source_depth_mm_effective','inactive_source_parameters','source_parameter_scope','preheat_scope'}
        for key in input_data:
            if key not in ignore and input_data[key]!=old_input.get(key):raise ValueError('resume thermal input differs: '+key)
        input_data['resume_from']=str(a.resume_from)
    (out/'input.json').write_text(json.dumps(input_data,indent=2),encoding='utf8')
    from joint_interface_thermal import InterfaceThermalObserver
    observer=InterfaceThermalObserver(out,out/'precoat-interface-observer',tab)
    tetra_bary=np.full((4,4),.1381966011250105);np.fill_diagonal(tetra_bary,.5854101966249685)
    quadrature_peak=np.full((len(e),4),20.)
    engine=pypardiso.PyPardisoSolver(mtype=2)
    T=np.full(n,20.);T[np.unique(e[m==1])]=a.initial_temperature
    active=m==1;time_s=0.;history=[];peak=T.copy();stage_rows=[];source_history=[]
    incoming=np.full((len(e),1),a.deposition_temperature);wire_energy=rho*volume*integral(incoming)[:,0]
    if a.pure_filler_birth:
        from ni99_physics_bounds import NI_MOLAR_KG
        pure_h=(47361+17150)/NI_MOLAR_KG+(a.deposition_temperature-1454.85)*38.91103/NI_MOLAR_KG+(25.-20.)*25.987/NI_MOLAR_KG
        wire_energy=8890e-9*volume*pure_h
    completed=0
    if a.resume_from:
        old_result=json.loads((a.resume_from/'result.json').read_text(encoding='utf8'))
        if old_result['error'] or not old_result['stages']:raise ValueError('resume requires completed short tracks and cooling')
        if abs(old_result['stages'][-1]['end_s']-old_result['time_s'])>1e-8:raise ValueError('resume only at a completed cooled-track boundary')
        with np.load(a.resume_from/'thermal-fields.npz',allow_pickle=False) as f:
            if not all(np.array_equal(f[key],value) for key,value in [('x',x),('e',e),('material',m)]):raise ValueError('resume native mesh differs')
            T=f['temperature'].copy();peak=f['peak_nodal_temperature'].copy();active=f['thermal_active'].copy()
            interface_peak=f['interface_peak_C'].copy();quadrature_peak=f['peak_element_quadrature_C'].copy()
        history=np.loadtxt(a.resume_from/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2).tolist()
        source_history=np.loadtxt(a.resume_from/'source-partition-history.csv',delimiter=',',skiprows=1,ndmin=2).tolist()
        stage_rows=old_result['stages'];time_s=old_result['time_s'];completed=len(stage_rows)
        previous_observer=a.resume_from/'precoat-interface-observer'
        obs_summary=json.loads((previous_observer/'interface-thermal-history-summary.json').read_text(encoding='utf8'))
        with np.load(previous_observer/'material-interface-thermal.npz',allow_pickle=False) as f:
            if not np.array_equal(f['face_nodes'],observer.faces):raise ValueError('resume observer faces differ')
            observer.peak=f['peak_quadrature_C'].copy();observer.wet=f['thermally_active'].copy();observer.nodal_fused=f['nodal_fusion_mask'].copy()
        observer.step=obs_summary['steps'];observer.time=time_s
        for mi,segments in obs_summary['actual_P1_melting_depth_below_z115_mm'].items():
            for si,depth in segments.items():
                if depth is not None:observer.minimum_melt_z[int(mi),int(si)-1]=115-depth
        shutil.copyfile(previous_observer/'melting-depth-witness.csv',observer.witness_path)
        if T[np.unique(e[active])].max()>90:raise ValueError('saved completed track is not cooled')
        print('resume actual cooled first-layer state',completed,time_s,flush=True)
    def save(partial,error=None):
        np.savez_compressed(out/'thermal-fields.npz',x=x,e=e,material=m,temperature=T,peak_nodal_temperature=peak,
            thermal_active=active,interface_nodes=interface_face,interface_area_mm2=interface_area,interface_peak_C=interface_peak,
            tetra_quadrature_barycentric=tetra_bary,peak_element_quadrature_C=quadrature_peak,volume_mm3=volume)
        np.savetxt(out/'thermal-history.csv',history,delimiter=',',comments='',header='t_s,dt_s,track,on,max_C,QT_max_C,Ni99_max_C,total_input_J,wire_J,loss_J,balance_J')
        np.savetxt(out/'source-partition-history.csv',source_history,delimiter=',',comments='',header='t_s,dt_s,track,born_volume_mm3,wire_J,command_J,arc_intercept_J,uncaptured_J,legacy_fullspace_capture,legacy_normalization_multiplier,arc_to_QT_J,arc_to_Ni_J')
        result=dict(partial=partial,error=error,time_s=time_s,stages=stage_rows,maximum_temperature_C=float(peak.max()),
            maximum_QT_C=float(peak[np.unique(e[m==1])].max()),elapsed_s=time.perf_counter()-started,
            nominal_interface_area_mm2=float(interface_area.sum()),actual_area_above_both_solidus_mm2=float(np.sum(interface_area*np.mean(interface_peak>=max(tab[1]['fusion_enthalpy']['solidus_C'],tab[3]['fusion_enthalpy']['solidus_C']),axis=1))),
            both_solidus_threshold_C=max(tab[1]['fusion_enthalpy']['solidus_C'],tab[3]['fusion_enthalpy']['solidus_C']),
            active_temperature_range_check_pass=not error and all(row[4]<2800 for row in history),
            mesh_time_convergence_verified=False,PMZ_capacity_assigned=False)
        if observer.step:observer.save(partial=partial or bool(error))
        (out/('failure.json' if error else 'result.json')).write_text(json.dumps(result,indent=2),encoding='utf8')
        return result
    try:
        for k,track in enumerate(tracks):
            if k<completed:continue
            local=0.;wait=0.;start=time_s;duration=track['arc_duration_s'];initial_max=float(T[np.unique(e[active])].max())
            while local<duration-1e-8 or T[np.unique(e[active])].max()>90:
                on=local<duration-1e-8;dt=min(a.dt,duration-local) if on else min(2.,1800-wait)
                if on:
                    if a.start_ramp+a.end_ramp>=duration:raise ValueError('arc ramps leave no steady interval')
                    ramps=np.array([a.start_ramp,duration-a.end_ramp,duration]);future=ramps[ramps>local+1e-8]
                    dt=min(dt,float(future.min()-local))
                if dt<=1e-8:raise RuntimeError('whole-seat cooling did not reach90 C within1800 s')
                old=T.copy();previous=active.copy()
                if on:
                    reached=track['angle_begin']+a.travel*(local+dt)/track['radius_mm']
                    active |= track['targets']&(angle<=reached+1e-10)
                born=active&~previous;factor=np.where(active,1.,1e-8);mass=rho*volume*factor
                ke=np.einsum('eik,ejk,e->eij',g,g,prop(T[e].mean(axis=1),'thermal_conductivity_w_mk')/1000*volume*factor)
                K=coo_matrix((ke.ravel(),(rr,cc)),shape=(n,n)).tocsr()
                wet=active[oa]^((ob>=0)&active[np.maximum(ob,0)])
                surface=np.bincount(face[wet].ravel(),weights=np.repeat(area[wet]/3,3),minlength=n)
                radiation=.7*5.670374419e-14*((np.maximum(T,20)+273.15)**2+293.15**2)*(np.maximum(T,20)+566.3)
                cooling=(15e-6+radiation)*surface
                entering=float(wire_energy[born].sum());q=np.zeros(n)
                if on:
                    midpoint=local+dt/2;fraction=1.
                    if a.start_ramp and midpoint<a.start_ramp:fraction=a.start_fraction+(1-a.start_fraction)*midpoint/a.start_ramp
                    if a.end_ramp and duration-midpoint<a.end_ramp:fraction=min(fraction,.35+.65*(duration-midpoint)/a.end_ramp)
                    remaining=a.power*fraction-entering/dt
                    if remaining<0:raise RuntimeError('hot first-layer birth exceeds the same net power budget')
                    theta=track['angle_begin']+a.travel*(local+dt/2)/track['radius_mm'];source=[track['radius_mm']*np.cos(theta),track['radius_mm']*np.sin(theta),top-a.source_drop]
                    d=centre-source;w=np.exp(-(d[:,0]**2+d[:,1]**2)/a.width**2-(d[:,2]/a.depth)**2)*volume*active
                    fullspace=np.pi**1.5*a.width**2*a.depth
                    capture=float(w.sum()/fullspace)
                    if a.source_model=='volume':
                        p=w/w.sum()*remaining
                        q=np.bincount(e.ravel(),weights=np.repeat(p/4,4),minlength=n)
                        arc_QT=float(p[m==1].sum());arc_Ni=float(p[m==3].sum())
                    else:
                        # Vertical arc on actual upward exposed facets.  Fixed
                        # analytic normalization prevents born-pool/edge amplification.
                        active_owner=np.where(active[oa],oa,np.maximum(ob,0))
                        orient=np.sign(np.einsum('ij,ij->i',cross,face_centre-centre[active_owner]))
                        projection=cross[:,2]*orient
                        expose=wet&(projection>1e-10)
                        if a.source_model=='visible_surface':
                            from visible_surface_flux import load
                            q,per_owner,source_diag=load(x,face,xyz,active_owner,projection,wet,source,a.width,remaining,a.surface_grid_step)
                            arc_QT=float(per_owner[m[:len(per_owner)]==1].sum());arc_Ni=float(per_owner[m[:len(per_owner)]==3].sum())
                            (out/'source-quadrature-last.json').write_text(json.dumps(source_diag,indent=2),encoding='utf8')
                        else:
                            sf=face[expose];sq=np.einsum('qj,fjk->fqk',bary,xyz[expose])
                            density=np.exp(-np.sum((sq[:,:,:2]-np.asarray(source)[:2])**2,axis=2)/a.width**2)/(np.pi*a.width**2)
                            power_q=density*projection[expose,None]/3*remaining
                            nodal=power_q@bary
                            q=np.bincount(sf.ravel(),weights=nodal.ravel(),minlength=n)
                            pm=power_q.sum(axis=1);qm=m[active_owner[expose]]
                            arc_QT=float(pm[qm==1].sum());arc_Ni=float(pm[qm==3].sum())
                        if q.sum()>remaining*1.01:raise RuntimeError('surface Gaussian quadrature interception exceeds analytic total by>1%')
                    arc=float(q.sum());command=a.power*fraction*dt
                    source_history.append([time_s+dt,dt,k+1,float(volume[born].sum()),entering,command,arc*dt,
                                           (remaining-arc)*dt,capture,1/capture,arc_QT*dt,arc_Ni*dt])
                    q+=np.bincount(e[born].ravel(),weights=np.repeat(wire_energy[born]/(4*dt),4),minlength=n)
                old_H=np.bincount(e.ravel(),weights=(mass[:,None]*integral(old[e])/4).ravel(),minlength=n)
                if born.any():old_H-=np.bincount(e[born].ravel(),weights=(mass[born,None]*integral(old[e])[born]/4).ravel(),minlength=n)
                def enthalpy(values):
                    point=values[e];H=np.bincount(e.ravel(),weights=(mass[:,None]*integral(point)/4).ravel(),minlength=n)
                    cp=prop(point,'specific_heat_j_kgk')+melting(point,derivative=True)
                    C=np.bincount(e.ravel(),weights=(mass[:,None]*cp/4).ravel(),minlength=n)
                    return H,C
                def residual(values,H):return H-old_H+dt*(K@values+cooling*(values-20)-q)
                for iteration in range(45):
                    H,C=enthalpy(T);r=residual(T,H)
                    if np.linalg.norm(r)<1e-5:break
                    A=diags(C+dt*cooling)+dt*K
                    delta=pypardiso.spsolve(triu(A,format='csr'),-r,solver=engine)
                    if np.linalg.norm(A@delta+r)>.001:raise RuntimeError('precoat linear residual exceeds0.001')
                    for power in range(12):
                        candidate=T+delta*.5**power;ch,_=enthalpy(candidate)
                        if np.linalg.norm(residual(candidate,ch))<np.linalg.norm(r):T=candidate;break
                    else:raise RuntimeError('precoat enthalpy line search failed')
                else:raise RuntimeError('precoat enthalpy Newton failed')
                time_s+=dt
                if on:local+=dt
                else:wait+=dt
                peak=np.maximum(peak,T);both=active[oa[interface]]&active[ob[interface]]
                interface_peak=np.maximum(interface_peak,np.where(both[:,None],T[interface_face]@bary.T,20.))
                quadrature_peak=np.maximum(quadrature_peak,np.where(active[:,None],T[e]@tetra_bary.T,20.))
                observer(time_s,T,active)
                loss=dt*float(cooling@(T-20));balance=float((H-old_H).sum())+loss-dt*float(q.sum())
                history.append([time_s,dt,k+1,int(on),float(T[np.unique(e[active])].max()),float(T[np.unique(e[m==1])].max()),float(T[np.unique(e[(m==3)&active])].max()) if np.any((m==3)&active) else 20.,dt*float(q.sum()),entering,loss,balance])
                if history[-1][4]>=2800:
                    raise RuntimeError('active temperature exceeds2800 C conservative guard below Ni boiling; vaporization is outside this enthalpy model')
                if len(history)%25==0:
                    save(True);print('first Ni99',k+1,round(time_s,3),round(history[-1][4],2),flush=True)
            stage_rows.append(dict(track=k+1,start_s=start,initial_max_C=initial_max,arc_s=duration,cool_wait_s=wait,end_s=time_s,
                end_active_max_C=float(T[np.unique(e[active])].max()),born_volume_mm3=float(volume[active&(m==3)].sum())))
            save(True)
            if a.stop_after_tracks is not None and k+1>=a.stop_after_tracks:
                result=save(True);print(json.dumps(result,indent=2),flush=True);return result
        if not active.all():raise RuntimeError('first-layer tracks did not cover all actual wing elements')
        result=save(False);print(json.dumps(result,indent=2),flush=True);return result
    except Exception as exc:
        save(True,str(exc));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mesh',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--power',type=float,default=300.);p.add_argument('--width',type=float,default=1.4);p.add_argument('--depth',type=float,default=.4)
    p.add_argument('--dt',type=float,default=.2);p.add_argument('--deposition-temperature',type=float,default=1450.)
    p.add_argument('--travel',type=float,default=2.)
    p.add_argument('--initial-temperature',type=float,default=20.,help='uniform QT preheat before the first track; no held furnace temperature')
    p.add_argument('--source-drop',type=float,default=0.,help='heat-source centroid below first-layer top, mm')
    p.add_argument('--ni1-solidus',type=float,default=1300.);p.add_argument('--ni-k-scale',type=float,default=.75)
    p.add_argument('--half-overlap',type=float,default=0.,help='overlap about the two short tracks central split, per side in mm')
    p.add_argument('--radial-tracks',type=int,choices=[2,3,6],default=2)
    p.add_argument('--radial-order',choices=['inner_first','outer_first'],default='inner_first')
    p.add_argument('--start-ramp',type=float,default=0.)
    p.add_argument('--start-fraction',type=float,default=.5)
    p.add_argument('--end-ramp',type=float,default=0.)
    p.add_argument('--source-model',choices=['volume','surface','visible_surface'],default='volume')
    p.add_argument('--surface-grid-step',type=float,default=.1)
    p.add_argument('--thermal-bounds',choices=['legacy','nominal','low_k','high_k','pure_Ni_endmember'],default='legacy')
    p.add_argument('--first-geometry',choices=['retained','full_pocket'],default='retained')
    p.add_argument('--pure-filler-birth',action='store_true')
    p.add_argument('--resume-from',type=Path,help='continue an unchanged real cooled short-track state in a new output directory')
    p.add_argument('--phase-carbon-corner',choices=['min_C','max_C'])
    p.add_argument('--phase-graphite-limit',choices=['graphite_allowed','graphite_suppressed'],default='graphite_suppressed')
    p.add_argument('--phase-temperature-shift',type=float,default=0.)
    p.add_argument('--stop-after-tracks',type=int,choices=[1,2,3],help='save an actual partial candidate after the specified completed short tracks')
    args=p.parse_args()
    if not 0<=args.start_fraction<=1 or args.travel<=0 or not 20<=args.initial_temperature<=600:raise ValueError('invalid initial power fraction, travel or preheat')
    if args.initial_temperature!=20 and (args.stop_after_tracks!=1 or args.resume_from):
        raise ValueError('preheat comparison currently covers one track; maintained interpass heating requires its own boundary and energy history')
    with threadpool_limits(limits=1):run(args)
