"""Analytic stress-free joining benchmark with simultaneous material addition.

Two translated free Ni bodies join opposite faces of an unloaded QT prism.
Symmetry removes arbitrary rigid rotation. At the common cold temperature
the exact final state has zero strain/stress/plasticity and original volumes.
This is a numerical manufacturing benchmark, not an experimental weld test.
"""
import argparse
import json
import numpy as np
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT
from run_candidate_solver import operators
from precoat_solid_mechanics import SolidMechanics


def run(kinematics='small_strain'):
    source=ROOT/'simulation/competition-r4/results/mma-first-end80-r12-phase-front-dt0125-20261007'
    inputs=json.loads((source/'input.json').read_text());inputs['cold_start_C']=20.
    x=np.array([[0,0,-1],[1,0,-1],[0,1,-1],
                [0,0,1],[1,0,1],[0,1,1],
                [1/3,1/3,-2],[1/3,1/3,2]],float)
    e=np.array([[0,1,2,5],[0,1,4,5],[0,3,4,5],[0,1,2,6],[3,4,5,7]])
    material=np.array([1,1,1,3,3]);_,volume,_,_=operators(x,e,False)
    model=SolidMechanics(x,e,material,volume,inputs,phase_method='cell_mean',kinematics=kinematics)
    ni=material==3
    model.solid_weight[ni]=.5;model.previous_occupation[ni]=.5
    gap=.28791122853114515
    for element,direction in [(3,-1),(4,1)]:
        model.u.reshape(-1,3)[model.e[element],2]=direction*gap
    before_strain=np.einsum('eij,ej->ei',model.B,model.u[model.dof])
    if abs(before_strain).max()>1e-12:raise RuntimeError('Initial free-body translation contains material strain')
    # Show the independent kinematic error of using the constraint snap as
    # a deposition shape. No legacy result is fabricated or treated as data.
    snapped=model.u.reshape(-1,3).copy()
    pairs=np.unique(model.fusion_vertex_pairs.reshape(-1,2),axis=0)
    snapped[pairs[:,1]]=snapped[pairs[:,0]]
    snap_strain=np.einsum('eij,ej->ei',model.B,snapped.ravel()[model.dof])
    erroneous_reference=.5*(snap_strain@model.pd)
    try:row=model.advance(1.,np.full(len(x),20.),np.ones(len(e)),np.ones(len(model.fusion_faces),bool))
    except Exception:
        folder=ROOT/'simulation/competition-r4/results/finite-interface-birth-diagnostic-20261007'
        if folder.exists():raise ValueError('Preserve the prior finite interface diagnostic')
        model.save(folder,1.,np.full(len(x),20.),np.ones(len(e)),True)
        print(json.dumps(model.failed_iteration,indent=2))
        raise
    strain=np.einsum('eij,ej->ei',model.B,model.u[model.dof])
    grad=np.einsum('eij,eik->ejk',model.u.reshape(-1,3)[model.e],model.g)
    J=np.linalg.det(np.eye(3)+grad)
    result=dict(benchmark='symmetric stress-free joining and cold material addition; analytic final zero strain, zero stress, zero plasticity and unchanged volume',
        exact_solution_basis='both cold materials are initially unstrained and free; translating each Ni body into contact is a rigid motion; symmetric opposite joining removes arbitrary global rotation',
        initial_free_Ni_translation_mm=gap,retained_Ni_fraction=.5,new_Ni_fraction=.5,
        postclosure_initialization_analytic_error=dict(maximum_spurious_new_material_reference_norm=float(np.linalg.norm(erroneous_reference[ni],axis=1).max()),
            explanation='the local constraint snap is not a stress-free new-material shape'),
        corrected_numerical=dict(equilibrium_residual_N=row[2],maximum_strain=float(abs(strain).max()),
            maximum_stress_MPa=float(abs(model.stress).max()),maximum_eqp=float(model.eqp.max()),
            maximum_abs_detF_minus_one=float(abs(J-1).max()),
            maximum_reference_tensor=float(abs(model.reference).max())),
        manufacturing_benchmark_pass=bool(abs(strain).max()<1e-6 and model.eqp.max()<1e-6 and abs(J-1).max()<1e-6 and abs(model.reference).max()<1e-12),
        kinematics=kinematics,actual_weld_thermal_qualification_assigned=False,full_manufacturing_verified=False)
    if not result['manufacturing_benchmark_pass']:raise RuntimeError(json.dumps(result,indent=2))
    folder=ROOT/'simulation/competition-r4/results/mma-continuous-end80-r12-20261007'
    output=folder/('interface-coherent-birth-order-audit.json' if kinematics=='small_strain' else 'interface-coherent-finite-birth-order-audit.json')
    if output.exists():raise ValueError('Preserve prior interface-birth benchmark evidence')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--kinematics',choices=['small_strain','finite_Hencky'],default='small_strain')
    with threadpool_limits(limits=1):run(p.parse_args().kinematics)
