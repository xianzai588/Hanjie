"""Actual first-layer floor coverage and quadrature molten-volume screening.

Molten volume is a temporal union at fixed tetrahedral quadrature points.
It is not a melt-flow solution or an observed first-layer dilution fraction.
"""
from pathlib import Path
import argparse,csv,json
import numpy as np


def audit(case,allow_partial=False):
    inp=json.loads((case/'input.json').read_text(encoding='utf8'))
    # A stopped run may leave an earlier periodic result.json. The failure
    # summary corresponds to the last saved raw fields and must take precedence.
    summary=case/('failure.json' if (case/'failure.json').exists() else 'result.json')
    result=json.loads(summary.read_text(encoding='utf8'))
    if result['partial'] and not allow_partial:raise ValueError('completed first-layer field required, or explicit partial diagnostic option')
    with np.load(case/'thermal-fields.npz',allow_pickle=False) as f:
        x,e,m=f['x'],f['e'],f['material'];volume=f['volume_mm3'];active=f['thermal_active']
        qp=f['peak_element_quadrature_C'];faces=f['interface_nodes']
        face_peak=f['interface_peak_C'];area=f['interface_area_mm2']
    ni=inp['materials'][3];qt=inp['materials'][1]
    born_faces=set()
    for tet in e[(m==3)&active]:
        for ij in [(0,1,2),(0,1,3),(0,2,3),(1,2,3)]:
            born_faces.add(tuple(sorted(tet[list(ij)])))
    deposited_floor=np.array([tuple(row) in born_faces for row in np.sort(faces,axis=1)])
    floor=float(x[np.unique(e[m==3]),2].min())
    threshold=max(qt['fusion_enthalpy']['solidus_C'],ni['fusion_enthalpy']['solidus_C'])
    xyz=np.einsum('qj,fjk->fqk',np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]]),x[faces])
    r=np.linalg.norm(xyz[:,:,:2],axis=2);s=74.98*np.arctan2(xyz[:,:,1],xyz[:,:,0])
    point_area=np.broadcast_to(area[:,None]/3,face_peak.shape)
    footprints={};rows=[]
    for leg,name in [(2.8,'root'),(4.,'cap'),(6.02,'full_radial_band')]:
        select=(abs(xyz[:,:,2]-floor)<1e-5)&(r>=75-leg)&(abs(s)<=9)
        if not select.any():raise RuntimeError('no physical interface floor quadrature')
        per=[]
        for b in range(18):
            points=select&(s>=b-9)&(s<b-8)
            total=float(point_area[points].sum());hot=float(point_area[points&(face_peak>=threshold)].sum())
            row=dict(footprint=name,arc_begin_mm=b-9,area_mm2=total,above_both_solidus_mm2=hot,
                minimum_point_peak_C=float(face_peak[points].min()) if points.any() else None)
            rows.append(row);per.append(row)
        footprints[name]=dict(physical_quadrature_area_mm2=float(point_area[select].sum()),
            above_both_solidus_area_mm2=float(point_area[select&(face_peak>=threshold)].sum()),
            minimum_point_peak_C=float(face_peak[select].min()),
            bins_without_any_molten_point=[row['arc_begin_mm'] for row in per if row['above_both_solidus_mm2']==0],
            all_sampled_points_reach_both_solidus=bool(np.all(face_peak[select]>=threshold)))
        formed=select&deposited_floor[:,None]
        footprints[name]['actually_deposited_portion']=dict(area_mm2=float(point_area[formed].sum()),
            above_selected_alloy_solidus_mm2=float(point_area[formed&(face_peak>=threshold)].sum()),
            above_pure_Ni_upper_melting_bound_1458p85C_mm2=float(point_area[formed&(face_peak>=1458.85)].sum()),
            minimum_point_peak_C=float(face_peak[formed].min()) if formed.any() else None,
            all_points_above_selected_alloy_solidus=bool(formed.any() and np.all(face_peak[formed]>=threshold)))
    qt_q=qp[m==1];qt_v=volume[m==1,None]/4
    full=float((qt_v*(qt_q>=qt['fusion_enthalpy']['liquidus_C'])).sum())
    any_melt=float((qt_v*(qt_q>=qt['fusion_enthalpy']['solidus_C'])).sum())
    ni_volume=float(volume[(m==3)&active].sum());ni_mass=ni_volume*ni['nominal_properties_20c']['density_kg_m3']*1e-9
    qt_rho=qt['nominal_properties_20c']['density_kg_m3']*1e-9
    screen=dict(fully_liquid_quadrature_union_mm3=full,any_liquid_quadrature_union_mm3=any_melt,
        deposited_first_layer_volume_mm3=ni_volume,
        conditional_complete_mixing_QT_mass_fraction=[full*qt_rho/(ni_mass+full*qt_rho),any_melt*qt_rho/(ni_mass+any_melt*qt_rho)],
        scope='4-point tetrahedron quadrature and each point temporal peak; conditional complete mixing of the spatial union, not actual transported dilution')
    screen['decision']='upper screen<=20% may support conservative selection after temperature/space/time qualification; upper screen>20% cannot certify<=20%, and does not prove transported dilution>20%'
    screen['maximum_QT_entrained_volume_mm3_for_20pct_at_actual_born_mass']=ni_mass/4/qt_rho
    screen['maximum_fraction_of_any_liquid_union_allowed_to_entrain_for_20pct']=ni_mass/4/(any_melt*qt_rho) if any_melt else None
    output=dict(thermal_run_partial=result['partial'],thermal_run_error=result.get('error'),summary_source=summary.name,converged_end_s=result['time_s'],floor_z_mm=floor,both_solidus_threshold_C=threshold,footprints=footprints,QT_molten_volume_screen=screen,
        mesh_time_convergence_verified=False,actual_dilution_verified=False,PMZ_capacity_assigned=False)
    with (case/'precoat-floor-footprint.csv').open('w',newline='',encoding='utf8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    (case/'precoat-floor-footprint.json').write_text(json.dumps(output,indent=2),encoding='utf8')
    return output


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--allow-partial',action='store_true')
    a=p.parse_args();print(json.dumps(audit(a.case,a.allow_partial),indent=2))
