"""Run the three authorised candidate restorations serially.

This is an immediate compute batch, not a scheduler or publication process.
Pause/failure prevents the next job from starting. Completed worker stages do
not imply engineering qualification.
"""
from pathlib import Path
import argparse,json,os,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[2]
CASES=('8p-E285-k2500-f2-bore008-h1125-dt0125-s025',
       '8p-E285-k2500-f2-bore008-h085-dt0125-s025',
       '8p-E285-k2500-f2-bore008-h1125-dt00625-s0125')


def run(threads=2,upload_helper=None):
    os.chdir(ROOT);out=ROOT/'output/cloud-20261005';out.mkdir(parents=True,exist_ok=True)
    memory_limit=int(Path('/sys/fs/cgroup/memory.max').read_text())
    if memory_limit<8*1024**3:raise RuntimeError('this candidate batch requires at least the preflight 8 GiB cgroup limit')
    completed=[]
    durability_path=out/'durable-upload-state.json'
    durability=json.loads(durability_path.read_text()) if durability_path.exists() else {}
    def persist(case):
        if upload_helper is None:return
        old=durability.get(case,{})
        if old.get('outcome_unknown'):return
        folder=ROOT/'simulation/competition-r4/results'/case
        stamp=(folder/'continuation-checkpoint.npz').stat().st_mtime_ns
        if old.get('checkpoint_mtime_ns')==stamp:return
        from cloud_checkpoint_archive import build
        path,manifest=build(case)
        request=dict(local_path=str(path),purpose='create_library_file',library_artifact_type='other')
        if old.get('library_file_id'):
            request=dict(local_path=str(path),purpose='replace_library_file',library_file_id=old['library_file_id'],version_reason='New committed cloud manufacturing checkpoint')
            if old.get('current_version_number') is not None:request['expected_current_version']=old['current_version_number']
        result=subprocess.run([sys.executable,str(upload_helper)],input=json.dumps(dict(uploads=[request])),
            text=True,capture_output=True)
        if result.returncode:
            durability[case]=dict(**old,outcome_unknown=True,error='durable upload failed or outcome unknown; no automatic retry')
        else:
            try:
                saved=json.loads(result.stdout)['results'][0]
                if saved['status']!='succeeded':raise ValueError('upload not successful')
                durability[case]=dict(saved,checkpoint_mtime_ns=stamp,committed_t_s=manifest['committed_t_s'])
            except (ValueError,KeyError,IndexError):
                durability[case]=dict(**old,outcome_unknown=True,error='upload outcome not confirmed; no automatic retry')
        durability_path.write_text(json.dumps(durability,indent=2),encoding='utf8')
    def status(stage,**extra):
        path=out/'batch-status.json';temporary=path.with_suffix('.pending.json')
        temporary.write_text(json.dumps(dict(stage=stage,threads=threads,
            cgroup_memory_limit_bytes=memory_limit,completed_workers=completed,
            complete_engineering_design_pass=False,**extra),indent=2),encoding='utf8')
        temporary.replace(path)
    for case in CASES:
        folder=ROOT/'simulation/competition-r4/results'/case
        inputs=json.loads((folder/'input.json').read_text(encoding='utf8'))
        if inputs['solver_threads']!=threads:
            raise ValueError('batch thread count must exactly match the committed input; do not rewrite metadata')
        worker=folder/'worker-status.json'
        old=json.loads(worker.read_text()) if worker.exists() else {}
        if old.get('stage')=='complete':
            completed.append(case);continue
        if (folder/'pause-requested').exists() or (out/'pause-batch').exists():
            status('paused_before_next_case',case=case);return
        status('running_serial_case',case=case)
        persist(case)
        args=[sys.executable,'-X','utf8','simulation/competition-r4/run_manufacturing_case.py',
            '--case',case,'--restore-saved-mesh','--path-journal','--reuse-symbolic',
            '--threads',str(threads),'--checkpoint-every','10']
        with (out/f'batch-{case}.log').open('a',encoding='utf8') as log:
            process=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            last_persist=time.monotonic()
            while process.poll() is None:
                if time.monotonic()-last_persist>=300:
                    persist(case);last_persist=time.monotonic()
                time.sleep(10)
            returncode=process.returncode
        persist(case)
        final=json.loads(worker.read_text()) if worker.exists() else {}
        if returncode or final.get('stage')!='complete':
            status('stopped_without_complete_case',case=case,returncode=returncode,
                worker_stage=final.get('stage'));return
        completed.append(case)
    status('three_manufacturing_workers_complete_not_design_qualification')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--threads',type=int,choices=(1,2,4),default=2)
    p.add_argument('--upload-helper',type=Path)
    a=p.parse_args();run(a.threads,a.upload_helper)
