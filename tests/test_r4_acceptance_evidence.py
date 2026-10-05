"""Reject stale evidence and a size-recovery part using the no-honing gate.

Numbers in these fixtures exercise acceptance logic only; they are not FE or
material results and must never be copied into the competition report.
"""
from pathlib import Path
import copy,json,sys
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'simulation/competition-r4'))
sys.path.insert(0,str(ROOT/'src'))
from aggregate_strength import aggregate
from welded_strength import vm,mixed_mode
import check_bore_size as bore


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf8')


def test_rebuilding_increment_does_not_destroy_independent_complete_evidence(tmp_path):
    cases=['coarse','space','time'];inputs=[dict(initial_bore_diameter_mm=40.008)]*3
    for case,inp in zip(cases,inputs):save(tmp_path/case/'input.json',inp)
    inc=dict(cases=cases,input_snapshots=inputs,static_service_design_pass=True)
    keys=('cold_residual_state_pass','same_mesh_tensor_combination_pass','load_and_geometry_pass',
          'combined_bulk_strength_pass','Ni99_layer_strength_pass','QT_PMZ_strength_pass',
          'both_interfaces_mixed_mode_pass','spatial_and_time_precision_pass','fusion_and_metallurgy_design_pass')
    welded=dict(incremental_cases=cases,residual_cases=cases,residual_input_snapshots=inputs,
        initial_bore_diameter_mm=40.008,checks=dict.fromkeys(keys,True))
    save(tmp_path/'service-increment-verification.json',inc)
    save(tmp_path/'welded-strength-verification.json',welded)
    save(tmp_path/'bore-size-verification.json',dict(manufacturing_window_mm=[40.006,40.008],bore_size_design_pass=True))
    save(tmp_path/'verification.json',dict(cases=cases))
    assert aggregate(tmp_path)['complete_welded_strength_design_pass']
    save(tmp_path/'service-increment-verification.json',inc)
    assert aggregate(tmp_path)['complete_welded_strength_design_pass']
    save(tmp_path/'space'/'input.json',dict(initial_bore_diameter_mm=40.008,source_depth_mm=.9))
    assert not aggregate(tmp_path)['complete_welded_strength_design_pass']
    assert json.loads((tmp_path/'welded-strength-verification.json').read_text())==welded


def test_tensor_cancellation_and_same_point_mixed_mode():
    residual=np.array([[100.,0,0,0,0,0]])
    assert vm(residual-residual)[0]==0
    assert vm(residual)[0]+vm(-residual)[0]>190
    normal=np.array([[0.,0.,1.]]*3)
    traction=np.array([[70.,0,70.],[0,0,110.],[10.,0,-110.]])
    interaction,compression,_,_=mixed_mode(traction,normal,100.,100.,200.)
    assert interaction[0]==pytest.approx(.98)
    assert interaction[1]>1
    assert interaction[2]==pytest.approx(.01) and compression[2]==pytest.approx(.55)


def test_repeated_lower_fields_are_not_independent_refinement():
    case='8p-E285-k2500-f2-bore006-h1125-dt0125-s025'
    result=bore.lower_discretization(case,{}, {},[case,case,case])
    assert not result['spatial_and_time_response_difference_pass']
    assert 'distinct' in result['reason']


@pytest.fixture
def manufacturing(tmp_path,monkeypatch):
    monkeypatch.setattr(bore,'OUT',tmp_path)
    lower='8p-thermal-tool-bore006-h15-dt025-s05'
    upper=lower.replace('006','008')
    case_input=json.loads((ROOT/'simulation/competition-r4/results'/upper/'input.json').read_text(encoding='utf8'))
    fit=dict(position_diameter_mm=.016,sampled_bore_two_point_diameter_min_mm=40.004,
             sampled_bore_two_point_diameter_max_mm=40.015)
    row=dict(fit=fit,measurement_sampling=dict(sampling_stability_pass=True,
        selected_protocol=dict(angular_count=384,section_count=33)),cold_shell_clamp_release=dict(free_shell_release_pass=True))
    for case,diameter in ((lower,40.006),(upper,40.008)):
        inp=copy.deepcopy(case_input);inp['initial_bore_diameter_mm']=diameter
        save(tmp_path/case/'input.json',inp);save(tmp_path/case/'measurement.json',row)
    monkeypatch.setattr(bore,'endpoint_quality',lambda *a:dict(quality=True))
    monkeypatch.setattr(bore,'lower_discretization',lambda *a:dict(spatial_and_time_response_difference_pass=True,
        comparison_cases=[lower,'space','time'],physics_identical=True,records=[row]))
    monkeypatch.setattr(bore,'finish_geometry',lambda *a:dict(maximum_local_radial_stock_mm=.002,
        final_sampled_fit=dict(position_diameter_mm=.016,sampled_bore_two_point_diameter_min_mm=40.001,
            sampled_bore_two_point_diameter_max_mm=40.015)))
    verification=dict(cases=[upper]*3,records=[row]*3,position_design_pass=True)
    interval=dict(endpoint_cases=[lower,upper],interior_cases=['middle'],
        contact_and_plastic_path_checks_pass=True,response_envelope_validation_pass=True,
        response_bound_basis='test-only envelope',physics_keys=['seat_geometry'],inputs=[case_input],records=[row],
        numerical_bounds=dict(minimum_diameter_mm=40.004,maximum_diameter_mm=40.015,
            maximum_raw_position_mm=.016,maximum_nominal_finished_position_mm=.016,
            maximum_nominal_radial_stock_mm=.002))
    return tmp_path,verification,interval


def test_required_honing_cannot_use_20_um_gate(manufacturing):
    out,verification,interval=manufacturing
    save(out/'manufacturing-interval-verification.json',interval)
    direct=bore.evaluate(verification)
    assert direct['finishing_branch']=='direct_size_no_honing'
    assert direct['post_finish_position_budget_mm']==pytest.approx(.046)
    interval['numerical_bounds']['minimum_diameter_mm']=39.998
    save(out/'manufacturing-interval-verification.json',interval)
    finish=bore.evaluate(verification)
    assert finish['finishing_branch']=='limited_honing_required'
    assert finish['selected_welding_position_limit_mm']==pytest.approx(.0135)
    assert finish['post_finish_position_budget_mm']==pytest.approx(.0525)
    assert not finish['checks']['final_position_budget_pass']


@pytest.mark.parametrize('key,value',[
    ('maximum_diameter_mm',40.026),('maximum_raw_position_mm',.023),('minimum_diameter_mm',True)])
def test_interval_values_control_acceptance_even_when_flags_pass(manufacturing,key,value):
    out,verification,interval=manufacturing
    interval['numerical_bounds'][key]=value
    save(out/'manufacturing-interval-verification.json',interval)
    assert not bore.evaluate(verification)['bore_size_design_pass']
