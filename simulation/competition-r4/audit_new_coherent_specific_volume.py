"""Free-body birth/cool and advected-reference density checks for manufacturing."""
import json
import numpy as np
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT
from precoat_solid_mechanics import SolidMechanics


def case(inputs,reference_scale=1.):
    tetra=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],float)
    x=np.vstack([tetra+[20,0,100],reference_scale*tetra+[71,0,114]])
    e=np.array([[0,1,2,3],[4,5,6,7]])
    volume=np.array([1/6,reference_scale**3/6]);m=np.array([1,3])
    model=SolidMechanics(x,e,m,volume,inputs)
    model.material_mass_kg[1]=model.cold_density_kg_mm3[1]/6
    temperatures=np.r_[np.full(4,20.),np.full(4,1000.)]
    hot=model.advance(1.,temperatures,np.ones(2))
    gradient=np.einsum('eij,eik->ejk',model.u.reshape(-1,3)[model.e],model.g)
    hot_volume=volume*np.linalg.det(np.eye(3)+gradient)
    cold=model.advance(2.,np.full(8,20.),np.ones(2))
    gradient=np.einsum('eij,eik->ejk',model.u.reshape(-1,3)[model.e],model.g)
    cold_volume=volume*np.linalg.det(np.eye(3)+gradient)
    density=model.material_mass_kg[1]/cold_volume[1]/1e-9
    expected=model.cold_density_kg_mm3[1]/1e-9
    result=dict(reference_scale=reference_scale,hot_equilibrium_residual_N=hot[2],
        cold_equilibrium_residual_N=cold[2],reference_volume_mm3=float(volume[1]),
        carried_mass_kg=float(model.material_mass_kg[1]),hot_actual_volume_mm3=float(hot_volume[1]),
        cold_actual_volume_mm3=float(cold_volume[1]),cold_density_kg_m3=float(density),
        density_relative_error=float(abs(density/expected-1)),maximum_eqp=float(model.eqp.max()),
        maximum_stress_MPa=float(abs(model.stress).max()),
        specific_volume_reference_trace=float(model.reference[1,:3].sum()))
    # The1% reference-coordinate change leaves only the explicitly measured
    # small-strain/log-volume truncation error, not a second thermal contraction.
    if result['density_relative_error']>.0005 or result['maximum_eqp']>1e-10:
        raise RuntimeError('Free coherent body does not recover its carried cold specific volume')
    return result


if __name__=='__main__':
    inputs=json.loads((ROOT/'simulation/competition-r4/results/mma-first-end80-r12-phase-cooling-20261007/input.json').read_text())
    inputs['cold_start_C']=20.
    with threadpool_limits(limits=1):results=[case(inputs),case(inputs,1.01)]
    output=ROOT/'simulation/competition-r4/results/mma-continuous-end80-r12-20261007/new-coherent-specific-volume-audit.json'
    output.write_text(json.dumps(dict(cases=results,reference_policy='carried mass/cold density/reference volume; current shear; surviving state unchanged',
        free_body_specific_volume_check_pass=True,full_manufacturing_verified=False),indent=2),encoding='utf8')
    print(output)
    print(json.dumps(results,indent=2))
