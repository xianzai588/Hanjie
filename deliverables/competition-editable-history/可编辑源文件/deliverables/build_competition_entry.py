"""Package the anonymous 8P engineering manual, pWPS and drawings with editable sources."""
from pathlib import Path
import json, os, re, shutil, sys, zipfile
import fitz
import yaml
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from hanjie.reporting.current_status import write_status_artifacts
OUT=ROOT/'deliverables/competition-entry'
ATTACHMENTS=ROOT/'deliverables/competition-editable-history'
MAIN_CARDS=('manufacturing-and-inspection-card.md','independent-precoat-design-card.md',
 'first-layer-input-card.md','precoat-tolerance-and-feed-card.md','joint-process-card.md',
 'copper-shield-card.md','fixture-load-and-transfer-card.md','NDT-inspection-card.md',
 'cleanliness-inspection-card.md','bore-compensation-and-finish-card.md',
 'clean-shield-engineering-detail.md','pilot-production-and-resource-card.md','shell-datum-and-cmm-execution-card.md','gas-water-fault-execution-card.md','calculation-index.md')

def fresh_stage(output):
    stage=output.with_name('.'+output.name+'-building')
    if stage.resolve().parent!=(ROOT/'deliverables').resolve():raise ValueError('Unexpected staging path')
    if stage.exists():shutil.rmtree(stage)
    stage.mkdir(parents=True)
    return stage

def copy_files(stage,mapping):
    for name,relative in mapping.items():
        src=ROOT/relative
        if not src.is_file():raise FileNotFoundError(src)
        with src.open('rb') as source:
            if source.read(128).startswith(b'version https://git-lfs.github.com/spec/v1'):
                raise ValueError(f'File content must be restored before delivery: {relative}')
        dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)

def publish(stage,output,archive):
    files=sorted(p for p in stage.rglob('*') if p.is_file())
    temporary=archive.with_suffix('.building.zip')
    with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as bundle:
        for path in files:bundle.write(path,path.relative_to(stage).as_posix())
    with zipfile.ZipFile(temporary) as bundle:
        if bundle.testzip() is not None or len(bundle.namelist())!=len(files):raise ValueError('Incomplete package archive')
    if output.resolve().parent!=(ROOT/'deliverables').resolve():raise ValueError('Unexpected replacement path')
    if output.exists():shutil.rmtree(output)
    os.replace(stage,output);os.replace(temporary,archive)
    return len(files)

