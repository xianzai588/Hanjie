"""Additional physical geometries for lower precision and interval validation.

Separate from the four original workers. No original input, checkpoint or
running process is modified. An invocation performs one real solve, release
and metrology; it is not a scheduled monitor or publication job.
"""
from pathlib import Path
import argparse,json,os,subprocess,sys,traceback

ROOT=Path(__file__).resolve().parents[2]
SETTINGS={
 '8p-thermal-tool-bore006-h1125-dt025-s05':(40.006,1.125,.25,.5,5,25),
 '8p-thermal-tool-bore006-h15-dt0125-s025':(40.006,1.5,.125,.25,2.5,12.5),
 '8p-thermal-tool-bore007-h15-dt025-s05':(40.007,1.5,.25,.5,5,25),
 '8p-thermal-tool-bore0065-h15-dt025-s05':(40.0065,1.5,.25,.5,5,25),
 '8p-thermal-tool-bore0075-h15-dt025-s05':(40.0075,1.5,.25,.5,5,25)}
CANDIDATE_CASES={
 '8p-E285-k2500-f2-bore008-h1125-dt0125-s025':(40.008,1.125,.125,.25,2.5,12.5),
 '8p-E285-k2500-f2-bore008-h085-dt0125-s025':(40.008,.85,.125,.25,2.5,12.5),
 '8p-E285-k2500-f2-bore008-h1125-dt00625-s0125':(40.008,1.125,.0625,.125,1.25,6.25)}
SETTINGS.update(CANDIDATE_CASES)


def run(case):
    os.chdir(ROOT);folder=ROOT/'simulation/competition-r4/results'/case
    folder.mkdir(parents=True,exist_ok=True)
    def status(stage,**extra):
        (folder/'worker-status.json').write_text(json.dumps(dict(case=case,pid=os.getpid(),stage=stage,**extra),ensure_ascii=False,indent=2),encoding='utf8')
    D,h,dt,sd,cd,event=SETTINGS[case]
    args=['--n','8','--initial-bore',str(D),'--h',str(h),'--dt',str(dt),
        '--struct-dt',str(sd),'--cold-struct-dt',str(cd),'--event-dT',str(event),
        '--imbalance','.05','--preheat','20','--seat-path','simulation/competition-r4/geometry/8P-R2-t15.step',
        '--contact-density','2000','--copper-h','50','--source-r','74.8',
        '--source-radius','1.270170592','--source-depth','.923760431',
        '--weld-h','1','--unilateral-pads','--material-enthalpy','--paired-opposed',
        '--pardiso-symmetric','--threads','2','--checkpoint','--output',str(folder),
        '--fixture-contact-h','2000','--fixture-refinement','1']
    script='run_verified.py'
    if case in CANDIDATE_CASES:
        script='run_candidate_solver.py'
        # Density2500 is below the independently calculated2767 N/mm3
        # fixture limit. Per-head470.25 W /1.65 mm/s =285 J/mm. Retain the
        # original+5% source imbalance and2-layer/8P geometry; resolve the
        # fixture thermal domain at refinement2 from the beginning.
        args[args.index('--contact-density')+1]='2500'
        args[args.index('--fixture-refinement')+1]='2'
        args+=['--net-power','470.25']
    if (folder/'continuation-checkpoint.npz').exists():args+=['--resume']
    def command(script,*params):
        subprocess.run([sys.executable,'-X','utf8',str(ROOT/'simulation/competition-r4'/script),*params],cwd=ROOT,check=True)
    try:
        status('cold_thermal_mechanical_solve',solver=script,arguments=args)
        command(script,*args)
        status('complete_shell_clamp_release')
        command('release_cold_shell.py','--case',str(folder),'--threads','2')
        status('independent_metrology_samples')
        from postprocess import measure
        row,_,_=measure(folder,free_shell=True)
        status('complete',position_mm=row['fit']['position_diameter_mm'],
            bore_min_mm=row['fit']['sampled_bore_two_point_diameter_min_mm'],
            bore_max_mm=row['fit']['sampled_bore_two_point_diameter_max_mm'])
    except BaseException as error:
        status('failed',error=str(error));traceback.print_exc();raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',choices=SETTINGS,required=True)
    run(p.parse_args().case)
