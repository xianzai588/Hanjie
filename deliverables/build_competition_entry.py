"""Assemble the fixed-topic design report, without asserting engineering release.

The separate build_submission.py retains its joint/precision/strength gates.
This package records their actual status alongside the submitted design report.
"""
from pathlib import Path
import json,re,shutil,zipfile,os,hashlib
import fitz
import sys
import yaml

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/competition-entry'


def build():
    sys.path.insert(0,str(ROOT/'src'))
    from hanjie.reporting.current_status import write_status_artifacts
    from hanjie.reporting.publication import verify_publication
    write_status_artifacts(ROOT)  # Do not trust an older generated status file.
    spec=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text())
    verify_publication(ROOT,spec['version'])
    stage=OUT.with_name('.competition-entry-building')
    if stage.exists():shutil.rmtree(stage)
    stage.mkdir(parents=True)
    copies={
        '校方提交原件/焊接赛道实施方案.pdf':'competition/original-files/welding/第一届辽宁省大学生材料焊接与铸造工艺设计大赛实施方案.pdf',
        '校方提交原件/附件1-参赛报名表.doc':'competition/original-files/welding/附件1 辽宁省大学生材料焊接与铸造工艺设计大赛（“中铁山桥杯”焊接工艺设计赛）参赛报名表.doc',
        '校方提交原件/附件2-院校项目汇总表.xlsx':'competition/original-files/welding/附件2 各院校参赛项目汇总表.xlsx',
        '01-工艺设计说明书与工程图.pdf':'output/pdf/工艺设计说明书与工程图-参赛设计稿.pdf',
        '03-工程图集.pdf':'output/pdf/基准与候选工程图集.pdf',
        '04-完整圆环名义母件装配.step':'cad/generated/ring-baseline/ring-assembly-QT450-10-Q235B.step',
        '05-完整圆环座体.step':'cad/generated/ring-baseline/ring-seat-QT450-10.step',
        '06-焊接工艺设计论文-正文.pdf':'output/pdf/焊接工艺设计论文-正文.pdf',
        '07-圆环局部预制存留名义实体.step':'cad/generated/ring-baseline/ring-precoat-eight-windows-17solids.step',
        '08-圆环紧凑工装总装.step':'cad/generated/ring-fixture/ring-fixture-assembly.step',
        '09-圆环专属工装图.pdf':'cad/generated/ring-fixture/HJ-F-S01-ring-fixture-drawings.pdf',
        '10-圆环UT方法声路示意.pdf':'docs/report/figures/publication/ring-ut-coverage.pdf',
        '计算依据/完整圆环当前验证状态.json':'deliverables/report/generated/current-status.json',
        '计算依据/圆环冷态承载FE.json':'simulation/ring-baseline-structure/results/assessment.json',
        '计算依据/圆环制造条件分析.json':'simulation/ring-baseline-manufacturing/results/assessment.json',
        '计算依据/圆环资源与费用.json':'studies/COMPETITION-DESIGN/results/ring-production-resources.json',
        '计算依据/当前数字工位回放.json':'automation/app/results/demo-summary.json',
        '计算依据/圆环最终组焊pWPS.json':'deliverables/process/ring-final-welding-card.json',
        '创新候选/八翼名义装配.step':'cad/generated/competition-design/competition-assembly-r4.step',
        '创新候选/八翼分层座体名义几何.step':'cad/generated/independent-precoat-curved/precoat-stack-R15-R08.step',
        '计算依据/圆环名义几何与质量.json':'cad/generated/ring-baseline/geometry-quality-and-mass.json',
        '计算依据/圆环自身预制供料与热量.json':'cad/generated/ring-baseline/ring-precoat-design.json',
        '计算依据/历史八通道解析解释.json':'studies/COMPETITION-DESIGN/results/ring-control-screening.json',
        '计算依据/圆环真实工装载荷环.json':'studies/COMPETITION-DESIGN/results/ring-fixture-feasibility.json',
        '计算依据/完整圆环基准输入.yaml':'project/submission-baseline.yaml',
        '计算依据/关键设计数字索引.md':'deliverables/process/calculation-index.md',
        '计算依据/冷态对比原稿.pdf':'deliverables/recovered-20261007/焊接工艺设计论文-正文.pdf',
        '计算依据/预制工艺量核算.json':'studies/COMPETITION-DESIGN/results/precoat-process-design.json',
        '计算依据/结构工装与位置度分配.json':'studies/COMPETITION-DESIGN/results/assessment.json',
        '计算依据/后序液路容积核算.json':'studies/COMPETITION-DESIGN/results/postweld-isolation.json',
        '计算依据/历史八翼制造复核.json':'simulation/competition-r4/results/design-repair-status-20261005.json',
        '计算依据/历史制造家族结果.json':'simulation/competition-r4/results/verification.json',
        '计算依据/历史承载参考结果.json':'simulation/competition-r4/results/service-verification.json',
        '计算依据/八翼历史验证状态.json':'deliverables/report/generated/eight-wing-status.json',
        '计算依据/真实公差实体与送丝.json':'cad/generated/precoat-tolerance-family-20261007/geometry-and-feed-audit.json',
        '计算依据/小批整线资源与费用情景.json':'studies/COMPETITION-DESIGN/results/pilot-production-20261007.json',
        '计算依据/首层制造表示诊断.json':'output/review/phase-interface-diagnosis-20261007/diagnosis.json',
        '计算依据/首层原生计算实际停止状态.json':'output/review/native-manufacturing-stop-20261007/native-stop-audit.json',
    }
    source=ROOT/'deliverables/report/technical-report-v4-unified.md'
    sources=[source,ROOT/'project/precoat-process-design.yaml',ROOT/'project/precoat-speed120-candidate.yaml',
             ROOT/'project/process-r3.yaml',ROOT/'project/competition-design.yaml',ROOT/'project/pilot-production-design.yaml',
             ROOT/'cad/parametric/build_precoat_tolerance_family.py',ROOT/'cad/parametric/inspect_precoat_tolerance_steps.py',
             ROOT/'cad/parametric/build_engineering_supplements.py',ROOT/'studies/COMPETITION-DESIGN/pilot_production_resources.py',
             ROOT/'project/submission-baseline.yaml',ROOT/'project/report.yaml',
             ROOT/'cad/parametric/build_ring_baseline.py',ROOT/'docs/report/build_publication_figures.py',
             ROOT/'deliverables/report/build_technical_report_pdf.py',ROOT/'deliverables/build_competition_entry.py',
             ROOT/'src/hanjie/reporting/fonts.py',ROOT/'studies/COMPETITION-DESIGN/ring-control-screening.py',
             ROOT/'studies/COMPETITION-DESIGN/ring-fixture-feasibility.py']
    sources.extend((ROOT/'assets/fonts').glob('*'))
    for relative in ('simulation/ring-baseline-structure','simulation/ring-baseline-manufacturing',
                     'cad/parametric/ring_fixture','cad/generated/ring-fixture','automation','src/hanjie'):
        directory=ROOT/relative
        sources.extend(p for p in directory.rglob('*') if p.is_file() and p.suffix in {'.py','.md','.json','.csv','.svg','.png','.yaml'} and
                       p.name != 'progress.json' and not any(part in {'__pycache__','data'} for part in p.parts))
    sources.extend([ROOT/'scripts/build_ring_delivery.py',ROOT/'pyproject.toml',ROOT/'README.md',
                    ROOT/'scripts/generate-ring-ut-coverage.py',
                    ROOT/'simulation/ring-baseline-structure/results/medium/mesh.npz',
                    ROOT/'deliverables/competition-route.md',ROOT/'deliverables/submission-checklist.md',
                    ROOT/'docs/review/ring-delivery-repair-20261008.md',
                    ROOT/'docs/review/ring-delivery-validation-20261008.json',
                    ROOT/'deliverables/package_volumes.py',
                    ROOT/'deliverables/process/generate_ring_process.py',ROOT/'studies/COMPETITION-DESIGN/ring-production-resources.py',
                    ROOT/'simulation/competition-r4/geometry/8P-R2-t15-manifest.json'])
    sources.extend((ROOT/'docs/report/figures/publication').glob('*'))
    sources.extend((ROOT/'cad/generated/ring-baseline').glob('*.svg'))
    sources.extend((ROOT/'cad/generated/ring-baseline').glob('*.png'))
    cards=['ring-fixture-design-card.md','ring-automation-card.md','ring-production-resource-card.md','ring-ut-coverage-design.md','ring-baseline-design-card.md','ring-final-welding-card.md','ring-final-welding-card.json','manufacturing-and-inspection-card.md','calculation-index.md',
           'independent-precoat-design-card.md','first-layer-input-card.md','joint-process-card.md',
           'copper-shield-card.md','fixture-load-and-transfer-card.md','NDT-inspection-card.md',
           'cleanliness-inspection-card.md','bore-compensation-and-finish-card.md','clean-shield-engineering-detail.md',
           'precoat-tolerance-and-feed-card.md','pilot-production-and-resource-card.md']
    sources.extend(ROOT/'deliverables/process'/name for name in cards)
    for name in cards:
        card=ROOT/'deliverables/process'/name
        if card.suffix!='.md':continue
        for image in re.findall(r'!\[[^]]*\]\(([^)]+)\)',card.read_text(encoding='utf8')):
            p=ROOT/image
            if not p.is_file():p=(card.parent/image).resolve()
            sources.append(p)
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
        with src.open('rb') as stream:
            if stream.read(80).startswith(b'version https://git-lfs.github.com/spec/v1'):
                raise ValueError('包内禁止LFS指针：'+relative)
        dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
    manual=fitz.open(ROOT/'output/pdf/工艺设计说明书-参赛设计稿.pdf')
    start=None
    for i,page in enumerate(manual):
        lines=[re.sub(r'\s+','',line) for line in page.get_text().splitlines()]
        if i>3 and 'HJ-S01完整圆环基准与工序接口设计卡' in lines:start=i;break
    if start is None:raise ValueError('Process-card section not found')
    card_pdf=fitz.open();card_pdf.insert_pdf(manual,from_page=start)
    card_pdf.set_metadata({'title':'独立预制、最终组焊与检验工艺卡','author':''})
    card_pdf.save(stage/'02-工艺规程与检验卡.pdf');card_pdf.close();manual.close()
    pages={};all_text=[]
    for name in ['01-工艺设计说明书与工程图.pdf','02-工艺规程与检验卡.pdf','03-工程图集.pdf','06-焊接工艺设计论文-正文.pdf']:
        with fitz.open(stage/name) as doc:
            pages[name]=len(doc)
            if doc.metadata.get('author','').strip():raise ValueError('Nonempty author metadata')
            for page in doc:
                all_text.append(page.get_text())
                for block in page.get_text('blocks'):
                    if block[0]<-1 or block[1]<-1 or block[2]>page.rect.width+1 or block[3]>page.rect.height+1:
                        raise ValueError(f'Page overflow: {name}/{page.number+1}')
    exports=json.loads((ROOT/'cad/generated/engineering-drawings/pdf/pdf-exports.json').read_text(encoding='utf8'))
    fixture_pages=len(fitz.open(ROOT/'cad/generated/ring-fixture/HJ-F-S01-ring-fixture-drawings.pdf'))
    if pages['03-工程图集.pdf']!=exports['sheet_count']+3+fixture_pages or {s['number'] for s in exports['sheets']}!=set(range(1,22)):
        raise ValueError('Expected continuous HJ-001..HJ-021 drawings')
    text='\n'.join(all_text)
    for forbidden in ['未取得全文','留作馆际调取','数字玩具','最终达标稿','学校：','参赛者姓名：','指导教师姓名：']:
        if forbidden in text:raise ValueError('Unresolved text: '+forbidden)
    for required in ['QT450-10','Q235B','0.05','52.084','独立','铜环','位置度','自动化']:
        if required not in text:raise ValueError('Missing required topic: '+required)
    state=json.loads((ROOT/'deliverables/report/generated/current-status.json').read_text(encoding='utf8'))
    legacy=state['historical_eight_wing']
    manifest={'process_version':state['process_version'],'primary_baseline_verification':state['primary_baseline_verification'],'submission_kind':'焊接固定题工艺设计研究报告与工程图','document_package_complete':True,
              'production_release':False,
              'submission_baseline':'完整圆环母件＋8×18 mm分段连接设计',
              'baseline_geometry':'cad/generated/ring-baseline/geometry-quality-and-mass.json',
              'engineering_drawings':{'baseline':'HJ-S01..HJ-S02','primary_fixture':'HJ-F-S01..HJ-F-S03','innovation_candidate_and_tooling':'HJ-001..HJ-021'},
              'innovation_candidate_verification':{
                  'physical_object':'8P-R2-t15八翼候选',
                  'current_route_fusion_verified':False,
                  'residual_position_verified':legacy['position_actual_family_pass'],
                  'bore_size_verified':legacy['bore_actual_family_pass'],
                  'complete_strength_verified':legacy['complete_strength_verified'],
                  'nominal_tolerance_geometry_valid':legacy['tolerance_geometry']['exported_solids_valid']},
              'legacy_calculation_files_role':'按原实体身份用于选型与问题分析；不转写圆环制造性能',
              'included_files':[*copies,'02-工艺规程与检验卡.pdf','验证与交付状态.json','00-校方审核说明.txt'],
              'page_counts':pages,'primary_file':'01-工艺设计说明书与工程图.pdf',
              'references':'Official implementation plan pp3-5 fixed topic; p8 school-organized submission.',
              'scope':'报告与工程图的完整设计论证；试制按工艺卡完成接头、孔轴和洁净检查。'}
    (stage/'验证与交付状态.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    (stage/'00-校方审核说明.txt').write_text(
        '焊接固定题工艺设计作品\n\n'
        f"主文件：01-工艺设计说明书与工程图.pdf；另有正文、工艺卡和工程图分册。图纸为完整圆环基准HJ-S01、局部预制断面HJ-S02、圆环专属工装图{fixture_pages}页及{exports['sheet_count']}张八翼候选/工装图。\n"
        '方案：完整圆环为结构基准，八翼开口为创新候选。壳外独立高镍预制、低碳第二层及孔加工先行；入壳后执行低热GTAW与铜实体洁净屏障。\n'
        '数字按设计输入、守恒核算、已有计算和试制方法分别标识。已有八翼计算保留原对象，圆环的母件几何与质量由本次STEP重读核对。工程确认按HJ-M-01执行。\n\n'
        '学校报名表、参赛者/教师身份及盖章汇总表由参赛团队与校方另行办理，不混入匿名技术文件。本工具不代签、不发送报名邮件。\n'
        '官方固定题说明书格式与篇幅不限，可提交研究报告、设计图或实物；不能套用铸造赛道的自编代码规则。按所附原件的焊接赛道流程及校方最新通知提交。\n'
        '可编辑源文件保留原目录关系并附中文字体与许可证，可直接修改Markdown、SVG及参数脚本。完整计算与构建在Hanjie仓库根目录执行；此源文件副本用于内容与图形编辑。\n'
        '圆环母件装配、座体及17实体预制STEP分别见04、05、07；圆环工装总装和专属图见08、09；过渡层加工断面见HJ-S02。八翼名义分层及九组公差实体放在创新候选/公差目录。\n'
        '圆环小批规划8件/8 h，首层10个、第二层10个、延迟PT24个位置，共44位。圆环费用已按自身物料/操作核算：3人专线178.69元/件、共享147.56元/件；均为预算。八翼原表作为历史情景。\n',encoding='utf8')
    files=[*copies,'02-工艺规程与检验卡.pdf','验证与交付状态.json','00-校方审核说明.txt']
    archive=ROOT/'deliverables/焊接固定题-参赛设计报告包.zip'
    if len(files)!=len(set(files)):raise ValueError('Duplicate package paths')
    temporary=archive.with_suffix('.building.zip')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as bundle:
        for name in files:bundle.write(stage/name,name)
    with zipfile.ZipFile(temporary) as bundle:
        if bundle.testzip() is not None or set(bundle.namelist())!=set(files):
            raise ValueError('Incomplete package archive')
    if OUT.exists():shutil.rmtree(OUT)
    os.replace(stage,OUT)
    os.replace(temporary,archive)
    record=ROOT/'deliverables/COMPETITION-R4-DESIGN-SHA256.txt'
    targets=[archive,*[OUT/name for name in files]]
    record.write_text('# 2026-10-08 参赛设计材料封版 SHA256\n# 记录本次设计文件；历史R3记录保留其原快照身份。\n'+
        ''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(ROOT).as_posix()+'\n' for p in targets),encoding='utf8')
    from package_volumes import split_package
    split_package(archive)
    print(json.dumps({'archive':str(archive),'files':len(files),'pages':pages,'design_verified':False},ensure_ascii=False))


if __name__=='__main__':build()
