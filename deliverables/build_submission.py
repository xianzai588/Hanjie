"""重建并汇集当前参赛技术文件；不代填报名、不执行外部提交。"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import zipfile
import tempfile
import os

ROOT = Path(__file__).resolve().parents[1]


def publish_validated(candidate, candidate_archive, destination, archive):
    """Replace both validated products, retaining the preceding set on failure."""
    backup = candidate.parent/'previous-submission'
    backup_archive = candidate.parent/'previous-package.zip'
    moved_directory = installed_directory = moved_archive = installed_archive = False
    try:
        if destination.exists():
            os.replace(destination, backup);moved_directory = True
        os.replace(candidate, destination);installed_directory = True
        if archive.exists():
            os.replace(archive, backup_archive);moved_archive = True
        os.replace(candidate_archive, archive);installed_archive = True
    except BaseException:
        if installed_archive:os.replace(archive, candidate_archive)
        if moved_archive:os.replace(backup_archive, archive)
        if installed_directory:os.replace(destination, candidate)
        if moved_directory:os.replace(backup, destination)
        raise


def main():
    import yaml
    spec = yaml.safe_load((ROOT/'project/competition-design.yaml').read_text(encoding='utf8'))
    joint_file = ROOT/'simulation/competition-r4/results/joint-process-verification.json'
    if not joint_file.exists():
        raise RuntimeError('首次QT界面、最终双侧熔合及预制存留状态尚无完整验证；见deliverables/competition-route.md')
    joint = json.loads(joint_file.read_text(encoding='utf8'))
    joint_checks = ('first_interface_continuous_fusion_pass', 'final_dual_side_fusion_pass',
                    'retained_layer_and_dilution_pass', 'PMZ_capacity_design_pass',
                    'precoat_machining_residual_state_transfer_pass')
    if not all(joint.get(key) is True for key in joint_checks):
        raise RuntimeError('有效接头验证未通过，禁止将填料出生或满片弹簧连接作为最终传力依据')
    if joint.get('layout') != spec['layout'] or not joint.get('manufacturing_cases'):
        raise RuntimeError('有效接头与整件制造算例尚未对齐')
    sys.path.insert(0, str(ROOT/'simulation/competition-r4'))
    from aggregate_strength import aggregate
    aggregate()
    from check_mandrel import evaluate as evaluate_mandrel
    if not evaluate_mandrel()['mandrel_compliance_design_pass']:
        raise RuntimeError('锁止胀套的全长承压与柔度未满足数值边界；禁止发布最终技术包')
    if spec['shield']['seal_engineering'].get('lower_backing_ring_thickness_mm') != 1.5 or not (ROOT/'deliverables/process/copper-shield-card.md').exists():
        raise RuntimeError('分瓣接缝与独立下密封座尚未统一到图纸和工艺参数；禁止发布最终技术包')
    numerical_file = ROOT/'simulation/competition-r4/results/verification.json'
    if not numerical_file.exists() or not json.loads(numerical_file.read_text(encoding='utf8')).get('position_design_pass', False):
        raise RuntimeError('完整冷态位置度预算或空间/时间精度未通过；禁止发布最终技术包')
    peening_file = ROOT/'simulation/competition-r4/results/peening-verification.json'
    if not peening_file.exists() or not json.loads(peening_file.read_text(encoding='utf8')).get('design_checks_pass', False):
        raise RuntimeError('随动轻击温度时序与工具空间尚未完成验证；禁止发布最终技术包')
    peening = json.loads(peening_file.read_text(encoding='utf8'))
    if not peening.get('material_specific_fusion_enthalpy'):
        raise RuntimeError('轻击温窗仍来自旧统一熔化区间；需先完成当前材料热焓的实际时序复核')
    numerical = json.loads(numerical_file.read_text(encoding='utf8'))
    if set(joint['manufacturing_cases']) != set(numerical['cases']):
        raise RuntimeError('接头验证对应的制造家族与控形验证不同，不能复用历史通过值')
    if not numerical.get('bore_size_design_pass', False):
        raise RuntimeError('焊前尺寸窗、焊后孔径与微量精整上限尚未完成闭环；禁止发布最终技术包')
    peen_folder = 'simulation/competition-r4/results/' + peening['source_run']
    source_input = json.loads((ROOT/peen_folder/'input.json').read_text(encoding='utf8'))
    coupled_input = json.loads((ROOT/'simulation/competition-r4/results'/numerical['cases'][0]/'input.json').read_text(encoding='utf8'))
    service = json.loads((ROOT/'simulation/competition-r4/results/service-verification.json').read_text(encoding='utf8'))
    if not service.get('static_service_design_pass',False):
        raise RuntimeError('实际座体服役强度及空间精度尚未通过')
    if not service.get('complete_welded_strength_design_pass',False):
        raise RuntimeError('完整强度尚缺残余张量合成与过渡层/界面承载依据；增量实体VM检查不能替代')
    for case in service['cases']:
        service_input=json.loads((ROOT/'simulation/competition-r4/results'/case/'input.json').read_text(encoding='utf8'))
        if service_input.get('initial_bore_diameter_mm') != coupled_input['initial_bore_diameter_mm']:
            raise RuntimeError('服役算例孔径与有效制造窗口未对齐，禁止发布最终技术包')
    if not coupled_input.get('fixture_thermal') or not numerical.get('fixture_thermal_model_pass',False):
        raise RuntimeError('最终家族必须包含工具实际热耦合及传热域离散复核')
    for key in ('materials','fusion_enthalpy_model','stage_sequence','travel_mm_s','net_W',
                'source_r_mm','source_radius_mm','source_depth_mm','seat_geometry',
                'copper_contact_W_m2K','copper_water_model','initial_bore_diameter_mm',
                'fixture_thermal','fixture_thermal_coupling_policy'):
        if source_input.get(key) != coupled_input.get(key):
            raise RuntimeError(f'轻击与位置度使用不同物理输入：{key}')
    for script in ("simulation/competition-r4/check_mandrel.py", "simulation/competition-r4/check_water_route.py", "simulation/competition-r4/check_copper_retraction.py", "simulation/competition-r4/postprocess_peening.py", "simulation/competition-r4/postprocess.py", "simulation/competition-r4/postprocess_service.py", "simulation/competition-r4/aggregate_strength.py", "simulation/competition-r4/postprocess_process.py",
                   "deliverables/report/sync_verified_results.py", "studies/COMPETITION-DESIGN/run.py", "studies/SCHAEFFLER-MAP/run.py",
                   "studies/COMPETITION-DESIGN/engineering_checks_r3.py",
                   "studies/COMPETITION-DESIGN/robust_selection.py",
                   "studies/COMPETITION-DESIGN/plot_engineering_checks.py",
                   "deliverables/process/generate_process_r3.py",
                   "cad/parametric/generate_engineering_drawings.py", "cad/parametric/export_drawing_pdfs.py",
                   "deliverables/report/build_technical_report_pdf.py"):
        command = [sys.executable, "-X", "utf8", str(ROOT/script)]
        if script == 'simulation/competition-r4/postprocess_peening.py':
            command += ['--run', peening['source_run'], '--fine', peening['fine_reference_run']]
        elif script == 'simulation/competition-r4/postprocess.py':
            command += ['--cases', *numerical['cases']]
        subprocess.run(command, cwd=ROOT, check=True)
    # Rejected candidates live only in a temporary directory. The previous
    # published directory/ZIP is untouched until all candidate checks pass.
    staging = tempfile.TemporaryDirectory(prefix='submission-candidate-', dir=ROOT/'output')
    stage = Path(staging.name)
    out = stage/'submission'
    out.mkdir(parents=True, exist_ok=True)
    numerical = json.loads((ROOT/"simulation/competition-r4/results/verification.json").read_text(encoding="utf-8"))
    service = json.loads((ROOT/"simulation/competition-r4/results/service-verification.json").read_text(encoding="utf-8"))
    process_temperature = json.loads((ROOT/"simulation/competition-r4/results/process-temperature-verification.json").read_text(encoding="utf-8"))
    accepted_case = numerical["cases"][-1]
    run_folder = "simulation/competition-r4/results/" + accepted_case
    files = {
        "00-评审导航.txt":"deliverables/submission/00-评审导航.txt",
        "01-工艺设计说明书.pdf":"output/pdf/technical-report-v4.pdf",
        "02-设计图集.pdf":"cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf",
        "03-名义装配包络.step":"cad/generated/competition-design/competition-assembly-r4.step",
        "04-设计计算.json":"studies/COMPETITION-DESIGN/results/assessment.json",
        "05-设计指标.csv":"studies/COMPETITION-DESIGN/results/result.csv",
        "06-工艺提案.md":"deliverables/process/joint-process-card.md",
        "07-设计参数.yaml":"project/competition-design.yaml",
        "08-整件热结构主网格结果.json":run_folder+"/measurement.json",
        "08b-整件热结构输入.json":run_folder+"/input.json",
        "08c-整件热结构能量历史.csv":run_folder+"/thermal-history.csv",
        "08d-整件热结构平衡历史.csv":run_folder+"/equilibrium-history.csv",
        "08e-工程载荷夹具洁净核算.json":"studies/COMPETITION-DESIGN/results/engineering-checks-r3.json",
        "08f-空间时间精度复核.json":"simulation/competition-r4/results/verification.json",
        "08g-整件冷态服役应力.json":"simulation/competition-r4/results/service-verification.json",
        "08h-整件冷态应力云图.png":"docs/report/figures/r4-service-strength.png",
        "08i-独立完整连接强度核验.json":"simulation/competition-r4/results/welded-strength-verification.json",
        "08j-制造区间数值包络.json":"simulation/competition-r4/results/manufacturing-interval-verification.json",
        "08k-后序闭合隔离核算.json":"studies/COMPETITION-DESIGN/results/postweld-isolation.json",
        "09-守恒修订与放行闭环.svg":"deliverables/submission/09-守恒修订与放行闭环.svg",
        "10-复现与版本冻结记录.md":"deliverables/submission/10-复现与版本冻结记录.md",
        "11-候选选择.json":"studies/COMPETITION-DESIGN/results/robust-selection.json",
        "17-参数来源与证据等级.md":"deliverables/submission/17-参数来源与证据等级.md",
        "18-证据等级总图.svg":"deliverables/submission/18-证据等级总图.svg",
        "19-Schaeffler相图映射.json":"studies/SCHAEFFLER-MAP/results/schaeffler-mapping.json",
        "20-Schaeffler相图映射.svg":"studies/SCHAEFFLER-MAP/results/schaeffler-map.svg",
        "21-冷焊热制度对比.svg":"studies/SCHAEFFLER-MAP/results/cold-weld-regime.svg",
        "22-冷焊与锤击工艺卡.md":"deliverables/process/cold-weld-and-peening-card.md",
        "23-网格与位置度图.png":"docs/report/figures/r4-mesh-budget.png",
        "24-热场与接触图.png":"docs/report/figures/r4-thermal-contact.png",
        "25-位移与残余应力图.png":"docs/report/figures/r4-residual-fields.png",
        "26-Ni99两层过渡工艺卡.md":"deliverables/process/Ni99-transition-pWPS.md",
        "27-三种布局工程比较.png":"docs/report/figures/layout-engineering-comparison.png",
        "28-设计疲劳载荷敏感性.png":"docs/report/figures/fatigue-load-sensitivity.png",
        "30-段前温控复核.json":"simulation/competition-r4/results/process-temperature-verification.json",
        "31-h2逐段起弧温度.json":f"simulation/competition-r4/results/{numerical['cases'][0]}/process-start-temperatures.json",
        "32-h1.5逐段起弧温度.json":f"simulation/competition-r4/results/{numerical['cases'][1]}/process-start-temperatures.json",
        "33-细时间步逐段起弧温度.json":run_folder+"/process-start-temperatures.json",
        "34-异种接头无损检查规程.md":"deliverables/process/NDT-inspection-card.md",
        "35-随动轻击验证.json":"simulation/competition-r4/results/peening-verification.json",
        "36-轻击温窗与轨迹.png":"docs/report/figures/peening-temperature-timing.png",
        "37-轻击热场输入.json":peen_folder+"/input.json",
        "38-轻击实际温度历史.csv":peen_folder+"/peening-surface-history.csv",
        "39-轻击测点与段序.json":peen_folder+"/peening-trace-sites.json",
        "40-铜瓣连续退位验证.json":"simulation/competition-r4/results/copper-retraction-verification.json",
        "41-铜瓣与整环下密封座.step":"cad/generated/competition-design/copper-sectors-and-backing.step",
        "42-铜环密封装配检查卡.md":"deliverables/process/copper-shield-card.md",
        "43-密封运动水路验证.json":"simulation/competition-r4/results/water-route-verification.json",
        "44-承力柱与根部刚度.json":run_folder+"/carrier-verification.json",
        "50-完全卸夹孔轴评价的平衡核验.json":run_folder+"/free-release-verification.json",
        "51-完全卸夹冷态空间场.npz":run_folder+"/free-release-fields.npz",
        "52-内腔洁净检验规程.md":"deliverables/process/cleanliness-inspection-card.md",
        "53-锁止胀套柔度核算.json":"simulation/competition-r4/results/mandrel-compliance-verification.json",
        "54-孔径补偿与微珩规程.md":"deliverables/process/bore-compensation-and-finish-card.md",
        "55-孔径尺寸链验证.json":"simulation/competition-r4/results/bore-size-verification.json",
        "56-胀套承力与基准转运卡.md":"deliverables/process/fixture-load-and-transfer-card.md",
        "57-夹具刚度容量包络.json":"output/review/carrier-design-envelope.json",
        "58-夹具实体粗网格结果.json":"simulation/competition-r4/results/fixture-axis-solid-core-h2/result.json",
        "59-夹具实体细网格结果.json":"simulation/competition-r4/results/fixture-axis-solid-core-h1.5/result.json",
        "60-夹具实体承力云图.png":"docs/report/figures/fixture-axis-solid-fe.png",
        "61-夹具实际热历程.csv":run_folder+"/fixture-thermal-history.csv",
        "62-夹具热模型输入与计算.json":run_folder+"/fixture-thermal-verification.json",
        "63-夹具传热域离散复核.json":run_folder+"/fixture-thermal-network-convergence.json",
        "64-夹具传热真实边界.npz":run_folder+"/fixture-boundary-trace.npz",
        "45-实际下托接触反力.csv":run_folder+"/pad-contact-history.csv",
        "46-下托接触验算.json":run_folder+"/pad-contact-audit.json",
        "47-高温事件积分.json":run_folder+"/mechanical-integration-audit.json",
        "48-材料热焓参数.yaml":"project/materials.yaml",
        "29-旧12mm座体独立刚度对比.json":"simulation/structural-v4/results/service-stiffness-8p.json",
    }
    files['65-铜环密封与水路工程展开.md']='deliverables/process/clean-shield-engineering-detail.md'
    # 复核输入和实际历史随包，避免只有主网格的数字而没有比较依据。
    for i, case in enumerate(numerical["cases"], start=1):
        for suffix in ("input.json", "measurement.json", "thermal-history.csv", "equilibrium-history.csv", "process-start-temperatures.json", "birth-continuation-verification.json", "pad-contact-audit.json", "carrier-verification.json", "mechanical-integration-audit.json", "free-release-verification.json", "fixture-thermal-network-convergence.json", "fixture-thermal-history.csv", "mandrel-vector-history.csv"):
            source = f"simulation/competition-r4/results/{case}/{suffix}"
            if suffix == 'process-start-temperatures.json':
                record=next(r for r in process_temperature['coupled_start_records'] if r['coupled_case']==case)
                source='simulation/competition-r4/results/'+record['start_record_source']
            files[f"复核{i}-{suffix}"] = source
    if coupled_input.get('paired_opposed_sources'):
        opposed_file = 'simulation/competition-r4/results/opposed-tool-verification.json'
        if not json.loads((ROOT/opposed_file).read_text(encoding='utf8'))['opposed_tool_geometry_pass']:
            raise RuntimeError('对向双枪实体避让尚未通过')
        files['49-对向工具避让.json'] = opposed_file
    import pymupdf
    integrated = ROOT/"output/pdf/工艺设计说明书与工程图.pdf"
    with pymupdf.open() as merged:
        for source in ("output/pdf/technical-report-v4.pdf", "cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf"):
            with pymupdf.open(ROOT/source) as part:
                merged.insert_pdf(part)
        merged.set_metadata({"title":"QT450-10/Q235B 工艺设计说明书与工程图", "author":""})
        merged.save(integrated)
    files["01a-说明书与工程图合订本.pdf"] = str(integrated.relative_to(ROOT)).replace("\\", "/")
    for name, source in files.items():
        target = out/name
        source_path = ROOT/source
        if source_path.resolve() != target.resolve():
            shutil.copyfile(source_path, target)
    # 清掉上一批次遗留、已不在清单内的旧文件，防止旧编号混入提交包。
    keep = set(files) | {"提交说明.txt", "manifest.json"}
    for stale in sorted(p for p in out.iterdir() if p.is_file() and p.name not in keep):
        if stale.suffix in {".json", ".csv", ".md", ".txt", ".yaml", ".svg", ".step", ".pdf"}:
            stale.unlink()
    page_counts = {}
    for name in ("01-工艺设计说明书.pdf", "02-设计图集.pdf"):
        with pymupdf.open(out/name) as pdf:
            page_counts[name] = len(pdf)
            for page in pdf:
                for block in page.get_text("blocks"):
                    if not page.rect.contains(pymupdf.Rect(block[:4])):
                        raise ValueError(f"{name}文字超出页面")
    (out/"提交说明.txt").write_text(
        f"修订5技术包（焊接固定题）\n说明书{page_counts['01-工艺设计说明书.pdf']}页，设计图{page_counts['02-设计图集.pdf']}页。"
        "STEP为名义装配包络。\n"
        "本包为工艺设计作品：几何来自真实BREP，数字结果由经典公式、整件热结构模型、逐层质量配混与公差预算给出，"
        "正文显式区分计算结果与设计目标；说明书§7列出设计放行顺序与试制工程确认要求。\n"
        "工艺体系：八段两道脉冲TIG、Ni99预制隔离层＋NiFe55填充、铸铁冷焊（不预热、层间≤100 ℃）、"
        "热态轻击；整件热结构结果与能量历史在08号文件，冶金适用域声明见19～21号。\n"
        "构建需完整项目及Python依赖，运行 python deliverables/build_submission.py。重建报告不会重新执行长时整件仿真；运行参数及复核命令见10号记录。\n"
        "校方另附真实报名表、推荐与盖章汇总表；固定命题作品详细描述按附件填‘无’。\n"
        "截止时间与命名按官方原件及后续通知执行。\n",
        encoding="utf-8")
    manifest={"version":"COMPETITION-R4-revision-5","files":files,
              "report_pages":page_counts["01-工艺设计说明书.pdf"],
              "drawing_pages":page_counts["02-设计图集.pdf"],
              "submission_scope":"technical_design_only",
              "residual_position_design_verified":numerical["position_design_pass"],
              "static_service_design_verified":service["static_service_design_pass"],
              "process_temperature_design_verified":process_temperature["process_temperature_design_pass"],
              "design_verified":bool(numerical["position_design_pass"] and service["static_service_design_pass"] and process_temperature["process_temperature_design_pass"]),
              "physical_validation_recommended":True,
              "design_verification_scope":"current 15 mm CAD; cold residual position, incremental static service envelope and segment-start temperature under declared numerical inputs; first QT/Ni99 interface and fatigue are confirmed by the prescribed A-class trial programme",
              "product_conformity_claimed":False}
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    archive=stage/"COMPETITION-R4-焊接固定题技术包.zip"
    # 只打包显式清单，目录中其他文件不自动混入提交物。
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as bundle:
        for name in [*files,"提交说明.txt","manifest.json"]:
            bundle.write(out/name,name)
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT/"scripts/competition_submission_lint.py"),
                    '--submission-dir',str(out),'--archive',str(archive)], cwd=ROOT, check=True)
    final_archive=ROOT/'deliverables/COMPETITION-R4-焊接固定题技术包.zip'
    publish_validated(out,archive,ROOT/'deliverables/submission',final_archive)
    staging.cleanup()
    print(f"已生成并通过检查：{final_archive}")


if __name__ == "__main__":
    main()


