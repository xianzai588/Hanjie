"""Author-supplied Fe-Ni-C CALPHAD: binary reproduction and layer corners.

Si/Mn/etc are removed and the three retained masses renormalized explicitly.
Equilibrium and graphite-suppressed limits are not welding kinetics or strength.
"""
from pathlib import Path
import csv,json,time,importlib.util
import numpy as np
from pycalphad import Database,equilibrium,variables as v
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[2]
MASS=np.array([12.011,55.847,58.690])


def evaluate(db,wt,temperatures,graphite=True):
    if np.min(temperatures)<25:raise ValueError('temperature below TableS1 SGTE function validity')
    atomic=wt/MASS;atomic/=atomic.sum()
    phases=['LIQUID','FCC_A1','BCC_A2','CEMENTITE']+(['GRAPHITE'] if graphite else [])
    result=equilibrium(db,['C','FE','NI','VA'],phases,
        {v.T:temperatures+273.15,v.P:101325,v.N:1,v.X('NI'):atomic[2],v.X('C'):atomic[0]},calc_opts={'pdens':2000})
    names=result.Phase.values.squeeze();amount=result.NP.values.squeeze();composition=result.X.values.squeeze()
    amount=np.nan_to_num(amount);composition=np.nan_to_num(composition)
    if not np.all(np.isfinite(result.GM)):raise RuntimeError('non-finite CALPHAD equilibrium')
    error=float(np.max(abs((amount[...,None]*composition).sum(axis=-2)-atomic)))
    total_error=float(np.max(abs(amount.sum(axis=-1)-1)))
    if max(error,total_error)>1e-6:raise RuntimeError('CALPHAD phase mass conservation failed')
    mean_mass=composition@MASS;weight=amount*mean_mass/(atomic@MASS)
    fractions={phase:np.where(names==phase,weight,0).sum(axis=-1) for phase in phases}
    # Liquid onset/completion are bracketing grid intervals, not invented exact roots.
    q=fractions['LIQUID'];on=np.flatnonzero(q>1e-6);full=np.flatnonzero(q>1-1e-6)
    def bracket(indices):
        if not len(indices):return None
        k=int(indices[0]);return [float(temperatures[max(0,k-1)]),float(temperatures[k])]
    return result,fractions,dict(maximum_atomic_balance_error=error,maximum_phase_sum_error=total_error,
        solidus_grid_bracket_C=bracket(on),liquidus_grid_bracket_C=bracket(full))


def run():
    out=ROOT/'simulation/competition-r4/results/FeNiC-2026-layer-corners-25C';out.mkdir(exist_ok=True)
    db=Database(ROOT/'simulation/competition-r4/materials/Oikawa-2026-FeNiC.tdb');started=time.perf_counter()
    # Binary carbon-free validation uses the author's actual six DSC compositions.
    ni=np.array([9.85,19.74,39.61,59.61,79.74,89.85]);xm=ni/58.690/(ni/58.690+(100-ni)/55.847)
    temperature=np.arange(1400.,1530.01,.25)
    result=equilibrium(db,['FE','NI','VA'],['LIQUID','FCC_A1','BCC_A2'],
        {v.T:temperature+273.15,v.P:101325,v.N:1,v.X('NI'):xm},calc_opts={'pdens':2000})
    phase=result.Phase.values.squeeze();amount=result.NP.values.squeeze()
    q=np.where(phase=='LIQUID',amount,0).sum(axis=-1);binary=[]
    for j,(ts,tl) in enumerate(zip([1498,1479,1445,1437,1443,1448],[1504,1489,1452,1439,1445,1450])):
        a=np.flatnonzero(q[:,j]>1e-6);b=np.flatnonzero(q[:,j]>1-1e-6)
        if not len(a) or not len(b):raise RuntimeError('binary transition outside validation temperature grid')
        calc_ts=float(temperature[a[0]]);calc_tl=float(temperature[b[0]])
        binary.append(dict(Ni_wt_pct=float(ni[j]),literature_DSC_solidus_C=ts,literature_DSC_liquidus_C=tl,
            calculated_solidus_grid_C=calc_ts,calculated_liquidus_grid_C=calc_tl,
            solidus_difference_C=calc_ts-ts,liquidus_difference_C=calc_tl-tl))
    result.to_netcdf(out/'binary-equilibrium.nc')
    spec=importlib.util.spec_from_file_location('layer_compositions',ROOT/'studies/SCHAEFFLER-MAP/run.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    selected=[row for row in module.transition_cases() if row['meets_selected_dilution_envelope']]
    cases=[]
    for key,name in [('first_composition_wt_pct','first'),('second_composition_wt_pct','second'),('final_composition_wt_pct','final')]:
        for label,fn in [('min_C',min),('max_C',max)]:
            row=fn(selected,key=lambda row:row[key]['C']);c=row[key]
            fe=100-sum(c.values());wt=np.array([c['C'],fe,c['Ni']]);retained=float(wt.sum());wt*=100/retained
            cases.append(dict(name=name+'_'+label,full_composition_wt_pct=dict(c,Fe=fe),
                omitted_constituents_wt_pct=100-retained,ternary_normalized_wt_pct=dict(zip(['C','Fe','Ni'],wt.tolist())),
                dilution={k:row[k] for k in ['first_QT_dilution','second_first_layer_remelt','final_Ni_layer_dilution','final_steel_dilution']}))
    rows=[]
    temperature=np.r_[25.,100.,300.,500.,700.,900.,1100.,np.arange(1200.,1510.01,2.)]
    for case in cases:
        wt=np.array([case['ternary_normalized_wt_pct'][k] for k in ['C','Fe','Ni']]);case['limits']={}
        for graphite,name in [(True,'graphite_allowed'),(False,'graphite_suppressed')]:
            eq,fractions,audit=evaluate(db,wt,temperature,graphite)
            eq.to_netcdf(out/(case['name']+'-'+name+'.nc'));case['limits'][name]=audit
            for k,T in enumerate(temperature):
                rows.append(dict(case=case['name'],limit=name,T_C=float(T),
                    **{phase+'_mass_fraction':float(fractions.get(phase,np.zeros(len(temperature)))[k]) for phase in ['LIQUID','FCC_A1','BCC_A2','CEMENTITE','GRAPHITE']}))
            print(case['name'],name,audit,flush=True)
    with (out/'phase-fractions.csv').open('w',newline='',encoding='utf8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=dict(source_DOI='10.2355/tetsutohagane.TETSU-2025-072',engine='pycalphad',binary_validation=binary,
        maximum_binary_transition_difference_C=max(abs(row[key]) for row in binary for key in ['solidus_difference_C','liquidus_difference_C']),
        cases=cases,elapsed_s=time.perf_counter()-started,
        scope='Fe-Ni-C ternary equilibrium and graphite-suppressed limits; no Si/Mn kinetics, Scheil path, PMZ spatial state or fracture capacity',
        mechanical_capacity_assigned=False,thermal_tables_updated=False)
    (out/'phase-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    return summary


if __name__=='__main__':
    with threadpool_limits(limits=1):result=run()
    print(json.dumps({key:result[key] for key in ['maximum_binary_transition_difference_C','elapsed_s','scope']},indent=2))
