"""Analytic objectivity/density and independent derivative checks before replay."""
import argparse
import json
import numpy as np
from scipy.spatial.transform import Rotation
from precoat_finite_kinematics import response,tensor,kelvin
from mma_literature_profile import ROOT


def run(output_name='finite-rotation-material-audit.json'):
    g=np.array([[[-1.,-1,-1],[1,0,0],[0,1,0],[0,0,1]]])
    z=np.zeros((1,6));q=Rotation.from_rotvec([.4,-.3,.5]).as_matrix()
    arguments=[g,z.copy(),z.copy(),np.zeros(1),np.zeros(1),np.array([80000.]),np.array([150000.]),np.array([80.]),np.array([3125.])]
    rigid=response(q[None],*arguments)
    arguments[4]=np.array([np.log1p(.02)])
    heated=response((1.02*q)[None],*arguments)
    reference=z.copy();reference[0,:3]=np.log(1.01)/3
    arguments[1]=reference;arguments[4]=np.zeros(1)
    mass=response((1.01**(1/3)*q)[None],*arguments)
    free_error=max(abs(rigid[0]).max(),abs(heated[0]).max(),abs(mass[0]).max())
    # Distorted state with active plastic return: independent nodal finite
    # differences test force against potential and tangent against force.
    F=(q@np.diag([1.05,.99,.96]))[None]
    arguments[1]=np.array([[.001,-.0005,-.0005,.0004,0,0]])
    arguments[2]=np.array([[.002,-.001,-.001,0,.0003,0]])
    arguments[3]=np.array([.003]);arguments[4]=np.array([.015])
    base=response(F,*arguments)
    rng=np.random.default_rng(710);d=rng.normal(size=(1,4,3));d/=np.linalg.norm(d)
    dF=np.einsum('eni,enj->eij',d,g);h=1e-7
    plus=response(F+h*dF,*arguments,tangent=False)
    minus=response(F-h*dF,*arguments,tangent=False)
    fd_force=(plus[0]-minus[0])/(2*h)
    analytic=np.einsum('eij,ej->ei',base[1],d.reshape(1,12))
    tangent_error=float(np.linalg.norm(fd_force-analytic)/np.linalg.norm(fd_force))
    fd_energy=float((plus[5]-minus[5])[0]/(2*h))
    force_power=float(base[0].ravel()@d.ravel())
    energy_error=abs(fd_energy-force_power)/max(abs(force_power),1.)
    Q=Rotation.from_rotvec([-.7,.2,.1]).as_matrix()
    rotated=response(np.einsum('ij,ejk->eik',Q,F),*arguments,tangent=False)
    expected_force=(base[0].reshape(1,4,3)@Q.T).reshape(1,12)
    expected_stress=kelvin(np.einsum('ij,ejk,lk->eil',Q,tensor(base[2]),Q))
    objectivity_error=float(np.linalg.norm(rotated[0]-expected_force)/np.linalg.norm(expected_force))
    stress_objectivity_error=float(np.linalg.norm(rotated[2]-expected_stress)/np.linalg.norm(expected_stress))
    high=response(F,*arguments,quadrature_order=32)
    quadrature_error=float(np.linalg.norm(high[1]-base[1])/np.linalg.norm(high[1]))
    symmetry_error=float(np.linalg.norm(base[1]-base[1].transpose(0,2,1))/np.linalg.norm(base[1]))
    passed=bool(free_error<1e-6 and max(tangent_error,energy_error,objectivity_error,stress_objectivity_error,quadrature_error,symmetry_error)<1e-6)
    report=dict(formulation_source='https://doi.org/10.1016/j.cma.2023.116101',
        analytic_cases='finite rigid rotation; freely heated1.02 stretch;1.01 carried-mass/reference-volume ratio with exact cold stretch',
        maximum_analytic_zero_force_error=free_error,force_potential_relative_error=energy_error,
        consistent_tangent_direction_relative_error=tangent_error,finite_rotation_force_objectivity_error=objectivity_error,
        Cauchy_stress_objectivity_error=stress_objectivity_error,log_Hessian_selected_vs32_quadrature_error=quadrature_error,
        force_derivative_rule='exact spectral first derivative; Hessian integral4 points for squared stretches0.8..1.25,16 otherwise',
        tangent_symmetry_relative_error=symmetry_error,plastic_increment_in_derivative_case=float(base[3][0]),
        finite_kinematics_benchmark_pass=passed,actual_manufacturing_verified=False)
    if not passed:raise RuntimeError(json.dumps(report,indent=2))
    destination=ROOT/'simulation/competition-r4/results/mma-continuous-end80-r12-20261007'/output_name
    if destination.exists():raise ValueError('Preserve the prior finite-kinematics audit')
    destination.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output-name',default='finite-rotation-material-audit.json')
    run(p.parse_args().output_name)
