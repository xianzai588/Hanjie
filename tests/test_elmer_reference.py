"""覆盖独立参考的几何、热源、观测语义和拒绝准入关键链路。"""
import sys
import json
from pathlib import Path

import numpy as np
import pytest


ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/"simulation/thermal-ref"
sys.path.insert(0,str(DIRECTORY))
import elmer_reference as ref
from assess_reference import cooling_metric, nonlinear_check


@pytest.fixture(scope="module")
def case():
    spec=ref.load(ref.SPEC)
    config=ref.load(ROOT/spec["inputs"])
    process=ref.load(ROOT/spec["process_input"])
    return spec,config,process,ref.geometry(config,process,{**spec["mesh"],**spec["cases"]["REF-C"]})


def test_independent_geometry_preserves_mass_gap_and_materials(case):
    spec,config,process,g=case
    material=g["ids"]; centres=g["nodes"][g["conn"]-1].mean(axis=1)
    assert g["area"]==pytest.approx(1.507964473723101)
    assert g["volume"][material==3].sum()==pytest.approx(g["area"]*60)
    assert np.all(centres[material==1,1]>0)
    assert np.all(centres[material==2,1]<-.02)
    assert not np.any((material!=3)&(centres[:,1]>-.02)&(centres[:,1]<0))
    assert g["leg"]==pytest.approx(1.7366430109398425)


def test_projected_source_conserves_power_and_never_crosses_artificial_boundaries(case):
    _,config,_,g=case
    for deposited in (False,True):
        weights=ref.visible_faces(g,deposited,config["heat_source"]["b_radial_mm"])
        assert sum(weights.values())==pytest.approx(1.,abs=1.e-12)
        assert min(weights.values())>=0
    rows,_=ref.boundaries(g,config)
    assert np.all(rows[rows[:,2]==1,6:8]==0)
    # 每个横截面、每种可见状态只有一个首交面接受同一束射线。
    for i in np.unique(g["index"][:,0]):
        r=rows[g["index"][rows[:,0].astype(int)-1,0]==i]
        assert r[:,6].sum()==pytest.approx(1.,abs=1.e-12)
        s=g["axes"][0][i]
        if -30<=s<30:
            assert r[:,7].sum()==pytest.approx(1.,abs=1.e-12)


def test_fixed_points_are_affine_exact_and_material_checked(case):
    spec,_,_,g=case
    points=ref.load(ROOT/spec["baseline"])["observation_points"]
    stencils=ref.sensor_stencils(g,points)
    values=13.+g["nodes"]@np.array([2.,3.,-7.])
    for p in stencils:
        assert np.dot(values[np.array(p["nodes"])-1],p["weights"])==pytest.approx(13.+np.dot(p["coordinate"],[2.,3.,-7.]))
    wrong=[{**points[0],"material_id":1}]
    with pytest.raises(ValueError,match="材料"):
        ref.sensor_stencils(g,wrong)


def test_cooling_never_fabricates_a_censored_cycle():
    assert cooling_metric(np.arange(3),np.array([900.,700.,600.]))["status"]=="right_censored"
    result=cooling_metric(np.arange(5),np.array([900.,400.,900.,700.,400.]))
    assert result["t8_5_s"]==pytest.approx(3+2/3-2.5)
    assert cooling_metric(np.arange(2),np.array([700.,600.]))["t8_5_s"] is None


def test_unconverged_and_truncated_logs_are_rejected():
    line="MAIN: Time: 1/1: 0.1\nComputeChange: NS (ITER=3) (NRM,RELC): ( 123.0 1.0E-09 ) :: heat equation"
    assert nonlinear_check(line,1.e-8,1)
    assert not nonlinear_check(line,1.e-8,2)
    assert not nonlinear_check(line.replace('1.0E-09','1.0E-02'),1.e-8,1)


def test_reference_is_fail_closed_and_uses_native_solver(case):
    spec,_,_,_=case
    assert not spec["thermal_1_allowed"] and not spec["formal_struct_0_allowed"]
    sif=ref.sif(spec["solver"],600)
    assert 'Procedure = "HeatSolve" "HeatSolver"' in sif
    assert 'Temperature Condition' in sif
    assert 'Lumped Mass Matrix = True' in sif


def test_recorded_reference_cannot_open_structural_admission():
    result=json.loads((DIRECTORY/"results/REF-C/assessment.json").read_text(encoding="utf-8"))
    stages=ref.load(ROOT/"project/stage-status.yaml")["stages"]
    assert result["execution_status"]=="full_history_executed"
    assert result["checks"]["component_verification"]
    assert not result["checks"]["final_enthalpy_balance"]
    assert not result["thermal_1_allowed"] and not result["formal_struct_0_allowed"]
    assert stages["THERMAL-REF"]["evidence"].endswith("REF-C/assessment.json")
    assert stages["THERMAL-1"]["acceptance_result"]=="not_admitted"
    assert stages["STRUCT-0"]["acceptance_result"]=="blocked_by_thermal_only"
