"""独立检验0.4R角度、浅层吸收和物性端点，不依赖熔化目标。"""
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.special import erf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"simulation/thermal-v5"))
from credibility_source import projected_weights
from mass_closed_geometry import build_geometry, surface_weights, source_power, filled_fraction
from run_credibility04r import material_scenario, load
from audit_credibility04r import compare


@pytest.fixture(scope="module")
def geometry():
    spec = load(ROOT/"project/thermal-mass-closed-v5.4r1.yaml")
    config = load(ROOT/spec["inputs"])
    return build_geometry(config,load(ROOT/spec["process_input"]),spec),config


def test_nominal_source_preserves_frozen_surface(geometry):
    g,_ = geometry
    for bead in (False,True):
        np.testing.assert_allclose(projected_weights(g,bead,2.5),surface_weights(g,bead,2.5),atol=1e-14)


@pytest.mark.parametrize("angle",[30.,60.])
def test_angle_matches_independent_ray_rectangle_oracle(geometry,angle):
    g,_ = geometry
    sn,cs = np.sin(np.deg2rad(angle)),np.cos(np.deg2rad(angle))
    n,z,ids = g["n_edges"],g["z_edges"],g["ids2"]
    j,k = np.where(ids>0)
    rays = np.arange(-10.+.0005,10.,.001)
    expected = np.zeros_like(ids,float)
    for start in range(0,len(rays),128):
        u = rays[start:start+128,None]
        entry = np.minimum((u*cs-n[j])/sn,(z[k+1]-u*sn)/cs)
        leave = np.maximum((u*cs-n[j+1])/sn,(z[k]-u*sn)/cs)
        selected = np.argmax(np.where(entry>leave,entry,-np.inf),axis=1)
        weight = np.sqrt(3/np.pi)/2.5*np.exp(-3*(u[:,0]/2.5)**2)*.001
        np.add.at(expected,(j[selected],k[selected]),weight)
    np.testing.assert_allclose(projected_weights(g,True,2.5,angle),expected,atol=5e-4)


def test_penetration_matches_independent_slab_integral_and_loses_transmission():
    # 高度足够的两层竖直板：材料路径长=板厚/sin(theta)，可直接解析每层吸收。
    g = dict(n_edges=np.array([0.,.2,.7]),z_edges=np.array([-100.,100.]),ids2=np.array([[1],[2]]))
    result = projected_weights(g,False,2.5,45.,1.,.5)[:,0]
    expected = [1-np.exp(-.2/(np.sqrt(.5)*.5)),np.exp(-.2/(np.sqrt(.5)*.5))*(1-np.exp(-.5/(np.sqrt(.5)*.5)))]
    np.testing.assert_allclose(result,expected,atol=1e-12)
    assert result.sum()<1.


def test_shallow_power_conserved_without_unborn_deposition(geometry):
    g,config = geometry
    a,b = [projected_weights(g,bead,2.5,45.,.1,.5) for bead in (False,True)]
    for center in (-30.,-29.99,0.,29.99):
        q = source_power(g,a,b,-30.,30.,center,config["heat_source"],495.)
        f = filled_fraction(g,-30.,30.,center+30.)
        # 指数源穿过有限厚度后仍有透射；只检查受控损失，不能强迫归一化为495W。
        assert 495.*.99999 < q.sum() <= 495.
        assert np.all(q[f==0]==0.)


def test_property_endpoints_do_not_change_reference_density_or_originals():
    mat,phy = load(ROOT/"project/materials.yaml"),load(ROOT/"project/thermal-physics-v5.3.yaml")
    for scenario,index in (("lower",0),("upper",1)):
        m,p = material_scenario(mat,phy,scenario)
        for name in phy["materials"]:
            assert m["materials"][name]["nominal_properties_20c"]["density_kg_m3"]==mat["materials"][name]["nominal_properties_20c"]["density_kg_m3"]
            assert p["materials"][name]["phase_change"]["solidus_c"]==phy["materials"][name]["phase_change"]["uncertainty"]["solidus_c"][index]
    assert phy["materials"]["qt450_10"]["phase_change"]["solidus_c"]==1100.


def test_convergence_does_not_call_zero_fusion_converged():
    import copy
    fields = dict(peak_temperature_c=1000.,ever_solidus_exceeded_volume_mm3=0.,ever_liquidus_exceeded_volume_mm3=0.,
        maximum_cross_section_solidus_area_mm2=0.,maximum_section_solidus_width_mm=0.,maximum_section_solidus_depth_mm=0.,
        t8_5_valid_volume_mm3=1.,t8_5_volume_weighted_mean_s=2.,exposure_above_400c_volume_mm3=3.)
    a = dict(material_statistics={n:copy.deepcopy(fields) for n in ('q235b','qt450_10','ernife_ci')})
    rules = load(ROOT/'project/thermal-credibility-v5.4r1.yaml')['convergence']
    equal = compare(a,a,rules)
    assert equal['nonzero_metrics_pass']
    assert not equal['fusion_geometry_demonstrated']
    b = copy.deepcopy(a)
    b['material_statistics']['qt450_10']['ever_solidus_exceeded_volume_mm3'] = .01
    assert not compare(a,b,rules)['nonzero_metrics_pass']
