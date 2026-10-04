"""Actual solids for leading wire and a small trailing peener; design envelopes."""
from pathlib import Path
import sys, json, math
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
import yaml
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder,BRepPrimAPI_MakeSphere
from OCP.gp import gp_Ax2,gp_Pnt,gp_Dir,gp_Trsf,gp_Ax1
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from hanjie.domain.tooling_access import read_brep,translated,cylinder,common_volume,clearance,make_torch
from hanjie.domain.competition_design import fuse

from hanjie.domain.following_tools import tools

def main():
    shell=read_brep(ROOT/'simulation/structural-v4/common/shell.brep')
    seat=translated(read_brep(ROOT/'simulation/competition-r4/geometry/8P-R2-t15.brep'),100.)
    spec=yaml.safe_load((ROOT/'project/competition-design.yaml').read_text(encoding='utf8'))
    upper=cylinder(spec['fixture']['upper_envelope_radius_mm'],115.,105.)
    rows=[]
    for leg in (2.8,4.):
        for lag in (0.,1.,2.,3.,4.,5.,6.,7.,8.):
            torch,feed,peener=tools(ROOT,leg,lag)
            pairs={'torch_wire':(torch,feed),'torch_peener':(torch,peener),'wire_peener':(feed,peener),
                   'peener_shell':(peener,shell),'peener_seat':(peener,seat),'peener_upper':(peener,upper),
                   'torch_shell':(torch,shell),'torch_seat':(torch,seat),'wire_shell':(feed,shell),'wire_seat':(feed,seat)}
            rows.append(dict(leg_mm=leg,lag_mm=lag,clearances_mm={k:clearance(*v) for k,v in pairs.items()},
                             intersections_mm3={k:common_volume(*v) for k,v in pairs.items()}))
    path=ROOT/'simulation/competition-r4/results/following-tool-clearances.json'
    path.write_text(json.dumps({'scope':'declared rigid tools, seat, shell and upper fixture; wire tip bead contact intentional','rows':rows},indent=2),encoding='utf8')
    print([(r['leg_mm'],r['lag_mm'],round(r['clearances_mm']['torch_wire'],3),round(r['clearances_mm']['torch_peener'],3),round(r['clearances_mm']['wire_peener'],3),max(r['intersections_mm3'].values())) for r in rows])
if __name__=='__main__':main()
