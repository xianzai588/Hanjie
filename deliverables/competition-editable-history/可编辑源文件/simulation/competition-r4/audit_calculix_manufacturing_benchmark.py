"""Audit actual native plastic/deposition/cutting states and a cold restart."""
import json
import os
import re
import shutil
import subprocess
import numpy as np
from run_calculix_manufacturing_benchmark import OUT, SOLVER


def read_states(path):
    split=re.split(r'S T E P\s+(\d+)',path.read_text())
    states={}
    for k in range(1,len(split),2):
        step=int(split[k]);body=split[k+1];fields={}
        for name,head in [('u','displacements ('),('stress','stresses ('),('peeq','equivalent plastic strain ('),('me','mechanical strains ('),('rf','forces (')]:
            start=body.find(head)
            if start<0:continue
            rows=[]
            for line in body[start:].splitlines()[2:]:
                try:q=[float(v) for v in line.split()]
                except ValueError:break
                if not q:
                    if rows:break
                    continue
                rows.append(q)
            if rows:fields[name]=np.array(rows)
        states[step]=fields
    return states


def main():
    states=read_states(OUT/'benchmark.dat')
    if list(states)!=list(range(1,9)):raise RuntimeError('Missing actual manufacturing stage')
    for step,fields in states.items():np.savez_compressed(OUT/f'state-{step}.npz',**fields)
    def qt(s):return states[s]['peeq'][states[s]['peeq'][:,0]<=40,2]
    def ni(s):return states[s]['peeq'][states[s]['peeq'][:,0]>40,2]
    native=dict(substrate_initial_plastic_strain=float(np.max(qt(1))),
                substrate_predeposit_plastic_strain=float(np.max(qt(3))),
                deposit_substrate_plastic_difference=float(np.max(abs(qt(4)-qt(3)))),
                coherent_deposit_plastic_max=float(np.max(ni(4))),
                cold_deposit_plastic_range=[float(np.min(ni(5))),float(np.max(ni(5)))],
                retained_substrate_cold_cut_plastic_difference=float(np.max(abs(qt(6)-qt(5)))),
                removed_element_ids=list(range(61,81)),
                cut_remaining_integration_points=len(states[6]['peeq']),
                cut_original_integration_points=len(states[5]['peeq']),
                cut_material_volume_mm3=10.,
                unload_displacement_difference_mm=float(np.max(abs(states[8]['u']-states[6]['u']))),
                unload_stress_difference_MPa=float(np.max(abs(states[8]['stress']-states[6]['stress']))),
                unload_plastic_difference=float(np.max(abs(states[8]['peeq']-states[6]['peeq']))))
    # An actual cold binary restart uses the mature tool's integration-point
    # plastic variables, not reconstructed stresses or zeroed initial history.
    path=OUT/'restart-from-cut';path.mkdir(exist_ok=True)
    if not (path/'restart.log').exists():
        shutil.copyfile(OUT/'benchmark.rout',path/'restart.rin')
        text=(OUT/'benchmark.inp').read_text();tail=text[text.index('** loaded'):]
        (path/'restart.inp').write_text('*RESTART,READ,STEP=6\n'+tail,encoding='ascii')
        env=os.environ.copy();env['OMP_NUM_THREADS']='1';env['CCX_NPROC_RESULTS']='1';env['CCX_NPROC_STIFFNESS']='1'
        result=subprocess.run([str(SOLVER),'-i','restart'],cwd=path,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace',timeout=120)
        (path/'restart.log').write_text(result.stdout,encoding='utf8')
        if result.returncode or '*ERROR' in result.stdout or 'Job finished' not in result.stdout:raise RuntimeError('Actual binary restart failed')
    restarted=read_states(path/'restart.dat')
    last=restarted[max(restarted)]
    restart_errors={name:float(np.max(abs(last[name]-states[8][name]))) for name in ['u','stress','peeq','me']}
    passed=(native['substrate_initial_plastic_strain']>0 and native['substrate_predeposit_plastic_strain']>0
            and native['deposit_substrate_plastic_difference']<1e-10
            and native['coherent_deposit_plastic_max']<1e-10
            and min(native['cold_deposit_plastic_range'])>0
            and native['retained_substrate_cold_cut_plastic_difference']<1e-10
            and native['cut_remaining_integration_points']==480
            and native['unload_stress_difference_MPa']<1e-5
            and native['unload_plastic_difference']<1e-10
            and max(restart_errors.values())<1e-5)
    audit=dict(native_history=native,actual_binary_cold_restart_difference=restart_errors,
               native_plastic_deposition_cut_history_passed=bool(passed),
               actual_first_layer_joint_passed=False, full_manufacturing_chain_passed=False,
               scope='Tool manufacturing-history qualification only; substrate plasticity, stress-free new solid addition, physical element removal and cold restart. No calibrated weld source, melting law, deposit mass/reference geometry, PMZ capacity or full component response is qualified here.',
               sources=['https://www.dhondt.de/','CalculiX 2.23 official manual *MODEL CHANGE / *PLASTIC / *RESTART'])
    (OUT/'native-history-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
    print(json.dumps(audit,indent=2))
    if not passed:raise RuntimeError('Native plastic manufacturing history did not satisfy its qualification')


if __name__=='__main__':main()
