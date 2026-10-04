"""Test actual merged-core/wing corner rounding without overwriting the design geometry."""
from pathlib import Path
import json,math
import gmsh
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent/'geometry'
def main():
    OUT.mkdir(exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0)
        gmsh.model.add('rounded-root-candidate')
        occ=gmsh.model.occ
        occ.importShapes(str(ROOT/'simulation/structural-v4/models/8p-fair-b/8P-FAIR_B.step'))
        occ.synchronize()
        chosen=[]
        for dim,tag in gmsh.model.getEntities(1):
            x0,y0,z0,x1,y1,z1=gmsh.model.getBoundingBox(dim,tag)
            r=math.hypot((x0+x1)/2,(y0+y1)/2)
            if x1-x0<1e-4 and y1-y0<1e-4 and z1-z0>11.99 and abs(r-41)<.01:
                chosen.append(tag)
        if not chosen:raise RuntimeError('no merged-core vertical corners found')
        occ.fillet([tag for _,tag in gmsh.model.getEntities(3)],chosen,[2.],removeVolume=True)
        occ.synchronize()
        gmsh.write(str(OUT/'8P-root-transition-R2.step'))
        (OUT/'root-rounding-candidate.json').write_text(json.dumps(dict(scope='unfrozen service design candidate',
            merged_core_transition_radius_mm=2,rounded_vertical_edges=len(chosen),
            source='simulation/structural-v4/models/8p-fair-b/8P-FAIR_B.step'),indent=2),encoding='utf8')
        print('actual root junctions rounded:',len(chosen))
    finally:gmsh.finalize()
if __name__=='__main__':main()