def build():
    baseline=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text(encoding='utf8'))
    write_status_artifacts(ROOT)
    report=yaml.safe_load((ROOT/'project/report.yaml').read_text(encoding='utf8'))['pdf']
    main_name='01-焊接工艺设计说明书与工程图.pdf'
    paper_name='06-焊接工艺设计说明书-正文.pdf'
    identity=baseline['geometry']['primary_object']
    if '8P' not in identity and '八翼' not in identity:raise ValueError('Package requires frozen 8P-R2-t15 baseline')
    layout,process=baseline['weld_layout'],baseline['final_GTAW']
    actual=layout['segment_count']*layout['segment_length_mm']*layout['pass_count']
    effective=layout['segment_length_mm']-layout['start_allowance_mm']-layout['end_allowance_mm']
    if abs(actual-layout['total_arc_length_mm'])>1e-8:raise ValueError('Actual arc path is inconsistent')
    if abs(effective-layout['effective_segment_length_mm'])>1e-8:raise ValueError('Effective length omits transitions')
    if abs(layout['segment_count']*effective-layout['effective_length_per_pass_mm'])>1e-8:raise ValueError('Effective weld-group length is inconsistent')
    if abs(actual*process['nominal_net_energy_J_mm']/1000-process['net_energy_kJ'])>1e-8:raise ValueError('Final heat ledger is inconsistent')
    stage=fresh_stage(OUT)
    copies={
      main_name:report['combined_pdf'],
      paper_name:report['paper_pdf'],
      '03-工程图集.pdf':report.get('drawing_pdf','cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf'),
      '04-八翼名义装配.step':baseline['geometry']['assembly_step'],
      '05-八翼曲面两层座体.step':'cad/generated/independent-precoat-curved/precoat-stack-R15-R08.step',
      '计算依据/参赛基准输入.yaml':'project/submission-baseline.yaml',
      '计算依据/关键设计数字索引.md':'deliverables/process/calculation-index.md',
      '计算依据/预制工艺量核算.json':'studies/COMPETITION-DESIGN/results/precoat-process-design.json',
      '计算依据/结构工装与位置度分配.json':'studies/COMPETITION-DESIGN/results/delivery-engineering-evidence-20261008.json',
      '计算依据/后序液路容积核算.json':'studies/COMPETITION-DESIGN/results/postweld-isolation.json',
      '计算依据/当前设计验证状态.json':'deliverables/report/generated/current-status.json',
      '计算依据/八翼名义几何.json':baseline['geometry']['manifest'],
      '计算依据/真实公差实体与送丝.json':'cad/generated/precoat-tolerance-family-20261007/geometry-and-feed-audit.json',
      '计算依据/小批整线资源与费用情景.json':'studies/COMPETITION-DESIGN/results/pilot-production-20261007.json',
      '计算依据/副压环真实工具净隙.json':'cad/generated/engineering-supplements-20261007/pressure-interface-clearance.json',
      '计算依据/副压环接口尺寸与局部校核.md':'docs/review/pressure-interface-design-20261008.md',
      '计算依据/04名义装配实际覆盖.json':'cad/generated/competition-design/assembly-coverage-20261008.json',
      '计算依据/本件截面与局部成形包络.json':'studies/COMPETITION-DESIGN/results/section-forming-envelope-20261008.json',
      '计算依据/本件截面与局部成形包络.md':'studies/COMPETITION-DESIGN/results/section-forming-envelope-20261008.md',
      '计算依据/原始证据工程迁移表.md':'docs/review/evidence-transfer-20261008.md',
      '计算依据/宏观制造表示与有限预算.md':'docs/review/macroscopic-manufacturing-plan-20261008.md',
      '计算依据/宏观输入独立审核.md':'docs/review/macroscopic-input-independent-review-20261008.md',
      '计算依据/第二层目录棒材供料决定.json':'studies/COMPETITION-DESIGN/results/second-layer-supply-decision-20261008.json',
      '计算依据/第二层目录棒材供料决定.md':'studies/COMPETITION-DESIGN/results/second-layer-supply-decision-20261008.md',
      '计算依据/根盖分道成形修订.json':'studies/COMPETITION-DESIGN/results/final-pass-forming-revision-20261008.json',
      '计算依据/根盖分道成形修订.md':'studies/COMPETITION-DESIGN/results/final-pass-forming-revision-20261008.md',
      '计算依据/原生冷态去料接口记录.json':'simulation/competition-r4/results/native-interface-adaptation-20261008/interface-readback.json',
      '计算依据/原生冷态去料接口说明.md':'docs/review/native-interface-adaptation-20261008.md',
      '计算依据/原生温度来源接口核对.json':'simulation/competition-r4/results/native-interface-adaptation-20261008/temperature-identity-readback.json',
      '计算依据/第二轮输入独立审核.md':'docs/review/second-round-input-independent-audit-20261008.md',
      '计算依据/有效焊长与完整焊缝组容量.json':'studies/COMPETITION-DESIGN/results/delivery-joint-capacity-20261008.json',
      '计算依据/历史首层热源预算与适用域诊断.json':'simulation/competition-r4/delivery_repair_surface_heat_20261008/summary.json',
      '计算依据/本轮源面修复与适用域诊断.json':'simulation/competition-r4/results/implementation-source-compatibility-20261008/compatibility-and-domain-audit.json',
      '计算依据/本轮源面修复说明.md':'simulation/competition-r4/results/implementation-source-compatibility-20261008/summary.md'}
    for item in baseline.get('submission',{}).get('current_calculation_files',[]):
        relative=item['path'] if isinstance(item,dict) else item
        if relative not in copies.values():copies['计算依据/'+Path(relative).name]=relative
    tolerance_dir=ROOT/'cad/generated/precoat-tolerance-family-20261007'
    tolerance=json.loads((tolerance_dir/'geometry-and-feed-audit.json').read_text(encoding='utf8'))
    for case in tolerance['cases']:
        name=case['case']+'.step';copies['公差设计实体/'+name]=(tolerance_dir/name).relative_to(ROOT).as_posix()
    copy_files(stage,copies)
    first_card=(ROOT/'deliverables/process/manufacturing-and-inspection-card.md').read_text(encoding='utf8').splitlines()[0].removeprefix('# ')
    first_card_title=re.sub(r'\s+','',first_card)
    with fitz.open(ROOT/report['manual_pdf']) as manual:
        start=None
        for i,page in enumerate(manual):
            lines=[re.sub(r'\s+','',line) for line in page.get_text().splitlines()]
            if i>3 and first_card_title in lines:start=i;break
        if start is None:raise ValueError('Manufacturing-and-inspection card section not found')
        with fitz.open() as card_pdf:
            card_pdf.insert_pdf(manual,from_page=start)
            card_pdf.set_metadata({'title':'八翼座体分工序焊接规程与检验卡','author':''})
            card_pdf.save(stage/'02-工艺规程与检验卡.pdf')
    pages={};all_text=[]
    for name in (main_name,'02-工艺规程与检验卡.pdf','03-工程图集.pdf',paper_name):
        with fitz.open(stage/name) as doc:
            pages[name]=len(doc)
            if doc.metadata.get('author','').strip():raise ValueError('Nonempty author metadata')
            for page in doc:
                all_text.append(page.get_text())
                for block in page.get_text('blocks'):
                    if block[0]<-1 or block[1]<-1 or block[2]>page.rect.width+1 or block[3]>page.rect.height+1:
                        raise ValueError(f'Page overflow: {name}/{page.number+1}')
    exports=json.loads((ROOT/report.get('drawing_manifest','cad/generated/engineering-drawings/pdf/pdf-exports.json')).read_text(encoding='utf8'))
    if pages['03-工程图集.pdf']!=exports['sheet_count'] or {s['number'] for s in exports['sheets']}!=set(range(1,exports['sheet_count']+1)):
        raise ValueError('Expected continuous main drawing numbers')
    text='\n'.join(all_text)
    for forbidden in ('未取得全文','留作馆际调取','数字玩具','最终达标稿','学校：','参赛者姓名：','指导教师姓名：'):
        if forbidden in text:raise ValueError('Unresolved text: '+forbidden)
    for required in ('QT450-10','Q235B','0.05','8P-R2-t15','独立','铜环','位置度','自动化'):
        if required not in text:raise ValueError('Missing required topic: '+required)
    state=json.loads((ROOT/'deliverables/report/generated/current-status.json').read_text(encoding='utf8'))
    nominal=json.loads((ROOT/baseline['geometry']['manifest']).read_text(encoding='utf8'))
    geometry=nominal.get('geometry',nominal)
    manifest={'submission_kind':'焊接固定题工艺设计说明书、pWPS与工程图','document_package_complete':True,
      'production_release':False,'submission_baseline':identity,'baseline_source':'project/submission-baseline.yaml',
      'current_source_diagnosis':state['source_compatibility_repair'],
      'nominal_assembly_coverage':state['assembly_geometry'],
      'local_forming':state['local_forming'],
      'second_layer_supply':state['second_layer_supply'],
      'native_interfaces':state['native_interfaces'],
      'public_evidence_route':state['no_physical_design_route'],
      'baseline_verification':{
        'physical_object':'8P-R2-t15八翼柔顺槽座体＋两层预制＋八段两道最终组焊',
        'nominal_geometry_valid':geometry.get('solid_valid',geometry.get('brep_valid',False)),
        'nominal_tolerance_geometry_valid':state['tolerance_geometry']['exported_solids_valid'],
        'first_interface_continuous_fusion_verified':state['current_route_fusion_verified'],
        'final_bilateral_continuous_fusion_verified':False,'complete_manufacturing_state_verified':False,
        'fully_released_residual_position_verified':state['position_actual_family_pass'],
        'fully_released_bore_size_verified':state['bore_actual_family_pass'],
        'same_state_complete_strength_verified':state['complete_strength_verified'],
        'status_source':'deliverables/report/generated/current-status.json','next_action':state['next_action']},
      'weld_length_ledger':{'actual_path_per_segment_per_pass_mm':layout['segment_length_mm'],
        'transition_allowance_each_end_mm':layout['start_allowance_mm'],'effective_segment_length_mm':effective,
        'effective_length_per_pass_mm':layout['effective_length_per_pass_mm'],'total_actual_arc_length_mm':actual,
        'nominal_net_heat_kJ':process['net_energy_kJ'],'nominal_arc_time_s':process['nominal_arc_time_s'],
        'nominal_wire_consumption_length_mm':process['nominal_wire_consumption_length_mm']},
      'engineering_drawings':{'main':f"HJ-001..HJ-{exports['sheet_count']:03d}",'sheet_count':exports['sheet_count']},
      'comparison_attachment':'焊接固定题-可编辑与历史附件.zip','page_counts':pages,
      'primary_file':main_name,'paper_file':paper_name,
      'scope':'设计文件及实际计算状态分别登记；历史失败与圆环对照另册保存。'}
    (stage/'00-提交与阅读说明.txt').write_text(
      '焊接固定题工艺设计作品\n\n'
      f"主文件为{main_name}，含说明书正文、工艺卡及{exports['sheet_count']}张主图；02、03供分别审阅，{paper_name}为单独正文。\n"
      '主方案为8P-R2-t15八翼柔顺槽座体，采用原详细设计门架、内锥胀套和铜环防护。完整圆环和短梁只作历史比较。\n'
      '04名义装配实际为13个导入根、33实体，覆盖既有名义力链、固定铜盘及根道枪丝包络，停用轻击器已移出。禁入体及四个见证片占位也计数，根道姿态不代表完整两道转位扫掠。\n'
      'HJ-022外耳/长压钩/支柱/转运指及HJ-023副压环/横臂/R340驱动制动副架/抽吸退位未加入04实体，以HJ-022/023图纸、净隙核算和装配覆盖记录为准。\n'
      f"每段实际{layout['segment_length_mm']:g} mm，两端各{layout['start_allowance_mm']:g} mm起止过渡；稳定有效{effective:g} mm，每道总有效长度{layout['effective_length_per_pass_mm']:g} mm。两道实际路径{actual:g} mm，名义净热{process['net_energy_kJ']:g} kJ。\n"
      '参赛设计采用报告与工程图路线，设计文件交付不等待实物。首次与最终有效连接、制造残余状态、完全卸夹孔形和同状态承载的实际状态见所附JSON及正文。\n'
      '现行根3.42/盖3.78±0.05 mm/s为一次分道设计修订，名义耗丝628.364 mm。两脚、实际喉部及4.30三角包络联合核查；面积界不等于制造窗口。旧3.50/3.68保持历史对照。\n'
      '第二层采用DMNA099目录Ø1.143×914.4 mm直棒，采购验收±0.020、送进8.00±0.20，每翼两轨同一180±0.5 mm棒、翼间换棒；本件采购两根整棒。\n'
      '旧QT删除/再加入PEEQ差0已核并复用；新增原生冷态整单元去料准备，实际冷态、后续层/壳/工装网格未接通，新制造性能FE数0。公开证据按问题组合，输入资格见第二轮新独立审核。\n'
      '实物试制按工艺卡完成工程确认；不得把预算、名义CAD或历史超差结果写成当前方案达标。\n'
      '报名身份、指导教师及盖章材料由参赛团队和校方另行办理，技术文件保持匿名。\n'
      '可编辑源、字体许可证、源图、圆环比较和历史失败摘要见单独附件ZIP。仓库根目录是维护源，包内副本是导出快照。\n',encoding='utf8')
    manifest['included_files']=sorted([p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file()]+['验证与交付状态.json'])
    (stage/'验证与交付状态.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    attachment_stage=fresh_stage(ATTACHMENTS)
    source=ROOT/'deliverables/report/technical-report-v4-unified.md'
    sources=[source,ROOT/'README.md',ROOT/'RESULTS_REPORT.md',ROOT/'CONTRIBUTING.md',ROOT/'simulation/README.md',
      ROOT/'deliverables/比赛交付-20261008/00-历史快照说明.md',
      ROOT/'deliverables/论文格式交付-20261008/00-历史快照说明.md',
      ROOT/'deliverables/competition-route.md',ROOT/'deliverables/submission-checklist.md',
      ROOT/'deliverables/process/current-candidate-state.md',ROOT/'project/stage-status.yaml',
      ROOT/'project/submission-baseline.yaml',ROOT/'project/report.yaml',
      ROOT/'project/precoat-process-design.yaml',ROOT/'project/process-r3.yaml',ROOT/'project/competition-design.yaml',
      ROOT/'project/pilot-production-design.yaml',ROOT/'deliverables/report/build_technical_report_pdf.py',Path(__file__),
      ROOT/'src/hanjie/reporting/fonts.py',ROOT/'src/hanjie/reporting/current_status.py',
      ROOT/'src/hanjie/domain/competition_design.py',ROOT/'src/hanjie/domain/following_tools.py',
      ROOT/'cad/generated/engineering-drawings/drawing-manifest.json',
      ROOT/'docs/review/implementation-goal-20261008.md',ROOT/'docs/review/independent-implementation-audit-20261008.md',
      ROOT/'docs/review/minimum-first-interface-inputs-20261008.md',
      ROOT/'docs/review/no-physical-evidence-route-20261008.md',
      ROOT/'docs/review/evidence-transfer-20261008.md',
      ROOT/'docs/review/macroscopic-manufacturing-plan-20261008.md',
      ROOT/'docs/review/macroscopic-input-independent-review-20261008.md',
      ROOT/'docs/review/second-round-input-independent-audit-20261008.md',
      ROOT/'docs/review/native-interface-adaptation-20261008.md',
      ROOT/'simulation/competition-r4/prepare_native_cold_cut.py',
      ROOT/'simulation/competition-r4/audit_calculix_manufacturing_benchmark.py',
      ROOT/'simulation/competition-r4/build_second_layer_from_cut.py',
      ROOT/'simulation/competition-r4/precoat_machining.py',
      ROOT/'simulation/competition-r4/run_first_layer_machining.py',
      ROOT/'simulation/competition-r4/mma_literature_profile.py',
      ROOT/'simulation/competition-r4/results/native-interface-adaptation-20261008/interface-readback.json',
      ROOT/'simulation/competition-r4/results/native-interface-adaptation-20261008/temperature-identity-readback.json',
      ROOT/'simulation/competition-r4/results/native-interface-adaptation-20261008/generation-check-remove-block.txt',
      ROOT/'studies/COMPETITION-DESIGN/second_layer_supply_decision_20261008.py',
      ROOT/'studies/COMPETITION-DESIGN/results/second-layer-supply-decision-20261008.json',
      ROOT/'studies/COMPETITION-DESIGN/results/second-layer-supply-decision-20261008.md',
      ROOT/'studies/COMPETITION-DESIGN/final_pass_forming_revision_20261008.py',
      ROOT/'studies/COMPETITION-DESIGN/results/final-pass-forming-revision-20261008.json',
      ROOT/'studies/COMPETITION-DESIGN/results/final-pass-forming-revision-20261008.md',
      ROOT/'docs/review/2026-10-08-项目独立审核与收束建议.md',
      ROOT/'cad/generated/competition-design/assembly-coverage-20261008.json',
      ROOT/'studies/COMPETITION-DESIGN/export_current_assembly.py',
      ROOT/'studies/COMPETITION-DESIGN/delivery_section_envelope.py',
      ROOT/'studies/COMPETITION-DESIGN/results/section-forming-envelope-20261008.json',
      ROOT/'studies/COMPETITION-DESIGN/results/section-forming-envelope-20261008.md',
      ROOT/'docs/sources/Weldwire-Duramax-DMNA099-ERNi-CI-TDS.pdf',
      ROOT/'docs/sources/ESAB-OK-Ni-CI-20160218.pdf',
      ROOT/'docs/sources/ESAB-OK-NiFe-CI-A-20160216.pdf',
      ROOT/'docs/sources/Kobelco-Specific-4Ed.pdf',
      ROOT/'docs/review/pressure-interface-design-20261008.md',ROOT/'cad/parametric/check_pressure_interfaces.py',
      ROOT/'simulation/competition-r4/visible_surface_flux.py',ROOT/'simulation/competition-r4/run_ni99_precoat_first.py',ROOT/'cad/parametric/build_precoat_tolerance_family.py',
      ROOT/'cad/parametric/inspect_precoat_tolerance_steps.py',ROOT/'cad/parametric/build_engineering_supplements.py',
      ROOT/'studies/COMPETITION-DESIGN/pilot_production_resources.py',
      ROOT/'studies/COMPETITION-DESIGN/delivery_joint_capacity.py',
      ROOT/'studies/COMPETITION-DESIGN/delivery_precoat_ledger.py',
      ROOT/'studies/COMPETITION-DESIGN/plot_delivery_design.py',
      ROOT/'studies/COMPETITION-DESIGN/plot_paper_figures.py',
      ROOT/'cad/parametric/competition_drawings.py',ROOT/'cad/parametric/export_drawing_pdfs.py',
      ROOT/'deliverables/process/generate_process_r3.py',ROOT/'deliverables/process/generate_joint_process_card.py',
      ROOT/'deliverables/process/joint-process-card.json']
    sources.extend((ROOT/'docs/report/figures/delivery').glob('*'))
    native_benchmark=ROOT/'simulation/competition-r4/results/calculix-plastic-deposition-cut-benchmark-restartfix-20261007'
    sources.extend(native_benchmark/name for name in ('native-history-audit.json','benchmark.dat'))
    sources.extend(native_benchmark/'reactivated-substrate-history'/name for name in
                   ('reactivation-history-audit.json','reactivation.inp','reactivation.dat','reactivation.rout','reactivation.log'))
    sources.extend(p for p in (ROOT/'docs/report/figures/paper').rglob('*')
                   if p.suffix.lower() in ('.png','.pdf','.svg'))
    sources.extend((ROOT/'simulation/competition-r4').glob('delivery_repair_*.py'))
    sources.extend((ROOT/'simulation/competition-r4/results/implementation-source-compatibility-20261008').glob('*.py'))
    sources.extend((ROOT/'simulation/competition-r4/results/implementation-source-compatibility-20261008').glob('*.json'))
    sources.extend((ROOT/'cad/generated/engineering-supplements-20261007').glob('*.json'))
    sources.extend((ROOT/'cad/generated/engineering-supplements-20261007').glob('HJ-DRW-*.pdf'))
    sources.extend((ROOT/'cad/generated/engineering-supplements-20261007').glob('HJ-DRW-*.png'))
    final_review=ROOT/'docs/review/final-delivery-audit-20261008.md'
    if final_review.is_file():sources.append(final_review)
    current_review=ROOT/'docs/review/final-limited-correction-audit-20261008.md'
    if current_review.is_file():sources.append(current_review)
    sources.extend((ROOT/'simulation/competition-r4/delivery_repair_surface_heat_20261008').glob('source-budget-comparison.*'))
    sources.extend(ROOT/'deliverables/process'/name for name in MAIN_CARDS)
    for directory,pattern in [('assets/fonts','*'),('docs/report/figures/publication','*'),
      ('cad/generated/engineering-drawings','*.svg'),('cad/generated/engineering-drawings','*.png')]:
        sources.extend((ROOT/directory).glob(pattern))
    for card in [source,*(ROOT/'deliverables/process'/name for name in MAIN_CARDS)]:
        for relative in re.findall(r'!\[[^]]*\]\(([^)]+)\)',card.read_text(encoding='utf8')):
            path=ROOT/relative
            if not path.is_file():path=(card.parent/relative).resolve()
            sources.append(path)
    attachments={'可编辑源文件/'+p.relative_to(ROOT).as_posix():p.relative_to(ROOT).as_posix() for p in sources if p.is_file()}
    attachments.update({
      '可编辑源文件/studies/COMPETITION-DESIGN/plot_paper_figures.py':'studies/COMPETITION-DESIGN/plot_paper_figures.py',
      '图表输入/图表数据来源索引.json':'docs/report/figures/paper/figure-sources.json',
      '图表输入/相平衡质量分数.csv':'simulation/competition-r4/results/design-precoat-materials-20261006/gibbs-checked/phase-fractions.csv',
      '图表输入/相平衡材料与条件.json':'simulation/competition-r4/results/design-precoat-materials-20261006/gibbs-checked/phase-summary.json',
      '图表输入/曲面两层名义几何.json':'cad/generated/independent-precoat-curved/geometry-audit.json',
      '图表输入/预制公差族几何与供料.json':'cad/generated/precoat-tolerance-family-20261007/geometry-and-feed-audit.json',
      '历史计算/旧八翼制造复核.json':'simulation/competition-r4/results/design-repair-status-20261005.json',
      '历史计算/旧八翼最终组焊冷却卸夹算例.json':'simulation/competition-r4/results/verification.json',
      '历史计算/旧八翼承载参考.json':'simulation/competition-r4/results/service-verification.json',
      '历史计算/首层制造表示诊断.json':'output/review/phase-interface-diagnosis-20261007/diagnosis.json',
      '历史计算/首层原生计算停止状态.json':'output/review/native-manufacturing-stop-20261007/native-stop-audit.json',
      '历史计算/首层供料边界复核.json':'studies/COMPETITION-DESIGN/results/precoat-supply-bounds-20261008.json',
      '圆环比较/冷态对比原稿.pdf':'deliverables/recovered-20261007/焊接工艺设计论文-正文.pdf',
      '圆环比较/名义几何与质量.json':'cad/generated/ring-baseline/geometry-quality-and-mass.json',
      '圆环比较/预制供料与热量.json':'cad/generated/ring-baseline/ring-precoat-design.json',
      '圆环比较/简化控形目标.json':'studies/COMPETITION-DESIGN/results/ring-control-screening.json',
      '圆环比较/短梁截面起点.json':'studies/COMPETITION-DESIGN/results/ring-fixture-feasibility.json'})
    for p in (ROOT/'cad/generated/ring-baseline').glob('*'):
        if p.suffix.lower() in ('.step','.svg','.png','.pdf'):attachments['圆环比较/'+p.name]=p.relative_to(ROOT).as_posix()
    for name in ('ring-baseline-design-card.md','ring-final-welding-card.md','ring-final-welding-card.json'):
        attachments['圆环比较/'+name]='deliverables/process/'+name
    copy_files(attachment_stage,attachments)
    (attachment_stage/'图表输入/工装原始场源路径.txt').write_text(
      '说明书图中的固定反锥下承力主体场读取既有计算，原始NPZ保留在项目中，不复制到本附件。\n'
      '原项目路径：E:/AI/bisai/Hanjie/simulation/competition-r4/results/fixture-axis-solid-core-h1.5/fields.npz\n'
      '项目相对路径：simulation/competition-r4/results/fixture-axis-solid-core-h1.5/fields.npz\n'
      '原场分量：x、e、u、stress；stress采用Kelvin记号。\n'
      '对象与边界：整体固定反锥/柱根；5 kN侧向力、170 kN·mm支承矩及双头各200 N附加载荷，E180 GPa。\n'
      '正文图从保存场绘制y=0截面，未重算或扩展为整门架与焊后工件场。\n',encoding='utf8')
    (attachment_stage/'00-附件用途说明.txt').write_text(
      '本册保存可编辑源快照、字体许可证、源图和历史比较。\n'
      '正式主对象为8P-R2-t15；完整圆环、短梁和旧计算按原实体及工艺身份读取。\n'
      '旧制造最大位置度预算52.084 μm，超50 μm要求2.084 μm；原首层冷态计算未形成可继承状态。\n'
      '上述记录用于解释修订和后续有限计算顺序，不转写为现行方案性能。\n',encoding='utf8')
    main_archive=ROOT/'deliverables/焊接固定题-参赛设计报告包.zip'
    attachment_archive=ROOT/'deliverables/焊接固定题-可编辑与历史附件.zip'
    main_count=publish(stage,OUT,main_archive)
    attachment_count=publish(attachment_stage,ATTACHMENTS,attachment_archive)
    print(json.dumps({'archive':str(main_archive),'files':main_count,'pages':pages,
      'editable_history_archive':str(attachment_archive),'attachment_files':attachment_count,
      'document_package_complete':True,'design_verified':False},ensure_ascii=False))

if __name__=='__main__':build()
