"""Product-specific Fe-Ni-C screening for the independent precoat design."""
from pathlib import Path
import csv
import json
import time
import numpy as np
from pycalphad import Database
from threadpoolctl import threadpool_limits
from run_fenic_phase import evaluate
from audit_fenic_gibbs import run as audit_gibbs

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'simulation/competition-r4/results/design-precoat-materials-20261006'
SOURCE = 'https://www.kobelco.co.jp/products/welding/pdf/catalog.pdf'


def run():
    raw_out = OUT / 'raw'
    if (raw_out / 'phase-summary.json').exists():
        raise ValueError('Preserve completed evidence; use the saved results')
    raw_out.mkdir(parents=True, exist_ok=True)
    database = Database(ROOT / 'simulation/competition-r4/materials/Oikawa-2026-FeNiC.tdb')
    temperature = np.r_[25., 200., 300., 500., 800., np.arange(1000., 1600.1, 10.)]
    # Published typical deposit values, not core-wire purity or batch certificates.
    fillers = {'CI-A1': np.array([1., 1.8, 96.]),
               'CI-A2': np.array([1.2, 42.3, 54.6])}
    qt = np.array([3.65, 93.25, .05])
    rows, cases = [], []
    started = time.perf_counter()
    for product, filler in fillers.items():
        for dilution in (0., .20):
            retained = (1-dilution)*filler + dilution*qt
            normalized = retained*100/retained.sum()
            name = product+'-QT'+str(int(100*dilution))
            case = dict(name=name, product=product, input_QT_mass_fraction=dilution,
                        ternary_normalized_wt_pct=dict(zip(['C', 'Fe', 'Ni'], normalized.tolist())),
                        unrepresented_mass_wt_pct=float(100-retained.sum()), limits={})
            for graphite, limit in ((True, 'graphite_allowed'), (False, 'graphite_suppressed')):
                eq, fractions, audit = evaluate(database, normalized, temperature, graphite)
                eq.to_netcdf(raw_out / (name+'-'+limit+'.nc'))
                case['limits'][limit] = audit
                for i, value in enumerate(temperature):
                    rows.append(dict(case=name, limit=limit, T_C=float(value),
                        **{phase+'_mass_fraction': float(fractions.get(phase, np.zeros(len(temperature)))[i])
                           for phase in ('LIQUID', 'FCC_A1', 'BCC_A2', 'CEMENTITE', 'GRAPHITE')}))
                print(name, limit, audit, flush=True)
            cases.append(case)
    with (raw_out / 'phase-fractions.csv').open('w', newline='', encoding='utf8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summary = dict(cases=cases, product_source=SOURCE, product_source_pages=[344, 345, 346, 347, 551],
                   typical_CI_A1_wt_pct={'C': 1., 'Si': .2, 'Mn': .6, 'Ni': 96., 'Fe': 1.8},
                   typical_CI_A2_wt_pct={'C': 1.2, 'Si': .3, 'Mn': 1.6, 'Ni': 54.6, 'Fe': 42.3},
                   source_DOI='10.2355/tetsutohagane.TETSU-2025-072',
                   scope='Typical deposit scenarios; 20% QT is an input, not predicted dilution. Fe-Ni-C omits Si/Mn and unreported constituents; equilibrium is not PMZ kinetics or strength.',
                   elapsed_s=time.perf_counter()-started,
                   first_interface_continuous_fusion_pass=False,
                   mechanical_capacity_assigned=False, thermal_tables_updated=False)
    (raw_out / 'phase-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
    audit_gibbs(raw_out, OUT / 'gibbs-checked')
    return OUT


if __name__ == '__main__':
    with threadpool_limits(limits=1):
        print(run())
