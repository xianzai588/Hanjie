"""Independent local FE job: cold solve, shell-clamp release and metrology."""
from pathlib import Path
import argparse,json,os,subprocess,sys,traceback,time
ROOT=Path(__file__).resolve().parents[2]
JOBS={
 '8p-bore006-h15-dt025-s05':(40.006,1.5,.25,.5,5,25),
 '8p-bore008-h15-dt025-s05':(40.008,1.5,.25,.5,5,25),
 '8p-bore008-h1125-dt025-s05':(40.008,1.125,.25,.5,5,25),
 '8p-bore008-h15-dt0125-s025':(40.008,1.5,.125,.25,2.5,12.5)}
for name,settings in list(JOBS.items()):
 JOBS[name.replace('8p-bore','8p-thermal-tool-bore')]=settings
JOBS['8p-thermal-tool-h200-bore008-h15-dt025-s05']=(40.008,1.5,.25,.5,5,25)
JOBS['8p-thermal-tool-ref2-bore008-h15-dt025-s05']=(40.008,1.5,.25,.5,5,25)
JOBS['8p-thermal-tool-bore008-h084375-dt025-s05']=(40.008,.84375,.25,.5,5,25)
JOBS['8p-thermal-tool-bore008-h06328125-dt025-s05']=(40.008,.6328125,.25,.5,5,25)
def main(name,after_case=None):
 os.chdir(ROOT)
 folder=ROOT/'simulation/competition-r4/results'/name
 folder.mkdir(parents=True,exist_ok=True)
 def status(stage,**extra):
  (folder/'worker-status.json').write_text(json.dumps(dict(pid=os.getpid(),case=name,stage=stage,**extra),indent=2),encoding='utf8')
 try:
  if after_case is not None:
   status('queued_after_reference_case',after_case=after_case)
   previous=ROOT/'simulation/competition-r4/results'/after_case/'worker-status.json'
   while True:
    if previous.exists():
     try:stage=json.loads(previous.read_text(encoding='utf8'))['stage']
     except (json.JSONDecodeError,OSError):stage='writing'
     if stage=='failed':raise RuntimeError('predecessor solve failed: '+after_case)
     if stage=='complete':break
    time.sleep(30)
  D,h,dt,sd,cd,event=JOBS[name]
  args=['--n','8','--initial-bore',str(D),'--h',str(h),'--dt',str(dt),'--struct-dt',str(sd),
        '--cold-struct-dt',str(cd),'--event-dT',str(event),'--imbalance','.05','--preheat','20',
        '--seat-path','simulation/competition-r4/geometry/8P-R2-t15.step','--contact-density','2000',
        '--copper-h','50','--source-r','74.8','--source-radius','1.270170592','--source-depth','.923760431',
        '--weld-h','1','--unilateral-pads','--material-enthalpy','--paired-opposed',
        '--pardiso-symmetric','--threads','2','--checkpoint','--output',str(folder)]
  if 'thermal-tool' in name:
   args+=['--fixture-contact-h','200' if 'h200-' in name else '2000',
          '--fixture-refinement','2' if 'ref2-' in name else '1']
  if (folder/'continuation-checkpoint.npz').exists():args+=['--resume']
  status('cold_thermal_mechanical_solve')
  subprocess.run([sys.executable,'-X','utf8','simulation/competition-r4/run_verified.py',*args],check=True)
  status('complete_shell_clamp_release')
  subprocess.run([sys.executable,'-X','utf8','simulation/competition-r4/release_cold_shell.py',
                  '--case',str(folder),'--threads','2'],check=True)
  status('independent_metrology_samples')
  from postprocess import measure
  row,_,_=measure(folder,free_shell=True)
  status('complete',position_mm=row['fit']['position_diameter_mm'],
         bore_min_mm=row['fit']['sampled_bore_two_point_diameter_min_mm'],
         bore_max_mm=row['fit']['sampled_bore_two_point_diameter_max_mm'])
 except Exception as error:
  status('failed',error=str(error));traceback.print_exc();raise
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--case',choices=JOBS,required=True)
 parser.add_argument('--after-case',choices=JOBS)
 a=parser.parse_args();main(a.case,a.after_case)
