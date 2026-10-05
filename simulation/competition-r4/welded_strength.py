"""Same-mesh residual/service tensor and mixed-mode connection assessment.

Elastic trial screening is intentionally separated from proof of nonlinear
service admissibility. A trial exceeding cold yield requires a stateful
elastic-plastic service solve; it is never clipped to obtain a passing gate.
No wrought-nickel or all-weld-metal value is assigned to an unverified PMZ.
"""
from pathlib import Path
import argparse,json
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import lsmr
from threadpoolctl import threadpool_limits

OUT=Path(__file__).parent/'results'
ROOT=Path(__file__).resolve().parents[2]
PV=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3


def vm(stress):
    return np.sqrt(1.5*np.sum((stress-stress@PV)**2,axis=-1))


def mixed_mode(traction,normal,tensile_capacity,shear_capacity,compression_capacity):
    """Same-point quadratic traction interaction with unilateral opening."""
    normal_value=np.sum(traction*normal,axis=1)
    shear=np.linalg.norm(traction-normal_value[:,None]*normal,axis=1)
    opening=np.maximum(normal_value,0)
    compression=np.maximum(-normal_value,0)
    interaction=(opening/tensile_capacity)**2+(shear/shear_capacity)**2
    return interaction,compression/compression_capacity,normal_value,shear


