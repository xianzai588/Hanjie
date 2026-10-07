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
    all_wings=getattr(a,'all_wings',False)
    coating=(m==3)|((m==4)&(a.first_geometry=='full_pocket'))
    keep=(m==1)|(coating if all_wings else coating&(sector==0));e=e[keep];m=m[keep]
    if a.first_geometry=='full_pocket':m[m==4]=3
    used=np.unique(e);remap=np.full(len(x),-1,int);remap[used]=np.arange(len(used));x=x[used];e=remap[e]
    np.savez_compressed(out/'mesh.npz',x=x,e=e,material=m)
    g,volume,_,_=operators(x,e,mechanical=False);n=len(x);centre=x[e].mean(axis=1)
    radius=np.linalg.norm(centre[:,:2],axis=1);angle=np.arctan2(centre[:,1],centre[:,0])
    sector=np.round(angle/(np.pi/4)).astype(int)%8
    top=float(x[np.unique(e[m==3]),2].max());tab=tables(a.ni1_solidus,a.ni_k_scale)
    if a.phase_carbon_corner:
        from phase_thermal_tables import overrides
        for index,table in overrides(tab,a.phase_carbon_corner,a.phase_graphite_limit,a.phase_temperature_shift).items():tab[index]=table
    from ni99_physics_bounds import apply_bounds
    tab=apply_bounds(tab,a.thermal_bounds)
    mma=getattr(a,'mma_profile',False)
    if mma:
        from mma_literature_profile import configure
        tab,hm_T,hm_H,hm_cp=configure(tab,mma if isinstance(mma,str) else 'CI-A1')
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
        if mma and key=='specific_heat_j_kgk':
            idx=np.clip(np.searchsorted(hm_T,T[m==3],side='right')-1,0,len(hm_cp)-1)
            answer[m==3]=hm_cp[idx]
        return answer
    def integral(T):
        answer=np.empty_like(T)
        for j in [1,3]:
            curve=tab[j]['temperature_dependent'];knots=np.asarray(curve['temperatures_c']);cp=np.asarray(curve['specific_heat_j_kgk'])
            prefix=np.r_[0,np.cumsum(np.diff(knots)*(cp[1:]+cp[:-1])/2)]
            q=T[m==j];k=np.clip(np.searchsorted(knots,q,side='right')-1,0,len(knots)-2);d=np.minimum(q,knots[-1])-knots[k]
            answer[m==j]=prefix[k]+cp[k]*d+.5*np.diff(cp)[k]/np.diff(knots)[k]*d*d+np.maximum(q-knots[-1],0)*cp[-1]
            answer[m==j]=np.where(q<knots[0],cp[0]*(q-knots[0]),answer[m==j])
        if mma:
            q=T[m==3]
            answer[m==3]=(np.interp(q,hm_T,hm_H)+np.minimum(q-hm_T[0],0)*hm_cp[0]
                          +np.maximum(q-hm_T[-1],0)*hm_cp[-1])
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
    conservative=getattr(a,'conservative_birth',False)
    continuous=getattr(a,'continuous_track',False)
    bottom_up=getattr(a,'deposition_growth','angular')=='bottom_up'
    if conservative and not (mma and continuous and a.radial_tracks==1):
        raise ValueError('mass-controlled birth currently applies to one continuous MMA track')
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
        if continuous:
            sr=a.track_radius_mm
            lo=-a.track_length_mm/(2*sr);hi=-lo
            segments=[(lo,hi)]
        else:segments=[(overlap,lo),(-overlap,hi)] if mma else [(lo,overlap),(-overlap,hi)]
        if mma and strip%2:segments=segments[::-1]
        for half,(begin,end) in enumerate(segments):
            targets=part if continuous else part&((angle<=overlap) if (end<0 if mma else half==0) else (angle>=-overlap));length=sr*abs(end-begin)
            if length>(50 if mma else 18):raise ValueError('precoat track exceeds specified length')
            tracks.append(dict(strip=strip+1,half=half+1,radius_mm=sr,angle_begin=begin,angle_end=end,
                length_mm=length,arc_duration_s=length/a.travel,targets=targets))
    if all_wings:
        if not (conservative and continuous and len(tracks)==1):
            raise ValueError('eight-wing replay requires the frozen single continuous MMA track')
        reference=tracks[0]
        tracks=[dict(reference,wing=j+1,angle_offset=j*np.pi/4,
            angle_begin=reference['angle_begin']+j*np.pi/4,
            angle_end=reference['angle_end']+j*np.pi/4,
            targets=(m==3)&(sector==j)) for j in [0,4,2,6,1,5,3,7]]
    end_fraction=getattr(a,'end_fraction',.35)
    mass_exponent=getattr(a,'mass_current_exponent',0)
    def cumulative_mass_g(arc_time):
        duration=tracks[0]['arc_duration_s'] if all_wings else sum(track['arc_duration_s'] for track in tracks)
        if not a.end_ramp or mass_exponent==0:return a.mass_rate_g_s*arc_time
        steady=duration-a.end_ramp
        u=max(0.,arc_time-steady);rate=(1-end_fraction)/a.end_ramp
        if mass_exponent!=2:raise ValueError('unfrozen mass/current profile')
        return a.mass_rate_g_s*(min(arc_time,steady)+u-rate*u*u+rate*rate*u**3/3)
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
        start_ramp_s=a.start_ramp,end_ramp_s=a.end_ramp,start_power_fraction=a.start_fraction,end_power_fraction=end_fraction,
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
    if mma:
        product=mma if isinstance(mma,str) else 'CI-A1'
        input_data.update(material_family=product+' SMAW',net_line_energy_J_mm=a.power/a.travel,
            source_anchor_DOI='10.1016/S0167-577X(99)00204-9',source_anchor_table=3,
            source_validation='line energy anchored to ENi-CI bead-on-plate; spatial Gaussian is an engineering hypothesis',
            source_depth_mm_effective=a.depth,
            inactive_source_parameters=['surface_grid_step'],
            surface_normalization='not an incident surface source; prescribed NET pool power normalized on connected active metal',
            power_policy='net workpiece+deposit power prescribed; subtract hot incoming metal enthalpy once; no additional interception efficiency',
            arc_start_stop='step input; endpoint masks report thermal startup under this source assumption, not measured arc stability',
            interpass_C=300.,final_cooling_target_C=500.,entering_enthalpy_basis=tab[3]['enthalpy_table'],
            first_followup='actual machining to0.70mm normal retention; no residual-stress state assigned by this thermal run')
    if conservative:
        input_data.update(deposition_geometry='P1-angle cut-cell sweep of saved volume-equivalent CAD envelope driven by cumulative deposited mass',
            deposited_mass_rate_g_s=a.mass_rate_g_s,
            birth_policy='exact cut volumes, cell occupancy homogenization with lumped mass at four parent vertices; retain previous enthalpy and add only new mass entering enthalpy',
            source_policy='midpoint Gaussian location, height, occupied domain and cut centroid evaluated at the same cumulative-mass time; cell load distributed to four vertices',
            thermal_cut_cell_scope='geometric P1 moments saved for domain auditing; thermal capacity/source use fraction/4, an approximation requiring local mesh comparison',
            cut_cell_extension='aggregate unsupported outside-front vertices to nearest present metal vertex; solve R^T A R and R^T residual, preserving all mass/heat',
            front_policy='mass-quantile angular front; source follows single CAD arc; report offset and spatial sensitivity',
            source_parameter_scope='effective conduction-source width/depth hypotheses, not gun settings',
            stop_time_s=getattr(a,'stop_time_s',None),electrical_power_W=2530.,net_efficiency=.8)
        input_data.update(mass_current_exponent=mass_exponent,deposited_mass_profile='steady rate followed by current-fraction^exponent during the end ramp',
            integrated_deposited_mass_g=cumulative_mass_g(tracks[0]['arc_duration_s'] if all_wings else sum(track['arc_duration_s'] for track in tracks)))
        input_data.update(liquid_transport_factor=getattr(a,'liquid_transport_factor',1.),
            liquid_transport_policy='k_eff=k_molecular*(1+(factor-1)*liquid_fraction); no solid enhancement, energy redistribution only',
            liquid_transport_method_source='Hu et al2024, Additive Manufacturing92 104379, DOI10.1016/j.addma.2024.104379 section2.1',
            liquid_transport_scope='factor3 is a literature method bound for SS316L, not a measured CI-A1 coefficient; no material calibration assigned')
    if all_wings:
        input_data.update(scope='actual eight-wing sequential first-layer thermal history on the complete QT seat; retained mechanical replay follows separately',
            wing_sequence=[row['wing'] for row in tracks],
            interpass_policy='before each actual wing, QT/interface nodes must be200..300C; air cool or300C furnace boundary conditioning preserves the full nodal field',
            integrated_deposited_mass_g=8*cumulative_mass_g(tracks[0]['arc_duration_s']),
            nodal_history_wing_interpretation='deposit fractions cover all eight wing envelopes; track id is in the simultaneous thermal CSV',
            final_cooling_target_C=500.)
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
    engine=pypardiso.PyPardisoSolver(mtype=11 if conservative else 2)
    T=np.full(n,20.);T[np.unique(e[m==1])]=a.initial_temperature
    active=m==1;time_s=0.;history=[];peak=T.copy();stage_rows=[];source_history=[];birth_history=[];solver_diagnostics=[];source_path=[];nodal_trace=[];trace_chunks=[]
    record_nodal=getattr(a,'record_nodal_history',False)
    boundary_history=[]
    if record_nodal:
        (out/'nodal-thermal-history').mkdir()
        input_data['nodal_history']='all accepted nodal temperature states and deposit fractions in float64; for retained-state thermomechanical replay'
        (out/'input.json').write_text(json.dumps(input_data,indent=2),encoding='utf8')
    if conservative:
        from mma_conservative_birth import ConservativeBirth
        geometry=json.loads((a.mesh/'geometry-audit.json').read_text(encoding='utf8'))
        cad_volume=geometry['target_deposited_volume_one_wing_mm3']
        raw_mesh_volume=float(volume[m==3].sum())
        input_data['raw_mesh_deposit_volume_mm3']=raw_mesh_volume
        input_data['CAD_deposit_volume_mm3']=cad_volume
        input_data['CAD_volume_quadrature_factor']=cad_volume/raw_mesh_volume
        input_data['volume_quadrature_policy']='constant deposit Jacobian correction to exact CAD volume; retain straight-tetra gradients; assess this geometric approximation with local mesh refinement'
        # Straight tetrahedra omit the curved pocket boundary volume. Integrate
        # the prescribed CAD volume with the same Jacobian factor in capacity,
        # incoming enthalpy, conductivity and source, rather than changing feed
        # or density. The raw discrepancy remains in the saved input.
        volume=volume.copy()
        if all_wings:
            factors={str(j+1):cad_volume/float(volume[(m==3)&(sector==j)].sum()) for j in range(8)}
            for j in range(8):volume[(m==3)&(sector==j)]*=factors[str(j+1)]
            input_data.update(CAD_deposit_volume_mm3=8*cad_volume,CAD_volume_quadrature_factors_by_wing=factors,
                CAD_volume_quadrature_factor=None)
        else:volume[m==3]*=cad_volume/raw_mesh_volume
        birth=ConservativeBirth(x,e,m,volume,rho,a.track_radius_mm,a.width if bottom_up else None,
            deposit_mask=tracks[0]['targets'] if all_wings else None)
        if bottom_up:
            input_data.update(deposition_geometry='mass-controlled bottom-up cut-cell envelope: phi=theta+width/radius*(z-floor)/(top-floor)',
                front_policy='volume-equivalent progressive groove filling; the existing effective source width sets rise length; no liquid transport or bead contour calibration assigned',
                source_z_policy='follow the evolving deposition surface at the same midpoint time as commanded arc xy; bounded by actual CAD floor/top',
                growth_floor_z_mm=birth.floor,growth_top_z_mm=birth.top,growth_rise_length_mm=a.width)
        prescribed_mass=cumulative_mass_g(tracks[0]['arc_duration_s'] if all_wings else sum(t['arc_duration_s'] for t in tracks))*1e-3
        if abs(prescribed_mass-birth.total_mass_kg)>prescribed_mass*1e-9:
            raise ValueError('CAD mass differs from pWPS duration/feed')
        input_data['mesh_mass_discretization_relative_error']=(birth.total_mass_kg-prescribed_mass)/prescribed_mass
        (out/'input.json').write_text(json.dumps(input_data,indent=2),encoding='utf8')
    incoming=np.full((len(e),1),a.deposition_temperature);wire_energy=rho*volume*integral(incoming)[:,0]
    if a.pure_filler_birth:
        from ni99_physics_bounds import NI_MOLAR_KG
        pure_h=(47361+17150)/NI_MOLAR_KG+(a.deposition_temperature-1454.85)*38.91103/NI_MOLAR_KG+(25.-20.)*25.987/NI_MOLAR_KG
        wire_energy=8890e-9*volume*pure_h
    interface_cycles=[];cycle_times=[]
    completed=0
    resume_local=0.
    transient_from=getattr(a,'transient_from',None)
    if transient_from:
        if not (conservative and len(tracks)==1 and record_nodal):raise ValueError('transient replay is restricted to one continuous traced MMA track')
        old_input=json.loads((transient_from/'input.json').read_text(encoding='utf8'))
        for key in ['arc_power_W','travel_mm_s','source_width_mm','source_depth_mm','entering_Ni99_C','cold_start_C',
                    'start_ramp_s','end_ramp_s','end_power_fraction','mass_current_exponent','tracks',
                    'liquid_transport_factor','source_policy','source_z_policy','CAD_deposit_volume_mm3','materials']:
            if input_data[key]!=old_input.get(key):raise ValueError('transient physical inputs differ: '+key)
        resume_local=float(a.transient_time)
        if not 0<resume_local<tracks[0]['arc_duration_s']:raise ValueError('restart must be within the first arc')
        from mma_thermal_restart import accepted_prefix
        nodal_trace,rows=accepted_prefix(transient_from,resume_local,x,e,m)
        history,source_history,birth_history,source_path=[rows[key] for key in ['history','source_history','birth_history','source_path']]
        for t,temperature,fractions,level in nodal_trace:
            mask=m==1;mask[m==3]=fractions>1e-14
            peak=np.maximum(peak,temperature)
            observer(t,temperature,mask,birth.nodal_values,level)
            qp_mask=mask[:,None]&((m!=3)[:,None]|(birth.nodal_values[e]@tetra_bary.T<=level))
            quadrature_peak=np.maximum(quadrature_peak,np.where(qp_mask,temperature[e]@tetra_bary.T,20.))
            present=birth.nodal_values[interface_face]@bary.T<=level
            interface_peak=np.maximum(interface_peak,np.where(present,temperature[interface_face]@bary.T,20.))
            cycle_times.append(t);interface_cycles.append(np.where(birth.nodal_values[interface_face]<=level,temperature[interface_face],20.).copy())
        T=nodal_trace[-1][1].copy();time_s=resume_local
        birth.advance(cumulative_mass_g(resume_local)*1e-3)
        active=birth.moments.sum(axis=1)>1e-14
        np.testing.assert_allclose(birth.moments[m==3].sum(axis=1),nodal_trace[-1][2],atol=1e-10)
        input_data['transient_restart']=dict(source=str(transient_from),accepted_prefix_s=resume_local,
            prefix_dt_s=old_input['dt_s'],continuation_dt_s=a.dt,scope='same actual state; endpoint discretization comparison only')
        (out/'input.json').write_text(json.dumps(input_data,indent=2),encoding='utf8')
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
        if nodal_trace:
            path=out/'nodal-thermal-history'/('chunk-%04d.npz'%len(trace_chunks))
            np.savez_compressed(path,time_s=np.array([row[0] for row in nodal_trace]),
                temperature_C=np.array([row[1] for row in nodal_trace]),
                deposit_fraction=np.array([row[2] for row in nodal_trace]),front_level_rad=np.array([row[3] for row in nodal_trace]),
                deposit_element_indices=np.flatnonzero(m==3))
            trace_chunks.append(dict(file=path.name,first_s=nodal_trace[0][0],last_s=nodal_trace[-1][0],steps=len(nodal_trace)))
            nodal_trace.clear()
            (out/'nodal-thermal-history/manifest.json').write_text(json.dumps(dict(chunks=trace_chunks,
                scope='every accepted thermal increment; complete temperatures/deposit fraction, no reconstructed residual stress'),indent=2),encoding='utf8')
        np.savez_compressed(out/'thermal-fields.npz',x=x,e=e,material=m,temperature=T,peak_nodal_temperature=peak,
            thermal_active=active,interface_nodes=interface_face,interface_area_mm2=interface_area,interface_peak_C=interface_peak,
            tetra_quadrature_barycentric=tetra_bary,peak_element_quadrature_C=quadrature_peak,volume_mm3=volume,
            deposited_P1_moments=birth.moments if conservative else np.where(active[:,None],.25,0.)*np.ones((len(e),4)))
        np.savetxt(out/'thermal-history.csv',history,delimiter=',',comments='',header='t_s,dt_s,track,on,max_C,QT_max_C,Ni99_max_C,total_input_J,wire_J,loss_J,balance_J')
        if all_wings:
            np.savetxt(out/'boundary-history.csv',boundary_history,delimiter=',',comments='',
                header='t_s,dt_s,track,wing,arc_on,conditioning,environment_C,interface_min_C,interface_max_C,net_surface_outflow_J')
        np.savetxt(out/'source-partition-history.csv',[row for row in source_history if row[0]<=time_s+1e-10],delimiter=',',comments='',header='t_s,dt_s,track,born_volume_mm3,wire_J,command_J,arc_intercept_J,uncaptured_J,legacy_fullspace_capture,legacy_normalization_multiplier,arc_to_QT_J,arc_to_Ni_J')
        if conservative:
            np.savetxt(out/'deposition-history.csv',[row for row in birth_history if row[0]<=time_s+1e-10],delimiter=',',comments='',
                header='t_s,dt_s,target_step_g,actual_step_g,target_cumulative_g,actual_cumulative_g,entering_J,front_angle_rad,front_minus_source_mm,disconnected_deposit_mm3,active_Ni_volume_mm3,minimum_cut_fraction')
            (out/'nonlinear-diagnostics.json').write_text(json.dumps(solver_diagnostics,indent=2),encoding='utf8')
            np.savetxt(out/'source-path-history.csv',[row for row in source_path if row[0]<=time_s+1e-10],delimiter=',',comments='',
                header='t_s,theta_rad,x_mm,y_mm,z_mm,capacity_front_level_rad,QT_domain_mm3,Ni_domain_mm3,source_front_level_rad,source_Ni_domain_mm3')
        result=dict(partial=partial,error=error,time_s=time_s,stages=stage_rows,maximum_temperature_C=float(peak.max()),
            maximum_QT_C=float(peak[np.unique(e[m==1])].max()),elapsed_s=time.perf_counter()-started,
            nominal_interface_area_mm2=float(interface_area.sum()),actual_area_above_both_solidus_mm2=float(np.sum(interface_area*np.mean(interface_peak>=max(tab[1]['fusion_enthalpy']['solidus_C'],tab[3]['fusion_enthalpy']['solidus_C']),axis=1))),
            both_solidus_threshold_C=max(tab[1]['fusion_enthalpy']['solidus_C'],tab[3]['fusion_enthalpy']['solidus_C']),
            final_active_minimum_C=float(T[np.unique(e[active])].min()),
            active_temperature_range_check_pass=not error and all(row[4]<2800 for row in history),
            mesh_time_convergence_verified=False,PMZ_capacity_assigned=False)
        if mma and interface_cycles:
            np.savez_compressed(out/'interface-cycles.npz',time_s=np.array(cycle_times),face_nodes=interface_face,
                nodal_temperature_C=np.array(interface_cycles,dtype=np.float32))
        if observer.step:observer.save(partial=partial or bool(error))
        (out/('failure.json' if error else 'result.json')).write_text(json.dumps(result,indent=2),encoding='utf8')
        return result
    try:
        for k,track in enumerate(tracks):
            if k<completed:continue
            if all_wings and k:
                birth=ConservativeBirth(x,e,m,volume,rho,a.track_radius_mm,a.width,
                    deposit_mask=track['targets'],initial_moments=birth.moments,
                    angle_offset=track['angle_offset'])
            if conservative and (not k or all_wings):front=float(birth.lo.min()-1e-10)
            local=resume_local if k==0 else 0.;wait=0.;start=time_s-local;duration=track['arc_duration_s'];initial_max=a.initial_temperature if local else float(T[np.unique(e[active])].max())
            cool_target=(500. if k==len(tracks)-1 else 300.) if mma else 90.
            conditioning_time=0.;conditioning_log=[];arc_started=False
            if all_wings:
                current_faces=interface_face[np.any(np.isin(interface_face,np.unique(e[track['targets']])),axis=1)]
                current_nodes=np.unique(current_faces)
                if not len(current_nodes):raise RuntimeError('current wing interface temperature check has no nodes')
            while local<duration-1e-8 or T[np.unique(e[active])].max()>cool_target:
                conditioning=all_wings and not arc_started and (T[current_nodes].min()<200. or T[current_nodes].max()>300.+1e-6)
                ambient=300. if conditioning and T[current_nodes].min()<200. else 20.
                on=local<duration-1e-8 and not conditioning
                dt=min(a.dt,duration-local) if on else min(10.,1800-conditioning_time) if conditioning else min(2.,1800-wait)
                if on and not arc_started:
                    arc_started=True
                    if all_wings:
                        start=time_s
                        initial_max=float(T[current_nodes].max())
                        conditioning_log.append(dict(arc_start_s=time_s,interface_min_C=float(T[current_nodes].min()),interface_max_C=initial_max))
                if on:
                    if a.start_ramp+a.end_ramp>=duration:raise ValueError('arc ramps leave no steady interval')
                    ramps=np.array([a.start_ramp,duration-a.end_ramp,duration]);future=ramps[ramps>local+1e-8]
                    dt=min(dt,float(future.min()-local))
                if getattr(a,'stop_time_s',None) is not None:dt=min(dt,a.stop_time_s-time_s)
                if dt<=1e-8:raise RuntimeError('whole-seat cooling did not reach90 C within1800 s')
                old=T.copy();previous=active.copy()
                if on and not conservative:
                    direction=1 if track['angle_end']>track['angle_begin'] else -1
                    reached=track['angle_begin']+direction*a.travel*(local+dt)/track['radius_mm']
                    if mma:
                        # Swept-front cell activation uses the first intersected
                        # vertex, not a centroid that can leave whole extrusion
                        # columns unsupported. This is a mesh-dependent birth
                        # approximation and is checked with mesh refinement.
                        node_angle=np.arctan2(x[e,1],x[e,0])
                        arrival=node_angle.min(axis=1) if direction>0 else node_angle.max(axis=1)
                        active |= track['targets']&(direction*(arrival-reached)<=1e-10)
                    else:active |= track['targets']&(direction*(angle-reached)<=1e-10)
                    if mma:
                        # A centroid cut on an unstructured extrusion can create
                        # floating hot tetrahedra above still-unborn substrate
                        # metal. Deposit only the face-connected pool; delayed
                        # elements remain eligible when the front reaches them.
                        from scipy.sparse.csgraph import connected_components
                        edge=two&active[oa]&active[np.maximum(ob,0)]
                        aa,bb=oa[edge],ob[edge]
                        graph=coo_matrix((np.ones(2*len(aa)),(np.r_[aa,bb],np.r_[bb,aa])),shape=(len(e),len(e))).tocsr()
                        _,labels=connected_components(graph,directed=False)
                        active &= np.isin(labels,np.unique(labels[m==1]))
                if conservative:
                    if on:
                        target=min(cumulative_mass_g(local+dt)*1e-3,birth.total_mass_kg)
                        old_mom,mom,delta_mom,factor,cut_centre,front=birth.advance(target)
                        active=factor>1e-14
                    else:
                        mom=birth.moments.copy();old_mom=mom.copy();delta_mom=np.zeros_like(mom)
                        factor=mom.sum(axis=1);cut_centre=centre.copy()
                    # Homogenize the unresolved partial volume in its parent
                    # cell. Total mass is unchanged. Exact cut nodal moments
                    # on unextended parent DOFs produced nonphysical front
                    # temperatures and are retained only as geometric data.
                    nodal_mass=np.repeat((rho*volume*(factor+(1-factor)*1e-8)/4)[:,None],4,axis=1)
                    old_fraction=old_mom.sum(axis=1)
                    old_nodal_mass=np.repeat((rho*volume*(old_fraction+(1-old_fraction)*1e-8)/4)[:,None],4,axis=1)
                    born=(delta_mom.sum(axis=1)>1e-14)&(m==3)
                    born_volume=float(volume@delta_mom.sum(axis=1))
                else:
                    born=active&~previous;factor=np.where(active,1.,1e-8)
                    nodal_mass=np.repeat((rho*volume*factor/4)[:,None],4,axis=1)
                    old_nodal_mass=nodal_mass.copy();old_nodal_mass[born]=0.
                    born_volume=float(volume[born].sum())
                extension=None
                if conservative:
                    from scipy.spatial import cKDTree
                    supported=np.unique(e[active])
                    parent_nodes=np.unique(e[m==1])
                    present_nodes=np.union1d(parent_nodes,supported[birth.nodal_values[supported]<=front])
                    ghost=np.setdiff1d(supported,present_nodes)
                    mapping=np.arange(n)
                    if len(ghost):
                        _,nearest=cKDTree(x[present_nodes]).query(x[ghost])
                        mapping[ghost]=present_nodes[nearest]
                    dofs,inverse=np.unique(mapping,return_inverse=True)
                    extension=coo_matrix((np.ones(n),(np.arange(n),inverse)),shape=(n,len(dofs))).tocsr()
                    T=extension@T[dofs]
                gram=np.einsum('eik,ejk->eij',g,g)
                ke=gram*(prop(T[e].mean(axis=1),'thermal_conductivity_w_mk')/1000*volume*factor)[:,None,None]
                K=coo_matrix((ke.ravel(),(rr,cc)),shape=(n,n)).tocsr()
                wet=active[oa]^((ob>=0)&active[np.maximum(ob,0)])
                surface=birth.surface(x,e,face,oa,ob,area,front) if conservative else np.bincount(face[wet].ravel(),weights=np.repeat(area[wet]/3,3),minlength=n)
                radiation=.7*5.670374419e-14*((np.maximum(T,20)+273.15)**2+293.15**2)*(np.maximum(T,20)+566.3)
                cooling=(15e-6+radiation)*surface
                entering=float(wire_energy@delta_mom.sum(axis=1)) if conservative else float(wire_energy[born].sum());q=np.zeros(n)
                if on:
                    midpoint=local+dt/2;fraction=1.
                    if a.start_ramp and midpoint<a.start_ramp:fraction=a.start_fraction+(1-a.start_fraction)*midpoint/a.start_ramp
                    if a.end_ramp and duration-midpoint<a.end_ramp:fraction=min(fraction,end_fraction+(1-end_fraction)*(duration-midpoint)/a.end_ramp)
                    remaining=a.power*fraction-entering/dt
                    if remaining<0:raise RuntimeError('hot first-layer birth exceeds the same net power budget')
                    direction=1 if track['angle_end']>track['angle_begin'] else -1
                    theta=track['angle_begin']+direction*a.travel*(local+dt/2)/track['radius_mm'];source=[track['radius_mm']*np.cos(theta),track['radius_mm']*np.sin(theta),top-a.source_drop]
                    source_factor=factor;source_centre=cut_centre if conservative else centre;source_front=front if conservative else None
                    if conservative:
                        _,source_factor,source_centre,source_front=birth.at_mass(cumulative_mass_g(midpoint)*1e-3)
                    if conservative and bottom_up:
                        source[2]=float(np.clip(birth.floor+(birth.top-birth.floor)*(source_front-theta+track.get('angle_offset',0.))*track['radius_mm']/a.width,birth.floor,birth.top))
                    d=source_centre-source;w=np.exp(-(d[:,0]**2+d[:,1]**2)/a.width**2-(d[:,2]/a.depth)**2)*volume*(source_factor if conservative else active)
                    fullspace=np.pi**1.5*a.width**2*a.depth
                    capture=float(w.sum()/fullspace)
                    if a.source_model in ('volume','mma_volume'):
                        if a.source_model=='mma_volume':
                            # Prescribed NET absorbed power (El-Banna Table3),
                            # not incident beam power. The effective pool source
                            # must integrate to the stated net budget. Shape and
                            # required electric power are separate assumptions.
                            w*=d[:,2]<=0
                            if w.sum()<=0:raise RuntimeError('No material supports the net distributed source')
                            p=w/w.sum()*remaining
                        else:p=w/w.sum()*remaining
                        load_mom=np.full((len(e),4),.25)
                        q=np.bincount(e.ravel(),weights=(p[:,None]*load_mom).ravel(),minlength=n)
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
                    if conservative:source_path.append([time_s+dt,theta,*source,front,float((volume*factor)[m==1].sum()),float((volume*factor)[m==3].sum()),source_front,float((volume*source_factor)[m==3].sum())])
                    if mma and arc>remaining*1.02:raise RuntimeError('source volume quadrature exceeds fixed analytic total')
                    source_history.append([time_s+dt,dt,k+1,born_volume,entering,command,arc*dt,
                                           (remaining-arc)*dt,capture,1/capture,arc_QT*dt,arc_Ni*dt])
                    wire_load=np.repeat((wire_energy*delta_mom.sum(axis=1)/(4*dt))[:,None],4,axis=1) if conservative else np.where(born[:,None],wire_energy[:,None]/(4*dt),0.)*np.ones((len(e),4))
                    q+=np.bincount(e.ravel(),weights=wire_load.ravel(),minlength=n)
                    if conservative:
                        from scipy.sparse.csgraph import connected_components
                        af=birth.nodal_values[face]
                        edge=two&active[oa]&active[np.maximum(ob,0)]&(af.min(axis=1)<front)
                        aa,bb=oa[edge],ob[edge]
                        graph=coo_matrix((np.ones(2*len(aa)),(np.r_[aa,bb],np.r_[bb,aa])),shape=(len(e),len(e))).tocsr()
                        _,labels=connected_components(graph,directed=False)
                        connected=np.isin(labels,np.unique(labels[m==1]))
                        disconnected=float(np.sum(volume[(m==3)&~connected]*factor[(m==3)&~connected]))
                        step_mass=float((rho*volume)@delta_mom.sum(axis=1))*1000
                        total_mass=float((rho*volume*(m==3))@factor)*1000
                        prior_mass=k*prescribed_mass*1000 if all_wings else 0.
                        birth_history.append([time_s+dt,dt,cumulative_mass_g(local+dt)-cumulative_mass_g(local),step_mass,prior_mass+cumulative_mass_g(local+dt),total_mass,
                            entering,front,(front-theta)*track['radius_mm'],disconnected,float((volume*(m==3))@factor),float(factor[(m==3)&active].min())])
                        if disconnected>1e-8:raise RuntimeError('cut deposit not face-connected to QT')
                old_H=np.bincount(e.ravel(),weights=(old_nodal_mass*integral(old[e])).ravel(),minlength=n)
                def enthalpy(values):
                    point=values[e];H=np.bincount(e.ravel(),weights=(nodal_mass*integral(point)).ravel(),minlength=n)
                    cp=prop(point,'specific_heat_j_kgk')+melting(point,derivative=True)
                    C=np.bincount(e.ravel(),weights=(nodal_mass*cp).ravel(),minlength=n)
                    return H,C
                def conduction(values,tangent=False):
                    means=values[e].mean(axis=1)
                    def conductivity(temperatures):
                        liquid=np.clip((temperatures-solidus[:,0])/(liquidus[:,0]-solidus[:,0]),0,1)
                        if curve:liquid[m==3]=np.interp(temperatures[m==3],phase_T,phase_q)
                        return prop(temperatures,'thermal_conductivity_w_mk')/1000*(1+(getattr(a,'liquid_transport_factor',1.)-1)*liquid)
                    cond=conductivity(means)
                    local_k=gram*(cond*volume*factor)[:,None,None]
                    stiffness=coo_matrix((local_k.ravel(),(rr,cc)),shape=(n,n)).tocsr()
                    if not tangent:return stiffness
                    derivative=(conductivity(means+.01)-conductivity(means-.01))/.02
                    gradient=np.einsum('eik,ei->ek',g,values[e])
                    extra=np.einsum('eik,ek->ei',g,gradient)*(derivative*volume*factor/4)[:,None]
                    jac=stiffness+coo_matrix((np.repeat(extra[:,:,None],4,axis=2).ravel(),(rr,cc)),shape=(n,n)).tocsr()
                    return stiffness,jac
                def heat_loss(values,derivative=False):
                    if derivative:return surface*(15e-6+.7*5.670374419e-14*4*(values+273.15)**3)
                    return surface*(15e-6*(values-ambient)+.7*5.670374419e-14*((values+273.15)**4-(ambient+273.15)**4))
                def residual(values,H):
                    return H-old_H+dt*((conduction(values)@values+heat_loss(values) if conservative else K@values+cooling*(values-20))-q)
                for iteration in range(45):
                    H,C=enthalpy(T);r=residual(T,H)
                    if conservative:r=extension.T@r
                    if np.linalg.norm(r)<1e-5:break
                    if conservative:
                        _,jac=conduction(T,True)
                        A=diags(C+dt*heat_loss(T,True))+dt*jac
                    else:A=diags(C+dt*cooling)+dt*K
                    if conservative:A=(extension.T@A@extension).tocsr()
                    delta=pypardiso.spsolve(A if conservative else triu(A,format='csr'),-r,solver=engine)
                    if np.linalg.norm(A@delta+r)>.001:raise RuntimeError('precoat linear residual exceeds0.001')
                    full_delta=extension@delta if conservative else delta
                    for power in range(12):
                        candidate=T+full_delta*.5**power
                        if conservative and candidate.min()<=-273.15:continue
                        ch,_=enthalpy(candidate);candidate_residual=residual(candidate,ch)
                        if conservative:candidate_residual=extension.T@candidate_residual
                        if np.linalg.norm(candidate_residual)<np.linalg.norm(r):T=candidate;break
                    else:
                        solver_diagnostics.append(dict(t_s=time_s,trial_dt_s=dt,iteration=iteration,residual_norm_J=float(np.linalg.norm(r)),
                            delta_norm_C=float(np.linalg.norm(delta)),minimum_C=float(T.min()),maximum_C=float(T.max()),
                            tangent_directional_relative_error=None))
                        raise RuntimeError('precoat enthalpy line search failed')
                else:raise RuntimeError('precoat enthalpy Newton failed')
                time_s+=dt
                if on:local+=dt
                elif conditioning:conditioning_time+=dt
                else:wait+=dt
                peak=np.maximum(peak,T);both=active[oa[interface]]&active[ob[interface]]
                present=both[:,None] if not conservative else both[:,None]&(birth.nodal_values[interface_face]@bary.T<=front)
                interface_peak=np.maximum(interface_peak,np.where(present,T[interface_face]@bary.T,20.))
                qp_present=active[:,None] if not conservative else active[:,None]&((m!=3)[:,None]|(birth.nodal_values[e]@tetra_bary.T<=front))
                quadrature_peak=np.maximum(quadrature_peak,np.where(qp_present,T[e]@tetra_bary.T,20.))
                observer(time_s,T,active,birth.nodal_values if conservative else None,front if conservative else None)
                if mma:
                    nodal_present=both[:,None] if not conservative else both[:,None]&(birth.nodal_values[interface_face]<=front)
                    cycle_times.append(time_s);interface_cycles.append(np.where(nodal_present,T[interface_face],20.).copy())
                loss=dt*float(heat_loss(T).sum()) if conservative else dt*float(cooling@(T-20))
                balance=float((H-old_H).sum())+loss-dt*float(q.sum())
                history.append([time_s,dt,k+1,int(on),float(T[np.unique(e[active])].max()),float(T[np.unique(e[m==1])].max()),float(T[np.unique(e[(m==3)&active])].max()) if np.any((m==3)&active) else 20.,dt*float(q.sum()),entering,loss,balance])
                if all_wings:boundary_history.append([time_s,dt,k+1,track['wing'],int(on),int(conditioning),ambient,float(T[current_nodes].min()),float(T[current_nodes].max()),loss])
                if record_nodal:nodal_trace.append((time_s,T.copy(),factor[m==3].copy(),front if conservative else None))
                if conservative:
                    (out/'progress.json').write_text(json.dumps(dict(t_s=time_s,track=k+1,arc_on=on,maximum_C=history[-1][4],
                        deposited_g=birth_history[-1][5] if birth_history else 0.,enthalpy_residual_norm_J=float(np.linalg.norm(r)),
                        source_xyz_mm=source if on else None)),encoding='utf8')
                if conservative and T[np.unique(e[active])].min()<20.-1e-4:
                    raise RuntimeError('active temperature below initial environment; cell occupancy discretization violates thermal minimum principle')
                if history[-1][4]>=2800:
                    raise RuntimeError('active temperature exceeds2800 C conservative guard below Ni boiling; vaporization is outside this enthalpy model')
                if getattr(a,'stop_time_s',None) is not None and time_s>=a.stop_time_s-1e-10:
                    result=save(True);print(json.dumps(result,indent=2),flush=True);return result
                if len(history)%25==0:
                    save(True);print('first Ni99',k+1,round(time_s,3),round(history[-1][4],2),flush=True)
            stage_rows.append(dict(track=k+1,start_s=start,initial_max_C=initial_max,arc_s=duration,cool_wait_s=wait,end_s=time_s,
                end_active_max_C=float(T[np.unique(e[active])].max()),born_volume_mm3=float(volume[active&(m==3)].sum())))
            if all_wings:stage_rows[-1].update(wing=track['wing'],conditioning_s=conditioning_time,process_temperature_checks=conditioning_log)
            save(True)
            if a.stop_after_tracks is not None and k+1>=a.stop_after_tracks:
                result=save(True);print(json.dumps(result,indent=2),flush=True);return result
        if not active.all():raise RuntimeError('first-layer tracks did not cover all actual wing elements')
        result=save(False);print(json.dumps(result,indent=2),flush=True);return result
    except Exception as exc:
        if conservative and source_history and source_history[-1][0]>time_s+1e-10:
            np.savez_compressed(out/'failed-trial-fields.npz',temperature=T,deposited_P1_moments=birth.moments,
                accepted_time_s=time_s,trial_time_s=source_history[-1][0])
            (out/'failed-trial-input.json').write_text(json.dumps(dict(source_row=source_history[-1],birth_row=birth_history[-1]),indent=2),encoding='utf8')
            T=old.copy();active=previous.copy();birth.moments=old_mom.copy()
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
