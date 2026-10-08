"""提交物章节引用门禁：§引用必须指向说明书真实章节，且标题须渲染进 PDF。"""
import importlib.util
from pathlib import Path


def _load_lint():
    root = Path(__file__).parents[1]
    spec = importlib.util.spec_from_file_location(
        "competition_submission_lint", root / "scripts/competition_submission_lint.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.SECTION_REF_DOCS = ["deliverables/competition-route.md", "deliverables/submission-checklist.md"]
    return module


def _pdf_text():
    import pymupdf
    root = Path(__file__).parents[1]
    return "\n".join(page.get_text() for page in pymupdf.open(
        root / "output/pdf/焊接工艺设计论文-正文.pdf"))


def test_delivered_documents_reference_real_sections():
    assert _load_lint().check_section_refs(_pdf_text()) == []


def test_dangling_section_ref_is_detected(tmp_path):
    module = _load_lint()
    doc = tmp_path / "sample.txt"
    doc.write_text("A类确认清单见说明书§9.2；适用域见§99.1；设计结论见§7。", encoding="utf-8")
    module.SECTION_REF_DOCS = [str(doc)]
    errors = module.check_section_refs(_pdf_text())
    assert any("§9.2" in error for error in errors), errors
    assert any("§99.1" in error for error in errors), errors
    assert not any("§7" in error for error in errors), errors


def test_missing_pdf_heading_is_detected():
    # 传入的“PDF 文本”缺少源稿中的章节标题 → 必须报缺少章节标题而不是静默通过。
    errors = _load_lint().check_section_refs("0 设计对象\n")
    assert any("缺少章节标题" in error for error in errors), errors
