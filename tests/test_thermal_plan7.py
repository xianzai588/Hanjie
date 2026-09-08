"""保护机制隔离的物理账本、成对比较和条件化加密边界。"""
import json
from pathlib import Path
import sys

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"simulation/thermal-ref"))
import run_plan7 as plan7
from assess_plan7 import pair_metrics
from assess_reference import nonlinear_check


def test_refinement_requires_complete_current_evidence(tmp_path):
    plan7.require_refinement("REF-C",tmp_path)
    with pytest.raises(ValueError,match="缺少"):
        plan7.require_refinement("REF-M",tmp_path)
    for case in ("REF-F","REF-VF"):
        with pytest.raises(ValueError,match="禁止"):
            plan7.require_refinement(case,tmp_path)
    digest=plan7.ref.digest(plan7.ref.HERE/"ReferenceCallbacks.F90")
    cases=[dict(case=name,passed=True,callback_sha256=digest,plan_sha256=plan7.ref.digest(plan7.PLAN)) for name in ("constant","nominal-150","nominal-1500","gauge-1500")]
    write=plan7.ref.write_json
    write(tmp_path/"birth/assessment.json",dict(birth_only_all_passed=True,cases=cases))
    write(tmp_path/"source-off/assessment.json",dict(source_off_explained=True))
    spec=plan7.ref.load(plan7.ref.SPEC)
    frozen=[plan7.ref.SPEC,*[ROOT/spec[k] for k in ("baseline","inputs","process_input","material_input","thermal_properties")]]
    hashes={p.relative_to(ROOT).as_posix():plan7.ref.digest(p) for p in frozen}
    hashes["simulation/thermal-ref/ReferenceCallbacks.F90"]=digest
    write(tmp_path/"source-off/run-inputs.json",dict(input_hashes=hashes))
    plan7.require_refinement("REF-M",tmp_path)
    cases[0]["callback_sha256"]="obsolete"
    write(tmp_path/"birth/assessment.json",dict(birth_only_all_passed=True,cases=cases))
    with pytest.raises(ValueError,match="失效"):
        plan7.require_refinement("REF-M",tmp_path)


def test_zero_transfer_birth_exposes_variable_capacity_defect():
    root=plan7.RESULTS/"birth"
    result=json.loads((root/"assessment.json").read_text(encoding="utf-8"))
    cases={c["case"]:c for c in result["cases"]}
    assert cases["constant"]["passed"]
    assert cases["constant"]["maximum_step_defect_j"]<1.e-12
    assert not result["birth_only_all_passed"]
    assert cases["nominal-150"]["steps"]==42
    assert cases["nominal-150"]["maximum_step_defect_j"]>1.e-7
    assert cases["nominal-1500"]["execution_failure"]
    for case in cases.values():
        assert all(case[k]==0 for k in ("source_w","conductivity_w_mk","convection_w_m2k","emissivity"))
        assert case["independent_vs_observer_error_j"]<1.e-10
        assert case["physical_mass_relative_error"]<1.e-10
    base=np.genfromtxt(root/"nominal-1500/birth-audit.csv",delimiter=",",names=True)
    gauge=np.genfromtxt(root/"gauge-1500/birth-audit.csv",delimiter=",",names=True)
    assert np.all(gauge["birth_enthalpy_j"]>0)
    np.testing.assert_allclose(gauge["birth_enthalpy_j"],gauge["effective_birth_mass_kg"]*12345.,atol=1.e-14,rtol=0)
    np.testing.assert_allclose(base["step_defect_j"],gauge["step_defect_j"],atol=1.e-10,rtol=0)


def test_source_off_has_no_extra_power_or_mass_step():
    out=plan7.RESULTS/"source-off"
    ledger=np.genfromtxt(out/"mechanism-ledger.csv",delimiter=",",names=True)
    last=ledger[np.argmin(abs(ledger["time_s"]-40.))]
    off=ledger[np.argmin(abs(ledger["time_s"]-40.1))]
    assert last["source_step_j"]==pytest.approx(49.5,abs=1.e-10)
    assert last["physical_birth_mass_kg"]>0
    assert off["source_step_j"]==0 and off["physical_birth_mass_kg"]==0
    assert off["step_defect_j"]==pytest.approx(.397794724,abs=1.e-8)
    assert abs(off["unexplained_step_j"])<1.e-6
    result=json.loads((out/"assessment.json").read_text(encoding="utf-8"))
    assert result["replay_sensor_maximum_difference_c"]<1.e-8
    assert max(abs(c["gaussian_vs_callback_j"]) for c in result["gauss_cross_checks"])<1.e-8
    # 机制定位不等于严格门通过；不能隐藏36 s处稍超限的余量。
    assert not result["source_off_explained"]
    with pytest.raises(ValueError,match="前置未通过"):
        plan7.require_refinement("REF-M")


def test_paired_comparison_rejects_truncated_history(tmp_path):
    for name in ("elmer","fvm"):
        (tmp_path/name).mkdir()
        np.savetxt(tmp_path/name/"sensors.dat",np.zeros((3,6)))
    with pytest.raises(ValueError,match="完整600步"):
        pair_metrics(tmp_path/"elmer",tmp_path/"fvm",[],True)
    for name,preborn in (("elmer",True),("fvm",False)):
        np.savetxt(tmp_path/name/"sensors.dat",np.column_stack([np.arange(1,601)*.1,np.full((600,5),150.)]))
        plan7.ref.write_json(tmp_path/name/"run-inputs.json",dict(preborn=preborn))
    with pytest.raises(ValueError,match="交叉配对"):
        pair_metrics(tmp_path/"elmer",tmp_path/"fvm",[],True)


def test_native_components_require_nonlinear_convergence():
    root=plan7.RESULTS/"components"
    result=json.loads((root/"assessment.json").read_text(encoding="utf-8"))
    assert result["passed"]
    assert result["callback_sha256"]==plan7.ref.digest(plan7.ref.HERE/"ReferenceCallbacks.F90")
    for name in ("interface","latent","birth"):
        assert nonlinear_check((root/name/"solver.log").read_text(encoding="utf-8"),1.e-10,1 if name=="interface" else 3)
        assert "Nonlinear System Abort Not Converged = True" in (root/name/"case.sif").read_text(encoding="ascii")


def test_full_paired_results_keep_admission_closed():
    result=json.loads((plan7.RESULTS/"assessment.json").read_text(encoding="utf-8"))
    assert all(result["same_grid_axes"].values())
    assert result["native_component_checks_passed"]
    for audit in result["welding_audits"].values():
        assert audit["complete"]
        assert audit["source_relative_error"]<1.e-8 and audit["mass_relative_error"]<1.e-10
    for name in ("weld_center","qt_near_interface"):
        assert result["comparisons"]["preborn"][name]["peak_difference_c"]>50.
    for flag in ("ref_m_allowed","ref_m_executed","ref_f_allowed","ref_vf_allowed","thermal_1_allowed","formal_struct_0_allowed"):
        assert not result[flag]
    stages=plan7.ref.load(ROOT/"project/stage-status.yaml")["stages"]
    assert stages["THERMAL-REF-PLAN7"]["diagnostic_iterations_used"]==1
    assert stages["THERMAL-1"]["acceptance_result"]=="not_admitted"
