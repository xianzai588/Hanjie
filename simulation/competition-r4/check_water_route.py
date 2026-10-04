"""Check actual installation bends through the specified Cu retraction stroke."""
from pathlib import Path
import sys, json, itertools
import numpy as np
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from hanjie.domain.water_route import bends


def main():
    rows=[];previous=None;max_motion=0;max_spacing=0
    for stroke in np.linspace(0,1.15,47):
        curves,radii,lengths=bends(float(stroke),count=601)
        spacing=max(float(np.linalg.norm(np.diff(c,axis=0),axis=1).max()) for c in curves)
        max_spacing=max(max_spacing,spacing)
        pair_min=min(float(cKDTree(a).query(b)[0].min()) for a,b in itertools.combinations(curves,2))
        if previous is not None:
            max_motion=max(max_motion,max(float(np.linalg.norm(a-b,axis=1).max()) for a,b in zip(curves,previous)))
        previous=curves
        radial=np.concatenate([np.linalg.norm(c[:,:2],axis=1) for c in curves])
        rows.append(dict(stroke_mm=float(stroke),minimum_bend_radius_mm=min(radii),
            minimum_sampled_hose_centre_distance_mm=pair_min,
            free_lengths_mm=lengths[:1]+lengths[8:9],radial_envelope_mm=[float(radial.min()),float(radial.max())]))
    # Conservative discretisation allowance is twice each maximum centreline
    # sample spacing and twice observed motion between adjacent stroke poses.
    # It bounds the reported polyline installation envelope, not hose stiffness.
    margin=2*max_spacing+2*max_motion
    distance_lower=min(r['minimum_sampled_hose_centre_distance_mm'] for r in rows)-margin
    result=dict(scope='16 constant-length installation bends; Cu connections move, welded manifold ports remain fixed; no cyclic Cu bending',
        hose_OD_nominal_mm=2,hose_OD_installed_envelope_mm=2.2,hose_ID_minimum_mm=.95,maximum_stroke_mm=1.15,
        stroke_spacing_mm=.025,maximum_curve_sample_spacing_mm=max_spacing,
        maximum_adjacent_pose_centre_motion_mm=max_motion,discretisation_allowance_mm=margin,
        hose_pair_surface_clearance_lower_mm=distance_lower-2.2,
        minimum_sampled_bend_radius_mm=min(r['minimum_bend_radius_mm'] for r in rows),
        copper_connection_radial_stagger_mm=10,copper_connection_tail_offset_mm=9,
        manifold_ports_local_xyz_mm=[[58,-8,92],[52,-8,94],[58,8,92],[52,8,94]],
        custom_union_design='316L M4x0.5 compression union, maximum OD5 x length8, PFA insertion >=4 mm, fitted low-outgassing ferrule; fixed to metal elbow, no swivelling joint',
        metallic_inlet='OD1.80 Cu microtube to machined5x5x5 Cu L-port block with integral M4 outlet nipple; block and compression joint stationary relative to the sector; inspect minimum clear bore and proof pressure',
        rows=rows,design_checks_pass=bool(distance_lower-2.2>=.2 and min(r['minimum_bend_radius_mm'] for r in rows)>=12
            and min(r['radial_envelope_mm'][0] for r in rows)-1.1>43
            and max(r['radial_envelope_mm'][1] for r in rows)+1.1<70))
    out=ROOT/'simulation/competition-r4/results/water-route-verification.json'
    out.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))
    if not result['design_checks_pass']:raise ValueError('water hose installation envelope failed')
if __name__=='__main__':main()
