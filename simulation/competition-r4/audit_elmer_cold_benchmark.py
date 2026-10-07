"""Compare the completed native Elmer cold baseline with its analytic solutions."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mma_literature_profile import ROOT


CASE = ROOT/'simulation/competition-r4/results/elmer-cold-thermoelastic-benchmark-libfix-20261007'
OUT = ROOT/'output/review/elmer-cold-thermoelastic-benchmark-20261007'


def field(body, stage):
    return dict(np.load(CASE/body/'mesh'/f'{stage}_t0001.npz'))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    run = json.loads((CASE/'execution.json').read_text(encoding='utf8'))
    hot, cold = [field('Ni-free', s) for s in ('hot', 'cold')]
    original = hot['coordinates']-hot['displacement']
    expected_u = original*(16.7e-6*980)
    lam = 1+16.7e-6*980
    mass_g = 1000*8.89e-3
    V_hot = 1000*lam**3
    rho_hot_g_mm3 = mass_g/V_hot
    ni = dict(hot_displacement_error_mm=float(np.max(np.abs(hot['displacement']-expected_u))),
              hot_von_mises_max_MPa=float(np.max(np.abs(hot['vonmises']))),
              cold_displacement_max_mm=float(np.max(np.abs(cold['displacement']))),
              cold_von_mises_max_MPa=float(np.max(np.abs(cold['vonmises']))),
              carried_mass_g=mass_g, hot_volume_mm3=V_hot,
              hot_density_g_mm3=rho_hot_g_mm3, cold_density_g_mm3=8.89e-3,
              density_mass_recovery_error_g=float(abs(rho_hot_g_mm3*V_hot-mass_g)))
    b = {s:field('QT-Ni-series',s) for s in ('hot','cold','loaded','unloaded')}
    x = (b['cold']['coordinates']-b['cold']['displacement'])[:,0]
    far = ((x>=20)&(x<=40))|((x>=60)&(x<=80))
    analytical = run['analytic_bar_cold_axial_stress_MPa']
    cold_far = b['cold']['stress_xx'][far]
    added_far = (b['loaded']['stress_xx']-b['cold']['stress_xx'])[far]
    stress_keys = [k for k in b['cold'] if k.startswith('stress_')]
    bar = dict(analytic_cold_axial_stress_MPa=analytical,
               far_field_mean_cold_axial_stress_MPa=float(np.mean(cold_far)),
               far_field_max_relative_error=float(np.max(abs(cold_far-analytical))/analytical),
               far_field_mean_added_axial_stress_MPa=float(np.mean(added_far)),
               far_field_added_stress_max_relative_error=float(np.max(abs(added_far-10))/10),
               local_axial_stress_range_MPa=[float(np.min(b['cold']['stress_xx'])),float(np.max(b['cold']['stress_xx']))],
               unloaded_cold_displacement_max_difference_mm=float(np.max(abs(b['unloaded']['displacement']-b['cold']['displacement']))),
               unloaded_cold_stress_max_difference_MPa=max(float(np.max(abs(b['unloaded'][k]-b['cold'][k]))) for k in stress_keys),
               cold_reference_retained=True,
               unloaded_from_actual_loaded_restart=True,
               mass_reference='40 C geometry, density rho20/(1+alpha*20)^3; the hot geometry is not treated as a cold stress-free CAD volume')
    passed = (ni['hot_displacement_error_mm']<1e-9 and ni['cold_displacement_max_mm']<1e-9
              and ni['hot_von_mises_max_MPa']<1e-6 and ni['cold_von_mises_max_MPa']<1e-6
              and bar['far_field_max_relative_error']<=.05
              and bar['far_field_added_stress_max_relative_error']<=.05
              and bar['unloaded_cold_displacement_max_difference_mm']<1e-9
              and bar['unloaded_cold_stress_max_difference_MPa']<1e-6)
    summary = dict(solver=run['solver'], Ni_free=ni, QT_Ni_series=bar,
                   analytic_cold_baseline_passed=bool(passed),
                   actual_deposited_joint_passed=False, plastic_history_transfer_qualified=False,
                   full_manufacturing_chain_passed=False,
                   sources=run['sources'],
                   scope='Actual native Elmer linear thermoelastic runs; free thermal recovery, elastic residual stress and same-reference elastic loading/unloading. No joint, melt or plastic state has been assigned by this benchmark.')
    (OUT/'cold-baseline-audit.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig, ax = plt.subplots(figsize=(6.5,3.5),layout='constrained')
    for s,label,color in [('cold','Cold residual','#247ba0'),('loaded','Loaded: +10 MPa','#d07829'),('unloaded','Unloaded','#50633a')]:
        unique = np.unique(x)
        vals = [np.mean(b[s]['stress_xx'][x==p]) for p in unique]
        ax.plot(unique,vals,label=label,color=color,ls='--' if s=='unloaded' else '-',lw=1.5)
    ax.axhline(analytical,color='#666666',lw=.8,ls=':',label='Analytic far-field residual')
    ax.axvline(50,color='#aaaaaa',lw=.8)
    ax.text(25,42,'QT reference',ha='center');ax.text(75,42,'Ni reference',ha='center')
    ax.set(xlabel='Original axial coordinate (mm)',ylabel='Mean axial stress (MPa)',ylim=(40,61))
    ax.legend(frameon=False,loc='upper center',ncol=2,fontsize=8)
    for ext in ('png','pdf','svg'):fig.savefig(OUT/f'actual-elmer-cold-load-unload.{ext}',dpi=240)
    plt.close(fig)
    print(json.dumps(summary,indent=2))
    if not passed:raise RuntimeError('Completed cold baseline disagrees with analytic qualification')


if __name__=='__main__':main()
