"""Four copper sectors with end clearances and port bosses, in working poses."""
import math
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.gp import gp_Pnt,gp_Trsf,gp_Ax1,gp_Dir,gp_Vec
from hanjie.domain.tooling_access import cylinder

def moved(shape,dx=0,dy=0,angle=0):
    tr=gp_Trsf()
    if angle:tr.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),angle)
    else:tr.SetTranslation(gp_Vec(dx,dy,0))
    return BRepBuilderAPI_Transform(shape,tr,True).Shape()

def sectors(gap=2.,stroke=0.):
    from hanjie.domain.competition_design import revolved_section,fuse
    ring=revolved_section([(71.8,90.5),(74.8,90.5),(74.8,99.5),(71.8,99.5)])
    quadrant=BRepPrimAPI_MakeBox(gp_Pnt(gap/2,gap/2,90.4),100,100,9.2).Shape()
    quarter=BRepAlgoAPI_Common(ring,quadrant).Shape()
    boss=BRepPrimAPI_MakeBox(gp_Pnt(69.8,-2,90.5),2,4,6).Shape()
    quarter=fuse([quarter,moved(boss,angle=math.radians(3)),moved(boss,angle=math.radians(87))])
    bodies=[]
    for i in range(4):
        angle=i*math.pi/2
        shape=moved(quarter,angle=angle) if i else quarter
        centre=angle+math.pi/4
        bodies.append(moved(shape,dx=-stroke*math.cos(centre),dy=-stroke*math.sin(centre)))
    return bodies

def backing_ring():
    from hanjie.domain.competition_design import revolved_section,fuse
    ring=revolved_section([(71.8,88.9),(74.8,88.9),(74.8,90.4),(71.8,90.4)])
    # Eight inner ears, flush upper surface and blind/countersunk M3 retention.
    ear=BRepPrimAPI_MakeBox(gp_Pnt(65,-5,88.9),7,10,1.5).Shape()
    return fuse([ring,*[moved(ear,angle=math.radians(22.5+45*i)) for i in range(8)]])

def pan_rim():
    from hanjie.domain.competition_design import revolved_section
    return revolved_section([(66.5,81.59),(74,81.59),(74,87.59),(66.5,87.59)])


def retention_screws():
    """ISO10642 M3x6 maximum outer envelopes; fitting fixes flush head pose."""
    from hanjie.domain.competition_design import revolved_section
    screw=revolved_section([(0,84.39),(1.5,84.39),(1.5,88.53),
                            (3.36,90.39),(0,90.39)])
    return [moved(screw,dx=69*math.cos(math.radians(22.5+45*i)),
                  dy=69*math.sin(math.radians(22.5+45*i))) for i in range(8)]

def lower_stop():
    from hanjie.domain.competition_design import revolved_section
    return revolved_section([(73.7,88.59),(74,88.59),(74,88.9),(73.7,88.9)])

def water_bulkheads():
    """Four welded sealed feedthrough blocks; internal waterways are detailed separately."""
    block=BRepPrimAPI_MakeBox(gp_Pnt(49,-8,83.59),12,16,15.41).Shape()
    return [moved(block,angle=math.radians(45+90*i)) for i in range(4)]
