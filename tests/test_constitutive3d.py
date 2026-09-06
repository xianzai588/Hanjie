import numpy as np
import pytest

from hanjie.simulation.constitutive3d import affine_mesh_response,instantaneous_thermal_strain,j2_update,mandel_to_symmetric,stress_free_birth_state,symmetric_to_mandel


MATERIAL=dict(elastic_modulus_mpa=210000.,poisson_ratio=.28,yield_strength_mpa=235.,hardening_modulus_mpa=0.)


def test_j2_hydrostatic_path_does_not_yield():
    result=j2_update(np.eye(3)*.01,0.,{},**MATERIAL)
    assert result["equivalent_stress_mpa"]==pytest.approx(0.,abs=1e-10)
    assert result["equivalent_plastic_strain"]==0.


def test_j2_pure_shear_returns_to_von_mises_surface():
    strain=np.array([[0.,.01,0.],[.01,0.,0.],[0.,0.,0.]])
    result=j2_update(strain,0.,{},**MATERIAL)
    assert result["equivalent_stress_mpa"]==pytest.approx(235.,rel=1e-12)
    assert result["stress_mpa"][0,1]==pytest.approx(235./np.sqrt(3),rel=1e-12)
    assert result["plastic_dissipation_mj_mm3"]>0


def test_j2_is_rotation_covariant():
    strain=np.array([[.003,.001,0.],[.001,-.001,0.],[0.,0.,-.002]])
    angle=.37
    rotation=np.array([[np.cos(angle),-np.sin(angle),0.],[np.sin(angle),np.cos(angle),0.],[0.,0.,1.]])
    base=j2_update(strain,0.,{},**MATERIAL)
    rotated=j2_update(rotation@strain@rotation.T,0.,{},**MATERIAL)
    np.testing.assert_allclose(rotated["stress_mpa"],rotation@base["stress_mpa"]@rotation.T,atol=1e-10)


def test_instantaneous_alpha_is_integrated_and_rejects_extrapolation():
    result=instantaneous_thermal_strain(np.array([20.,100.,200.]),[20.,200.],[1e-5,2e-5])
    assert result[0]==0.
    assert result[-1]==pytest.approx(180.*1.5e-5)
    with pytest.raises(ValueError):
        instantaneous_thermal_strain(np.array([201.]),[20.,200.],[1e-5,2e-5])


def test_affine_tetra_mesh_has_force_and_moment_balance():
    response=affine_mesh_response(np.diag([.002,-.0005,-.0005]),0.,MATERIAL)
    assert response["volume_mm3"]==pytest.approx(1.)
    assert np.linalg.norm(response["resultant_internal_force_n"])<1e-10
    assert np.linalg.norm(response["resultant_internal_moment_n_mm"])<1e-10
    assert all(state["plastic_dissipation_mj_mm3"]>=0 for state in response["element_states"])


@pytest.mark.parametrize("strain",[np.diag([5e-4,-1e-4,-1e-4]),np.diag([4e-3,-1e-3,-1e-3])])
def test_j2_consistent_tangent_matches_finite_difference(strain):
    base=j2_update(strain,0.,{},**{**MATERIAL,"hardening_modulus_mpa":1500.})
    analytical=base["consistent_tangent_mpa"]
    numerical=np.zeros((6,6))
    step=1e-8
    for column in range(6):
        perturb=np.zeros(6); perturb[column]=step
        plus=j2_update(strain+mandel_to_symmetric(perturb),0.,{},**{**MATERIAL,"hardening_modulus_mpa":1500.})
        minus=j2_update(strain-mandel_to_symmetric(perturb),0.,{},**{**MATERIAL,"hardening_modulus_mpa":1500.})
        numerical[:,column]=(symmetric_to_mandel(plus["stress_mpa"])-symmetric_to_mandel(minus["stress_mpa"]))/(2*step)
    np.testing.assert_allclose(analytical,numerical,rtol=3e-5,atol=3e-3)


def test_high_temperature_stress_free_birth_then_cooling_has_correct_reference_state():
    hot_thermal=.006
    state=stress_free_birth_state(np.zeros((3,3)),hot_thermal)
    born=j2_update(np.zeros((3,3)),hot_thermal,state,**MATERIAL)
    assert np.max(np.abs(born["stress_mpa"]))<1e-10

    constrained_cold=j2_update(np.zeros((3,3)),0.,state,**MATERIAL)
    assert np.trace(constrained_cold["stress_mpa"])/3>0
    free_cold=j2_update(-np.eye(3)*hot_thermal,0.,state,**MATERIAL)
    assert np.max(np.abs(free_cold["stress_mpa"]))<1e-10
