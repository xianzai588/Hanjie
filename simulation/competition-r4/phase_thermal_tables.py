"""Use the actual author-TDB liquid fractions for thermal corner calculations.

The corner envelope varies each layer's permitted composition independently.
It is not a single chemical trajectory, a Scheil calculation or PMZ capacity.
"""
from pathlib import Path
import copy,csv,json

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'simulation/competition-r4/results/FeNiC-2026-layer-corners-gibbs-checked'


def overrides(tables,carbon_corner,graphite_limit,temperature_shift=0.):
    summary=json.loads((SOURCE/'phase-summary.json').read_text(encoding='utf8'))
    if not summary['Gibbs_branch_audit']['nested_phase_feasibility_pass']:
        raise ValueError('source liquid fractions failed nested Gibbs feasibility')
    rows=list(csv.DictReader((SOURCE/'phase-fractions.csv').open(encoding='utf8')))
    result={}
    for index,label in [(2,'final'),(3,'first'),(4,'second')]:
        name=label+'_'+carbon_corner
        case=next(row for row in summary['cases'] if row['name']==name)
        selected=[row for row in rows if row['case']==name and row['limit']==graphite_limit]
        T=[float(row['T_C'])+temperature_shift for row in selected]
        liquid=[float(row['LIQUID_mass_fraction']) for row in selected]
        onset=next(k for k,value in enumerate(liquid) if value>1e-6)
        completion=next(k for k,value in enumerate(liquid) if value>1-1e-6)
        if onset==0:raise ValueError('unbracketed melting onset')
        table=copy.deepcopy(tables[index]);fusion=table['fusion_enthalpy']
        # Upper onset bracket for fusion detection, lower bracket for depth.
        # Actual curve, including solver roundoff, is retained without smoothing.
        fusion.update(solidus_C=T[onset],remelt_solidus_C=T[onset-1],liquidus_C=T[completion],
            liquid_fraction_curve=dict(temperature_C=T,liquid_mass_fraction=liquid),
            basis='author Fe-Ni-C TDB, actual mass-balanced Gibbs-checked equilibrium liquid fractions; latent heat magnitude remains an engineering input',
            phase_source=dict(DOI=summary['source_DOI'],case=name,graphite_limit=graphite_limit,
                temperature_shift_C=temperature_shift,ternary_normalized_wt_pct=case['ternary_normalized_wt_pct'],
                omitted_constituents_wt_pct=case['omitted_constituents_wt_pct'],
                first_liquid_bracket_C=[T[onset-1],T[onset]],full_liquid_bracket_C=[T[completion-1],T[completion]],
                thermal_scope='independent layer composition envelope; missing Si/Mn and kinetics not bounded by binary reproduction error',
                mechanical_capacity_assigned=False))
        result[index]=table
    return result
