"""Material-interface upper bounds from computed nodal peak temperatures.

max_t(sum N_i T_i) <= sum N_i max_t(T_i). If even this upper envelope is
below solidus on the entire interface, the specified run cannot fuse it.
No positive fusion area is certified from a nodal peak envelope alone.
"""
from pathlib import Path
import argparse,json
import numpy as np


def evaluate(folder):
    folder=Path(folder);inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    with np.load(folder/'thermal-fields.npz',allow_pickle=False) as f:
        x,e,m=f['x'],f['e'],f['material'];p=f['peak_nodal_temperature'];pe=f['peak_temperature']
        faces=np.sort(np.vstack([e[:,idx] for idx in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1).astype(np.int32)
        owner=np.tile(np.arange(len(e)),4)
        order=np.lexsort(faces.T[::-1]);faces=faces[order];owner=owner[order]
        change=np.r_[True,np.any(np.diff(faces,axis=0)!=0,axis=1),True];beg=np.flatnonzero(change)
        two=beg[:-1][np.diff(beg)==2];pairs=np.sort(np.c_[m[owner[two]],m[owner[two+1]]],axis=1)
        fc=faces[two];xyz=x[fc];area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)/2
        centre=xyz.mean(axis=1);theta=np.arctan2(centre[:,1],centre[:,0]);along=75*np.abs(np.arctan2(np.sin(theta),np.abs(np.cos(theta))))
        current=along<=9.25 # first opposed segments0/4, root only
        rows={}
        for name,ids,threshold in [('Ni99_NiFe',(2,4),inp['materials'][4]['fusion_enthalpy']['solidus_C']),
                                  ('steel_NiFe',(0,2),inp['materials'][0]['fusion_enthalpy']['solidus_C']),
                                  ('QT_first_Ni99',(1,3),inp['materials'][1]['fusion_enthalpy']['solidus_C'])]:
            pick=current&np.all(pairs==ids,axis=1)
            if not pick.any():raise ValueError('physical material interface missing: '+name)
            upper=p[fc[pick]]
            rows[name]=dict(physical_face_area_mm2=float(area[pick].sum()),solidus_C=threshold,
                nodal_peak_envelope_max_C=float(upper.max()),
                entire_interface_below_solidus_proved=bool(upper.max()<threshold),
                face_area_with_any_node_above_solidus_upper_bound_mm2=float(area[pick][np.any(upper>=threshold,axis=1)].sum()))
        result=dict(scope='first opposed root segments, final welding geometry; no precoat fusion claim',interfaces=rows,
            material_peak_C={str(i):dict(nodal=float(p[np.unique(e[m==i])].max()),element=float(pe[m==i].max())) for i in range(5)},
            QT_side_fusion_definitely_absent=rows['Ni99_NiFe']['entire_interface_below_solidus_proved'],
            positive_fusion_certified=False,position_or_strength_verification_completed=False)
    (folder/'explicit-interface-fusion.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True)
    print(json.dumps(evaluate(p.parse_args().case),indent=2))
