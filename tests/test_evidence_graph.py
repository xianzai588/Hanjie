"""证据链 (Evidence Graph) 自洽性与闭环校验测试。"""

from __future__ import annotations

from pathlib import Path
import json
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_evidence_graph_is_closed_loop() -> None:
    graph_path = ROOT / "evidence" / "evidence_graph.yaml"
    assert graph_path.exists(), "evidence_graph.yaml 不存在"

    with graph_path.open("r", encoding="utf-8") as f:
        graph = yaml.safe_load(f)

    taxonomy = graph["taxonomy"]
    all_evidence_ids = set()
    for category, items in taxonomy.items():
        for item_id in items.keys():
            all_evidence_ids.add(item_id)

    claims = graph["claims_graph"]
    assert len(claims) >= 6, "至少应有 6 条核心工程主张"

    for claim_id, data in claims.items():
        assert "statement" in data
        assert "supporting_evidence" in data
        assert len(data["supporting_evidence"]) >= 1, f"{claim_id} 缺乏支持证据"

        # 检查每个支持证据 ID 是否均在分类字典中登记
        for ev_id in data["supporting_evidence"]:
            assert ev_id in all_evidence_ids, f"{claim_id} 引用的证据 {ev_id} 在 taxonomy 中未定义！"


def test_evidence_levels_and_references() -> None:
    from hanjie.domain.evidence import validate_evidence_graph
    graph = yaml.safe_load((ROOT / "evidence/evidence_graph.yaml").read_text(encoding="utf-8"))
    assert validate_evidence_graph(graph, ROOT) == []
    graph["taxonomy"]["simulations"]["SIM-FE3D-BASE"]["status"] = "gate_b1_passed"
    assert validate_evidence_graph(graph, ROOT)
    graph["taxonomy"]["simulations"]["SIM-FE3D-BASE"]["evidence_level"] = "solver_verified"
    assert any("artifacts" in e for e in validate_evidence_graph(graph, ROOT))


def test_low_level_evidence_cannot_promote_item_or_claim() -> None:
    from hanjie.domain.evidence import validate_evidence_graph
    graph = yaml.safe_load((ROOT / "evidence/evidence_graph.yaml").read_text(encoding="utf-8"))
    graph["taxonomy"]["simulations"]["SIM-FE3D-BASE"]["status"] = "verified"
    errors = validate_evidence_graph(graph, ROOT)
    assert any("low-level evidence cannot pass verification" in e for e in errors)

    graph = yaml.safe_load((ROOT / "evidence/evidence_graph.yaml").read_text(encoding="utf-8"))
    graph["claims_graph"]["CLAIM-004"]["status"] = "verified"
    errors = validate_evidence_graph(graph, ROOT)
    assert any("low-level support cannot promote claim" in e for e in errors)


def test_tolerance_chains_do_not_claim_closure() -> None:
    budget = yaml.safe_load((ROOT / "project/tolerance.yaml").read_text(encoding="utf-8"))
    product = budget["product_geometry_chain"]
    assert abs(sum(product["contributions_mm"].values()) - product["worst_case_design_sum_mm"]) < 1e-12
    assert product["worst_case_design_sum_mm"] > budget["target"]["radial_deviation_limit_mm"]
    assert budget["measurement_chain"]["expanded_uncertainty_mm"] is None
    assert product["p95_mm"] is None


def test_pareto_filter_excludes_dominated_candidate(monkeypatch) -> None:
    from hanjie.optimization.robust_pareto import RobustCoDesignOptimizer, RobustDesignCandidate
    optimizer = RobustCoDesignOptimizer()
    def evaluate(cid, n, length, width, current, preheat):
        score = 1.0 if cid == "OPT-4P-MIN-HEAT" else 2.0
        return RobustDesignCandidate(cid, n, length, width, current, preheat,
                                     score, score, score, score, score, score)
    monkeypatch.setattr(optimizer, "evaluate_candidate", evaluate)
    front = optimizer.generate_pareto_front()
    assert [r.design_id for r in front] == ["OPT-4P-MIN-HEAT"]
    assert front[0].is_pareto_optimal


