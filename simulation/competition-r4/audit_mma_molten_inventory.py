"""Actual simultaneous molten inventories; complete-mixing scenarios only."""
import argparse,json
import numpy as np
from mma_literature_profile import ROOT
from mma_conservative_birth import clipped_moments


def audit(folder):
    inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    f=np.load(folder/'thermal-fields.npz');e,m,volume=f['e'],f['material'],f['volume_mm3']
    qt=m==1;ni=m==3
    manifest=json.loads((folder/'nodal-thermal-history/manifest.json').read_text(encoding='utf8'))
    tq=inp['materials'][1]['fusion_enthalpy']['liquidus_C'];tn=inp['materials'][3]['fusion_enthalpy']['liquidus_C']
    rq=inp['materials'][1]['nominal_properties_20c']['density_kg_m3']*1e-6
    rn=inp['materials'][3]['nominal_properties_20c']['density_kg_m3']*1e-6
    rows=[]
    for chunk in manifest['chunks']:
        with np.load(folder/'nodal-thermal-history'/chunk['file']) as data:
            for time,T,occupancy in zip(data['time_s'],data['temperature_C'],data['deposit_fraction']):
                point=T[e[qt]]
                if point.max()<tq:continue
                fraction=np.zeros(len(point));fraction[point.min(axis=1)>=tq]=1.
                for i in np.flatnonzero((point.min(axis=1)<tq)&(point.max(axis=1)>=tq)):
                    fraction[i]=clipped_moments(-point[i],-tq).sum()
                qvolume=float(volume[qt]@fraction)
                nipoint=T[e[ni]]
                lower=float((volume[ni]*occupancy)@(nipoint.min(axis=1)>=tn))
                upper=float((volume[ni]*occupancy)@(nipoint.max(axis=1)>=tn))
                mass=qvolume*rq;lowermass=lower*rn;uppermass=upper*rn
                rows.append([time,qvolume,lower,upper,mass,lowermass,uppermass,
                    mass/(mass+uppermass) if mass+uppermass else 0.,
                    mass/(mass+lowermass) if mass+lowermass else 0.])
    rows=np.asarray(rows)
    np.savetxt(folder/'simultaneous-molten-inventory.csv',rows,delimiter=',',comments='',
        header='t_s,QT_fully_liquid_volume_mm3,Ni_liquid_volume_lower_mm3,Ni_liquid_volume_upper_mm3,QT_liquid_g,Ni_liquid_lower_g,Ni_liquid_upper_g,fullmix_QT_fraction_lower_scenario,fullmix_QT_fraction_upper_scenario')
    k=int(np.argmax(rows[:,1]));row=rows[k]
    result=dict(source_run=folder.name,maximum_simultaneous_QT_liquid_volume_mm3=float(row[1]),
        time_of_QT_inventory_maximum_s=float(row[0]),QT_liquid_mass_at_maximum_g=float(row[4]),
        Ni_liquid_mass_range_at_that_time_g=row[5:7].tolist(),
        complete_mix_QT_mass_fraction_scenarios_at_that_time=row[7:9].tolist(),
        QT_inventory_method='exact P1 temperature-threshold clipped tetrahedron volume at each actual recorded time',
        Ni_inventory_method='occupied volume whose parent tetra all vertices exceed liquidus (lower) or any vertex exceeds liquidus (upper)',
        chemical_interpretation='simultaneous-domain complete-mixing scenarios; not actual transport, retained-layer composition or a rigorous global dilution bound',
        required_followup='first-layer material and remelted-QT state must cover justified composition scenarios before retained mechanical replay',
        transport_dilution_verified=False,PMZ_capacity_assigned=False)
    (folder/'simultaneous-molten-inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=lambda s:ROOT/s,required=True)
    a=p.parse_args();audit(a.run)
