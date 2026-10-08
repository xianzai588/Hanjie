"""Two approved short source/birth compatibility cases; no new process search."""
from pathlib import Path
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'simulation/competition-r4'))
from run_mma_startup_check import arguments
from run_ni99_precoat_first import run
from threadpoolctl import threadpool_limits

OUT=Path(__file__).resolve().parent
plan=dict(scope='approved one local source-assembly correction, current width only',
    cases=[dict(name='dt0125',dt_s=.125),dict(name='dt00625',dt_s=.0625)],
    stop_time_s=1.,wall_clock_review_after_s=600,
    source='visible_surface, midpoint actual born polygons and internal front',
    unchanged_inputs=dict(current_A=110,voltage_V=23,design_efficiency=.8,net_reference_W=2024,
        speed_mm_min=100,mass_rate_g_s=.17,initial_QT_C=300,
        Gaussian_one_over_e_half_width_mm=3.2,growth_rise_length_mm=3.2,
        liquid_transport_factor=1,Ni_conductivity_reference_scale=.75),
    same_comparison='prior visible-surface/original-width branch; no return to factor3',
    stop_conditions=['original nonlinear residual/line-search failure',
        'original temperature guard at2800C or minimum-principle failure',
        'source hits any unborn Ni polygon','source Gaussian power exceeds its analytic total'],
    no_mechanical_transfer=True,no_process_or_material_qualification_assigned=True)
(OUT/'approved-run-plan.json').write_text(json.dumps(plan,indent=2),encoding='utf8')
executions=[]
for case in plan['cases']:
    output=OUT/case['name']
    config=arguments(None,output,case['dt_s'],False,1.,1.,'bottom_up')
    config.source_model='visible_surface'
    config.record_nodal_history=True
    start=time.perf_counter();error=None
    print('START',case['name'],flush=True)
    try:
        with threadpool_limits(limits=1):result=run(config)
    except Exception as exc:
        error=str(exc)
        result=json.loads((output/'failure.json').read_text(encoding='utf8')) if (output/'failure.json').exists() else None
        print('STOP',case['name'],error,flush=True)
    row=dict(case=case['name'],runtime_s=time.perf_counter()-start,error=error,result=result,
        mechanical_transfer_allowed=False)
    executions.append(row)
    (OUT/'execution.json').write_text(json.dumps(executions,indent=2),encoding='utf8')
    print('END',case['name'],round(row['runtime_s'],2),flush=True)
