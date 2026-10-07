"""Check actual cold geometry against carried mass and constitutive volume.

Force convergence and a small finite/linear volume difference do not by
themselves verify material geometry after changing a cut-space extension.
"""
import argparse
import json
import numpy as np
from mma_literature_profile import ROOT
from run_candidate_solver import operators
from run_first_layer_machining import datum_frame


def audit(source, output):
    result=json.loads((source/'result.json').read_text())
    with np.load(source/'fields.npz') as f:
        x,e,m,v=[f[k].copy() for k in ['x','e','material','volume_mm3']]
        u=f['u'].copy();reference=f['solid_reference_strain'].copy()
        plastic=f['plastic'].copy();stress=f['stress'].copy()
        weight=f['solid_weight'].copy();mass=f['material_mass_kg'].copy()
        temperature=f['temperature_C'].copy();time_s=float(f['time_s'])
    g,straight_volume,B,dof=operators(x,e,True)
    gradient=np.einsum('eij,eik->ejk',u[e],g)
    J=np.linalg.det(np.eye(3)+gradient)
    F=np.eye(3)+gradient
    left,_,right=np.linalg.svd(F)
    rotation=np.einsum('eij,ejk->eik',left,right)
    cosine=(np.trace(rotation,axis1=1,axis2=2)-1)/2
    rotation_angle=np.arccos(np.clip(cosine,-1,1))
    strain=np.einsum('eij,ej->ei',B,u.ravel()[dof])
    full=weight>=1-1e-10
    rows=[]
    inputs=json.loads((source/'input.json').read_text())
    thermal=json.loads((ROOT/inputs['source']/'input.json').read_text())
    from precoat_solid_mechanics import SolidMechanics
    with np.load(ROOT/inputs['source']/'thermal-fields.npz') as t:
        model=SolidMechanics(t['x'],t['e'],t['material'],t['volume_mm3'],thermal,
            inputs['phase_method'],inputs['interface_policy'])
    local_T=temperature[e].mean(axis=1)
    alpha=model.thermal_strain(local_T)
    E,_,nu,_=model.material_properties(np.where(full,local_T,20.))
    K=E/(3*(1-2*nu))
    mass_reference=np.log(mass/(model.cold_density_kg_mm3*v))
    # The original material reference plus physically carried mass determines
    # volume. A representation-only tensor shift cannot change physical mass
    # or move its geometry without recording the corresponding coordinate map.
    finite=result.get('kinematics')=='finite_Hencky'
    if finite:alpha=np.log1p(alpha)
    # For the power-conjugate Hencky formulation tr(T)=J*tr(Cauchy),
    # including noncoaxial retained references. The first derivative of log
    # maps the stress measures; it is not sufficient merely to rotate T.
    elastic_trace=stress[:,:3].mean(axis=1)/K*(J if finite else 1.)
    predicted_trace=mass_reference+plastic[:,:3].sum(axis=1)+3*alpha+elastic_trace
    logJ=np.full(len(J),np.nan);np.log(J,out=logJ,where=J>0)
    volume_defect=logJ-predicted_trace
    for material_id in np.unique(m):
        select=full&(m==material_id)
        if not np.any(select):continue
        rows.append(dict(material_id=int(material_id),fully_solid_elements=int(select.sum()),
            minimum_det_F=float(J[select].min()),
            maximum_abs_surviving_reference_trace=float(abs(reference[select,:3].sum(axis=1)-mass_reference[select]).max()),
            maximum_abs_log_volume_vs_mass_thermal_elastic_trace=float(abs(volume_defect[select]).max()),
            maximum_abs_log_vs_small_strain_trace=float(abs(np.log(J[select])-strain[select,:3].sum(axis=1)).max()),
            mass_weighted_reference_trace=float(np.average(reference[select,:3].sum(axis=1)-mass_reference[select],weights=mass[select])),
            density_range_kg_m3=[float((mass[select]/(v[select]*J[select])*1e9).min()),float((mass[select]/(v[select]*J[select])*1e9).max())]))
        rows[-1].update(reference_quadrature_vs_straight_tet_volume_ratio_range=[
            float((v[select]/straight_volume[select]).min()),float((v[select]/straight_volume[select]).max())],
            density_definition='carried mass / CAD-corrected reference quadrature volume / detF; curved-to-straight geometric approximation reported separately')
    registered,datum=datum_frame(x,u,e,m)
    qt=np.unique(e[m==1]);bore=qt[abs(np.linalg.norm(x[qt,:2],axis=1)-20)<1e-5]
    bore_diameter=2*np.linalg.norm(registered[bore,:2],axis=1)
    report=dict(source=str(source),time_s=time_s,partial=result['partial'],kinematics=result.get('kinematics','small_strain'),
        constitutive_volume_check='logJ=reference-mass trace+plastic trace+3*log(thermal stretch)+J*mean(Cauchy)/K' if finite else 'small-strain volume law; finite geometry compared independently',
        cold_complete=bool(not result['partial'] and temperature.max()<=20.05),
        maximum_temperature_C=float(temperature.max()),materials=rows,
        occupied_coherent_geometry=dict(minimum_det_F=float(J[weight>1e-12].min()),
            fully_solid_maximum_polar_rotation_deg=float(np.rad2deg(rotation_angle[full]).max()),
            all_coherent_maximum_polar_rotation_deg=float(np.rad2deg(rotation_angle[weight>1e-12]).max()),
            full_solid_rotation_scope='actual cold rotational response must be considered with interface closure, bore and tool geometry; volume check alone is not geometry qualification'),
        datum=datum,actual_registered_bore_radial_diameter_range_mm=[float(bore_diameter.min()),float(bore_diameter.max())],
        bore_note='existing rough-bore radial diameter in the A/B frame; not final manufactured hole tolerance or positional result',
        interpretation='Compare the recorded reference-volume changes with actual geometry and mass before accepting tool cutting; small-strain truncation is reported separately.',
        full_manufacturing_verified=False)
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():raise ValueError('Preserve previous geometry audit')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=lambda s:ROOT/s,required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True);a=p.parse_args()
    audit(a.source,a.output)
