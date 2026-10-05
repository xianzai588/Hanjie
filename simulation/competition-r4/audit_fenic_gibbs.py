"""Check nested feasible phase sets and replace higher-energy branch solutions.

The graphite-suppressed solution is feasible in the graphite-allowed problem.
Replacement is an independently solved lower-energy state, never curve smoothing.
"""
from pathlib import Path
import csv,json,shutil,argparse
import numpy as np
import xarray as xr
from pycalphad import Database,calculate
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[2]


def run(source=None,out=None):
    source=source or ROOT/'simulation/competition-r4/results/FeNiC-2026-layer-corners-25C'
    out=out or source.with_name('FeNiC-2026-layer-corners-gibbs-checked');out.mkdir(exist_ok=True)
    db=Database(ROOT/'simulation/competition-r4/materials/Oikawa-2026-FeNiC.tdb')
    summary=json.loads((source/'phase-summary.json').read_text());witness=[];rows=[];nested_excess=[]
    masses=np.array([12.011,55.847,58.690])
    for case in summary['cases']:
        name=case['name'];allowed=xr.load_dataset(source/(name+'-graphite_allowed.nc'))
        suppressed=xr.load_dataset(source/(name+'-graphite_suppressed.nc'))
        excess=(allowed.GM-suppressed.GM).values.ravel()
        for index in np.flatnonzero(excess>1e-4):
            T=float(allowed.T.values[index]);mu=suppressed.MU.sel(T=T).values.ravel();checks={}
            if list(suppressed.component.values)!=['C','FE','NI']:raise RuntimeError('unexpected component order')
            for phase in db.phases:
                points=calculate(db,['C','FE','NI','VA'],[phase],T=T,P=101325,output='GM',pdens=8000)
                tangent=points.GM.values.ravel()-points.X.values.reshape(-1,3)@mu
                checks[phase]=dict(minimum_sampled_tangent_plane_distance_J_mol=float(np.nanmin(tangent)),samples=len(tangent))
            if min(row['minimum_sampled_tangent_plane_distance_J_mol'] for row in checks.values())<-.001:
                raise RuntimeError('lower-energy candidate still has a negative sampled phase driving force')
            witness.append(dict(case=name,T_C=T-273.15,original_higher_Gibbs_energy_J_mol=float(excess[index]),
                selected_source=name+'-graphite_suppressed.nc',sampled_phase_stability=checks))
            for key in allowed.data_vars:
                if 'T' in allowed[key].dims:allowed[key].loc[dict(T=T)]=suppressed[key].sel(T=T)
        if np.max((allowed.GM-suppressed.GM).values)>1e-4:raise RuntimeError('nested Gibbs feasibility still violated')
        nested_excess.append(float(np.max((allowed.GM-suppressed.GM).values)))
        for limit,data in [('graphite_allowed',allowed),('graphite_suppressed',suppressed)]:
            data.to_netcdf(out/(name+'-'+limit+'.nc'))
            phase=data.Phase.values.squeeze();amount=np.nan_to_num(data.NP.values.squeeze());composition=np.nan_to_num(data.X.values.squeeze())
            composition_wt=np.array([case['ternary_normalized_wt_pct'][key] for key in ['C','Fe','Ni']]);atomic=composition_wt/masses;atomic/=atomic.sum()
            weight=amount*(composition@masses)/(atomic@masses)
            q=np.where(phase=='LIQUID',weight,0).sum(axis=-1)
            temperature=data.T.values-273.15
            for key,indices in [('solidus_grid_bracket_C',np.flatnonzero(q>1e-6)),('liquidus_grid_bracket_C',np.flatnonzero(q>1-1e-6))]:
                k=int(indices[0]) if len(indices) else None
                case['limits'][limit][key]=[float(temperature[max(0,k-1)]),float(temperature[k])] if k is not None else None
            for index,T in enumerate(data.T.values):
                rows.append(dict(case=name,limit=limit,T_C=float(T-273.15),
                    **{p+'_mass_fraction':float(np.where(phase[index]==p,weight[index],0).sum()) for p in ['LIQUID','FCC_A1','BCC_A2','CEMENTITE','GRAPHITE']}))
    with (out/'phase-fractions.csv').open('w',newline='',encoding='utf8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    audit=dict(replaced_higher_energy_states=witness,source_directory=str(source),
        maximum_corrected_nested_Gibbs_excess_J_mol=max(nested_excess),
        nested_phase_feasibility_pass=bool(max(nested_excess)<=1e-4 and all(
            min(row['minimum_sampled_tangent_plane_distance_J_mol'] for row in item['sampled_phase_stability'].values())>=-.001 for item in witness)),
        scope='same actual composition and temperature; independently converged lower-energy subset state; graphite exact and all phases sampled tangent-plane checks, not a proof over every continuous site fraction')
    summary['Gibbs_branch_audit']=audit
    for case in summary['cases']:
        # Retain the original branch gap while recording the actually selected result.
        case['nested_phase_feasibility_pass']=audit['nested_phase_feasibility_pass']
    (out/'phase-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    (out/'Gibbs-branch-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
    if (source/'binary-equilibrium.nc').exists():shutil.copyfile(source/'binary-equilibrium.nc',out/'binary-equilibrium.nc')
    return audit


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args()
    with threadpool_limits(limits=1):print(json.dumps(run(a.source,a.output),indent=2))
