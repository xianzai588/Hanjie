"""Replay actual saved temperatures/deposition; optionally append the furnace."""
import argparse
import json
import time
import numpy as np
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT
from precoat_solid_mechanics import SolidMechanics


def run(source,output,furnace=None,stop_time=None,phase_method='exact_P1',checkpoint=None,interface_policy='chronological',furnace_increment=12.5,solver_threads=1):
    if (output/'input.json').exists():raise ValueError('Preserve mechanical replay evidence')
    output.mkdir(exist_ok=True,parents=True)
    inputs=json.loads((source/'input.json').read_text())
    with np.load(source/'thermal-fields.npz') as f:
        x,e,m,volume=f['x'],f['e'],f['material'],f['volume_mm3']
        source_material_mass=f['material_mass_kg'].copy() if 'material_mass_kg' in f else None
    mechanics=SolidMechanics(x,e,m,volume,inputs,phase_method,interface_policy)
    if source_material_mass is not None:mechanics.material_mass_kg=source_material_mass
    if interface_policy=='chronological':
        with np.load(source/'interface-cycles.npz') as f:
            if not np.array_equal(mechanics.fusion_faces,f['face_nodes']):raise ValueError('Chronological fusion face order mismatch')
            fusion_times=f['time_s'].copy();fusion_history=f['nodal_temperature_C'].min(axis=2)>=mechanics.fusion_threshold_C
    (output/'input.json').write_text(json.dumps(dict(source=str(source),furnace=str(furnace) if furnace else None,
        material_reference=mechanics.reference_input,phase_method=phase_method,interface_policy=interface_policy,
        mechanical_step_policy='all deposition increments; source cooling max nodal change12.5C or60s; fully solid rate-independent furnace max nodal change at specified increment plus hold/ramp/final events',
        furnace_temperature_increment_C=furnace_increment,furnace_time_policy_basis='reference elastoplastic model contains no creep/time-rate term; temperature increments and process events govern furnace path resolution',
        solver_threads=solver_threads,
        accepted_checkpoint_source=str(checkpoint) if checkpoint else None,
        no_uniform_annealing_reset=True,scope='solid manufacturing demand; PMZ fracture capacity separate'),ensure_ascii=False,indent=2),encoding='utf8')
    clock=time.perf_counter();previous=np.full(len(x),inputs['cold_start_C']);old_occupation=np.isin(m,mechanics.preexisting_material_ids).astype(float)
    last_time=0.;last_record=None;step=0
    if not checkpoint and inputs.get('initial_state_path'):
        initial_path=ROOT/inputs['initial_state_path']
        with np.load(initial_path) as f:
            if not np.array_equal(f['x'],x) or not np.array_equal(f['e'],e):raise ValueError('Inherited second-layer mesh mismatch')
            for key,field in [('plastic','plastic'),('eqp','eqp'),('reference','solid_reference_strain'),
                              ('solid_weight','solid_weight'),('stress','stress'),('remelted','remelted_QT')]:
                setattr(mechanics,key,f[field].copy())
            mechanics.u=f['u'][mechanics.thermal_origin].ravel().copy()
            previous=f['temperature_C'].copy();old_occupation=f['occupation'].copy()
        mechanics.previous_actual_temperature=previous[mechanics.thermal_origin].copy()
        mechanics.previous_occupation=old_occupation.copy()
        mechanics.advance(0.,previous,old_occupation,np.zeros(len(mechanics.fusion_faces),bool))
        mechanics.save(output/'initial-re-equilibration',0.,previous,old_occupation,True)
    if checkpoint:
        checkpoint_input=json.loads((checkpoint/'input.json').read_text())
        checkpoint_result=json.loads((checkpoint/'result.json').read_text())
        if checkpoint_input['material_reference']!=mechanics.reference_input or 'carried mass' not in checkpoint_result['source_state_policy']:
            raise ValueError('Replay checkpoint material reference differs from current specific-volume policy')
        with np.load(checkpoint/'fields.npz') as f:
            if not np.array_equal(f['e'],mechanics.e) or not np.array_equal(f['x'],mechanics.x):raise ValueError('Replay checkpoint mesh mismatch')
            for key,field in [('u','u'),('plastic','plastic'),('eqp','eqp'),('reference','solid_reference_strain'),
                              ('solid_weight','solid_weight'),('stress','stress'),('remelted','remelted_QT')]:
                value=f[field].copy();setattr(mechanics,key,value.ravel() if key=='u' else value)
            last_time=float(f['time_s']);previous=f['thermal_source_temperature_C'].copy() if 'thermal_source_temperature_C' in f else f['temperature_C'].copy();old_occupation=f['occupation'].copy()
            if interface_policy=='chronological':mechanics.fused_faces=f['fused_faces'].copy()
            if 'current_bond_pairs' in f:mechanics.current_bond_pairs=f['current_bond_pairs'].copy()
            if 'bonded_faces' in f:mechanics.bonded_faces=f['bonded_faces'].copy()
            if len(mechanics.current_bond_pairs) and 'preclosure configuration' not in checkpoint_result.get('coherent_reference_initialization_order',''):
                raise ValueError('Joined checkpoint initialized new-solid shear after the closure snap; preserve it as a diagnostic and restart before joining')
            if 'material_mass_kg' in f:mechanics.material_mass_kg=f['material_mass_kg'].copy()
            mechanics.previous_actual_temperature=previous[mechanics.thermal_origin].copy()
            mechanics.previous_occupation=old_occupation.copy()
        recovered_record=None
        for folder in [source]+([furnace] if furnace and (furnace/'nodal-thermal-history/manifest.json').exists() else []):
            manifest=json.loads((folder/'nodal-thermal-history/manifest.json').read_text())
            for chunk in manifest['chunks']:
                if not chunk['first_s']-1e-8<=last_time<=chunk['last_s']+1e-8:continue
                with np.load(folder/'nodal-thermal-history'/chunk['file']) as data:
                    selected=np.flatnonzero(abs(data['time_s']-last_time)<1e-8)
                    if len(selected):
                        j=selected[0];indices=data['deposit_element_indices']
                        actual_occupation=np.ones(len(e));actual_occupation[indices]=data['deposit_fraction'][j]
                        recovered_record=(data['temperature_C'][j].copy(),actual_occupation)
        if recovered_record is None or not np.allclose(recovered_record[0],previous,rtol=0,atol=1e-8) or not np.allclose(recovered_record[1],old_occupation,rtol=0,atol=1e-10):
            raise ValueError('Checkpoint is not the same accepted nodal-temperature/deposition state of this actual process')
        (output/'accepted-state-recovery.json').write_text(json.dumps(dict(time_s=last_time,
            maximum_temperature_difference_C=float(abs(recovered_record[0]-previous).max()),
            maximum_occupation_difference=float(abs(recovered_record[1]-old_occupation).max()),
            same_accepted_state=True,material_history_reset=False),indent=2),encoding='utf8')
        mechanics.history=np.loadtxt(checkpoint/'equilibrium-history.csv',delimiter=',',skiprows=1,ndmin=2).tolist()
        mechanics.maximum_residual=max(row[2] for row in mechanics.history)
        mechanics.total_iterations=int(sum(row[1] for row in mechanics.history))
        checkpoint_time=last_time
    else:checkpoint_time=-1.
    for folder in [source]+([furnace] if furnace else []):
        in_furnace=folder==furnace
        events=[]
        if in_furnace:
            furnace_input=json.loads((folder/'input.json').read_text())
            start=furnace_input['source_end_s'];hold=furnace_input['hold_duration_s'];ramp=furnace_input['ramp_duration_s']
            events=[start+hold,start+hold+ramp]
        manifest=json.loads((folder/'nodal-thermal-history/manifest.json').read_text())
        for chunk in manifest['chunks']:
            with np.load(folder/'nodal-thermal-history'/chunk['file']) as data:
                for j,t in enumerate(data['time_s']):
                    if t<=checkpoint_time+1e-9:continue
                    temperature=data['temperature_C'][j];occupation=np.ones(len(e))
                    deposit_indices=data['deposit_element_indices'] if 'deposit_element_indices' in data else np.flatnonzero(np.isin(m,mechanics.deposition_material_ids))
                    occupation[deposit_indices]=data['deposit_fraction'][j]
                    last_record=(float(t),temperature.copy(),occupation.copy())
                    birth=bool(np.max(abs(occupation-old_occupation))>1e-12)
                    mandatory=stop_time is not None and t>=stop_time-1e-9
                    process_event=any(abs(t-event)<1e-8 for event in events)
                    temperature_limit=furnace_increment if in_furnace else 12.5
                    if birth or abs(temperature-previous).max()>temperature_limit or (not in_furnace and t-last_time>=60) or process_event or mandatory:
                        checkpoint={key:getattr(mechanics,key).copy() for key in ('u','plastic','eqp','reference','solid_weight','stress','remelted')}
                        if interface_policy=='chronological':
                            q=np.searchsorted(fusion_times,t+1e-8,side='right');fused=fusion_history[:q].any(axis=0)
                            checkpoint['fused_faces']=mechanics.fused_faces.copy()
                            checkpoint['bonded_faces']=mechanics.bonded_faces.copy()
                            checkpoint['current_bond_pairs']=mechanics.current_bond_pairs.copy()
                        else:fused=None
                        try:row=mechanics.advance(float(t),temperature,occupation,fused)
                        except Exception as error:
                            mechanics.save(output/'failed-trial',float(t),temperature,occupation,True)
                            for key,value in checkpoint.items():setattr(mechanics,key,value)
                            mechanics.save(output,last_time,previous,old_occupation,True)
                            (output/'failure.json').write_text(json.dumps(dict(trial_s=float(t),last_accepted_s=last_time,error=str(error)),indent=2),encoding='utf8')
                            raise
                        previous=temperature.copy();old_occupation=occupation.copy();last_time=float(t);step+=1
                        if step%5==0:
                            mechanics.save(output,last_time,temperature,occupation,True)
                            print('solid',step,round(t,3),row[1],round(row[2],5),round(time.perf_counter()-clock,1),flush=True)
                    if mandatory:
                        final=mechanics.save(output,float(t),temperature,occupation,True)
                        print(json.dumps(final,ensure_ascii=False,indent=2));return
    if last_record is None:raise ValueError('No actual nodal history found')
    t,temperature,occupation=last_record
    if last_time!=t:mechanics.advance(t,temperature,occupation,fusion_history.any(axis=0) if interface_policy=='chronological' else None)
    final=mechanics.save(output,t,temperature,occupation,False)
    print(json.dumps(final,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=lambda s:ROOT/s,required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True)
    p.add_argument('--furnace',type=lambda s:ROOT/s)
    p.add_argument('--stop-time',type=float)
    p.add_argument('--phase-method',choices=['cell_mean','exact_P1'],default='exact_P1')
    p.add_argument('--checkpoint',type=lambda s:ROOT/s)
    p.add_argument('--interface-policy',choices=['chronological','conformal'],default='chronological')
    p.add_argument('--furnace-temperature-increment',type=float,default=12.5)
    p.add_argument('--threads',type=int,choices=[1,2,4,8],default=1)
    a=p.parse_args()
    with threadpool_limits(limits=a.threads):run(a.source,a.output,a.furnace,a.stop_time,a.phase_method,a.checkpoint,a.interface_policy,a.furnace_temperature_increment,a.threads)
