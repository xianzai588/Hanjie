"""重建并汇集当前参赛技术文件；不代填报名、不执行外部提交。"""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    for script in ("studies/COMPETITION-DESIGN/run.py", "studies/SCHAEFFLER-MAP/run.py",
                   "studies/COMPETITION-DESIGN/robust_selection.py",
                   "studies/COMPETITION-DESIGN/engineering_checks_r3.py",
                   "deliverables/process/generate_process_r3.py",
                   "cad/parametric/generate_engineering_drawings.py", "cad/parametric/export_drawing_pdfs.py",
                   "deliverables/report/build_technical_report_pdf.py"):
        subprocess.run([sys.executable, "-X", "utf8", str(ROOT/script)], cwd=ROOT, check=True)
    out = ROOT/"deliverables/submission"
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "00-评审导航.txt":"deliverables/submission/00-评审导航.txt",
        "01-工艺设计说明书.pdf":"output/pdf/technical-report-v4.pdf",
        "02-设计图集.pdf":"cad/generated/engineering-drawings/pdf/HJ-DRW-drawing-set.pdf",
        "03-名义装配包络.step":"cad/generated/competition-design/competition-assembly.step",
        "04-设计计算.json":"studies/COMPETITION-DESIGN/results/assessment.json",
        "05-设计指标.csv":"studies/COMPETITION-DESIGN/results/result.csv",
        "06-工艺提案.md":"deliverables/process/joint-process-card.md",
        "07-设计参数.yaml":"project/competition-design.yaml",
        "08-整件热结构主网格结果.json":"simulation/competition-r3/results/8p-coarse/result.json",
        "08b-整件热结构输入.json":"simulation/competition-r3/results/8p-coarse/input.json",
        "08c-整件热结构能量历史.csv":"simulation/competition-r3/results/8p-coarse/thermal-history.csv",
        "08d-整件热结构平衡历史.csv":"simulation/competition-r3/results/8p-coarse/equilibrium-history.csv",
        "08e-工程载荷夹具洁净核算.json":"studies/COMPETITION-DESIGN/results/engineering-checks-r3.json",
        "09-守恒修订与放行闭环.svg":"deliverables/submission/09-守恒修订与放行闭环.svg",
        "10-复现与版本冻结记录.md":"deliverables/submission/10-复现与版本冻结记录.md",
        "11-候选选择.json":"studies/COMPETITION-DESIGN/results/engineering-checks-r3.json",
        "17-参数来源与证据等级.md":"deliverables/submission/17-参数来源与证据等级.md",
        "18-证据等级总图.svg":"deliverables/submission/18-证据等级总图.svg",
        "19-Schaeffler相图映射.json":"studies/SCHAEFFLER-MAP/results/schaeffler-mapping.json",
        "20-Schaeffler相图映射.svg":"studies/SCHAEFFLER-MAP/results/schaeffler-map.svg",
        "21-冷焊热制度对比.svg":"studies/SCHAEFFLER-MAP/results/cold-weld-regime.svg",
        "22-冷焊与锤击工艺卡.md":"deliverables/process/cold-weld-and-peening-card.md",
        "23-网格与位置度图.png":"docs/report/figures/r3-mesh-budget.png",
        "24-热场与接触图.png":"docs/report/figures/r3-thermal-contact.png",
        "25-位移与残余应力图.png":"docs/report/figures/r3-residual-fields.png",
    }
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
        f"COMPETITION-R3 技术包（焊接固定题）\n说明书{page_counts['01-工艺设计说明书.pdf']}页，设计图{page_counts['02-设计图集.pdf']}页。"
        "STEP为名义装配包络。\n"
        "本包为纯数字设计作品：几何来自真实BREP，全部数字结果由经典公式计算、局部热模型诊断与公差预算给出，"
        "正文显式区分计算结果与设计目标；说明书§7列出设计放行顺序与试制工程确认要求。\n"
        "工艺体系：八段两道脉冲TIG、Ni99预制隔离层＋NiFe55填充、铸铁冷焊（不预热、层间≤100 ℃）、"
        "热态轻击；整件热结构结果与能量历史在08号文件，冶金适用域声明见19～21号。\n"
        "复现需完整项目及Python依赖，在项目根目录运行 python deliverables/build_submission.py。\n"
        "校方另附真实报名表、推荐与盖章汇总表；固定命题作品详细描述按附件填‘无’。\n"
        "截止时间与命名按官方原件及后续通知执行。\n",
        encoding="utf-8")
    manifest={"version":"COMPETITION-R3","files":files,
              "report_pages":page_counts["01-工艺设计说明书.pdf"],
              "drawing_pages":page_counts["02-设计图集.pdf"],
              "submission_scope":"technical_design_only",
              "design_verified":False,"physical_validation_recommended":True,
              "product_conformity_claimed":False}
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    archive=ROOT/"deliverables/COMPETITION-R3-焊接固定题技术包.zip"
    # 只打包显式清单，目录中其他文件不自动混入提交物。
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as bundle:
        for name in [*files,"提交说明.txt","manifest.json"]:
            bundle.write(out/name,name)
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT/"scripts/competition_submission_lint.py")], cwd=ROOT, check=True)
    print(f"已生成技术包：{archive}")


if __name__ == "__main__":
    main()


