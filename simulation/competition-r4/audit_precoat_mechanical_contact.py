"""Check chronological fusion before conformal solid/solid force transfer."""
import argparse
import json
import numpy as np
from mma_literature_profile import ROOT


def audit(source,output):
    inputs=json.loads((source/'input.json').read_text())
    with np.load(source/'thermal-fields.npz') as f:
        e,m=f['e'],f['material']
    with np.load(source/'precoat-interface-observer/material-interface-thermal.npz') as f:
        faces,adj,area=f['face_nodes'],f['adjacent_elements'],f['face_area_mm2']
    with np.load(source/'interface-cycles.npz') as f:
        if not np.array_equal(f['face_nodes'],faces):raise ValueError('Interface history face order mismatch')
        times=f['time_s'];cycles=f['nodal_temperature_C']
    solidus=np.array([row['fusion_enthalpy']['solidus_C'] for row in inputs['materials']])[m]
    liquidus=np.array([row['fusion_enthalpy']['liquidus_C'] for row in inputs['materials']])[m]
    ni=np.where(m[adj[:,0]]==3,adj[:,0],adj[:,1]);qt=np.where(m[adj[:,0]]==1,adj[:,0],adj[:,1])
    fused=np.zeros(len(faces),bool);records=[]
    manifest=json.loads((source/'nodal-thermal-history/manifest.json').read_text())
    for chunk in manifest['chunks']:
        with np.load(source/'nodal-thermal-history'/chunk['file']) as f:
            for j,t in enumerate(f['time_s']):
                index=int(np.argmin(abs(times-t)))
                if abs(times[index]-t)>1e-6:raise ValueError('Missing chronological interface state')
                fused|=cycles[index].min(axis=1)>=1400
                temperature=f['temperature_C'][j];occupation=np.ones(len(e));occupation[m==3]=f['deposit_fraction'][j]
                mean=temperature[e].mean(axis=1)
                solid=occupation*(1-np.clip((mean-solidus)/(liquidus-solidus),0,1))
                coupled=(solid[ni]>1e-12)&(solid[qt]>1e-12)
                unfused=coupled&~fused
                records.append([float(t),float(area[fused].sum()),float(area[coupled].sum()),float(area[unfused].sum()),
                    float(np.sum(area[unfused]*np.minimum(solid[ni[unfused]],solid[qt[unfused]])))])
    a=np.array(records);k=int(np.argmax(a[:,3]));output.mkdir(parents=True,exist_ok=True)
    np.savetxt(output/'chronological-contact.csv',a,delimiter=',',comments='',
        header='t_s,previously_full_face_liquid_area_mm2,possible_solid_solid_area_mm2,unqualified_conformal_area_mm2,solid_fraction_weighted_unqualified_area_mm2')
    result=dict(source=str(source),criterion='saved entire-face simultaneous1400C with actual birth mask, before possible solid/solid force transfer',
        maximum_potential_unqualified_conformal_area_mm2=float(a[k,3]),time_of_maximum_s=float(a[k,0]),
        maximum_solid_fraction_weighted_unqualified_area_mm2=float(a[:,4].max()),
        chronological_conformal_mechanical_connection_pass=bool(a[:,3].max()<1e-8),
        scope='potential coupling audit from the selected constant-stress-cell solid fractions; does not assign traction or capacity',
        full_manufacturing_verified=False)
    (output/'contact-audit.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=lambda s:ROOT/s,required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True);a=p.parse_args();audit(a.source,a.output)
