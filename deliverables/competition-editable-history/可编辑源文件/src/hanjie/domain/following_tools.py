"""Declared root/cover torch, leading wire and trailing light-peening envelopes."""
import math, yaml
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder,BRepPrimAPI_MakeSphere
from OCP.gp import gp_Ax2,gp_Pnt,gp_Dir,gp_Trsf,gp_Ax1
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from hanjie.domain.tooling_access import make_torch
from hanjie.domain.competition_design import fuse

def stick(start,end,r):
    d=[b-a for a,b in zip(start,end)];length=math.sqrt(sum(q*q for q in d))
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*start),gp_Dir(*d)),r,length).Shape()

def tools(root,leg,lag):
    # Targets lie on the actual bead face; the wire enters from the leading side.
    target=(74.5,117.3) if leg==2.8 else (74.,118.)
    p=yaml.safe_load((root/'project/process-r3.yaml').read_text(encoding='utf8'))['process']['nominal']
    spec=yaml.safe_load((root/'studies/TOOLING-ACCESS/config.yaml').read_text(encoding='utf8'))['torch']
    torch,_,_=make_torch(spec,p,target,30,True)
    direction=(-.35,.93,math.sqrt(1-.35**2-.93**2))
    point=lambda d:(target[0]-1.3+direction[0]*d,direction[1]*d,target[1]-1.3+direction[2]*d)
    elbow=point(15.)
    feed=fuse([stick(point(0.),elbow,.8),BRepPrimAPI_MakeSphere(gp_Pnt(*elbow),2.).Shape(),stick(elbow,(elbow[0],elbow[1],220.),2.)])
    radius=73.6 if leg==2.8 else 73.
    z=115.+radius-75.+leg
    head=(radius-3/math.sqrt(2),0.,z+3/math.sqrt(2))
    # A horizontal, low-profile shank stays below the nozzle. Its remote piston
    # is lifted above the QT top; the full piston envelope is included.
    peener=fuse([BRepPrimAPI_MakeSphere(gp_Pnt(*head),3.).Shape(),
                 stick(head,(45.,0.,head[2]),2.5),
                 stick((45.,0.,head[2]),(45.,0.,123.),2.5),
                 stick((45.,0.,123.),(45.,0.,135.),5.)])
    tr=gp_Trsf();tr.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),-lag/74.98)
    peener=BRepBuilderAPI_Transform(peener,tr,True).Shape()
    return torch,feed,peener
