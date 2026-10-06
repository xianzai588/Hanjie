"""Rebuild the review bundle and inspect changed PDF pages, never the final package."""
from pathlib import Path
import json
import fitz
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT/'output/pdf/工艺设计说明书-修订审阅稿.pdf'
DRAWINGS = ROOT/'cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf'
COMBINED = ROOT/'output/pdf/工艺设计说明书与工程图-修订审阅稿.pdf'
OUT = ROOT/'output/review/route-repair-20261006'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.append(str(REPORT))
    writer.append(str(DRAWINGS))
    writer.add_metadata({'/Title': 'QT450-10/Q235B 工艺设计说明书与工程图 - 修订审阅稿',
                         '/Author': '', '/Subject': '有效接头与分工序工艺窗口重选'})
    writer.write(str(COMBINED))
    checks = {}
    for label, path in [('report', REPORT), ('drawings', DRAWINGS), ('combined', COMBINED)]:
        doc = fitz.open(path)
        text = '\n'.join(page.get_text() for page in doc)
        checks[label] = dict(path=str(path), pages=len(doc), author=doc.metadata.get('author', ''),
                             empty_pages=[i+1 for i,p in enumerate(doc) if not p.get_text().strip()])
        if label == 'report':
            assert '141.7' not in text and '125.781' in text
            assert '§4.3' not in text
            changed = [i for i,p in enumerate(doc) if '125.781' in p.get_text() or '排液方法边界' in p.get_text()]
            for i in sorted({0, *changed}):
                doc[i].get_pixmap(matrix=fitz.Matrix(1.3, 1.3), alpha=False).save(OUT/f'report-page-{i+1}.png')
            checks[label]['changed_pages'] = [i+1 for i in changed]
        doc.close()
    with fitz.open(ROOT/'cad/generated/engineering-drawings/pdf/postweld-isolation.pdf') as drawing:
        assert '净差压' in drawing[0].get_text()
        drawing[0].get_pixmap(matrix=fitz.Matrix(1.3, 1.3), alpha=False).save(OUT/'HJ-015.png')
    assert checks['combined']['pages'] == checks['report']['pages']+checks['drawings']['pages']
    assert all(c['author'] in ('', 'anonymous') and not c['empty_pages'] for c in checks.values())
    checks['final_submission_rebuilt'] = False
    checks['scope'] = 'changed review pages and author fields empty/anonymous; not all attachment anonymity or scientific qualification'
    (OUT/'artifact-checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
