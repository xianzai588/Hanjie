"""重建并汇集当前参赛技术文件；不代填报名、不执行外部提交。"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    for script in ("studies/COMPETITION-DESIGN/run.py", "studies/COMPETITION-DESIGN/robust_selection.py",
                   "studies/ROBUST-BOUNDARY/run.py",
                   "deliverables/process/generate_joint_process_card.py",
                   "cad/parametric/generate_engineering_drawings.py", "cad/parametric/export_drawing_pdfs.py",
                   "deliverables/report/build_technical_report_pdf.py"):
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT/script)], cwd=ROOT, check=True)
    out = ROOT/"deliverables/submission"
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "01-工艺设计说明书.pdf":"output/pdf/technical-report-v4.pdf",
        "02-设计图集.pdf":"cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf",
        "03-名义装配包络.step":"cad/generated/competition-design/competition-assembly.step",
        "04-设计计算.json":"studies/COMPETITION-DESIGN/results/assessment.json",
        "05-设计指标.csv":"studies/COMPETITION-DESIGN/results/result.csv",
        "06-工艺提案.md":"deliverables/process/joint-process-card.md",
        "07-设计参数.yaml":"project/competition-design.yaml",
        "08-R1单段热诊断.json":"simulation/thermal-ref/results/competition-r2/r1-singlepass/assessment.json",
        "09-守恒修订与放行闭环.svg":"deliverables/submission/09-守恒修订与放行闭环.svg",
        "10-复现与版本冻结记录.md":"deliverables/submission/10-复现与版本冻结记录.md",
        "11-候选选择.json":"studies/COMPETITION-DESIGN/results/robust-selection.json",
        "12-确定性边界汇总.json":"studies/ROBUST-BOUNDARY/results/boundary-summary.json",
        "13-6P-8P切换边界.csv":"studies/ROBUST-BOUNDARY/results/strength-boundary.csv",
        "14-位置度失效边界.csv":"studies/ROBUST-BOUNDARY/results/position-boundary.csv",
        "15-确定性边界图.svg":"studies/ROBUST-BOUNDARY/results/strength-boundary.svg",
        "16-位置度边界图.svg":"studies/ROBUST-BOUNDARY/results/position-boundary.svg",
        "17-参数来源与证据等级.md":"deliverables/submission/17-参数来源与证据等级.md",
        "18-证据等级总图.svg":"deliverables/submission/18-证据等级总图.svg",
    }
    for name, source in files.items():
        target = out/name
        source_path = ROOT/source
        if source_path.resolve() != target.resolve():
            shutil.copyfile(source_path, target)
    import pymupdf
    page_counts = {}
    for name in ("01-工艺设计说明书.pdf", "02-设计图集.pdf"):
        with pymupdf.open(out/name) as pdf:
            page_counts[name] = len(pdf)
            for page in pdf:
                for block in page.get_text("blocks"):
                    if not page.rect.contains(pymupdf.Rect(block[:4])):
                        raise ValueError(f"{name}文字超出页面")
    (out/"提交说明.txt").write_text(
        f"COMPETITION-R1 技术包\n说明书{page_counts['01-工艺设计说明书.pdf']}页，设计图{page_counts['02-设计图集.pdf']}页。STEP为名义装配包络，不是完整制造模型。\n"
        "本包为纯数字设计，实物位置度、洁净、完整热结构与疲劳未验证。\n"
        "候选选择结果由当前 COMPETITION-DESIGN 四道比较生成；R1单段热诊断为冻结历史附件。\n"
        "复现需完整项目及Python依赖，在项目根目录运行 python deliverables/build_submission.py。\n"
        "校方另附真实报名表、推荐与盖章汇总表；固定命题作品详细描述按附件填‘无’。\n"
        "本包没有办理报名、学校推荐或外部提交。截止时间与命名请核对官方原件及后续通知。\n",
        encoding="utf-8")
    manifest={"version":"COMPETITION-R1","files":files,
              "report_pages":page_counts["01-工艺设计说明书.pdf"],
              "drawing_pages":page_counts["02-设计图集.pdf"],
              "submission_scope":"technical_design_only","physical_performance_verified":False}
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    archive=ROOT/"deliverables/COMPETITION-R1-技术包.zip"
    # 只打包显式清单，目录中其他文件不自动混入提交物。
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as bundle:
        for name in [*files,"提交说明.txt","manifest.json"]:
            bundle.write(out/name,name)
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT/"scripts/competition_submission_lint.py")], cwd=ROOT, check=True)
    print(f"已生成技术包：{archive}")


if __name__ == "__main__":
    main()


