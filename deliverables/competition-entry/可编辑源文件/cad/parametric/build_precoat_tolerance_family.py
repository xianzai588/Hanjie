"""Actual R1.5 pocket / normal-offset tolerance corners on the 8P seat."""
import json
import math
from pathlib import Path
import gmsh

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'cad/generated/precoat-tolerance-family-20261007'


def build(depth, retained, radius=1.5):
    gmsh.clear();gmsh.model.add(f'D{depth:.2f}_N{retained:.2f}_R{radius:.2f}')
    occ=gmsh.model.occ
    seat=occ.importShapes(str(ROOT/'simulation/competition-r4/geometry/8P-R2-t15.step'))
    occ.translate(seat,0,0,100)
    original=sum(occ.getMass(*s) for s in seat if s[0]==3)
    top,R,ri,ro=115.,radius,68.98,74.98
    cr,cz=ri+R,top-depth+R

    def pocket(offset):
        radius=R-offset
        if cz<top:
            start=(cr-radius,0,cz)
            roof=(cr-radius,0,top)
            vertical=True
        else:
            # With D<R the actual cutter circle is trimmed by the stock top.
            # An assumed complete quarter arc would have an off-circle start.
            start=(cr-math.sqrt(radius**2-(top-cz)**2),0,top)
            roof=start;vertical=False
        a=occ.addPoint(*roof);b=occ.addPoint(ro,0,top)
        c=occ.addPoint(ro,0,cz-radius);d=occ.addPoint(cr,0,cz-radius)
        centre=occ.addPoint(cr,0,cz)
        end=occ.addPoint(*start) if vertical else a
        curves=[occ.addLine(a,b),occ.addLine(b,c),occ.addLine(c,d),occ.addCircleArc(d,centre,end)]
        if vertical:curves.append(occ.addLine(end,a))
        face=occ.addPlaneSurface([occ.addCurveLoop(curves)])
        ring=[s for s in occ.revolve([(2,face)],0,0,0,0,0,1,2*math.pi) if s[0]==3]
        portions,_=occ.intersect(ring,seat,removeObject=True,removeTool=False)
        return [s for s in portions if s[0]==3]

    full=pocket(0);second=pocket(retained)
    first,_=occ.cut(full,second,removeObject=True,removeTool=False)
    first=[s for s in first if s[0]==3]
    if len(first)!=8 or len(second)!=8:raise RuntimeError('Eight actual wing patches required')
    _,mapping=occ.fragment(seat,first+second);occ.synchronize()
    def ids(start,count):return {t for q in mapping[start:start+count] for d,t in q if d==3}
    one,two=ids(len(seat),8),ids(len(seat)+8,8)
    qt=ids(0,len(seat))-one-two
    groups={'QT450-10':qt,'first_CI_A1':one,'second_bare_Ni99':two}
    volumes={k:sum(occ.getMass(3,t) for t in tags) for k,tags in groups.items()}
    boundary={k:{t for solid in tags for d,t in gmsh.model.getBoundary([(3,solid)],False,False) if d==2} for k,tags in groups.items()}
    bypass=boundary['QT450-10']&boundary['second_bare_Ni99']
    if bypass:raise RuntimeError('Second-layer QT direct-contact bypass')
    closure=sum(volumes.values())-original
    if abs(closure)/original>1e-7:raise RuntimeError('Material partition closure failed')
    for i,(k,tags) in enumerate(groups.items(),1):gmsh.model.addPhysicalGroup(3,sorted(tags),i,k)
    name=f'D{depth:.2f}-N{retained:.2f}-R{radius:.2f}'
    gmsh.write(str(OUT/(name+'.step')))
    return dict(case=name,pocket_depth_mm=depth,retained_normal_mm=retained,QT_radius_mm=R,
                first_machining_radius_mm=R-retained,common_circle_centre_rz_mm=[cr,cz],
                actual_pocket_volume_one_wing_mm3=(volumes['first_CI_A1']+volumes['second_bare_Ni99'])/8,
                retained_first_volume_one_wing_mm3=volumes['first_CI_A1']/8,
                final_second_volume_one_wing_mm3=volumes['second_bare_Ni99']/8,
                material_volumes_mm3=volumes,partition_closure_mm3=closure,
                second_QT_shared_face_area_mm2=0.,full_manufacturing_state_assigned=False)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    gmsh.initialize();gmsh.option.setNumber('General.Terminal',0)
    try:
        cases=[build(1.5,.7)]+[build(d,n,r) for d in [1.4,1.6] for n in [.65,.75] for r in [1.4,1.6]]
    finally:gmsh.finalize()
    rho=.00889;length=19.28169543353246;r=80/110
    deficit=1.2*(1-(1+r+r*r)/3)
    maximum=max(c['actual_pocket_volume_one_wing_mm3'] for c in cases)
    mass=rho*maximum
    feed=[]
    for rate,speed,error in [(.15,100,0),(.15,100,.02),(.15,120,0),(.17,120,0),(.17,120,.02)]:
        t=length/(speed/60*(1+error))-deficit
        feed.append(dict(rate_g_s=rate,nominal_speed_mm_min=speed,relative_speed_upper_scenario=error,
                         deposited_mass_g=rate*t,actual_max_pocket_fill_mass_g=mass,
                         mass_margin_g=rate*t-mass,necessary_nominal_feed_g_s=mass/t,
                         interpretation='historical feed sensitivity and stated speed scenario; not supplier-guaranteed window or local bead coverage'))
    result=dict(cases=cases,QT_radius_tolerance_mm=.1,QT_radius_tolerance_basis='Explicitly retain the existing drawing general +/-0.10mm tolerance; do not narrow it to protect supply margin',maximum_actual_pocket_volume_one_wing_mm3=maximum,
                density_basis_g_mm3=rho,maximum_pocket_fill_mass_g=mass,
                feed_scenarios=feed,
                conditional_zero_overfill_speed_limit_at_015_mm_min=60*length/(mass/.15+deficit),
                local_profile_qualification_required=True,actual_residual_cut_performed=False,
                decision='Retain100mm/min pWPS;120mm/min remains conditional because the historical0.15g/s scenario underfills the actual maximum pocket.')
    (OUT/'geometry-and-feed-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
