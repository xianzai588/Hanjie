"""Fe-Ni-C projection for the saved simultaneous liquid-inventory scenarios.

The two mixture compositions are conditional inventories, not fitted dilution.
Their phase states do not assign retained chemistry or mechanical capacity.
"""
import csv
import json
from pathlib import Path
import numpy as np
import xarray as xr
from pycalphad import Database, equilibrium, variables as v
from threadpoolctl import threadpool_limits
from run_fenic_phase import ROOT, MASS
from audit_fenic_gibbs import run as audit_gibbs

BASE = ROOT/'simulation/competition-r4/results'
OUT = BASE/'mma-end80-r12-inventory-phase-20261007'


def run():
    if (OUT/'phase-summary.json').exists():
        raise ValueError('Preserve the completed inventory-composition calculation')
    OUT.mkdir(exist_ok=True)
    raw_dir = OUT/'raw'
    raw_dir.mkdir(exist_ok=True)
    inventory = json.loads((BASE/'mma-first-end80-r12-trace-20261007/simultaneous-molten-inventory.json').read_text())
    qt_fractions = inventory['complete_mix_QT_mass_fraction_scenarios_at_that_time']
    # Same nominal full chemistry used by the thermal input. Si/Mn/Mg/P/S/Cr
    # are omitted only after computing the full mass mixture and Fe balance.
    qt = np.array([3.65, 93.25, .05])
    filler = np.array([1., 1.8, 96.])
    temperatures = np.unique(np.r_[25., 200., 300., 500., 700., 900.,
        np.arange(1050., 1500.1, 10.), 1700., 2000.])
    db = Database(ROOT/'simulation/competition-r4/materials/Oikawa-2026-FeNiC.tdb')
    cases = []
    for name, fraction in [('undiluted_CI_A1', 0.),
                           ('inventory_QT_low', qt_fractions[0]),
                           ('inventory_QT_high', qt_fractions[1])]:
        full = filler*(1-fraction)+qt*fraction
        wt = full*100/full.sum()
        atomic = wt/MASS
        atomic /= atomic.sum()
        case = dict(name=name, conditional_QT_mass_fraction=fraction,
                    ternary_normalized_wt_pct=dict(zip(['C', 'Fe', 'Ni'], wt.tolist())),
                    omitted_constituents_wt_pct=100-float(full.sum()),
                    limits={'graphite_allowed': {}, 'graphite_suppressed': {}})
        for graphite, label in [(True, 'graphite_allowed'), (False, 'graphite_suppressed')]:
            phases = ['LIQUID', 'FCC_A1', 'BCC_A2', 'CEMENTITE']+(['GRAPHITE'] if graphite else [])
            data = equilibrium(db, ['C', 'FE', 'NI', 'VA'], phases,
                {v.T: temperatures+273.15, v.P: 101325, v.N: 1,
                 v.X('C'): atomic[0], v.X('NI'): atomic[2]},
                output=['HM'], calc_opts={'pdens': 2000})
            data.to_netcdf(raw_dir/f'{name}-{label}.nc')
            print(name, label, 'equilibrium saved', flush=True)
        cases.append(case)
    (raw_dir/'phase-summary.json').write_text(json.dumps(dict(cases=cases)), encoding='utf8')
    branch = audit_gibbs(raw_dir, OUT/'gibbs-checked')
    checked = json.loads((OUT/'gibbs-checked/phase-summary.json').read_text())
    rows = []
    for case in checked['cases']:
        wt = np.array([case['ternary_normalized_wt_pct'][k] for k in ('C', 'Fe', 'Ni')])
        atomic = wt/MASS
        atomic /= atomic.sum()
        for label in ('graphite_allowed', 'graphite_suppressed'):
            data = xr.load_dataset(OUT/'gibbs-checked'/f'{case["name"]}-{label}.nc')
            phase = data.Phase.values.squeeze()
            amount = np.nan_to_num(data.NP.values.squeeze())
            composition = np.nan_to_num(data.X.values.squeeze())
            balance = float(np.max(abs((amount[..., None]*composition).sum(axis=-2)-atomic)))
            if balance > 1e-6 or not np.all(np.isfinite(data.HM)):
                raise RuntimeError('Invalid phase composition or enthalpy')
            weight = amount*(composition@MASS)/(atomic@MASS)
            enthalpy = (data.HM.values.squeeze()-data.HM.values.squeeze()[0])/(atomic@MASS/1000)
            if np.min(np.diff(enthalpy)) < -10:
                raise RuntimeError('Non-monotone equilibrium enthalpy')
            case['limits'][label]['maximum_atomic_balance_error'] = balance
            for j, t in enumerate(temperatures):
                rows.append(dict(case=case['name'], limit=label, T_C=float(t),
                    delta_H_25C_J_kg=float(enthalpy[j]),
                    **{p+'_mass_fraction': float(np.where(phase[j]==p, weight[j], 0).sum())
                       for p in ('LIQUID', 'FCC_A1', 'BCC_A2', 'CEMENTITE', 'GRAPHITE')}))
    with (OUT/'phase-fractions-enthalpy.csv').open('w', newline='', encoding='utf8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(cases=checked['cases'], Gibbs_branch_audit=branch,
        inventory_source=inventory['source_run'],
        source_DOI='10.2355/tetsutohagane.TETSU-2025-072',
        interpretation='actual-time liquid-inventory complete-mix scenarios; not actual dilution, retained layer composition or a rigorous global bound',
        applicability='Fe-Ni-C projection; omitted Si/Mn and graphite kinetics. FCC mass fraction is not interface or PMZ fracture capacity.',
        transport_dilution_verified=False, remelted_material_capacity_assigned=False)
    (OUT/'phase-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        run()
