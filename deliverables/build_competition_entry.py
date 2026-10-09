"""Publish one anonymous, self-contained judge PDF and two geometry companions."""
from pathlib import Path
import json, re, shutil, zipfile
import fitz, yaml
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/competition-entry'
ARCHIVE=ROOT/'deliverables/焊接固定题-参赛设计报告包.zip'

def build():
    config=yaml.safe_load((ROOT/'project/report.yaml').read_text(encoding='utf8'))['pdf']
    baseline=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text(encoding='utf8'))
    OUT.mkdir(parents=True,exist_ok=True)
    name='01-焊接工艺设计说明书与工程图.pdf'
    shutil.copyfile(ROOT/config['combined_pdf'],OUT/name)
    with fitz.open(OUT/name) as doc:
        pages=len(doc);text='\n'.join(p.get_text() for p in doc)
        outline=doc.get_toc()
        bookmarks=len(outline)
        roots={re.sub(r'\s+','',item[1]):item[2] for item in outline if item[0]==1}
        abstract=roots['设计概要']
        appendix_a=next(page for title,page in roots.items() if title.startswith('附录A'))
        appendix_b=next(page for title,page in roots.items() if title.startswith('附录B'))
        appendix_c=next(page for title,page in roots.items() if title.startswith('附录C'))
        sections=dict(封面与目录=dict(start=1,end=abstract-1,pages=abstract-1),
            设计概要与九章正文及参考文献=dict(start=abstract,end=appendix_a-1,pages=appendix_a-abstract),
            附录A工艺规程与检验卡=dict(start=appendix_a,end=appendix_b-1,pages=appendix_b-appendix_a),
            附录B按比例工程图=dict(start=appendix_b,end=appendix_c-1,pages=appendix_c-appendix_b),
            附录C工艺与工装功能示意=dict(start=appendix_c,end=pages,pages=pages-appendix_c+1))
        if doc.metadata.get('author','').strip():raise ValueError('Author metadata must be anonymous')
        for token in ['Claude','Codex','haha','C:/Users/','E:\\AI','第二轮输入独立审核','原生重启','出生域','52.084']:
            if token.lower() in text.lower():raise ValueError('Internal/identity text in submission: '+token)
        for page in doc:
            for block in page.get_text('blocks'):
                if block[0]<-1 or block[1]<-1 or block[2]>page.rect.width+1 or block[3]>page.rect.height+1:
                    raise ValueError(f'Text outside page {page.number+1}')
    steps={'02-八翼名义装配.step':baseline['geometry']['assembly_step'],
           '03-八翼曲面两层座体.step':'cad/generated/independent-precoat-curved/precoat-stack-R15-R08.step'}
    for dest,src in steps.items():
        content=(ROOT/src).read_text(encoding='utf8')
        content,n=re.subn(r"FILE_NAME\s*\(.*?\);", "FILE_NAME('8P-R2-t15','2026-10-09T00:00:00',(''),(''),'Open CASCADE','Engineering design','');",content,count=1,flags=re.S)
        if n!=1:raise ValueError('STEP header not found')
        header=content.split('DATA;',1)[0]
        if any(t.lower() in header.lower() for t in ['haha','Claude','Codex','C:/Users','E:\\AI']):raise ValueError('STEP identity remains')
        (OUT/dest).write_text(content,encoding='utf8')
    with fitz.open(ROOT/config['paper_pdf']) as doc:paper_pages=len(doc)
    with fitz.open(ROOT/config['manual_pdf']) as doc:manual_pages=len(doc)
    note=f"""QT450-10主轴承座与Q235B壳体焊接工艺设计
参赛对象：8P-R2-t15八翼径向柔顺槽方案。

建议阅读顺序
先读主PDF的设计概要及第1章，了解指标、创新和总体路线；第3、5、6章说明材料链、位置度与承载；第7、9章给出检测判据和首件实施安排。
主PDF共{pages}页：封面与目录{abstract-1}页，设计概要、九章正文与参考文献{appendix_a-abstract}页，附录A工艺规程与检验卡{appendix_b-appendix_a}页，附录B按比例工程图5页，附录C工艺与工装功能示意18页。目录与{bookmarks}个书签对应，可跳转至章节、二级标题、各工艺卡、工程图和工艺附图。
工程图HJ-F01～05依次为座体零件、焊接接头、焊接装配、定位退出工装、首批工作站。工艺附图说明密封、气水、回收和检测接口，制造尺寸结合工程图和现行工艺卡使用。

文件用途
01是完整参赛作品；02、03是名义装配与两层预制几何的STEP辅助文件。最终孔径在入壳装夹态一次成形；完全卸夹后用独立A/B评价孔轴位置度。计算与试制验收分别在正文相应章节列明。
材料清单.json列出本包全部文件及页数。
"""
    (OUT/'00-提交与阅读说明.txt').write_text(note,encoding='utf8')
    files=[dict(path='00-提交与阅读说明.txt',purpose='评委阅读导航'),dict(path=name,purpose='完整参赛作品：说明书、工艺卡、工程图和工艺附图',pages=pages),dict(path='02-八翼名义装配.step',purpose='名义装配几何辅助'),dict(path='03-八翼曲面两层座体.step',purpose='两层预制名义几何辅助')]
    manifest=dict(design='8P-R2-t15',edition='2026-10-09',main_pdf_pages=pages,body_pdf_pages=paper_pages,
        manual_pdf_pages=manual_pages,navigation_bookmarks=bookmarks,main_pdf_sections=sections,scaled_engineering_drawings=5,nts_process_illustrations=18,files=files+[dict(path='材料清单.json',purpose='本包文件及页数组成')])
    (OUT/'材料清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    expected={f['path'] for f in manifest['files']}
    actual={p.relative_to(OUT).as_posix() for p in OUT.rglob('*') if p.is_file()}
    if actual!=expected:raise ValueError('Unexpected package members; archive the previous export before publishing: '+str(actual-expected))
    with zipfile.ZipFile(ARCHIVE,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as bundle:
        for file in sorted(expected):bundle.write(OUT/file,file)
    with zipfile.ZipFile(ARCHIVE) as bundle:
        if bundle.testzip() is not None:raise ValueError('Archive integrity error')
    print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':build()