def recover_residual_interface(fields,folder):
    from run_verified import operators
    x,e=fields['x'],fields['e'];nn=len(x)
    _,vol,B,dof=operators(x,e)
    fi=np.einsum('eji,ej,e->ei',B,fields['stress'],vol)
    force=np.bincount(dof.ravel(),weights=fi.ravel(),minlength=3*nn).reshape(nn,3)
    nodes,weights=fields['link_nodes'],fields['link_weights']
    L=coo_matrix((weights.ravel(),(np.repeat(np.arange(len(nodes)),nodes.shape[1]),nodes.ravel())),shape=(len(nodes),nn)).tocsr()
    release=json.loads((folder/'free-release-verification.json').read_text(encoding='utf8'))
    gauge=np.array(release['remaining_gauge_dofs']);recovered=np.empty((len(nodes),3));errors=[]
    for axis in range(3):
        free=np.setdiff1d(np.arange(nn),gauge[gauge%3==axis]//3)
        A=L[:,free].T.tocsr();rhs=-force[free,axis]
        sol=lsmr(A,rhs,atol=1e-13,btol=1e-13,maxiter=8000)
        recovered[:,axis]=sol[0];errors.append(float(np.linalg.norm(A@sol[0]-rhs)))
    return recovered,errors


def evaluate_case(case,basis):
    folder=OUT/case
    missing=[n for n in ('free-release-fields.npz','free-release-verification.json',
        'service-area-fields.npz','interface-service-demand.npz') if not (folder/n).exists()]
    if missing:return dict(case=case,complete=False,missing=missing)
    with np.load(folder/'free-release-fields.npz') as f:fields={k:f[k] for k in f.files}
    with np.load(folder/'mesh.npz') as mesh:
        same=all(np.array_equal(fields[k],mesh[k]) for k in ('x','e','material','link_nodes','link_weights'))
    with np.load(folder/'service-area-fields.npz') as sf:
        service=sf['service_stress_Mandel_MPa'];cyclic=sf['continuous_amplitude_stress_Mandel_MPa']
    if not same or service.shape!=fields['stress'].shape:
        return dict(case=case,complete=False,reason='residual/service tensor meshes differ; field interpolation is not authorised')
    inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    measure=json.loads((folder/'measurement.json').read_text(encoding='utf8'))
    release=json.loads((folder/'free-release-verification.json').read_text(encoding='utf8'))
    # The 1.5 safety factor multiplies applied service load. Self-equilibrated
    # residual stress remains a physical initial state, not a second load.
    tensors=[fields['stress']+1.5*service,
             fields['stress']+service+cyclic,fields['stress']+service-cyclic]
    equivalent=np.max([vm(s) for s in tensors],axis=0)
    material=fields['material'];zones={};yield_values=[]
    for j,name in enumerate(('Q235','QT','NiFe')):
        table=inp['materials'][j];tab=table['temperature_dependent']
        yield_value=float(np.interp(20.,tab['temperatures_c'],tab['yield_strength_mpa']))
        yield_values.append(yield_value)
        peak=float(equivalent[material==j].max())
        zones[name]=dict(maximum_trial_combined_VM_MPa=peak,cold_yield_MPa=yield_value,
            elastic_admissibility_pass=peak<=yield_value)
    residual_force,recovery_errors=recover_residual_interface(fields,folder)
    with np.load(folder/'interface-service-demand.npz') as demand:
        area=demand['area_mm2'];service_traction=demand['traction_MPa'];cast=demand['is_QT_interface'];xyz=demand['xyz']
    # extract_interface_demand reports force ON the master in its signed jump
    # convention. For opening, orient from master/weld into the host; an axial
    # QT opening is positive jump_z, while radial steel opening is negative.
    residual_traction=residual_force/area[:,None]
    combined=residual_traction+1.5*service_traction
    outputs={}
    for name,mask in [('QT_Ni99_transition',cast),('Q235_NiFe',~cast)]:
        normal=np.tile([0.,0.,1.],(int(mask.sum()),1)) if name.startswith('QT') else -xyz[mask].copy()
        if not name.startswith('QT'):
            normal[:,2]=0;normal/=np.linalg.norm(normal,axis=1)[:,None]
        t=combined[mask];n=(t*normal).sum(axis=1);tau=np.linalg.norm(t-n[:,None]*normal,axis=1)
        # Demand-only equivalent is reported even when capacities are missing.
        equiv=np.sqrt(np.maximum(n,0)**2+3*tau**2)
        cap=basis.get('interfaces',{}).get(name,{})
        valid=all(isinstance(cap.get(k),(int,float)) and cap[k]>0 for k in (
            'tensile_capacity_MPa','shear_capacity_MPa','compression_capacity_MPa'))
        valid=valid and cap.get('applicable_to_current_process') is True and bool(cap.get('source'))
        output=dict(maximum_opening_MPa=float(np.maximum(n,0).max()),maximum_compression_MPa=float(np.maximum(-n,0).max()),
            maximum_shear_MPa=float(tau.max()),minimum_required_ductile_yield_MPa=float(equiv.max()),
            capacity_basis=cap,capacity_basis_applicable=valid,mixed_mode_design_pass=False)
        if valid:
            interaction,compression,_,_=mixed_mode(t,normal,cap['tensile_capacity_MPa'],cap['shear_capacity_MPa'],cap['compression_capacity_MPa'])
            i=int(np.argmax(interaction));output.update(maximum_interaction=float(interaction[i]),
                maximum_compression_utilization=float(compression.max()),hotspot_xyz_mm=xyz[mask][i].tolist(),
                hotspot_opening_MPa=float(max(n[i],0)),hotspot_shear_MPa=float(tau[i]),
                mixed_mode_design_pass=bool(interaction.max()<=1 and compression.max()<=1))
        outputs[name]=output
    thermal=measure.get('final_max_C',999)<=20.5 and release.get('free_shell_release_pass') is True
    return dict(case=case,complete=True,input=inp,initial_bore_diameter_mm=inp['initial_bore_diameter_mm'],
        tensor_method='same element Mandel tensor; residual + 1.5 service; residual + service +/- cyclic amplitude; no scalar VM addition',
        cold_residual_state_pass=bool(thermal),same_mesh_tensor_combination_pass=bool(same),
        retained_plastic_state=dict(maximum_eqp=float(fields['eqp'].max()),
            maximum_plastic_tensor_norm=float(np.linalg.norm(fields['plastic'],axis=1).max())),
        interface_force_recovery_residual_N=recovery_errors,interface_recovery_pass=max(recovery_errors)<.05,
        bulk_zones=zones,combined_bulk_strength_pass=all(z['elastic_admissibility_pass'] for z in zones.values()),
        interfaces=outputs,both_interfaces_mixed_mode_pass=all(o['mixed_mode_design_pass'] for o in outputs.values()),
        nonlinear_service_required=any(not z['elastic_admissibility_pass'] for z in zones.values()),
        scope='elastic trial on inherited cold stress/plastic state; explicit Ni99/PMZ assessment and local fusion evidence remain separate')


def main(cases):
    path=ROOT/'project/connection-strength-basis.json'
    basis=json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
    rows=[evaluate_case(c,basis) for c in cases]
    complete=all(r.get('complete') for r in rows)
    checks=dict(cold_residual_state_pass=complete and all(r['cold_residual_state_pass'] for r in rows),
        same_mesh_tensor_combination_pass=complete and all(r['same_mesh_tensor_combination_pass'] for r in rows),
        load_and_geometry_pass=complete and len({r['initial_bore_diameter_mm'] for r in rows})==1 and
            all(r['input']['seat_geometry']==rows[0]['input']['seat_geometry'] and r['input']['materials']==rows[0]['input']['materials'] for r in rows),
        combined_bulk_strength_pass=complete and all(r['combined_bulk_strength_pass'] for r in rows),
        Ni99_layer_strength_pass=False,QT_PMZ_strength_pass=False,
        both_interfaces_mixed_mode_pass=complete and all(r['both_interfaces_mixed_mode_pass'] and r['interface_recovery_pass'] for r in rows),
        spatial_and_time_precision_pass=False,fusion_and_metallurgy_design_pass=False)
    # The present mesh has three bulk materials and an elastic thin-layer
    # connection. It contains no explicit Ni99/PMZ state or resolved remelting
    # interface. An external file of True flags cannot supply those fields.
    # A local state solver and its numeric verifier must replace these pending
    # checks before the complete design gate can pass.
    if complete and len(rows)==3:
        values=np.array([[r['bulk_zones'][z]['maximum_trial_combined_VM_MPa'] for z in ('Q235','QT','NiFe')] for r in rows])
        differences=abs(values[1:]-values[0])/np.maximum(np.maximum(values[1:],values[0]),1e-12)
        checks['spatial_and_time_precision_pass']=bool(np.all(differences<=.05))
    summary=dict(residual_cases=cases,incremental_cases=cases,residual_input_snapshots=[r.get('input') for r in rows],records=rows,checks=checks,
        pending_local_evidence=['explicit Ni99 layer inherited cold and service state',
            'QT first-interface PMZ constitutive/fracture basis applicable to current process',
            'resolved final root/cap fusion and Ni99 remelting union'],
        initial_bore_diameter_mm=rows[0].get('initial_bore_diameter_mm'),
        complete_welded_strength_design_pass=all(checks.values()))
    (OUT/'welded-strength-verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    from aggregate_strength import aggregate
    aggregate()
    print(json.dumps({k:v for k,v in summary.items() if k not in ('records','residual_input_snapshots')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cases',nargs=3,required=True)
    with threadpool_limits(limits=1):main(p.parse_args().cases)
