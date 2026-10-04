"""Recover warm pad reactions where saved neighbouring QT cells stayed elastic.

This is postprocessing of the actual run, not a second mechanics solution.
Float32 snapshots are used only to check the sign and load scale of reactions.
"""
from pathlib import Path
import json
import numpy as np
from run_verified import operators

OUT=Path(__file__).parent/'results'


def audit(name):
    folder=OUT/name
    f=np.load(folder/'fields.npz');inp=json.loads((folder/'input.json').read_text())
    x,e,m=f['x'],f['e'],f['material']
    qt=np.unique(e[m==1]);lower=qt[abs(x[qt,2]-100)<1e-4]
    nodes=np.array([lower[np.argmin(np.linalg.norm(x[lower,:2]-[30*np.cos(a),30*np.sin(a)],axis=1))] for a in (0,2*np.pi/3,4*np.pi/3)])
    selected=np.flatnonzero(np.any(np.isin(e,nodes),axis=1))
    assert np.all(m[selected]==1)
    maximum_plastic=float(f['eqp'][selected].max());maximum_peak=float(f['peak_temperature'][selected].max())
    base=dict(case=name,support_nodes=nodes.tolist(),actual_support_coordinates_mm=x[nodes].tolist(),
        adjacent_maximum_eqp=maximum_plastic,adjacent_maximum_peak_C=maximum_peak,
        elastic_history_recovery_applicable=bool(maximum_plastic<1e-14 and maximum_peak<1200))
    if not base['elastic_history_recovery_applicable']:return base
    _,vol,b,dof=operators(x,e[selected])
    pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3
    tab=inp['materials'][1]['temperature_dependent'];knots=np.array(tab['temperatures_c']);alpha=np.array(tab['alpha_per_k'])
    prefix=np.r_[0,np.cumsum(np.diff(knots)*(alpha[1:]+alpha[:-1])/2)]
    hist=np.loadtxt(folder/'equilibrium-history.csv',delimiter=',',skiprows=1)[9::10]
    ts=f['temperature_snapshots'];us=f['displacement_snapshots']
    assert len(hist)==len(ts)==len(us)
    rows=[]
    for entry,T,U in zip(hist,ts,us):
        if entry[4]:continue
        T=T[selected].astype(float);pos=np.clip(np.searchsorted(knots,T,side='right')-1,0,len(knots)-2)
        delta=T-knots[pos];al=prefix[pos]+alpha[pos]*delta+.5*(alpha[pos+1]-alpha[pos])/(knots[pos+1]-knots[pos])*delta**2
        E=np.interp(T,knots,tab['elastic_modulus_gpa'])*1000;nu=inp['materials'][1]['nominal_properties_20c']['poisson_ratio']
        strain=np.einsum('eij,ej->ei',b,U[dof].astype(float));strain[:,:3]-=al[:,None]
        stress=2*(E/(2*(1+nu)))[:,None]*(strain-strain@pv)+3*(E/(3*(1-2*nu)))[:,None]*(strain@pv)
        local=np.einsum('eji,ej,e->ei',b,stress,vol)
        force=np.bincount(dof.ravel(),weights=local.ravel(),minlength=3*len(x))
        rows.append(dict(t_s=float(entry[0]),upward_pad_reaction_N=force[3*nodes+2].tolist()))
    reaction=np.array([r['upward_pad_reaction_N'] for r in rows])
    base.update(minimum_upward_pad_reaction_N=float(reaction.min()),maximum_upward_pad_reaction_N=float(reaction.max()),
        tensile_reaction_detected=bool(reaction.min()<-.1),records=rows,
        scope='elastic adjacent cells, no annealing, saved Float32 warm snapshots; signs below -0.1 N flag a bilateral ideal-support assumption to revisit')
    return base


if __name__=='__main__':
    result=audit('8p-birthpatch-h20-dt025-s05')
    path=Path('output/review/warm-pad-reaction-audit.json')
    path.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
