"""A separating-plane certificate for the two opposed candidate tool packs."""
from pathlib import Path
import sys,json
import numpy as np
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from hanjie.domain.following_tools import tools


def main():
    rows=[]
    for leg in (2.8,4.):
        for lag in np.arange(4.5,7.0001,.5):
            for name,shape in zip(('torch','wire','peener'),tools(ROOT,leg,float(lag))):
                box=Bnd_Box();BRepBndLib.Add_s(shape,box)
                bounds=box.Get()
                rows.append(dict(leg_mm=leg,lag_mm=float(lag),tool=name,
                    minimum_x_mm=bounds[0],maximum_x_mm=bounds[3]))
    minimum=min(r['minimum_x_mm'] for r in rows)
    # Between samples, <=75 mm radial distance and <=.25 mm arc half-step
    # give <.251 mm displacement. Both packs may suffer full pose/growth errors.
    continuous=2*(minimum-.251-.05-.02)
    result=dict(scope='two identical declared rigid tool packs, opposed by 180 degrees; workpiece rotates, tool packs remain fixed',
        sampled_positive_halfspace_minimum_mm=minimum,opposed_pack_clearance_lower_bound_mm=continuous,
        sampling_motion_allowance_per_pack_mm=.251,pose_error_per_pack_mm=.05,
        growth_allowance_per_pack_mm=.02,rows=rows,
        certificate='all pack-1 points have x>=a; 180-degree pack-2 points have x<=-a; common rotation and vertical lifts preserve separation',
        opposed_tool_geometry_pass=bool(continuous>=.2))
    path=ROOT/'simulation/competition-r4/results/opposed-tool-verification.json'
    path.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))


if __name__=='__main__':main()
