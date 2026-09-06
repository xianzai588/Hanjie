"""准备模块验证，不宣称已经求解焊接残余应力。"""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from hanjie.simulation.structural_prep import fit_position_diameter, fixture_released, service_loads, volume_weighted_p95


def ring(radius,z):
    theta = np.linspace(0,2*np.pi,48,endpoint=False)
    return np.column_stack((radius*np.cos(theta),radius*np.sin(theta),np.full(48,z)))


def test_volume_quantile_is_invariant_to_splitting_tiny_elements():
    assert volume_weighted_p95([10.,100.],[99.,1.])==10.
    assert volume_weighted_p95(np.r_[10.,np.full(100,100.)],np.r_[99.,np.full(100,.01)])==10.
    with pytest.raises(ValueError):
        volume_weighted_p95([10.],[0.])


def test_release_requires_both_conditions_and_stays_released():
    assert not fixture_released(False,119.,150.)
    assert not fixture_released(False,120.,200.)
    assert fixture_released(False,120.,199.9)
    assert fixture_released(True,130.,250.)


def test_datum_refit_removes_rigid_motion_but_preserves_hole_offset_and_tilt():
    a = ring(78.,0.)
    b = np.vstack((ring(75.,0.),ring(75.,100.)))
    hole = np.vstack((ring(20.,0.),ring(20.,6.),ring(20.,12.)))
    hole[:,0] += .01
    expected = fit_position_diameter(a,b,hole)["position_diameter_mm"]
    assert expected == pytest.approx(.02,abs=1e-7)
    rot = Rotation.from_rotvec([.2,-.1,.3]).as_matrix()
    shift = np.array([10.,-4.,7.])
    moved = fit_position_diameter(a@rot.T+shift,b@rot.T+shift,hole@rot.T+shift)
    assert moved["position_diameter_mm"] == pytest.approx(expected,abs=1e-7)
    hole[:,0] += .001*hole[:,2]
    assert fit_position_diameter(a,b,hole)["position_diameter_mm"] > .04


@pytest.mark.parametrize("axis",[[1.,0.,0.],[0.,0.,1.]])
def test_service_resultant_force_and_overturning_moment(axis):
    points = np.vstack((ring(20.,0.),ring(20.,12.)))
    for force,moment in ((100.,0.),(0.,200.)):
        loads = service_loads(points,axis,force,moment)
        assert loads.sum(axis=0) == pytest.approx(np.array(axis)*force,abs=1e-8)
        torque = np.cross(points-points.mean(axis=0),loads).sum(axis=0)
        assert torque == pytest.approx(np.array(axis)*moment,abs=1e-8)
