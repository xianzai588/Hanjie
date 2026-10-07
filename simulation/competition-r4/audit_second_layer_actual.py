"""Check the two real Ni99 tracks on the actual cold-cut first layer.

The interface criterion uses all three P1 vertices at the same recorded time.
No peak of independently heated vertices, assumed dilution or missing end
region is substituted for a continuous connection.
"""
import argparse
import json
import numpy as np
from mma_literature_profile import ROOT


def audit(source):
    destination=source/'second-layer-connection-audit.json'
    if destination.exists():raise ValueError('Preserve the previous actual second-layer audit')
    result=json.loads((source/'result.json').read_text())
    if result['partial'] or result.get('error'):raise ValueError('Require the completed actual two-track thermal history')
    inputs=json.loads((source/'input.json').read_text())
    if inputs['deposition_material_ids']!=[4,5] or inputs['preexisting_material_ids']!=[1,3]:
        raise ValueError('Expected retained CI-A1 and the two actual low-carbon Ni99 tracks')
    with np.load(source/'thermal-fields.npz') as f:
        x,e,m=f['x'],f['e'],f['material']
        final_fraction=f['deposited_P1_moments'].sum(axis=1)
        mass=f['material_mass_kg']
    with np.load(source/'interface-cycles.npz') as f:
        face=f['face_nodes'];temperature=f['nodal_temperature_C'];times=f['time_s']
    all_faces=np.sort(np.vstack([e[:,q] for q in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1)
    owners=np.tile(np.arange(len(e)),4)
    faces,first,inverse,count=np.unique(all_faces,axis=0,return_index=True,return_inverse=True,return_counts=True)
    last=np.zeros(len(count),int);np.maximum.at(last,inverse,np.arange(len(all_faces)))
    adjacent=np.c_[owners[first],owners[last]]
    pending=(count==2)&(m[adjacent[:,0]]!=m[adjacent[:,1]])&np.any(m[adjacent]>=4,axis=1)
    if not np.array_equal(faces[pending],face):raise ValueError('Recorded physical interface face order differs from actual mesh')
    material_pairs=np.sort(m[adjacent[pending]],axis=1)
    if np.any(material_pairs[:,0]==1):raise ValueError('New Ni bypasses the actual retained first layer')
    xyz=x[face];area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)/2
    liquidus=np.array([row['fusion_enthalpy']['liquidus_C'] for row in inputs['materials']])
    threshold=liquidus[material_pairs].max(axis=1)
    minimum=temperature.min(axis=2)
    peak=minimum.max(axis=0)
    qualified=peak>=threshold
    hot=(minimum>=threshold)
    duration=(np.diff(times)[:,None]*(hot[:-1]&hot[1:])).sum(axis=0)
    rows=[]
    for pair in [(3,4),(3,5),(4,5)]:
        selected=np.all(material_pairs==pair,axis=1)
        if not selected.any():raise ValueError(f'Required physical material interface {pair} is missing')
        coldest=int(np.flatnonzero(selected)[np.argmin(peak[selected]-threshold[selected])])
        rows.append(dict(material_pair=list(pair),faces=int(selected.sum()),
            total_area_mm2=float(area[selected].sum()),qualified_area_mm2=float(area[selected&qualified].sum()),
            every_required_face_pass=bool(qualified[selected].all()),
            liquidus_threshold_C=float(threshold[selected].max()),weakest_whole_face_peak_C=float(peak[selected].min()),
            minimum_whole_face_margin_C=float((peak-threshold)[selected].min()),
            weakest_face_centroid_mm=xyz[coldest].mean(axis=0).tolist(),
            minimum_recorded_full_liquid_duration_s=float(duration[selected].min()),
            duration_scope='lower estimate from adjacent recorded times both satisfying the whole-face criterion'))
    old_interface=(count==2)&np.all(np.sort(m[adjacent],axis=1)==[1,3],axis=1)
    old_faces=faces[old_interface]
    if not len(old_faces):raise ValueError('Retained QT/CI-A1 physical interface is missing')
    old_xyz=x[old_faces]
    old_area=np.linalg.norm(np.cross(old_xyz[:,1]-old_xyz[:,0],old_xyz[:,2]-old_xyz[:,0]),axis=1)/2
    old_max=np.full(len(old_faces),-np.inf);old_whole_peak=old_max.copy()
    manifest=json.loads((source/'nodal-thermal-history/manifest.json').read_text())
    for chunk in manifest['chunks']:
        with np.load(source/'nodal-thermal-history'/chunk['file']) as f:
            actual=f['temperature_C'][:,old_faces]
            old_max=np.maximum(old_max,actual.max(axis=(0,2)))
            old_whole_peak=np.maximum(old_whole_peak,actual.min(axis=2).max(axis=0))
    old_solidus=min(inputs['materials'][j]['fusion_enthalpy']['solidus_C'] for j in [1,3])
    old_liquidus=max(liquidus[[1,3]])
    old_coherent=old_max<old_solidus
    retained_interface=dict(total_area_mm2=float(old_area.sum()),
        maximum_recorded_nodal_temperature_C=float(old_max.max()),whole_face_coherence_limit_C=old_solidus,
        ever_not_whole_face_coherent_area_mm2=float(old_area[~old_coherent].sum()),
        whole_face_both_sides_liquid_area_mm2=float(old_area[old_whole_peak>=old_liquidus].sum()),
        every_face_stays_whole_face_coherent=bool(old_coherent.all()),
        mechanical_requirement='If any retained first interface loses whole-face coherence, replay must explicitly release/reconnect that preexisting interface while retaining surviving material history; a permanently shared cold interface is insufficient.')
    birth=np.loadtxt(source/'deposition-history.csv',delimiter=',',skiprows=1,ndmin=2)
    history=np.loadtxt(source/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
    mass_error=float(abs(birth[:,2]-birth[:,3]).max())
    scale=np.maximum.reduce([abs(history[:,7]),abs(history[:,9]),np.ones(len(history))])
    energy_error=float((abs(history[:,10])/scale).max())
    arc_time=float(history[history[:,3]>0,1].sum())
    commanded=float(history[:,7].sum())
    arc_error=abs(commanded-inputs['arc_power_W']*arc_time)
    all_born=bool(np.min(final_fraction)>=1-1e-10)
    passed=bool(all(row['every_required_face_pass'] for row in rows) and all_born
        and mass_error<1e-9 and energy_error<1e-6 and arc_error<1e-7 and result['maximum_temperature_C']<2800)
    report=dict(source=str(source),interfaces=rows,retained_first_interface=retained_interface,
        fusion_criterion='max_time(min_all_three_P1_vertices(T)) >= max(actual two-side liquidus); all required physical faces, including ends',
        maximum_track_cumulative_mass_error_g=mass_error,completed_deposited_mass_g=float(mass[m>=4]@final_fraction[m>=4]*1000),
        total_arc_time_s=arc_time,commanded_net_energy_J=commanded,net_power_time_error_J=arc_error,
        maximum_relative_step_energy_balance_error=energy_error,all_deposition_completed=all_born,
        actual_second_layer_thermal_connection_screen_pass=passed,
        retained_first_layer_state_source=inputs['initial_state_path'],
        numerical_response_convergence_verified=False,physical_source_calibrated=False,
        PMZ_capacity_assigned=False,full_manufacturing_verified=False)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=lambda s:ROOT/s,required=True)
    audit(p.parse_args().source)
