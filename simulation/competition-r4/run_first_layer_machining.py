"""Cut the completed cold deposit in its actual datum frame and re-equilibrate."""
import argparse
import json
import numpy as np
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT
from precoat_solid_mechanics import SolidMechanics
from precoat_machining import retained_moments


def datum_frame(x,u,e,m):
    p=x+u;qt=np.unique(e[m==1]);r=np.linalg.norm(x[:,:2],axis=1)
    bottom=qt[(abs(x[qt,2]-100)<1e-7)&(r[qt]<65)]
    if len(bottom)<10:raise ValueError('QT datum A floor not found')
    centre=p[bottom].mean(axis=0)
    _,_,v=np.linalg.svd(p[bottom]-centre,full_matrices=False);normal=v[-1]
    if normal[2]<0:normal=-normal
    ex=np.array([1.,0,0]);ex-=normal*(ex@normal);ex/=np.linalg.norm(ex)
    basis=np.column_stack([ex,np.cross(normal,ex),normal])
    q=p@basis;radial_min=r[qt].min()
    bore=qt[(abs(r[qt]-radial_min)<1e-5)&(abs(x[qt,2]-100)<1e-7)]
    if len(bore)<8:raise ValueError('Existing bore datum B lower ring not found')
    a=np.column_stack([2*q[bore,:2],np.ones(len(bore))]);b=np.sum(q[bore,:2]**2,axis=1)
    fit=np.linalg.lstsq(a,b,rcond=None)[0]
    offset=np.array([fit[0],fit[1],centre@normal-100])
    return q-offset,dict(rotation_columns=basis.tolist(),translation_in_rotated_frame_mm=offset.tolist(),
        datum='actual QT lower plane A and existing bore lower-ring centre B; yaw fixed to original X projection',
        datum_A_nodes=len(bottom),datum_B_nodes=len(bore),
        datum_A_max_plane_error_mm=float(abs((p[bottom]-centre)@normal).max()))


