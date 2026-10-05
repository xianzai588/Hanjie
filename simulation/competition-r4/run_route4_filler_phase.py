"""Small fixed composition comparison for the independent SMAW fallback.

Target dilution scenarios are inputs; no composition is inferred from heat.
"""
from pathlib import Path
import csv,json,time,argparse
import numpy as np
from pycalphad import Database
from threadpoolctl import threadpool_limits
from run_fenic_phase import evaluate

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'simulation/competition-r4/results/route4-filler-phase-fullchem'


def run(out=OUT):
    global OUT
    OUT=out
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'phase-summary.json').exists():raise ValueError('preserve completed phase evidence')
    db=Database(ROOT/'simulation/competition-r4/materials/Oikawa-2026-FeNiC.tdb')
    temperature=np.r_[25.,350.,500.,np.arange(1100.,1510.1,10.)]
    fillers={'bare_Ni99':np.array([.01,.15,99.62]),
             'Pascual2009_Ni97p6':np.array([.30,1.,97.6]),
             'RepTecCast1_typical':np.array([.7,2.,97.])}
    # Full nominal chemistry sets the iron balance before dropping other elements.
    # bare Ni99 additionally has Si0.05/Mn0.17; QT has Si/Mn/Mg/P/S/Cr.
    QT=np.array([3.65,93.25,.05])
    rows=[];summaries=[];start=time.perf_counter()
    for name,filler in fillers.items():
        for dilution in [0.,.20]:
            raw=(1-dilution)*filler+dilution*QT;wt=100*raw/raw.sum()
            scenario=name+'-QT'+str(int(100*dilution));limits={};energies={}
            for graphite,label in [(False,'graphite_suppressed'),(True,'graphite_allowed')]:
                eq,fractions,audit=evaluate(db,wt,temperature,graphite)
                eq.to_netcdf(OUT/(scenario+'-'+label+'.nc'));energies[label]=eq.GM.values.squeeze()
                limits[label]=audit
                for k,T in enumerate(temperature):
                    rows.append(dict(case=scenario,limit=label,T_C=float(T),Gibbs_J_mol=float(energies[label][k]),
                        **{p+'_mass_fraction':float(fractions.get(p,np.zeros(len(temperature)))[k]) for p in ['LIQUID','FCC_A1','BCC_A2','CEMENTITE','GRAPHITE']}))
                print(scenario,label,audit,flush=True)
            nested=energies['graphite_allowed']-energies['graphite_suppressed']
            summaries.append(dict(name=scenario,input_QT_mass_fraction=dilution,ternary_normalized_wt_pct=dict(zip(['C','Fe','Ni'],wt.tolist())),
                omitted_mass_wt_pct=float(100-raw.sum()),limits=limits,
                nested_Gibbs_positive_gap_max_J_mol=float(np.maximum(nested,0).max()),
                nested_phase_feasibility_pass=bool(nested.max()<=1e-4)))
    with (OUT/'phase-fractions.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    out=dict(cases=summaries,elapsed_s=time.perf_counter()-start,source_DOI='10.2355/tetsutohagane.TETSU-2025-072',
        scope='fixed FeNiC equilibrium scenarios,10C high-temperature brackets; omitted SiMn and kinetics, no QT/PMZ capacity, no transport dilution',
        product_note='RepTec2024 sheet contains polarity and carbon-limit contradictions; typical composition used only for comparison, not production specification',
        thermal_inputs_updated=False,mechanical_capacity_assigned=False)
    (OUT/'phase-summary.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=OUT)
    with threadpool_limits(limits=1):print(json.dumps(run(p.parse_args().output),indent=2))
