"""提交物页数口径门禁：文档声明必须与 manifest 实际计数一致。"""
import importlib.util
import json
from pathlib import Path


def _load_lint():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "competition_submission_lint", root / "scripts/competition_submission_lint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repo_documents_match_manifest_page_counts():
    root = Path(__file__).parents[1]
    manifest = json.loads((root / "deliverables/submission/manifest.json").read_text(encoding="utf-8"))
    assert _load_lint().check_page_claims(manifest) == []


def test_stale_page_claims_are_detected():
    scan = _load_lint().scan_page_claims
    actual = {"report": 14, "drawing": 6}
    stale = [
        "当前构建为14页说明书、5页设计图",
        "交付10页说明书、5页设计图与可复算数据",
        "交付说明书、五页图纸、名义装配STEP",
        "当前说明书和四页图集采用圆柱胀套",
        "（当前版本为14页与5页）",
        "导出图集共5页",
    ]
    for text in stale:
        assert scan("样本", text, actual), f"未识别过期页数: {text}"
    for text in ["当前构建为14页说明书、6页设计图", "交付说明书、六页设计图集", "（当前版本为14页与6页）"]:
        assert scan("样本", text, actual) == []


def test_parse_count_accepts_arabic_and_chinese():
    parse = _load_lint().parse_count
    assert (parse("14"), parse("6"), parse("六"), parse("十"), parse("十四")) == (14, 6, 6, 10, 14)
