"""Assemble the fixed-topic design report, without asserting engineering release.

The separate build_submission.py retains its joint/precision/strength gates.
This package records their actual status alongside the submitted design report.
"""
from pathlib import Path
import json,re,shutil,zipfile
import fitz

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/competition-entry'


def build():
    OUT.mkdir(parents=True,exist_ok=True)
    copies={
        '01-工艺设计说明书与工程图.pdf':'output/pdf/工艺设计说明书与工程图-参赛设计稿.pdf',
        '03-工程图集.pdf':'cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf',
        '04-名义装配.step':'cad/generated/competition-design/competition-assembly-r4.step',
        '05-分层座体名义几何.step':'cad/generated/independent-precoat-curved/precoat-stack-R15-R08.step',
        '计算依据/预制工艺量核算.json':'studies/COMPETITION-DESIGN/results/precoat-process-design.json',
        '计算依据/结构工装与位置度分配.json':'studies/COMPETITION-DESIGN/results/assessment.json',
        '计算依据/后序液路容积核算.json':'studies/COMPETITION-DESIGN/results/postweld-isolation.json',
        '计算依据/基准制造复核.json':'simulation/competition-r4/results/design-repair-status-20261005.json',
        '计算依据/历史制造家族结果.json':'simulation/competition-r4/results/verification.json',
        '计算依据/历史承载参考结果.json':'simulation/competition-r4/results/service-verification.json',
        '计算依据/当前候选验证状态.json':'deliverables/report/generated/current-status.json',
        '计算依据/真实公差实体与送丝.json':'cad/generated/precoat-tolerance-family-20261007/geometry-and-feed-audit.json',
        '计算依据/小批整线资源与费用情景.json':'studies/COMPETITION-DESIGN/results/pilot-production-20261007.json',
        '计算依据/首层制造表示诊断.json':'output/review/phase-interface-diagnosis-20261007/diagnosis.json',
        '计算依据/首层原生计算实际停止状态.json':'output/review/native-manufacturing-stop-20261007/native-stop-audit.json',
    }
    source=ROOT/'deliverables/report/technical-report-v4-unified.md'
    sources=[source,ROOT/'project/precoat-process-design.yaml',ROOT/'project/precoat-speed120-candidate.yaml',
             ROOT/'project/process-r3.yaml',ROOT/'project/competition-design.yaml',ROOT/'project/pilot-production-design.yaml',
             ROOT/'cad/parametric/build_precoat_tolerance_family.py',ROOT/'cad/parametric/inspect_precoat_tolerance_steps.py',
             ROOT/'cad/parametric/build_engineering_supplements.py',ROOT/'studies/COMPETITION-DESIGN/pilot_production_resources.py']
    cards=['independent-precoat-design-card.md','first-layer-input-card.md','joint-process-card.md',
           'copper-shield-card.md','fixture-load-and-transfer-card.md','NDT-inspection-card.md',
           'cleanliness-inspection-card.md','bore-compensation-and-finish-card.md','clean-shield-engineering-detail.md',
           'precoat-tolerance-and-feed-card.md','pilot-production-and-resource-card.md']
    sources.extend(ROOT/'deliverables/process'/name for name in cards)
    for name in re.findall(r'!\[[^]]*\]\(([^)]+)\)',source.read_text(encoding='utf8')):
        sources.append(ROOT/name)
    for p in sources:copies['可编辑源文件/'+p.relative_to(ROOT).as_posix()]=p.relative_to(ROOT).as_posix()
    tolerance_dir=ROOT/'cad/generated/precoat-tolerance-family-20261007'
    tolerance=json.loads((tolerance_dir/'geometry-and-feed-audit.json').read_text(encoding='utf8'))
    for case in tolerance['cases']:
        name=case['case']+'.step'
        copies['公差设计实体/'+name]=(tolerance_dir/name).relative_to(ROOT).as_posix()
    for name,relative in copies.items():
        src=ROOT/relative
        if not src.is_file():raise FileNotFoundError(src)
        dest=OUT/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    manual=fitz.open(ROOT/'output/pdf/工艺设计说明书-参赛设计稿.pdf')
    start=None
    for i,page in enumerate(manual):
        text=re.sub(r'\s+','',page.get_text())
        if i>2 and 'HJ-W-00C独立预制与中间修整设计卡' in text:start=i;break
    if start is None:raise ValueError('Process-card section not found')
    card_pdf=fitz.open();card_pdf.insert_pdf(manual,from_page=start)
    card_pdf.set_metadata({'title':'独立预制、最终组焊与检验工艺卡','author':''})
    card_pdf.save(OUT/'02-工艺规程与检验卡.pdf');card_pdf.close()
    pages={};all_text=[]
    for name in ['01-工艺设计说明书与工程图.pdf','02-工艺规程与检验卡.pdf','03-工程图集.pdf']:
        with fitz.open(OUT/name) as doc:
            pages[name]=len(doc)
            if doc.metadata.get('author','').strip():raise ValueError('Nonempty author metadata')
            for page in doc:
                all_text.append(page.get_text())
                for block in page.get_text('blocks'):
                    if block[0]<-1 or block[1]<-1 or block[2]>page.rect.width+1 or block[3]>page.rect.height+1:
                        raise ValueError(f'Page overflow: {name}/{page.number+1}')
    exports=json.loads((ROOT/'cad/generated/engineering-drawings/pdf/pdf-exports.json').read_text(encoding='utf8'))
    if pages['03-工程图集.pdf']!=exports['sheet_count'] or {s['number'] for s in exports['sheets']}!=set(range(1,22)):
        raise ValueError('Expected continuous HJ-001..HJ-021 drawings')
    text='\n'.join(all_text)
    for forbidden in ['未取得全文','留作馆际调取','数字玩具','最终达标稿','学校：','参赛者姓名：','指导教师姓名：']:
        if forbidden in text:raise ValueError('Unresolved text: '+forbidden)
    for required in ['QT450-10','Q235B','0.05','52.084','独立','铜环','位置度','自动化']:
        if required not in text:raise ValueError('Missing required topic: '+required)
    state=json.loads((ROOT/'deliverables/report/generated/current-status.json').read_text(encoding='utf8'))
    manifest={'submission_kind':'焊接固定题工艺设计研究报告与工程图','document_package_complete':True,
              'production_release':False,'current_route_fusion_verified':False,
              'residual_position_verified':state['position_actual_family_pass'],
              'bore_size_verified':state['bore_actual_family_pass'],
              'complete_strength_verified':state['complete_strength_verified'],
              'nominal_tolerance_geometry_valid':state['tolerance_geometry']['exported_solids_valid'],
              'legacy_calculation_files_role':'历史失效/参考结果；不是CI-A1当前完整制造链',
              'included_files':[*copies,'02-工艺规程与检验卡.pdf','验证与交付状态.json','00-校方审核说明.txt'],
              'page_counts':pages,'primary_file':'01-工艺设计说明书与工程图.pdf',
              'references':'Official implementation plan pp3-5 fixed topic; p8 school-organized submission.',
              'scope':'文件齐备与计算性能分别记录；本包不冒充生产工艺评定或全部设计验证通过。'}
    (OUT/'验证与交付状态.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    (OUT/'00-校方审核说明.txt').write_text(
        '焊接固定题工艺设计作品\n\n'
        f"主文件：01-工艺设计说明书与工程图.pdf；工艺卡与{exports['sheet_count']}张图纸已合订，另提供分册、名义STEP、九组公差设计实体及可编辑源文件。\n"
        '主方案：独立CI-A1高镍预制—低碳Ni99第二层—8P低热输入GTAW—铜环实体屏障。\n'
        '文件完整性已检查；当前有效接头、完整制造精度与完整强度尚未全部验证通过，实际计算状态见正文0、4、5及验证与交付状态.json。不得将设计目标改写为已经达标。\n\n'
        '学校报名表、参赛者/教师身份及盖章汇总表由参赛团队与校方另行办理，不混入匿名技术文件。本工具不代签、不发送报名邮件。\n'
        '官方固定题说明书格式与篇幅不限，可提交研究报告、设计图或实物；不能套用铸造赛道的自编代码规则。按所附原件的焊接赛道流程及校方最新通知提交。\n'
        '可编辑源文件中保留原目录关系；图片位于其中docs/report/figures。STEP是名义/公差设计几何，尚未赋予实际切削后残余状态。\n'
        '整线设计目标8件/8 h：首层8个、第二层预留9个、延迟PT24个工艺位置；费用为假设输入情景，非供应商报价。计算依据中历史制造/承载文件不得冒充当前链结果。\n',encoding='utf8')
    files=[*copies,'02-工艺规程与检验卡.pdf','验证与交付状态.json','00-校方审核说明.txt']
    archive=ROOT/'deliverables/焊接固定题-参赛设计报告包.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for name in files:bundle.write(OUT/name,name)
    print(json.dumps({'archive':str(archive),'files':len(files),'pages':pages,'design_verified':False},ensure_ascii=False))


if __name__=='__main__':build()