def run(source,output):
    if (output/'input.json').exists():raise ValueError('Preserve previous machining evidence')
    result=json.loads((source/'result.json').read_text())
    if result['partial'] or result['maximum_equilibrium_residual_N']>=.05:
        raise ValueError('Require the completed equilibrated cold manufacturing demand state')
    replay=json.loads((source/'input.json').read_text())
    thermal_input=json.loads((ROOT/replay['source']/'input.json').read_text())
    with np.load(source/'fields.npz') as f:
        x,e,m,v=f['x'].copy(),f['e'].copy(),f['material'].copy(),f['volume_mm3'].copy()
        temperature=f['thermal_source_temperature_C'].copy() if 'thermal_source_temperature_C' in f else f['temperature_C'].copy()
        occupation=f['occupation'].copy();time_s=float(f['time_s'])
        if temperature.max()>20.05 or np.min(occupation)<1-1e-10:
            raise ValueError('Actual completed cold deposition is required for first-layer machining')
        interface_policy=replay.get('interface_policy','conformal')
        with np.load(ROOT/replay['source']/'thermal-fields.npz') as thermal:
            mechanics=SolidMechanics(thermal['x'],thermal['e'],m,v,thermal_input,replay['phase_method'],interface_policy)
        if not np.array_equal(mechanics.x,x) or not np.array_equal(mechanics.e,e):raise ValueError('Machining-state mesh reconstruction differs from actual source')
        for key,field in [('u','u'),('plastic','plastic'),('eqp','eqp'),('reference','solid_reference_strain'),
                          ('solid_weight','solid_weight'),('stress','stress'),('remelted','remelted_QT')]:
            value=f[field].copy();setattr(mechanics,key,value.ravel() if key=='u' else value)
        inherited_interface=f['original_fusion_faces'].copy() if 'original_fusion_faces' in f else None
        if interface_policy=='chronological':mechanics.fused_faces=f['fused_faces'].copy()
        if 'current_bond_pairs' in f:mechanics.current_bond_pairs=f['current_bond_pairs'].copy()
        if 'bonded_faces' in f:mechanics.bonded_faces=f['bonded_faces'].copy()
        mechanics.previous_actual_temperature=temperature[mechanics.thermal_origin].copy()
        mechanics.previous_occupation=occupation.copy()
        if 'material_mass_kg' in f:mechanics.material_mass_kg=f['material_mass_kg'].copy()
    gradient=np.einsum('eij,eik->ejk',mechanics.u.reshape(-1,3)[e],mechanics.g)
    determinant=np.linalg.det(np.eye(3)+gradient)
    volume_error=abs(determinant-(1+np.trace(gradient,axis1=1,axis2=2)))/np.maximum(abs(determinant),1e-30)
    if determinant.min()<=0 or volume_error.max()>.05:
        raise ValueError('Cold parent geometry requires a finite-deformation representation before tool cutting')
    current,registration=datum_frame(x,mechanics.u.reshape(-1,3),e,m)
    # Shared QT/Ni faces identify the actual original pocket floor. Check the
    # prescribed normal layer against the registered, deformed substrate;
    # a failed thickness is not corrected by changing the design allowance.
    faces=np.sort(np.vstack([e[:,q] for q in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1)
    owners=np.tile(np.arange(len(e)),4)
    _,first,inverse,count=np.unique(faces,axis=0,return_index=True,return_inverse=True,return_counts=True)
    last=np.zeros(len(count),int);np.maximum.at(last,inverse,np.arange(len(faces)))
    a,b=owners[first],owners[last]
    interface=inherited_interface if inherited_interface is not None else faces[first[(count==2)&(m[a]!=m[b])]]
    points=current[np.unique(interface)]
    radius=np.linalg.norm(points[:,:2],axis=1)
    thickness=np.where(radius>=70.48,114.2-points[:,2],np.hypot(radius-70.48,points[:,2]-115)-.8)
    thickness_audit=dict(minimum_normal_remaining_mm=float(thickness.min()),maximum_normal_remaining_mm=float(thickness.max()),
        required_interval_mm=[.65,.75],normal_thickness_pass=bool(thickness.min()>=.65 and thickness.max()<=.75))
    output.mkdir(parents=True,exist_ok=True)
    (output/'input.json').write_text(json.dumps(dict(source=str(source),registration=registration,thickness=thickness_audit,
        machining_surface='prescribed z114.20/R0.80 in actual A/B datum frame; no change of retained-layer or bore allowances',
        tensor_transfer='surviving parent plasticity and material reference retained; removed volume carries no further stiffness/force'),indent=2),encoding='utf8')
    if not thickness_audit['normal_thickness_pass']:raise RuntimeError('Prescribed tool contour misses the normal layer tolerance; revise tool registration/contour before cutting')
    moments=retained_moments(current,e,m);remaining=moments.sum(axis=1)
    before_plastic=mechanics.plastic.copy();before_eqp=mechanics.eqp.copy()
    row=mechanics.advance(time_s,temperature,remaining,geometry_cut_moments=moments)
    np.savez_compressed(output/'machining-cut.npz',retained_P1_moments=moments,registered_cold_coordinates=current,
        removed_reference_volume_mm3=v*(occupation-remaining),source_plastic=before_plastic,source_eqp=before_eqp)
    final=mechanics.save(output,time_s,temperature,remaining,False)
    final.update(machining_demand_equilibrated=True,retained_first_layer_reference_volume_mm3=float(v[m==3]@remaining[m==3]),
        removed_reference_volume_mm3=float(v@(occupation-remaining)),thickness_before_cut=thickness_audit,
        mechanical_scope='actual reference-material demand; no CI-A1/PMZ fracture capacity or complete-manufacturing pass assigned')
    (output/'result.json').write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({key:value for key,value in final.items() if key!='mechanical_reference'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=lambda s:ROOT/s,required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True);a=p.parse_args()
    with threadpool_limits(limits=1):run(a.source,a.output)
