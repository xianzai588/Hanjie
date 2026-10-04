"""Actual sector self-collision plus dimensional continuous-path certificate."""
from pathlib import Path
import sys,json,math,itertools
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from hanjie.domain.copper_sectors import sectors,backing_ring,water_bulkheads,retention_screws
from hanjie.domain.water_route import moving_union_envelopes,moving_elbow_envelopes
from hanjie.domain.tooling_access import common_volume,clearance
from OCP.STEPControl import STEPControl_Writer,STEPControl_AsIs

def main():
    sys.path.insert(0,str(ROOT/'studies/COMPETITION-DESIGN'))
    from seal_design import evaluate
    engineering=evaluate()
    rows=[];writer=STEPControl_Writer()
    for stroke in (0.,.55,1.15):
        bodies=sectors(gap=1.95,stroke=stroke);backing=backing_ring();blocks=water_bulkheads();unions=moving_union_envelopes(stroke);screws=retention_screws();elbows=moving_elbow_envelopes(stroke)
        pairs=[(a,b) for a,b in itertools.combinations(bodies,2)]+[(a,backing) for a in bodies]+[(a,b) for a in bodies for b in blocks]+[(backing,b) for b in blocks]
        union_pairs=[(a,b) for a,b in itertools.combinations(unions,2)]+[(a,b) for a in unions for b in [*bodies,backing,*blocks,*screws]]
        screw_pairs=[(a,b) for a in screws for b in [*bodies,*blocks]]
        elbow_pairs=[(a,b) for a,b in itertools.combinations(elbows,2)]+[(a,b) for a in elbows for b in [*bodies,backing,*blocks,*screws]]+[(a,b) for i,a in enumerate(elbows) for j,b in enumerate(unions) if i!=j]
        rows.append(dict(stroke_mm=stroke,maximum_intersection_mm3=max(common_volume(a,b) for a,b in pairs),
                         minimum_clearance_mm=min(clearance(a,b) for a,b in pairs),
                         union_maximum_intersection_mm3=max(common_volume(a,b) for a,b in union_pairs),
                         union_minimum_clearance_mm=min(clearance(a,b) for a,b in union_pairs),
                         screw_maximum_intersection_mm3=max(common_volume(a,b) for a,b in screw_pairs),
                         screw_minimum_clearance_mm=min(clearance(a,b) for a,b in screw_pairs),
                         elbow_maximum_intersection_mm3=max(common_volume(a,b) for a,b in elbow_pairs),
                         elbow_minimum_clearance_mm=min(clearance(a,b) for a,b in elbow_pairs)))
        if stroke==0:
            for body in [*bodies,backing,*blocks,*unions,*screws,*elbows]:writer.Transfer(body,STEPControl_AsIs)
    gap_min=1.95-2*1.15/math.sqrt(2)
    result=dict(scope='four sectors including two port bosses each, stationary backing ring, four welded water blocks, sixteen unions/L-port blocks and eight screw envelopes; each matching union/nipple is an intentional assembly overlap; hoses detailed in water-route-verification.json',
                rows=rows,continuous_sector_separation_lower_mm=gap_min,backing_ring_axial_clearance_nominal_mm=.1,
                backing_ring_axial_clearance_with_position_tolerance_mm=.06,
                upper_bridge_overlap_initial_mm=4,upper_bridge_pocket_length_mm=6,
                upper_bridge_max_sliding_mm=2*1.15/math.sqrt(2),
                upper_bridge_overlap_remaining_mm=4-2*1.15/math.sqrt(2),
                fixed_backing_ring_hot_outer_radius_mm=74.81*(1+11.2e-6*28),
                seal_water_and_capacity=engineering,
                design_checks_pass=engineering['checks_pass'] and gap_min>=.1 and all(r['maximum_intersection_mm3']<1e-6 and r['minimum_clearance_mm']>=.06 and r['union_maximum_intersection_mm3']<1e-6 and r['union_minimum_clearance_mm']>=.2 and r['screw_maximum_intersection_mm3']<1e-6 and r['screw_minimum_clearance_mm']>=.06 and r['elbow_maximum_intersection_mm3']<1e-6 and r['elbow_minimum_clearance_mm']>=.2 for r in rows))
    out=ROOT/'simulation/competition-r4/results';(out/'copper-retraction-verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    writer.Write(str(ROOT/'cad/generated/competition-design/copper-sectors-and-backing.step'))
    print(json.dumps(result,indent=2))
    if not result['design_checks_pass']:raise ValueError('copper retreat self-collision')
if __name__=='__main__':main()
