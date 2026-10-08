"""Rebuild the active ring delivery; reject missing or stale engineering results.

Run expensive calculations explicitly using each simulation's README first.
This command rebuilds CAD/cards/automation/publication from the frozen inputs.
"""
from pathlib import Path
import subprocess
import sys
import json
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))


def run(*args):
    subprocess.run([sys.executable,*args],cwd=ROOT,check=True)


def main():
    from hanjie.domain.submission import read_submission
    from hanjie.reporting.current_status import write_status_artifacts
    spec=read_submission()
    for name in ('simulation/ring-baseline-structure/results/assessment.json',
                 'simulation/ring-baseline-manufacturing/results/assessment.json'):
        path=ROOT/name
        if not path.is_file():
            raise ValueError(f'缺少圆环计算结果：{name}；先按该目录README执行求解')
        record=json.loads(path.read_text(encoding='utf8'))
        if record.get('process_version')!=spec['version']:
            raise ValueError(f'计算版本过期：{name}；禁止用旧结果构建当前圆环交付')
        if 'manufacturing' in name and not record.get('thermal_cycle_completed'):
            raise ValueError('圆环主热过程尚未完成；禁止把计算中间状态封为完整交付')
    run('cad/parametric/build_ring_baseline.py')
    run('studies/COMPETITION-DESIGN/ring-fixture-feasibility.py')
    run('cad/parametric/ring_fixture/build_ring_fixture.py')
    run('studies/COMPETITION-DESIGN/ring-production-resources.py')
    run('deliverables/process/generate_ring_process.py')
    run('automation/app/run_demo.py','--count','1000')
    write_status_artifacts(ROOT)
    run('docs/report/build_publication_figures.py')
    run('scripts/generate-ring-ut-coverage.py')
    run('deliverables/report/build_technical_report_pdf.py','--competition-entry','--with-drawings')
    run('deliverables/build_competition_entry.py')
    print('当前圆环交付已重建；实际页数与验证范围见包内清单。')


if __name__=='__main__':main()
