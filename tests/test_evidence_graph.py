"""证据链 (Evidence Graph) 自洽性与闭环校验测试。"""

from __future__ import annotations

from pathlib import Path
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
