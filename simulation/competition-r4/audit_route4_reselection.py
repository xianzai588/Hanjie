"""Read saved fields: threshold sensitivity and implementable energy accounting.

No actual dilution, PMZ capacity or complete manufacturing state is assigned.
"""
from pathlib import Path
import csv,json
import numpy as np
from visible_surface_flux import load

ROOT=Path(__file__).resolve().parents[2]
RESULTS=ROOT/'simulation/competition-r4/results'
OUT=RESULTS/'route4-reselection'


def thermal_ledger(case):
    inp=json.loads((case/'input.json').read_text(encoding='utf8'))
    path=case/('failure.json' if (case/'failure.json').exists() else 'result.json')
    res=json.loads(path.read_text(encoding='utf8'))
    h=np.loadtxt(case/'source-partition-history.csv',delimiter=',',skiprows=1,ndmin=2)
    history=np.loadtxt(case/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
    with np.load(case/'thermal-fields.npz',allow_pickle=False) as f:
        x,e,m=f['x'],f['e'],f['material'];fa=f['interface_nodes'];area=f['interface_area_mm2'];peak=f['interface_peak_C']
        v=f['volume_mm3'];active=f['thermal_active'];qp=f['peak_element_quadrature_C']
    bary=np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
    xyz=np.einsum('qj,fjk->fqk',bary,x[fa]);radius=np.linalg.norm(xyz[:,:,:2],axis=2)
    arc=74.98*np.arctan2(xyz[:,:,1],xyz[:,:,0]);floor=x[np.unique(e[m==3]),2].min()
    # Match actual born coating faces, rather than count uncoated future tracks.
    born_faces={tuple(sorted(tet[list(idx)])) for tet in e[(m==3)&active]
                for idx in [(0,1,2),(0,1,3),(0,2,3),(1,2,3)]}
    deposited=np.array([tuple(sorted(row)) in born_faces for row in fa])
    selected=(abs(xyz[:,:,2]-floor)<1e-5)&(radius>=72.2)&(abs(arc)<=9)&deposited[:,None]
    weights=np.broadcast_to(area[:,None]/3,peak.shape)
    thresholds=[1232.,1234.,1300.,1348.,1353.5,1359.,1450.85,1454.85,1458.85]
    response=[dict(threshold_C=t,root_area_mm2=float(weights[selected&(peak>=t)].sum())) for t in thresholds]
    full_volume=float(v[(m==3)&active].sum())
    command=float(h[:,5].sum());wire=float(h[:,4].sum());intercept=float(h[:,6].sum());missed=float(h[:,7].sum())
    arc_time=float(h[:,1].sum());ni_rho=inp['materials'][3]['nominal_properties_20c']['density_kg_m3']
    mass=full_volume*ni_rho*1e-9
    wire_cross=np.pi*1.2**2/4
    feed=[mass/(8890e-9*wire_cross*eta*arc_time) for eta in [.98,.90]]
    qt=inp['materials'][1];qt_rho=qt['nominal_properties_20c']['density_kg_m3']*1e-9
    v_any=float((v[m==1,None]/4*(qp[m==1]>=qt['fusion_enthalpy']['solidus_C'])).sum())
    v_full=float((v[m==1,None]/4*(qp[m==1]>=qt['fusion_enthalpy']['liquidus_C'])).sum())
    dilution=[q*qt_rho/(mass+q*qt_rho) for q in [v_full,v_any]]
    curve=qt['temperature_dependent'];target=float(inp['cold_start_C'])
    knots=np.asarray(curve['temperatures_c']);cp=np.asarray(curve['specific_heat_j_kgk'])
    temp=np.unique(np.r_[20.,knots[(knots>20)&(knots<target)],target])
    preheat=inp['QT_volume_mm3']*qt_rho*np.trapezoid(np.interp(temp,knots,cp),temp)
    return dict(case=case.name,result_source=path.name,partial=res['partial'],error=res.get('error'),
        initial_QT_C=target,QT_peak_C=res['maximum_QT_C'],metal_peak_C=res['maximum_temperature_C'],
        end_s=res['time_s'],arc_s=arc_time,preheat_stored_sensible_J=float(preheat),
        modeled_born_volume_mm3=full_volume,modeled_born_mass_kg=mass,
        source_command_J=command,wire_entering_J=wire,intercepted_surface_J=intercept,uncaptured_J=missed,
        source_partition_error_J=command-wire-intercept-missed,
        maximum_step_energy_balance_error_J=float(abs(history[:,10]).max()),
        average_equivalent_wire_feed_mm_s_eta098_to090=feed,
        maximum_instantaneous_wire_power_W=float((h[:,4]/h[:,1]).max()),
        steady_GTAW_equivalent_I_A_at_12V_eta055=inp['arc_power_W']/(12*.55),
        Gaussian95pct_diameter_mm=2*inp['source_width_mm']*float(np.sqrt(-np.log(.05))),
        deposited_root_area_mm2=float(weights[selected].sum()),
        minimum_deposited_root_point_peak_C=float(peak[selected].min()),threshold_response=response,
        QT_liquid_union_mm3=[v_full,v_any],conditional_union_complete_mixing_QT_mass_fraction=dilution,
        actual_transport_dilution_computed=False,thermal_property_envelope_verified=False,
        phase_and_contour_note='phase composition, liquid k and deposited contour are input scenarios, not solved dilution or calibrated footprint')


def source_controls():
    # Analytic two stacked plates over the exact same planar projection.
    x=np.array([[-10,-10,0],[10,-10,0],[10,10,0],[-10,10,0],
                [-10,-10,1],[10,-10,1],[10,10,1],[-10,10,1]],float)
    faces=np.array([[0,1,2],[0,2,3],[4,5,6],[4,6,7]])
    xyz=x[faces];owner=np.array([0,0,1,1]);projected=np.full(4,200.);wet=np.ones(4,bool)
    rows=[]
    for step in [.1,.05]:
        for z in [-100.,100.]:
            q,per,diag=load(x,faces,xyz,owner,projected,wet,[.2,.3,z],1.4,100.,step)
            rows.append(dict(step_mm=step,source_z_mm=z,total_W=float(q.sum()),lower_W=float(per[0]),upper_W=float(per[1]),q=q.tolist()))
    return dict(controls=rows,maximum_source_z_response_W=max(abs(np.array(rows[i]['q'])-np.array(rows[i+1]['q'])).max() for i in [0,2]),
        sampling_response_difference=abs(rows[0]['total_W']-rows[2]['total_W'])/rows[2]['total_W'],
        scope='shadowing/planar source invariant only; not FE field or welding-footprint qualification')


def fallback_budget():
    g=json.loads((ROOT/'simulation/competition-r4/geometry/explicit-ni99-wing-t14-first07-h15-lh05/geometry-audit.json').read_text())
    full_area=g['expected_Ni99_volume_mm3']/g['total_layer_mm']
    stock_volume=full_area*1.70 # maximum1.60mm pocket plus required0.10mm contour overfill
    mass=stock_volume*8890e-9
    return dict(route='independent Ni SMAW prebutter before final bore machining',
        surface_area_mm2=full_area,nominal_stock_height_mm=1.70,pure_Ni_stock_mass_kg=mass,
        minimum_rod_core_length_mm_at_d2p5_eta1=mass/(8890e-9*np.pi*2.5**2/4),
        rod_count_lower_bound_at_250mm_usable_core=int(np.ceil(mass/(8890e-9*np.pi*2.5**2/4*250))),
        mass_scope='100% pure-Ni core recovery theoretical minimum, not electrode consumption or deposition-rate claim; actual loss and alloy composition required',
        preheat_candidate_C=350.,preheat_source='Pascual2009 SMAW ductile iron350C; not currentQT450/rod product qualification',
        available_product_current_A=[50,100],available_product_diameter_mm=2.5,
        product_composition_note='RepTec Cast1 Ni97/C0.7/Fe2 differs from bare Ni99 C0.01 and Pascual97.6Ni/C0.30; must rerun phase/PMZ evidence, cannot inherit old ternary corner',
        unresolved_inputs=['selected electrode composition and applicable hot-preheat guidance',
            'actual deposition contour, arc voltage/travel and heat-transfer bounds',
            'QT/first-Ni PMZ normal/shear/cyclic capacity for stated microstructure and defect class'],
        effective_connection_certified=False)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    names=['ni99-physics-L350-v6-3strip-ramp05-f20-visible-q01',
           'route4-P20-Ni0-GTAW-equivalent-first','route4-P150-Ni0-GTAW-equivalent-first','route4-P350-Ni0-GTAW-equivalent-first',
           'route4-P350-Ni0-GTAW-equivalent-first-dt0125-q005']
    rows=[]
    for name in names:
        case=RESULTS/name
        path=case/('failure.json' if (case/'failure.json').exists() else 'result.json')
        if not path.exists():continue
        state=json.loads(path.read_text(encoding='utf8'))
        if state.get('error') or len(state.get('stages',[]))>=1:rows.append(thermal_ledger(case))
    old=json.loads((RESULTS/'design-repair-status-20261005.json').read_text())
    fine=next(r for r in old['records'] if r['case']=='8p-thermal-tool-bore008-h1125-dt025-s05')
    budget=28+2+6.5+fine['position_mm']*1000
    result=dict(cases=rows,source_controls=source_controls(),fallback_budget=fallback_budget(),
        old_worst_position_budget_um=budget,position_limit_um=50.,old_family_accepted=old['accepted_design'],
        complete_joint_process_adopted=False,
        decision='Local thermal/preheat comparison; full-chain use requires continuous effective connection and applicable PMZ capacity; no acceptance flags overridden')
    nominal=next((r for r in rows if r['case']=='route4-P350-Ni0-GTAW-equivalent-first'),None)
    refined=next((r for r in rows if r['case']=='route4-P350-Ni0-GTAW-equivalent-first-dt0125-q005'),None)
    if nominal and refined:
        selected=lambda r:next(t['root_area_mm2'] for t in r['threshold_response'] if t['threshold_C']==1450.85)
        result['joint_time_source_refinement']={key:abs(a-b)/max(abs(a),abs(b),1e-12) for key,a,b in [
            ('QT_peak_relative_difference',nominal['QT_peak_C'],refined['QT_peak_C']),
            ('metal_peak_relative_difference',nominal['metal_peak_C'],refined['metal_peak_C']),
            ('fusion_area_relative_difference',selected(nominal),selected(refined)),
            ('coldest_root_point_relative_difference',nominal['minimum_deposited_root_point_peak_C'],refined['minimum_deposited_root_point_peak_C'])]}
        result['joint_time_source_refinement']['scope']='combined dt/2 and source-plane step/2; not independent spatial convergence or separate time/source validation'
    (OUT/'route4-audit.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    flat=[dict(case=r['case'],threshold_C=t['threshold_C'],root_area_mm2=t['root_area_mm2']) for r in rows for t in r['threshold_response']]
    with (OUT/'threshold-response.csv').open('w',encoding='utf8',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=['case','threshold_C','root_area_mm2']);w.writeheader();w.writerows(flat)
    print(json.dumps({k:result[k] for k in ['old_worst_position_budget_um','source_controls','fallback_budget']},indent=2))
    print(json.dumps([dict(case=r['case'],QT=r['QT_peak_C'],metal=r['metal_peak_C'],area=r['deposited_root_area_mm2'],minimum=r['minimum_deposited_root_point_peak_C'],thresholds=r['threshold_response']) for r in rows],indent=2))


if __name__=='__main__':main()
