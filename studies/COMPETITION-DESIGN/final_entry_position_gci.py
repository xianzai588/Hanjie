"""Estimate numerical uncertainty from saved cases; do not launch a solve."""
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
    def completed(case):
        folder = RESULTS / case
        worker = json.loads((folder/'worker-status.json').read_text(encoding='utf8'))
        measurement = json.loads((folder/'measurement.json').read_text(encoding='utf8'))
        progress = json.loads((folder/'progress.json').read_text(encoding='utf8'))
        if worker['stage'] != 'complete' or not measurement['released'] or not progress['released']:
            raise RuntimeError(f'{case}: complete full-release result required')
        return measurement, progress
    fine, fine_progress = completed(CASE)
    single_case = '8p-thermal-tool-bore008-h15-single-dt025-s05'
    single, single_progress = completed(single_case)
    f = fine['fit']['position_diameter_mm']*1000
    single_um = single['fit']['position_diameter_mm']*1000
    epsilon21, epsilon32 = b-f, a-b
    ratio = epsilon32/epsilon21
    if ratio >= 0:
        raise RuntimeError('Saved sequence classification changed; re-evaluate the uncertainty method')
    # Equal nominal ratios: q(p)=0 even with s=-1. This is a diagnostic
    # apparent order of oscillation amplitudes, not a monotonic convergence order.
    apparent_order = math.log(abs(ratio))/math.log(r)
    delta_m = max(abs(b-f), abs(a-b), abs(a-f))
    band = 3*delta_m  # TMR uncertainty summary, equation (14), non-monotonic branch.
    spatial = dict(classification='oscillatory', epsilon21_um=epsilon21,
        epsilon32_um=epsilon32, signed_difference_ratio=ratio,
        nominal_ratio_apparent_order=apparent_order, richardson_extrapolated_um=None,
        method='Non-monotonic range estimate, TMR uncertainty summary equation (14)',
        maximum_solution_difference_um=delta_m, range_factor=3,
        GCI_fine_percent=100*band/abs(f), GCI_fine_absolute_um=band,
        fine_grid_error_band_um=[f-band,f+band], asymptotic_convergence_passed=False)
    q = 1
    coarse_correction = rt**q*(t-a)/(rt**q-1)
    time_band = 3*abs(coarse_correction)
    temporal = dict(assumed_order=q, correction_from_dt025_um=coarse_correction,
        numerical_uncertainty_um=time_band, scope='Combined temporal protocol; coarse spatial grid only')
    point = f+coarse_correction
    absolute_error = band+time_band
    report = dict(source='simulation/competition-r4/results/verification.json',
        cases=source['cases'][:3]+[CASE,single_case], input_results=[dict(case=c, h_mm=row['h_mm'],
            dt_s=row['dt_s'], nodes=row['nodes'], tetrahedra=row['tetrahedra'],
            elapsed_s=row['elapsed_s'], position_diameter_um=row['fit']['position_diameter_mm']*1000,
            bore_two_point_range_mm=[row['fit']['sampled_bore_two_point_diameter_min_mm'],
                row['fit']['sampled_bore_two_point_diameter_max_mm']]) for c,row in zip(source['cases'],rows)],
        nominal_h_ratio=r, spatial=spatial, temporal=temporal,
        combined=dict(time_adjusted_point_um=point, total_budget_point_um=30+point,
            error_band_about_fine_solution_um=[f-absolute_error,f+absolute_error],
            total_budget_error_band_um=[30+f-absolute_error,30+f+absolute_error],
            point_below_20_um=point<=20, uncertainty_upper_below_20_um=f+absolute_error<=20),
        single_head_comparison=dict(case=single_case, paired_case=source['cases'][0],
            same_h_mm=1.5, same_dt_s=.25, paired_position_um=a,single_position_um=single_um,
            difference_um=single_um-a, relative_increase_percent=100*(single_um/a-1),
            single_total_budget_point_um=30+single_um,
            uncertainty_scope='No independent single-head spatial or temporal error estimate is available'),
        model_assumptions=['The three spatial solutions oscillate; no monotonic Richardson limit is reported.',
            'The apparent order uses nominal parent-grid ratios; weld_h remains 1 mm and the family is not uniformly refined.',
            'Non-monotonic range uncertainty is an engineering estimate, not an asymptotic convergence certificate.',
            'q=1 follows the backward-Euler thermal discretization; spatial/time separability remains an assumption and the only temporal comparison is on h=1.5 mm.',
            'The time comparison also changes structural/event update steps.',
            'The single-head case has one grid; paired uncertainty is not transferred as a validated single-head bound.',
            'Material, contact, heat-source and precoat residual assumptions are verified in the trial plan.',
            'The saved bore is before final clamped forming; full-release size and forming-induced axis change require first-article calibration.'],
        method_source='https://tmbwg.github.io/turbmodels/Papers/uncertainty_summary.pdf',
        third_grid=dict(case=CASE,h_mm=fine['h_mm'],dt_s=fine['dt_s'],
            nodes=fine['nodes'],tetrahedra=fine['tetrahedra'],elapsed_s=fine_progress['elapsed_s'],
            other_worker_arguments_unchanged=True,complete_run_started=True,complete=True))
    for case, measurement, progress in [(CASE,fine,fine_progress),(single_case,single,single_progress)]:
        fit=measurement['fit']
        report['input_results'].append(dict(case=case,h_mm=measurement['h_mm'],dt_s=measurement['dt_s'],
            nodes=measurement['nodes'],tetrahedra=measurement['tetrahedra'],elapsed_s=progress['elapsed_s'],
            position_diameter_um=fit['position_diameter_mm']*1000,
            bore_two_point_range_mm=[fit['sampled_bore_two_point_diameter_min_mm'],fit['sampled_bore_two_point_diameter_max_mm']]))
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:report[k] for k in ['spatial','temporal','combined','single_head_comparison']},ensure_ascii=False))


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
