"""打分矩阵防漂移门禁：JSON 格子×权重必须复现总分，说明书§1.1表格必须与 JSON 同源。

历史事故：说明书表格曾把 TIG 加权总分写成 8.40，而格子×权重为 8.50，
随后重定基又引入第二轮漂移。本测试把"格子—总分—说明书表格"三处锁死。
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
CHECKS = ROOT / "studies/COMPETITION-DESIGN/results/engineering-checks-r3.json"
REPORT_MD = ROOT / "deliverables/report/technical-report-v4-unified.md"


def _load_scoring():
    return json.loads(CHECKS.read_text(encoding="utf-8"))["scoring"]


def test_json_cells_times_weights_reproduce_totals():
    scoring = _load_scoring()
    weights, cells, totals = scoring["weights"], scoring["cells"], scoring["weighted_scores"]
    assert len(cells) == len(scoring["candidates"]) == len(totals)
    for row, total in zip(cells, totals):
        assert len(row) == len(weights)
        recomputed = round(sum(w * s for w, s in zip(weights, row)), 2)
        assert abs(recomputed - total) < 1e-9, f"总分漂移: 格子×权重={recomputed}, 记录={total}"


def test_report_table_matches_json_cells():
    scoring = _load_scoring()
    lines = REPORT_MD.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip().startswith("| 维度 |"))
    rows = []
    for ln in lines[start + 2:]:
        if not ln.strip().startswith("|"):
            break
        rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
    dim_rows = [r for r in rows if r[0] != "加权辅助总分"]
    total_row = next(r for r in rows if r[0] == "加权辅助总分")
    assert len(dim_rows) == len(scoring["weights"]), "说明书打分维度数与 JSON 权重数不一致"

    def _num(cell_text):
        return float(re.sub(r"[*（(].*$", "", cell_text.replace("**", "")).strip())

    # md 表按"维度行×候选列"组织，JSON cells 按"候选行×维度列"存储，比较需转置。
    for j, candidate in enumerate(scoring["candidates"]):
        md_col = [int(r[j + 1]) for r in dim_rows]
        assert md_col == scoring["cells"][j], f"说明书打分格子与 JSON 漂移: 候选「{candidate}」"
    md_totals = [_num(c) for c in total_row[1:]]
    assert md_totals == scoring["weighted_scores"], "说明书加权总分与 JSON 漂移"


def test_report_candidate_columns_match_json_order():
    scoring = _load_scoring()
    lines = REPORT_MD.read_text(encoding="utf-8").splitlines()
    header = next(ln for ln in lines if ln.strip().startswith("| 维度 |"))
    columns = [c.strip() for c in header.strip().strip("|").split("|")[1:]]
    # 中文列名对 JSON 候选的映射顺序固定：外塞焊/激光/微束等离子/脉冲TIG/钎焊
    expected = ["GMAW外塞焊", "激光", "微束等离子", "脉冲TIG", "钎焊"]
    assert len(columns) == len(scoring["candidates"])
    assert columns == expected
