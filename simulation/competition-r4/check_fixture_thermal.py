"""Refine the fixture domain under actual recorded part boundary histories.

The boundary is the computed part temperature/displacement, not synthetic
experimental data. Baseline replay must reproduce the coupled calculation
before a refined thermal network is compared. This checks the fixture domain;
part mesh/time convergence is checked separately by postprocess.py.
"""
from pathlib import Path
import argparse,json
import numpy as np
import yaml
from scipy.sparse import diags
from scipy.sparse.linalg import spsolve
from fixture_thermal import FixtureThermal
from pad_contact import PadContact

OUT=Path(__file__).parent/'results'

def evaluate(case):
    folder=OUT/case
    inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    source=inp.get('fixture_thermal')
    if not source or not (folder/'fixture-boundary-trace.npz').exists():
        raise ValueError('completed actual fixture boundary trace required')
    if inp.get('fixture_thermal_coupling_policy')!='previous converged displacement and gap; current implicit part temperature':
        raise ValueError('actual displacement-feedback boundary required')
    mesh=np.load(folder/'mesh.npz');record=np.load(folder/'fixture-boundary-trace.npz')
    x=mesh['x'];bore=record['bore'];nodes=record['boundary_nodes'];trace=record['trace'];nb=len(nodes)
    pads=PadContact(x,mesh['boundary'])
    h=source['contact_conductance_W_m2K'];ref=source['axial_refinement']
    models=[FixtureThermal(x,bore,record['bore_area'],h,r,pads) for r in (ref,ref*2)]
    if models[0].audit!=source:raise ValueError('fixture source model differs; preserve/replay its declared model version')
    assert all(np.array_equal(m.boundary_nodes,nodes) for m in models)
    normals=x[bore,:2]/np.linalg.norm(x[bore,:2],axis=1)[:,None]
    histories=[[],[]];growth_errors=[];flux_errors=[];pad_spreads=[[],[]]
    for row in trace:
        t,dt,released=row[:3]
        if dt==0:
            for hist,m in zip(histories,models):hist.append([t,m.temperature.max(),m.offset().min(),m.offset().max()])
            continue
        old=np.full(len(x),20.);current=old.copy();u=np.zeros(3*len(x))
        old[nodes]=row[3:3+nb];current[nodes]=row[3+nb:3+2*nb]
        u.reshape(-1,3)[nodes,2]=row[3+2*nb:3+3*nb]
        radial=row[3+3*nb:];u.reshape(-1,3)[bore,:2]=radial[:,None]*normals
        flux=[]
        for index,(hist,m) in enumerate(zip(histories,models)):
            gap=radial-float(record['initial_intrusion_mm'])-m.offset()
            M,part_diag,tool_diag=m.coupling(len(x),gap,bool(released),u,old)
            A=diags(m.capacity+dt*(m.external+tool_diag))+dt*m.conduction
            rhs=m.capacity*m.temperature+dt*(m.external*20+M.T@current)
            temperature=spsolve(A.tocsc(),rhs)
            if np.linalg.norm(A@temperature-rhs)>1e-7:raise RuntimeError('fixture replay heat balance failed')
            m.temperature=temperature
            if not released:pad_spreads[index].append(float(np.ptp(m.pad_offset())))
            hist.append([t,temperature.max(),m.offset().min(),m.offset().max()])
            flux.append(float(tool_diag@temperature-np.asarray(M.T@current).sum()))
        if not released:
            growth_errors.append(float(np.max(abs(models[0].offset()-models[1].offset()))))
            flux_errors.append(abs(flux[0]-flux[1]))
    actual=np.loadtxt(folder/'fixture-thermal-history.csv',delimiter=',',skiprows=1)
    a,b=map(np.asarray,histories)
    reproduction=float(np.max(abs(a[:,1]-actual[:,1])))
    reproduction_growth=float(np.max(abs(a[:,2:4]-actual[:,2:4])))
    amplitude=float(abs(a[:,2:4]).max())
    meaningful_response=amplitude>=1e-8
    relative=max(growth_errors)/amplitude if meaningful_response else None
    spec=yaml.safe_load((OUT.parents[2]/'project/competition-design.yaml').read_text(encoding='utf8'))
    precision=spec['precision']
    support_spread=max(max(s,default=0.) for s in pad_spreads)
    support_combined=support_spread+precision['support_manufacturing_height_spread_limit_mm']
    result=dict(source_case=case,scope='fixture-domain axial and angular refinement under the same actual part temperature/displacement boundary; part discretization checked separately',
        baseline_refinement=ref,fine_refinement=ref*2,baseline_angular_sectors=models[0].sectors,fine_angular_sectors=models[1].sectors,
        baseline_temperature_reproduction_error_C=float(reproduction),baseline_growth_reproduction_error_mm=reproduction_growth,
        maximum_radial_growth_difference_mm=max(growth_errors),maximum_radial_growth_response_mm=amplitude,
        meaningful_growth_response=meaningful_response,relative_growth_error=relative,
        maximum_part_to_tool_heat_flux_difference_W=max(flux_errors),relative_precision_limit=.05,
        maximum_support_thermal_height_spread_mm=support_spread,
        support_manufacturing_height_spread_mm=precision['support_manufacturing_height_spread_limit_mm'],
        combined_support_height_spread_mm=support_combined,
        support_thermal_height_budget_pass=support_combined<=precision['support_height_spread_limit_mm'],
        fixture_thermal_discretization_pass=bool(reproduction<=1e-4 and reproduction_growth<=1e-8 and meaningful_response and relative<=.05))
    target=folder/'fixture-thermal-network-convergence.json'
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    np.savetxt(folder/'fixture-network-refinement-history.csv',np.c_[a,b[:,1:]],delimiter=',',
        header='t_s,baseline_max_C,baseline_min_growth_mm,baseline_max_growth_mm,fine_max_C,fine_min_growth_mm,fine_max_growth_mm',comments='')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);a=p.parse_args();evaluate(a.case)
