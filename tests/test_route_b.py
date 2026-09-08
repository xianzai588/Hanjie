"""保护公共观测、热账本、结构载荷与非正式证据边界。"""
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"simulation/thermal-ref"),str(ROOT/"simulation/structural-v4")]
from audit_plan8_elmer import shapes
from assess_plan8 import weights
from run_plan7 import require_refinement
from run_struct_uncertainty import drivers, operators, support_areas, ref, OUTPUT, SPEC
from assess_struct_uncertainty import compare_pair


def test_hex_gradient_and_common_projection_reproduce_affine_field():
    points=np.array([[-.2,.3,.4],[.7,-.4,.1]])
    N,D=shapes(points)
    corners=2*ref.CORNERS-1
    np.testing.assert_allclose(N.sum(axis=1),1.,atol=1.e-14)
    nodal=130+corners@np.array([3.,-7.,11.])
    np.testing.assert_allclose(N@nodal,130+points@np.array([3.,-7.,11.]),atol=1.e-12)
    np.testing.assert_allclose(np.einsum('n,qnd->qd',nodal,D),np.tile([3.,-7.,11.],(2,1)),atol=1.e-12)
    centres=np.array([[x,y,z] for x in (-1.,0.,1.) for y in (-1.,0.,1.) for z in (-1.,0.,1.)])
    ids=np.where(centres[:,0]<=0,2,3)
    valid=np.ones(len(ids),bool); valid[0]=False
    point=np.array([-.3,.2,.4]); chosen,w=weights(centres,ids,valid,point,2)
    assert np.all(ids[chosen]==2) and 0 not in chosen
    np.testing.assert_allclose(w@(130+centres[chosen]@np.array([3.,-7.,11.])),130+point@np.array([3.,-7.,11.]),atol=1.e-9)
    with pytest.raises(ValueError,match="秩不足"):
        weights(centres,np.ones(len(ids)),centres[:,2]==0,point,1)


def test_partition_evidence_keeps_physical_and_discrete_energy_distinct():
    p=ROOT/"simulation/thermal-ref/results/plan8"
    r=ref.load(p/"assessment.json")
    assert r["diagnostic_execution_checks_passed"]
    assert r["source_partition_maximum_difference_j"]<1.e-8
    for mode in ("dynamic","constant"):
        for solver in ("elmer","fvm"):
            part=r["partitions"][f"{solver}-{mode}"]
            assert sum(m["source_j"] for m in part["materials"].values())==pytest.approx(3960.,abs=1.e-8)
        d=pd.read_csv(p/f"common-probes-{mode}.csv")
        assert np.allclose(d.delta_common_c,d.elmer_common_c-d.fvm_common_c,equal_nan=True)
        assert d.loc[d.birth_fraction==0,"elmer_common_c"].isna().all()
    dynamic=r["partitions"]["elmer-dynamic"]
    constant=r["partitions"]["elmer-constant"]
    assert dynamic["maximum_material_physical_step_discrepancy_j"]>1.e-3
    assert dynamic["maximum_material_solver_discrete_step_residual_j"]<1.e-4
    assert constant["maximum_material_physical_step_discrepancy_j"]<1.e-6
    # 消融未关闭局部场差异，不能把离散残差通过解释成物理焓门通过。
    assert r["observations"]["constant"]["qt_near_interface"]["common_peak_gap_c"]>50.


def test_uniform_inherent_strain_load_is_self_equilibrated_and_matches_affine_displacement():
    points=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    mesh=SimpleNamespace(points=points,tetrahedra=np.array([[0,1,2,3]]))
    data={"n_edges":np.array([-100.,100.]),"z_edges":np.array([-100.,100.]),"index":np.array([[0,0]])}
    force,_=operators(mesh,data,1000.,.25)
    load=force(np.full((1,3),.002),np.full((1,3),.002),"uniform_half").reshape(-1,3)
    # 均匀体胀的应力为4 MPa；四面体体积1/6，解析形函数梯度已知。
    expected=4/6*np.array([[-1.,-1.,-1.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    np.testing.assert_allclose(load,expected,atol=1.e-12)
    np.testing.assert_allclose(load.sum(axis=0),0.,atol=1.e-12)
    np.testing.assert_allclose(np.cross(points,load).sum(axis=0),0.,atol=1.e-12)


def test_foundation_uses_physical_face_area_and_rank_does_not_sort_numerical_ties():
    r=74.98
    points=np.array([[r,0,0],[0,r,0],[r,0,2.]])
    mesh=SimpleNamespace(points=points,boundary_triangles=np.array([[0,1,2]]))
    w=support_areas(mesh)
    assert w.sum()==pytest.approx(r*np.sqrt(2))
    np.testing.assert_allclose(w,np.full(3,r*np.sqrt(2)/3))
    order=compare_pair(np.array([.009,.011,.015]),np.array([.01,.01,.01]),np.full(3,.0001),np.full(3,.0001),.001)
    np.testing.assert_array_equal(order,[0,0,1])


def test_thermal_checkpoint_rejects_tampering(tmp_path):
    np.savez(tmp_path/"thermal-drivers.npz",fvm=[20.])
    ref.write_json(tmp_path/"thermal-driver-inputs.json",dict(driver_sha256="wrong",source_input_hashes={"project/process.yaml":"wrong"}))
    with pytest.raises(ValueError,match="来源记录"):
        drivers(tmp_path)


def test_route_b_executed_results_do_not_bypass_formal_gate():
    r=ref.load(OUTPUT/"assessment.json")
    assert r["cases_executed"]==432 and r["execution_checks_passed"]
    assert not r["robust_candidate_ranking_established"]
    assert r["pairs"][2]["unresolved"]==r["paired_scenarios"]
    for key in ("thermal_1_allowed","formal_struct_0_allowed","physical_validation","experimental_data_required","product_position_acceptance_claim_allowed"):
        assert r[key] is False
    assert ref.load(SPEC)["metrology"]["ranking_tie_tolerance_mm"]==.001
    for case in ("REF-M","REF-F","REF-VF"):
        with pytest.raises(ValueError):
            require_refinement(case)
    stage=ref.load(ROOT/"project/stage-status.yaml")
    assert stage["route_b"]["experimental_data_required"] is False
    assert stage["stages"]["THERMAL-REF-PLAN8"]["diagnostic_iterations_used"]==2
    assert stage["stages"]["THERMAL-1"]["acceptance_result"]=="not_admitted"