def test_robust_study_keeps_finite_candidate_set_explicit() -> None:
    from hanjie.optimization.robust_pareto import RobustCoDesignOptimizer
    optimizer = RobustCoDesignOptimizer(monte_carlo_samples=8)
    candidates = optimizer.evaluate_handpicked_candidates()
    front = optimizer.generate_pareto_front()
    assert len(candidates) == 7
    assert 0 < len(front) <= len(candidates)
    assert all(candidate.evidence_level == "surrogate_result" for candidate in candidates)
    assert all(candidate.is_pareto_optimal for candidate in front)


def test_pdf_builder_reads_current_markdown(tmp_path) -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("report_builder", ROOT / "deliverables/report/build_technical_report_pdf.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.register_project_fonts(ROOT)
    source = tmp_path / "report.md"
    source.write_text("# Current source sentinel\nChanged evidence: surrogate_result", encoding="utf-8")
    story = builder.build_story(source)
    assert any("Current source sentinel" in getattr(item, "text", "") for item in story)
    assert builder.SOURCE.name == "technical-report-v4-unified.md"
    assert builder.OUT.name == "technical-report-v4.pdf"


def test_v42_artifacts_keep_current_evidence_boundaries() -> None:
    fe = yaml.safe_load((ROOT / "studies/FE3D-BASE/results/convergence_summary.json").read_text(encoding="utf-8"))
    assert fe["evidence_level"] == "surrogate_result"
    assert fe["solver_executed"] is False
    assert fe["gate_b1_passed"] is False
    assert fe["energy_balance_error_pct"] is None

    adaptive = json.loads((ROOT / "studies/ADAPTIVE-SEQUENCE/results/adaptive_sequence_study.json").read_text(encoding="utf-8"))
    disturbed = {row["name"]: row for row in adaptive["disturbed_condition"]}
    assert disturbed["S3-DISTURBED"]["p_mm"] == pytest.approx(0.06648, abs=1e-5)
    assert disturbed["ADAPTIVE-TEMPERATURE-DRIVEN"]["p_mm"] == pytest.approx(0.07220, abs=1e-5)
    assert all(adaptive["fairness_check"].values())

    calibration_text = (ROOT / "data/synthetic/few-shot-calibration/calibration_summary.json").read_text(encoding="utf-8")
    calibration = json.loads(calibration_text)
    assert calibration["evidence_level"] == "synthetic_demo"
    assert calibration["uncertainty_reduction_pct"] is None
    assert calibration["excluded_trial_types"] == ["hardness"]
    assert all("measured" not in key.lower() for key in calibration)

    robust = json.loads((ROOT / "studies/ROBUST-OPT/results/robust_pareto_summary.json").read_text(encoding="utf-8"))
    assert robust["candidate_count"] == 7
    assert robust["search_scope"] == "seven_handpicked_candidates"
    assert all(row["p95_p_mm"] > 0.05 for row in robust["evaluated_candidates"])


def test_generated_report_status_uses_current_authorities() -> None:
    from hanjie.reporting.current_status import collect_current_status,render_markdown
    status = collect_current_status(ROOT)
    assert status["stages"]["stages"]["THERMAL-0.4R1"]["execution_status"]=="ten_case_run_and_audit_completed"
    assert status["stages"]["stages"]["THERMAL-0.4R1"]["acceptance_result"]=="failed_spatial_convergence"
    assert status["stages"]["stages"]["STRUCT-0"]["execution_status"]=="not_executed"
    assert status["tolerance"]["status"]=="not_closed"
    assert status["joint"]["nominal_wire_deposition"]["equivalent_ideal_fillet_leg_mm"]==pytest.approx(1.7366430137)
    assert status["structural"]["ranking"][0]["model_id"]=="Continuous"
    assert status["thermal"]["stage"]=="THERMAL-0.4R1"
    assert status["thermal_spatial_fix"]["stage"]=="THERMAL-0.4R2-A-FIXED-GEOMETRY"
    assert status["thermal_spatial_fix"]["spatial_gate_pass"] is False
    assert status["thermal_xsec"]["stage"]=="THERMAL-0.5-XSEC"
    assert status["thermal_xsec"]["time_step_recheck_allowed"] is False
    assert status["thermal_boundary_neumann"]["formal_struct_0_allowed"] is False
    assert status["joint_load_basis"]["decision"]["three_point_five_mm_necessary"] is None
    assert all(status["structural_3d_components"]["checks"].values())
    assert all(status["structural_global_newton"]["checks"].values())
    assert status["continuous_unified_mesh"]["struct_prep_gate_pass"] is False
    assert status["continuous_swept_mesh"]["mesh_acceptance_pass"] is True
    assert status["struct0_dress_rehearsal"]["struct0_prep_status"] == "ready_pending_admitted_thermal_history"
    assert "自动生成的当前证据摘要" in render_markdown(status)
    assert "未校准局部热诊断；禁止正式整件性能结论" in render_markdown(status)


def test_active_structural_gate_points_to_current_failed_assessment() -> None:
    prep = yaml.safe_load((ROOT/"project/struct-0-prep.yaml").read_text(encoding="utf-8"))
    gate = json.loads((ROOT/prep["thermal_gate"]).read_text(encoding="utf-8"))
    assert gate["stage"] == "THERMAL-0.7-BOUNDARY-NEUMANN"
    assert prep["thermal_gate_field"] == "spatial_gate_pass"
    assert gate[prep["thermal_gate_field"]] is False
    assert prep["formal_thermal_coupling_allowed"] is False


def test_numerical_and_physical_thermal_routes_are_not_conflated() -> None:
    stages = yaml.safe_load((ROOT/"project/stage-status.yaml").read_text(encoding="utf-8"))["stages"]
    assert stages["THERMAL-1"]["upstream_dependencies"] == ["THERMAL-NUMERICAL-GATE"]
    assert stages["THERMAL-1"]["optional_physical_dependency"] == "THERMAL-PHYSICAL-CALIBRATION"
    assert stages["THERMAL-NUMERICAL-GATE"]["acceptance_result"] == "not_passed"
    assert stages["THERMAL-PHYSICAL-CALIBRATION"]["acceptance_result"] == "not_executed"


def test_struct_prep_records_global_solver_without_claiming_full_part_solution() -> None:
    prep = yaml.safe_load((ROOT/"project/struct-0-prep.yaml").read_text(encoding="utf-8"))
    assert prep["constitutive"]["three_dimensional_j2"]["status"] == "algorithm_verified"
    assert prep["constitutive"]["affine_tetrahedral_small_mesh"]["status"] == "equilibrium_verified"
    assert prep["constitutive"]["elastoplastic_solver"]["status"] == "sparse_global_newton_sector_rehearsal_verified"
    assert prep["geometry"]["unified_mesh"]["status"] == "swept_topology_quality_admitted"
    assert prep["geometry"]["heat_to_structure_mapping"]["status"] == "local_benchmark_passed_formal_load_blocked"
    assert prep["acceptance"]["struct_0_continuous_baseline_ready"] == "ready_pending_admitted_thermal_history"


def test_current_report_has_no_known_v42_stale_claims() -> None:
    report = (ROOT/"deliverables/report/technical-report-v4-unified.md").read_text(encoding="utf-8")
    assert "COMPETITION-R1" in report
    assert "尚未完成 FAIR-A/B" not in report
    assert "GB/T 1182-2008" not in report
    assert "THERMAL-0.4R1" in report
    assert "Continuous 0.000304 mm" in report
