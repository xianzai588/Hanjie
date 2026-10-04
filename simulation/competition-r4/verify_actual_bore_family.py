"""Finish the already-started family with cold release, metrology and QA.

This is a local calculation continuation, not a scheduled task or a report
publication job. It never turns a failed design gate into a passing result.
"""
from pathlib import Path
import json,os,subprocess,sys,time,traceback

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent/'results'
CASES=['8p-thermal-tool-bore008-h15-dt025-s05',
       '8p-thermal-tool-bore008-h1125-dt025-s05',
       '8p-thermal-tool-bore008-h15-dt0125-s025']
LOWER='8p-thermal-tool-bore006-h15-dt025-s05'

def main():
    target=OUT/'actual-family-worker-status.json'
    def status(stage,**extra):
        data=dict(pid=os.getpid(),stage=stage,cases=CASES,lower_endpoint=LOWER,**extra)
        temporary=target.with_suffix('.next.json')
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
        temporary.replace(target)
    def command(script,*arguments):
        subprocess.run([sys.executable,'-X','utf8',str(ROOT/script),*arguments],cwd=ROOT,check=True)
    try:
        previous=None
        while True:
            states={}
            for case in [LOWER,*CASES]:
                try:states[case]=json.loads((OUT/case/'worker-status.json').read_text(encoding='utf8'))['stage']
                except (OSError,json.JSONDecodeError):states[case]='starting'
            if states!=previous:
                status('waiting_for_actual_cold_release',workers=states)
                print(json.dumps(states),flush=True);previous=states
            if 'failed' in states.values():raise RuntimeError('actual cold worker failed: '+json.dumps(states))
            if all(v=='complete' for v in states.values()):break
            time.sleep(30)
        status('position_bore_and_fixture_domain_checks')
        command('simulation/competition-r4/postprocess.py','--cases',*CASES)
        status('segment_start_temperature_check')
        command('simulation/competition-r4/postprocess_process.py')
        status('peening_window_check')
        command('simulation/competition-r4/postprocess_peening.py','--run',CASES[0],'--fine',CASES[2])
        verification=json.loads((OUT/'verification.json').read_text(encoding='utf8'))
        process=json.loads((OUT/'process-temperature-verification.json').read_text(encoding='utf8'))
        peening=json.loads((OUT/'peening-verification.json').read_text(encoding='utf8'))
        gates=dict(position=verification['position_design_pass'],bore=verification['bore_size_design_pass'],
                   fixture_heat_and_support=verification['fixture_thermal_model_pass'],
                   segment_temperature=process['process_temperature_design_pass'],peening=peening['design_checks_pass'])
        rows=verification['records']
        text=['# 实际热耦合家族的完全卸夹核验',
              '\n数据来自当前实体、完整冷却与独立基准测量；不是实物检测记录。',
              '\n| 算例 | 冷态位置度 / μm | 最小孔径 / mm | 最大孔径 / mm |',
              '| --- | ---: | ---: | ---: |']
        for name,row in zip(CASES,rows):
            fit=row['fit'];text.append(f"| {name} | {fit['position_diameter_mm']*1000:.3f} | {fit['sampled_bore_two_point_diameter_min_mm']:.5f} | {fit['sampled_bore_two_point_diameter_max_mm']:.5f} |")
        text += [f"\n空间响应差：{verification['spatial_response_relative_error']*100:.3f}%；时间响应差：{verification['temporal_response_relative_error']*100:.3f}%。",
                 f"焊后位置度预算：{verification['position_budget_mm']*1000:.3f} μm。",
                 '\n各设计门：'+json.dumps(gates,ensure_ascii=False),
                 '\n说明书、WPS、气路和图纸在选型与全部设计门核对后同步。此计算继续任务不自动发布正式提交稿。']
        path=ROOT/'output/review/实际热耦合家族完全卸夹核验.md'
        path.write_text('\n'.join(text)+'\n',encoding='utf8')
        status('calculation_checks_complete' if all(gates.values()) else 'engineering_repair_required',gates=gates,review=str(path))
    except Exception as error:
        status('calculation_check_failed',error=str(error));traceback.print_exc();raise

if __name__=='__main__':main()
