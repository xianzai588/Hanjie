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
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    spec = importlib.util.spec_from_file_location("report_builder", ROOT / "deliverables/report/build_technical_report_pdf.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    pdfmetrics.registerFont(TTFont("Deng", "C:/Windows/Fonts/Deng.ttf"))
    pdfmetrics.registerFont(TTFont("Deng-Bold", "C:/Windows/Fonts/Dengb.ttf"))
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
