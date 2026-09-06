"""准入预检验证：质量闭合、越界拒绝及解析通过不能升级物理状态。"""
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"simulation/thermal-v5"))
from preflight_thermal1 import density_state, matrix_case, physics_blockers
from run_physics03 import load


def inputs():
    return load(ROOT/"project/g-inputs-v5.2.yaml"),load(ROOT/"project/process.yaml")["process"]["acceptable_window"]


def test_constant_tangent_expansion_matches_closed_form_and_conserves_mass():
    material = {"nominal_properties_20c":{"density_kg_m3":8000.,"alpha_per_k":1e-5}}
    phase = {"uncertainty":{"solidus_c":[1300.,1400.]}}
    state = density_state(material,phase,1000.)
    jacobian = np.exp(3e-5*(1000.-20.))
    assert state["volume_ratio"] == pytest.approx(jacobian)
    assert state["density_kg_m3"]*state["volume_ratio"] == pytest.approx(8000.)
    assert state["fixed_volume_naive_mass_error_pct"]<0
    assert density_state(material,phase,20.)["density_kg_m3"]==8000.
    assert density_state(material,phase,1500.)["density_kg_m3"] is None


def test_piecewise_alpha_uses_integral_and_refuses_uncovered_temperature():
    material = {"nominal_properties_20c":{"density_kg_m3":8000.,"alpha_per_k":1e-5},
                "temperature_dependent":{"temperatures_c":[20.,100.,200.],"alpha_per_k":[1e-5,2e-5,4e-5]}}
    phase = {"uncertainty":{"solidus_c":[1300.,1400.]}}
    expected_integral = 80.*1.5e-5+50.*2.5e-5
    state = density_state(material,phase,150.)
    assert state["volume_ratio"]==pytest.approx(np.exp(3*expected_integral))
    assert density_state(material,phase,201.)["status"]=="missing_evidence"
    with pytest.raises(ValueError):
        density_state(material,phase,np.nan)


def test_source_narrowing_is_rejected_by_spatial_resolution_without_changing_energy():
    config,window = inputs()
    nominal = matrix_case(config,window,(.55,6.,10.,2.5,2.5))
    narrow = matrix_case(config,window,(.55,4.8,10.,2.,2.))
    assert nominal["numerical_preflight_pass"]
    assert not narrow["checks"]["source_resolution"]
    assert nominal["net_line_energy_j_mm"]==narrow["net_line_energy_j_mm"]==330.
    assert narrow["thermal_simulation_executed"] is False


def test_high_efficiency_and_long_source_are_rejected_independently():
    config,window = inputs()
    forced = matrix_case(config,window,(.9,6.,10.,2.5,2.5))
    assert not forced["checks"]["line_energy"]
    long = matrix_case(config,window,(.55,6.,20.,2.5,2.5))
    assert not long["checks"]["source_boundary_margin"]
    with pytest.raises(ValueError):
        matrix_case(config,window,(.55,0.,10.,2.5,2.5))


def test_missing_or_string_physics_pass_cannot_admit_cases():
    blocked = physics_blockers({})
    assert "weld_mass_consistency" in blocked
    assert physics_blockers({"checks":{key:"PASS" for key in blocked}})==blocked
    assert physics_blockers({"checks":{key:True for key in blocked}})==["gate_status"]
    assert physics_blockers({"gate_status":"PASS","checks":{key:True for key in blocked}})==[]


def test_review_gate_and_failed_numerical_check_remain_blocking():
    checks = {key:True for key in physics_blockers({}) if key!="gate_status"}
    assert "gate_status" in physics_blockers({"gate_status":"REVIEW","checks":checks})
    checks["energy_conservation"] = False
    assert physics_blockers({"gate_status":"PASS","checks":checks})==["energy_conservation"]
    assert "weld_mass_consistency" in physics_blockers({"checks":None})


@pytest.mark.parametrize("rho",[-8000.,0.,np.nan,np.inf])
def test_invalid_reference_density_is_rejected(rho):
    with pytest.raises(ValueError,match="参考密度"):
        density_state({"nominal_properties_20c":{"density_kg_m3":rho,"alpha_per_k":1e-5}},
                      {"uncertainty":{"solidus_c":[1300.,1400.]}},150.)


@pytest.mark.parametrize("temperatures,alpha",[
    ([20.,200.,100.],[1e-5,2e-5,3e-5]),
    ([20.,100.,100.],[1e-5,2e-5,3e-5]),
    ([20.,100.],[1e-5]),
    ([100.,200.],[1e-5,2e-5]),
    ([20.,200.],[1e-5,np.nan]),
])
def test_malformed_alpha_table_is_not_silently_interpolated(temperatures,alpha):
    material = {"nominal_properties_20c":{"density_kg_m3":8000.},
                "temperature_dependent":{"temperatures_c":temperatures,"alpha_per_k":alpha}}
    with pytest.raises(ValueError,match="alpha表"):
        density_state(material,{"uncertainty":{"solidus_c":[1300.,1400.]}},150.)


def test_out_of_window_preheat_fails_preflight():
    config,window = inputs()
    config["process"]["preheat_temperature_c"] = 500.
    result = matrix_case(config,window,(.55,6.,10.,2.5,2.5))
    assert result["checks"]["line_energy"]
    assert not result["checks"]["preheat_bounds"]
    assert not result["numerical_preflight_pass"]


@pytest.mark.parametrize("section,key,value",[
    ("process","travel_speed_mm_s",0.),
    ("process","voltage_v",np.nan),
    ("thermal_grid","arc_points",0),
    ("thermal_grid","radial_points",2.5),
    ("thermal_grid","axial_max_offset_mm",-20.),
    ("heat_source","rear_fraction",0.),
    ("heat_source_path","source_end_s_mm",np.nan),
])
def test_invalid_source_geometry_fails_before_division(section,key,value):
    config,window = inputs()
    config[section][key] = value
    with pytest.raises(ValueError):
        matrix_case(config,window,(.55,6.,10.,2.5,2.5))
