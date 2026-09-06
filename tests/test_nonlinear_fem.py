import numpy as np
import pytest

from hanjie.simulation.constitutive3d import tetrahedral_cube
from hanjie.simulation.nonlinear_fem import solve_incremental_tetra


def _uniaxial_cube_problem(stress_mpa):
    nodes,elements=tetrahedral_cube()
    force=np.zeros((len(nodes),3))
    # x=1 方形面由两个三角形组成，按一致节点力施加均匀面力。
    for triangle in ((1,2,6),(1,6,5)):
        force[list(triangle),0]+=stress_mpa/6
    prescribed={}
    for node in np.where(nodes[:,0]==0)[0]:
        prescribed[3*int(node)]=0.
    for node in np.where(nodes[:,1]==0)[0]:
        prescribed[3*int(node)+1]=0.
    for node in np.where(nodes[:,2]==0)[0]:
        prescribed[3*int(node)+2]=0.
    return nodes,elements,force,prescribed


def test_global_newton_reproduces_hardening_uniaxial_bar():
    material=dict(elastic_modulus_mpa=210000.,poisson_ratio=.28,yield_strength_mpa=235.,hardening_modulus_mpa=2000.)
    nodes,elements,_,prescribed=_uniaxial_cube_problem(0.)
    steps=[]
    for stress in (100.,250.,300.):
        _,_,force,_=_uniaxial_cube_problem(stress)
        steps.append({"name":f"traction_{stress:g}","external_force_n":force,"prescribed_dofs":prescribed,"thermal_strain":0.})
    result=solve_incremental_tetra(nodes,elements,material,steps,relative_tolerance=1e-9,absolute_tolerance_n=1e-8,max_iterations=20)

    assert all(step["converged"] for step in result["steps"])
    final=result["steps"][-1]
    expected_strain=300./210000.+(300.-235.)/2000.
    x_face=np.where(nodes[:,0]==1)[0]
    assert np.mean(np.asarray(final["displacement_mm"])[x_face,0])==pytest.approx(expected_strain,rel=2e-8)
    assert -np.sum(np.asarray(final["reaction_force_n"])[nodes[:,0]==0,0])==pytest.approx(300.,rel=1e-9)
    assert final["residual_norm_n"]<1e-8
    assert final["newton_iterations"]<=6
    assert final["plastic_dissipation_mj"]>0


def test_constrained_heat_release_and_cooling_leave_residual_shape_without_force():
    nodes,elements=tetrahedral_cube()
    symmetry={}
    for node in np.where(nodes[:,0]==0)[0]:
        symmetry[3*int(node)]=0.
    for node in np.where(nodes[:,1]==0)[0]:
        symmetry[3*int(node)+1]=0.
    for node in np.where(nodes[:,2]==0)[0]:
        symmetry[3*int(node)+2]=0.
    constrained={**symmetry,**{3*int(node):0. for node in np.where(nodes[:,0]==1)[0]}}
    zero=np.zeros_like(nodes)
    steps=[{"name":f"heat_{value:g}","external_force_n":zero,"prescribed_dofs":constrained,"thermal_strain":value} for value in (.002,.004,.006)]
    steps += [
        {"name":"release_hot","external_force_n":zero,"prescribed_dofs":symmetry,"thermal_strain":.006},
        {"name":"cool_mid","external_force_n":zero,"prescribed_dofs":symmetry,"thermal_strain":.003},
        {"name":"cool_20c","external_force_n":zero,"prescribed_dofs":symmetry,"thermal_strain":0.},
    ]
    material=dict(elastic_modulus_mpa=150000.,poisson_ratio=.28,yield_strength_mpa=150.,hardening_modulus_mpa=1000.)
    result=solve_incremental_tetra(nodes,elements,material,steps,max_iterations=20)

    assert all(step["converged"] for step in result["steps"])
    assert result["steps"][2]["plastic_dissipation_mj"]>0
    for step in result["steps"][3:]:
        assert np.linalg.norm(step["reaction_force_n"])<1e-8
    final_displacement=np.asarray(result["steps"][-1]["displacement_mm"])
    assert np.mean(final_displacement[nodes[:,0]==1,0])<0
    assert np.linalg.norm(result["steps"][-1]["force_balance_n"])<1e-8
    assert np.linalg.norm(result["steps"][-1]["moment_balance_n_mm"])<1e-8


def test_element_activation_is_stress_free_at_birth_in_global_mesh():
    nodes,elements=tetrahedral_cube()
    hot_displacement=.01*nodes
    hot_dofs={3*node+axis:float(hot_displacement[node,axis]) for node in range(len(nodes)) for axis in range(3)}
    cold_dofs={dof:0. for dof in hot_dofs}
    initial=np.zeros(len(elements),dtype=bool); initial[0]=True
    material=dict(elastic_modulus_mpa=1000.,poisson_ratio=.25,yield_strength_mpa=1e9,hardening_modulus_mpa=1000.)
    result=solve_incremental_tetra(nodes,elements,material,[
        {"name":"hot_substrate","prescribed_dofs":hot_dofs,"thermal_strain":.01,"active_elements":initial,"stress_free_on_activation":True},
        {"name":"activate_weld_hot","prescribed_dofs":hot_dofs,"thermal_strain":.01,"active_elements":np.ones(len(elements),bool),"stress_free_on_activation":True},
        {"name":"fixed_geometry_cooling","prescribed_dofs":hot_dofs,"thermal_strain":0.,"active_elements":np.ones(len(elements),bool)},
        {"name":"release_and_contract","prescribed_dofs":cold_dofs,"thermal_strain":0.,"active_elements":np.ones(len(elements),bool)},
    ])
    assert result["steps"][1]["maximum_abs_stress_mpa"]<1e-10
    assert result["steps"][2]["maximum_abs_stress_mpa"]>1.
    assert result["steps"][3]["maximum_abs_stress_mpa"]<1e-10
    assert result["steps"][1]["newly_activated_element_count"]==len(elements)-1
