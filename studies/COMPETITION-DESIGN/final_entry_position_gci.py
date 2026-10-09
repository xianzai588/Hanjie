"""Use only the three saved final-weld cases; optionally prepare one finer mesh."""
from pathlib import Path
import argparse
import json
import math
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'simulation/competition-r4/results'
OUTPUT = Path(__file__).with_name('results') / 'final-entry-position-gci-20261009.json'
CASE = '8p-thermal-tool-bore008-h084375-dt025-s05'


def estimate():
    source = json.loads((RESULTS / 'verification.json').read_text(encoding='utf8'))
    rows = source['records'][:3]
    a, b, t = [row['fit']['position_diameter_mm'] * 1000 for row in rows]
    r = rows[0]['h_mm'] / rows[1]['h_mm']
    rt = rows[0]['dt_s'] / rows[2]['dt_s']
    spatial = {}
    temporal = {}
    for p in (1, 2):
        correction = (b - a) / (r**p - 1)
        band = 3 * abs(correction)
        spatial[str(p)] = dict(assumed_order=p, extrapolated_um=b+correction,
            fine_grid_correction_um=correction, safety_factor=3,
            GCI_fine_percent=100*band/abs(b), GCI_fine_absolute_um=band,
            fine_grid_error_band_um=[b-band, b+band])
        fine_correction = (t-a)/(rt**p-1)
        coarse_correction = rt**p*fine_correction
        temporal[str(p)] = dict(assumed_order=p, extrapolated_um=t+fine_correction,
            correction_from_dt025_um=coarse_correction,
            GCI_coarse_absolute_um=3*abs(coarse_correction))
    point = spatial['2']['extrapolated_um'] + temporal['2']['correction_from_dt025_um']
    absolute_error = spatial['2']['GCI_fine_absolute_um'] + temporal['2']['GCI_coarse_absolute_um']
    count_exponent = math.log(rows[1]['elapsed_s']/rows[0]['elapsed_s']) / math.log(rows[1]['tetrahedra']/rows[0]['tetrahedra'])
    report = dict(source='simulation/competition-r4/results/verification.json',
        cases=source['cases'][:3], input_results=[dict(case=c, h_mm=row['h_mm'],
            dt_s=row['dt_s'], nodes=row['nodes'], tetrahedra=row['tetrahedra'],
            elapsed_s=row['elapsed_s'], position_diameter_um=row['fit']['position_diameter_mm']*1000,
            bore_two_point_range_mm=[row['fit']['sampled_bore_two_point_diameter_min_mm'],
                row['fit']['sampled_bore_two_point_diameter_max_mm']]) for c,row in zip(source['cases'],rows)],
        nominal_h_ratio=r, spatial=spatial, temporal=temporal,
        combined_p2_q2=dict(point_prediction_um=point, total_budget_point_um=30+point,
            error_band_about_existing_fine_solution_um=[b-absolute_error,b+absolute_error],
            total_budget_error_band_um=[30+b-absolute_error,30+b+absolute_error],
            point_below_20_um=point<=20, GCI_upper_below_20_um=b+absolute_error<=20),
        model_assumptions=['Two spatial grids do not determine observed order or asymptotic convergence.',
            'p=1 and p=2 are sensitivity assumptions; q=1/q=2 likewise.',
            'dt refinement also refines structural/event steps; correction represents the combined temporal protocol.',
            'The h parameter changes parent-solid sizing while weld_h remains 1 mm; GCI uses the nominal h ratio and is provisional.',
            'Spatial/time corrections are assumed separable; only one temporal comparison exists.',
            'GCI is a numerical error indicator, not a statistical confidence interval or a material/process uncertainty bound.',
            'The saved final-weld cases represent their original process and cold-start assumptions; precoat residual stress is a trial-plan assumption.',
            'All saved bore minima are below 40.000 mm; direct-size acceptance is a first-article condition, not a completed FE result.'],
        method_source='https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html',
        third_grid=dict(case=CASE,h_mm=rows[1]['h_mm']/r,dt_s=.25,
            other_worker_arguments_unchanged=True,complete_run_started=False,
            wall_time_count_exponent=count_exponent))
    if (RESULTS/CASE/'mesh-smoke-summary.json').exists():
        smoke=json.loads((RESULTS/CASE/'mesh-smoke-summary.json').read_text(encoding='utf8'))
        count=smoke['tetrahedra']
        predicted=rows[1]['elapsed_s']*(count/rows[1]['tetrahedra'])**count_exponent
        report['third_grid'].update(smoke=smoke, estimated_wall_time_hours=predicted/3600,
            planning_range_hours=[.75*predicted/3600,1.5*predicted/3600],
            wall_time_scope='Empirical same-host solve-time/count trend from two saved runs; memory and host contention can change it.')
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:report[k] for k in ['spatial','temporal','combined_p2_q2','third_grid']},ensure_ascii=False))


def mesh_smoke():
    import numpy as np
    sys.path.insert(0,str(ROOT/'simulation/competition-r4'))
    from run_verified import mesh
    from affine_interface import audit
    folder=RESULTS/CASE
    folder.mkdir(exist_ok=True)
    if (folder/'mesh-smoke-summary.json').exists():
        raise RuntimeError('This one permitted mesh preparation has already completed.')
    start=time.perf_counter()
    x,e,m,bd,links=mesh(8,.84375,1.,ROOT/'simulation/competition-r4/geometry/8P-R2-t15.step',None)
    bore=np.abs(np.linalg.norm(x[:,:2],axis=1)-20)<1e-4
    x[bore,:2]*=20.004/20
    patch=audit(x,links)
    np.savez_compressed(folder/'mesh-smoke.npz',x=x,e=e,material=m,boundary=bd)
    info=dict(h_mm=.84375,dt_s=.25,weld_h_mm=1.,initial_bore_mm=40.008,
        nodes=len(x),tetrahedra=len(e),material_element_counts={str(k):int((m==k).sum()) for k in np.unique(m)},
        interface_patch=patch,mesh_generation_elapsed_s=time.perf_counter()-start,
        smoke_scope='Mesh generation and unchanged affine interface patch only; no thermal/mechanical step or full solve.',
        full_run_started=False)
    (folder/'mesh-smoke-summary.json').write_text(json.dumps(info,indent=2),encoding='utf8')
    estimate()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mesh-smoke',action='store_true')
    if p.parse_args().mesh_smoke:mesh_smoke()
    else:estimate()
