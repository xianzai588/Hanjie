"""Normal first-layer cut on the actual deposited tetrahedral envelope.

The flat0.70mm retained layer and R0.80 corner are the saved engineering
geometry. The signed surface is represented by parent P1 values. A machining
state operation removes material volume and retains every surviving tensor;
it never substitutes a stress-free manufactured part.
"""
import argparse
import json
import numpy as np
from mma_literature_profile import ROOT
from mma_conservative_birth import clipped_moments


def retained_moments(x,e,material,normal_mm=.7):
    radius=1.5-normal_mm
    r=np.linalg.norm(x[:,:2],axis=1)
    signed=np.where(r>=70.48,x[:,2]-(115-radius),
                    np.maximum(x[:,2]-115,radius-np.hypot(r-70.48,x[:,2]-115)))
    # OCC roof coordinates carry sub-picometre floating-point offsets.
    # Classify the exact zero surface at a1e-9mm geometry tolerance instead
    # of asking Qhull to create a volume from an effectively planar sliver.
    signed[abs(signed)<1e-9]=0.
    moments=np.full((len(e),4),.25)
    ni=np.flatnonzero(material==3)
    values=signed[e[ni]]
    moments[ni]=0.
    full=values.max(axis=1)<=0
    moments[ni[full]]=.25
    for j in np.flatnonzero((values.min(axis=1)<0)&~full):
        moments[ni[j]]=clipped_moments(values[j],0.)
    return moments


def audit(sources,output):
    if output.exists():raise ValueError('Preserve the completed machining geometry audit')
    rows=[]
    reference=json.loads((ROOT/'cad/generated/independent-precoat-curved/geometry-audit.json').read_text())
    target=reference['material_volumes_mm3']['first_CI_A1']/8
    for source in sources:
        with np.load(source/'thermal-fields.npz') as f:
            x,e,m,v=f['x'],f['e'],f['material'],f['volume_mm3']
        moments=retained_moments(x,e,m)
        actual=float(v[m==3]@moments[m==3].sum(axis=1))
        rows.append(dict(source=str(source),normal_retained_mm=.7,corner_R_mm=.8,
            source_deposit_volume_mm3=float(v[m==3].sum()),retained_first_layer_mm3=actual,
            exact_OCC_retained_first_layer_mm3=target,relative_retained_volume_error=abs(actual-target)/target,
            removed_volume_mm3=float(v[m==3].sum())-actual,
            retained_volume_pass=bool(abs(actual-target)/target<=.05)))
    result=dict(cases=rows,cut_surface='R0.80 normal-offset corner and flat z114.20, inner lip capped at z115; parent P1 level-set cut',
        geometric_zero_surface_tolerance_mm=1e-9,
        geometric_cut_verified=bool(all(row['retained_volume_pass'] for row in rows)),
        surviving_plastic_and_residual_history_policy='volume removal only; no stress/plastic reset; re-equilibration required after the actual cold-state cut',
        machining_mechanical_state_verified=False,full_manufacturing_verified=False)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',action='append',type=lambda s:ROOT/s,required=True)
    p.add_argument('--output',type=lambda s:ROOT/s,required=True)
    a=p.parse_args();audit(a.source,a.output)
