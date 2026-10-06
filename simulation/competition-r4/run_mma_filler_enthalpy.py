"""Product-specific Fe-Ni-C projection: hot-metal enthalpy and full melting.

Only the two undiluted deposited chemistries are evaluated. Si/Mn and coating
reactions remain outside this thermodynamic projection; no bead or PMZ assigned.
"""
from pathlib import Path
import csv
import json
import numpy as np
import yaml
from pycalphad import Database,equilibrium,variables as v
from threadpoolctl import threadpool_limits
from audit_fenic_gibbs import run as audit_gibbs
import xarray as xr

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'simulation/competition-r4/results/mma-filler-enthalpy-20261006'
MASS=np.array([12.011,55.847,58.690])


def run():
    if (OUT/'summary.json').exists():raise ValueError('Preserve the completed thermodynamic calculation')
    OUT.mkdir(parents=True,exist_ok=True)
    config=yaml.safe_load((ROOT/'project/independent-precoat-candidates.yaml').read_text(encoding='utf8'))
    db=Database(ROOT/'simulation/competition-r4/materials/Oikawa-2026-FeNiC.tdb')
    temperatures=np.unique(np.r_[25.,200.,300.,500.,800.,1000.,
                                  np.arange(1050.,1500.1,10.),1550.,1700.,2000.])
    raw=OUT/'raw';raw.mkdir(exist_ok=True)
    db_cases=[]
    for product,inp in config['candidates'].items():
        wt=np.array([inp['typical_deposit_wt_pct'][k] for k in ('C','Fe','Ni')])
        atomic=wt/MASS;atomic/=atomic.sum()
        for graphite,label in [(True,'graphite_allowed'),(False,'graphite_suppressed')]:
            phases=['LIQUID','FCC_A1','BCC_A2','CEMENTITE']+(['GRAPHITE'] if graphite else [])
            eq=equilibrium(db,['C','FE','NI','VA'],phases,
                {v.T:temperatures+273.15,v.P:101325,v.N:1,v.X('C'):atomic[0],v.X('NI'):atomic[2]},
                output=['HM'],calc_opts={'pdens':2000})
            eq.to_netcdf(raw/f'{product}-{label}.nc')
            print('raw thermodynamics',product,label,flush=True)
        db_cases.append(dict(name=product,ternary_normalized_wt_pct=dict(zip(['C','Fe','Ni'],(wt*100/wt.sum()).tolist())),
            limits={'graphite_allowed':{},'graphite_suppressed':{}}))
    (raw/'phase-summary.json').write_text(json.dumps({'cases':db_cases}),encoding='utf8')
    branch_audit=audit_gibbs(raw,OUT/'gibbs-checked')
    rows=[];cases=[]
    for product,inp in config['candidates'].items():
        composition=inp['typical_deposit_wt_pct']
        wt=np.array([composition[k] for k in ('C','Fe','Ni')])
        atomic=wt/MASS;atomic/=atomic.sum()
        mean_molar_mass_kg=float(atomic@MASS)/1000
        for graphite in (True,False):
            phases=['LIQUID','FCC_A1','BCC_A2','CEMENTITE']+(['GRAPHITE'] if graphite else [])
            label='graphite_allowed' if graphite else 'graphite_suppressed'
            eq=xr.load_dataset(OUT/'gibbs-checked'/f'{product}-{label}.nc')
            names=eq.Phase.values.squeeze();amount=eq.NP.values.squeeze();x=eq.X.values.squeeze()
            amount=np.nan_to_num(amount);x=np.nan_to_num(x)
            hm=eq.HM.values.squeeze()
            if not np.all(np.isfinite(hm)):raise RuntimeError('Non-finite calculated enthalpy')
            atomic_error=float(np.max(abs((amount[...,None]*x).sum(axis=-2)-atomic)))
            if atomic_error>1e-6:raise RuntimeError('Thermodynamic composition balance failed')
            phase_mass=amount*(x@MASS)/(atomic@MASS)
            liquid=np.where(names=='LIQUID',phase_mass,0).sum(axis=-1)
            h=(hm-hm[0])/mean_molar_mass_kg
            if np.min(np.diff(h))<-10:raise RuntimeError('Enthalpy is not monotone at the saved temperature points')
            full=np.flatnonzero(liquid>1-1e-6)
            if not len(full):raise RuntimeError('Complete liquid state missing from enthalpy grid')
            index=int(full[0])
            tests=[]
            for requested in [800000.,1000000.,1300000.]:
                t=float(np.interp(requested,h,temperatures))
                q=float(np.interp(t,temperatures,liquid))
                tests.append(dict(requested_delta_H_J_kg=requested,
                    interpolated_temperature_C=t,interpolated_liquid_mass_fraction=q,
                    complete_liquid_in_this_ternary_branch=q>=.999))
            case=dict(product=product,graphite_allowed=graphite,
                ternary_normalized_wt_pct=dict(zip(['C','Fe','Ni'],(wt*100/wt.sum()).tolist())),
                omitted_constituents_wt_pct=100-float(wt.sum()),mean_molar_mass_kg_mol=mean_molar_mass_kg,
                solid_reference='25 C equilibrium in the same stated phase collection',
                full_liquid_first_sample_C=float(temperatures[index]),
                full_liquid_delta_H_J_kg=float(h[index]),maximum_atomic_balance_error=atomic_error,
                current_engineering_enthalpy_checks=tests)
            cases.append(case)
            for t,value,q in zip(temperatures,h,liquid):
                rows.append(dict(product=product,graphite_allowed=graphite,T_C=float(t),
                    delta_H_J_kg=float(value),liquid_mass_fraction=float(q)))
            print(case,flush=True)
    with (OUT/'enthalpy.csv').open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=dict(source_DOI='10.2355/tetsutohagane.TETSU-2025-072',cases=cases,Gibbs_branch_audit=branch_audit,
        scope='Fe-Ni-C projection from undiluted typical deposited chemistry; 25 C equilibrium branch reference. Not actual coating chemistry, full Si/Mn alloy enthalpy, droplet measurement, transport dilution or welding qualification.',
        requires_full_melting_inlet_check=True,full_multicomponent_thermal_table_validated=False,
        first_interface_continuous_fusion_pass=False)
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    return summary


if __name__=='__main__':
    with threadpool_limits(limits=1):run()
