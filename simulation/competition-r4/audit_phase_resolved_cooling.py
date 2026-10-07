"""Check the actual post-arc coherent-domain responses before mechanical replay."""
import json
import numpy as np
from mma_literature_profile import ROOT
from mma_conservative_birth import clipped_moments


def read(folder):
    inputs=json.loads((folder/'input.json').read_text());result=json.loads((folder/'result.json').read_text())
    if result['partial'] or result['error']:raise ValueError('Cooling audit requires the complete actual thermal state')
    with np.load(folder/'thermal-fields.npz') as f:
        x,e,m,v=f['x'],f['e'],f['material'],f['volume_mm3']
    times=[];values=[]
    manifest=json.loads((folder/'nodal-thermal-history/manifest.json').read_text())
    arc_end=inputs['tracks'][0]['arc_duration_s']
    for chunk in manifest['chunks']:
        if chunk['last_s']<arc_end-1e-9:continue
        with np.load(folder/'nodal-thermal-history'/chunk['file']) as f:
            selected=np.flatnonzero(f['time_s']>=arc_end-1e-9)
            times.extend(f['time_s'][selected]);values.extend(f['temperature_C'][selected])
    times=np.array(times);values=np.array(values)
    with np.load(folder/'interface-cycles.npz') as f:
        face=f['face_nodes'];cycle=f['nodal_temperature_C'];cycle_times=f['time_s']
    threshold=max(inputs['materials'][j]['fusion_enthalpy']['liquidus_C'] for j in [1,3])
    fused=np.any(cycle.min(axis=2)>=threshold,axis=0)
    coherent=min(inputs['materials'][j]['fusion_enthalpy']['solidus_C'] for j in [1,3])
    xyz=x[face];area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)/2
    chronological_fusion=np.maximum.accumulate(cycle.min(axis=2)>=threshold,axis=0)
    coherent_area=np.sum((cycle.max(axis=2)<coherent)*chronological_fusion*area,axis=1)
    onset=cycle_times[np.flatnonzero(coherent_area>0)[0]]
    all_time=cycle_times[np.flatnonzero(coherent_area>=area[fused].sum()*(1-1e-10))[0]]
    probes=[]
    for delay in [.125,.25,.5,1.,2.,3.,4.,6.,10.,12.,16.]:
        t=arc_end+delay;pos=int(np.searchsorted(times,t));j=max(0,pos-1)
        if abs(times[j]-t)<1e-8:T=values[j]
        elif pos<len(times) and abs(times[pos]-t)<1e-8:T=values[pos]
        else:
            fraction=(t-times[j])/(times[pos]-times[j]);T=(1-fraction)*values[j]+fraction*values[pos]
        local=T[e];row=dict(delay_s=delay,maximum_temperature_C=float(T.max()))
        for material,name in [(1,'QT'),(3,'Ni')]:
            solidus=inputs['materials'][material]['fusion_enthalpy']['solidus_C'];selected=m==material
            fraction=(local.max(axis=1)<=solidus).astype(float)
            crossing=np.flatnonzero(selected&(local.min(axis=1)<solidus)&(local.max(axis=1)>solidus))
            for k in crossing:fraction[k]=clipped_moments(local[k],solidus).sum()
            row[name+'_coherent_volume_mm3']=float(v[selected]@fraction[selected])
        row['qualified_coherent_face_area_mm2']=float(area[fused&(T[face].max(axis=1)<coherent)].sum())
        probes.append(row)
    return dict(source=str(folder),peak_C=result['maximum_temperature_C'],final_max_C=result['stages'][-1]['end_active_max_C'],
        cooling_end_s=result['time_s'],qualified_reference_area_mm2=float(area[fused].sum()),
        first_coherent_facet_s=float(onset),all_qualified_facets_coherent_s=float(all_time),probes=probes)


def run():
    root=ROOT/'simulation/competition-r4/results'
    labels=['phase-front-dt0125','phase-front-dt00625','phase-front-h045']
    cases=[read(root/('mma-first-end80-r12-'+label+'-20261007')) for label in labels]
    comparisons=[]
    for name,other in zip(['time half','local mesh'],cases[1:]):
        metrics=[]
        for a,b in zip(cases[0]['probes'],other['probes']):
            for key in ['maximum_temperature_C','Ni_coherent_volume_mm3','QT_coherent_volume_mm3']:
                metrics.append(dict(delay_s=a['delay_s'],response=key,reference=a[key],comparison=b[key],
                    relative_difference=abs(b[key]-a[key])/max(abs(b[key]),abs(a[key]),1e-30)))
            a_fraction=a['qualified_coherent_face_area_mm2']/cases[0]['qualified_reference_area_mm2']
            b_fraction=b['qualified_coherent_face_area_mm2']/other['qualified_reference_area_mm2']
            metrics.append(dict(delay_s=a['delay_s'],response='fraction of qualified interface coherent',
                reference=a_fraction,comparison=b_fraction,relative_difference=abs(a_fraction-b_fraction),
                normalization='absolute coverage-fraction difference over each actual qualified area'))
        for key in ['first_coherent_facet_s','all_qualified_facets_coherent_s']:
            metrics.append(dict(response=key,reference=cases[0][key],comparison=other[key],
                relative_difference=abs(other[key]-cases[0][key])/other[key]))
        comparisons.append(dict(name=name,maximum_relative_difference=max(row['relative_difference'] for row in metrics),metrics=metrics))
    passed=all(row['maximum_relative_difference']<=.05 for row in comparisons)
    result=dict(cases=cases,comparisons=comparisons,coherent_domain_time_mesh_check_pass=passed,
        interpolation_scope='only audit probes between actual saved states; manufacturing uses accepted nodal histories',
        physical_temperature_or_capacity_modified=False,full_manufacturing_verified=False)
    prior=read(root/'mma-first-end80-r12-trace-20261007')
    prior_differences=[]
    for old,new in zip(prior['probes'],cases[0]['probes']):
        if new['delay_s']<2.:continue
        for key in ['maximum_temperature_C','Ni_coherent_volume_mm3','QT_coherent_volume_mm3']:
            prior_differences.append(dict(delay_s=new['delay_s'],response=key,prior2s=old[key],phase_resolved=new[key],
                relative_difference=abs(old[key]-new[key])/max(abs(new[key]),abs(old[key]),1e-30)))
    prior_max=max(row['relative_difference'] for row in prior_differences)
    result.update(prior2s_comparison=prior_differences,prior2s_maximum_coherent_domain_difference=prior_max,
        prior2s_cooling_eligible_for_manufacturing=prior_max<=.05)
    output=root/'mma-continuous-end80-r12-20261007/phase-resolved-cooling-verification.json'
    output.write_text(json.dumps(result,indent=2),encoding='utf8');print(output)
    print(json.dumps(dict(pass_check=passed,comparisons=[dict(name=row['name'],maximum_relative_difference=row['maximum_relative_difference']) for row in comparisons]),indent=2))


if __name__=='__main__':run()
