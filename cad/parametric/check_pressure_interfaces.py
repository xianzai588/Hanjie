"""Finite geometry check of HJ023 against the existing torch/wire envelopes.

No FE, candidate search or STEP-family generation.  The projected capsule
distance also covers the complete vertical tool withdrawal, independent of z.
"""
import json, math, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Pnt,gp_Dir,gp_Ax1,gp_Ax2,gp_Trsf,gp_Vec
from hanjie.domain.following_tools import tools
from hanjie.domain.competition_design import fuse,clearance

ANGLES=[22.5,157.5,292.5]
def turn(shape,angle):
    tr=gp_Trsf();tr.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),math.radians(angle))
    return BRepBuilderAPI_Transform(shape,tr,True).Shape()
def box(r,w,z,h,end):return BRepPrimAPI_MakeBox(gp_Pnt(r,-w/2,z),end-r,w,h).Shape()
def cyl(r,z,h,x=0,y=0):return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x,y,z),gp_Dir(0,0,1)),r,h).Shape()
def move(shape,lift):
    tr=gp_Trsf();tr.SetTranslation(gp_Vec(0,0,lift));return BRepBuilderAPI_Transform(shape,tr,True).Shape()
def footprint_point(p,angle):
    a=math.radians(angle);return (p[0]*math.cos(a)-p[1]*math.sin(a),p[0]*math.sin(a)+p[1]*math.cos(a))
def point_segment(p,a,b):
    d=(b[0]-a[0],b[1]-a[1]);q=sum((p[i]-a[i])*d[i] for i in (0,1))/sum(v*v for v in d)
    q=min(1,max(0,q));return math.hypot(p[0]-a[0]-q*d[0],p[1]-a[1]-q*d[1])
def seg_distance(a,b,c,d):
    def cross(u,v):return u[0]*v[1]-u[1]*v[0]
    ab=(b[0]-a[0],b[1]-a[1]);cd=(d[0]-c[0],d[1]-c[1]);ac=(c[0]-a[0],c[1]-a[1]);den=cross(ab,cd)
    if abs(den)>1e-12:
        t=cross(ac,cd)/den;u=cross(ac,ab)/den
        if 0<=t<=1 and 0<=u<=1:return 0.
    return min(point_segment(a,c,d),point_segment(b,c,d),point_segment(c,a,b),point_segment(d,a,b))
def seg_rect(a,b,lo,hi,half):
    if any(lo<=p[0]<=hi and abs(p[1])<=half for p in (a,b)):return 0.
    corners=[(lo,-half),(hi,-half),(hi,half),(lo,half)]
    return min(seg_distance(a,b,corners[i],corners[(i+1)%4]) for i in range(4))

def main():
    ring=BRepAlgoAPI_Cut(cyl(52,115.3,11.7),cyl(37,115,13)).Shape()
    pads=[turn(box(36,6,115,2,38),a) for a in (0,120,240)]
    arms=[turn(box(50,10,115.3,11.7,60),a) for a in ANGLES]
    press=fuse([ring,*pads,*arms])
    rods=[turn(cyl(4,127,98,60),a) for a in ANGLES]
    beams=[turn(fuse([box(60,3.,225,20,90),box(90,40,225,20,340),cyl(7,225,20,60)]),a) for a in ANGLES]
    obstacles={'ring':press,'rods':fuse(rods),'beams':fuse(beams)}
    rows=[];projection=[]
    # Exact finite poses use unchanged current torch/wire shapes.
    for name,leg,target in [('root',2.8,(74.5,117.3)),('cover',3.8,(74,118))]:
        torch,wire,_=tools(ROOT,leg,5)
        for wing in range(8):
            for end in (-1,1):
                theta=wing*45+end*math.degrees(9/74.98)
                for lift in (0,40,150):
                    for toolname,shape in [('torch',torch),('wire',wire)]:
                        posed=move(turn(shape,theta),lift)
                        rows.append(dict(pass_name=name,wing=wing+1,end=end,lift=lift,tool=toolname,
                                         gaps={k:clearance(posed,v) for k,v in obstacles.items()}))
                # Conservative full vertical swept footprint: capsule radii bound
                # the actual tilted cylinder projections; vertical body is a disk.
                face=(target[0]-10.5*.5,0);bend=(target[0]-35.5*.5,0)
                tip=(target[0]-2.5*.5,0)
                start=(target[0]-1.3,0);elbow=(start[0]-.35*15,.93*15)
                capsules=[('tungsten',tip,face,1),('nozzle',face,bend,5),('body',bend,bend,8),
                          ('wire',start,elbow,.8),('wire-elbow',elbow,elbow,2)]
                for arm in ANGLES:
                    gaps=[]
                    for toolname,a,b,rad in capsules:
                        aa=footprint_point(a,theta-arm);bb=footprint_point(b,theta-arm)
                        # Point capsules avoid division by zero in segment routine.
                        if aa==bb:bb=(bb[0]+1e-10,bb[1])
                        gaps.append((toolname,min(seg_rect(aa,bb,60,90,1.5)-rad,
                                                 seg_rect(aa,bb,90,340,20)-rad,
                                                 point_segment((60,0),aa,bb)-7-rad)))
                    projection.append(dict(pass_name=name,wing=wing+1,end=end,arm=arm,
                                           min_gap=min(v for _,v in gaps),components=dict(gaps)))
    minima={k:min(r['gaps'][k] for r in rows) for k in obstacles}
    worst=min(projection,key=lambda r:r['min_gap'])
    result=dict(configuration='HJ023 fixed external actuator / 150 independent withdrawal',
                checked_poses=len(rows),nominal_minimum_gaps_mm=minima,
                complete_vertical_tool_sweep_projected_minimum_mm=worst,
                dimensional_allowance_mm=.50+.05+.10,
                segment_transition_lift_mm=150,
                parked_tools_z_bounds_mm=[265.2,370.],
                parked_tools_to_working_arm_z_clearance_mm=20.2,
                parked_tools_to_retracted_arm_z_clearance_mm=5.,
                note='Nominal CAD distances use the existing torch/wire; projection is a conservative full vertical sweep bound. Arm local placement tolerance ±0.50, tool pose ±0.05, feature size allowance 0.10. No FE or physical clearance measurement.')
    out=ROOT/'cad/generated/engineering-supplements-20261007/pressure-interface-clearance.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
