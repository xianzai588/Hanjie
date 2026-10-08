"""HJ-F-S01-R2: complete-ring tooling, independent of the old wing portal.

Working, unlocked and transferred assemblies are exported and reopened.
All parts are nominal solids. Purchased actuator/hose models are installation
envelopes; their material volume is excluded from the fabricated mass total.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from xml.sax.saxutils import escape

import cadquery as cq

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "cad/parametric"))
from build_ring_baseline import export_step, recheck_step, render_png
from hanjie.domain.copper_sectors import sectors, backing_ring, water_bulkheads
from hanjie.domain.water_route import bends, moving_elbow_envelopes, moving_union_envelopes

OUT = ROOT / "cad/generated/ring-fixture"
STUDY = ROOT / "studies/COMPETITION-DESIGN/ring-fixture-feasibility.py"


def cyl(d, z, h, x=0, y=0):
    return cq.Solid.makeCylinder(d/2, h, cq.Vector(x,y,z))


def ring(di, do, z, h):
    return cyl(do,z,h).cut(cyl(di,z-.01,h+.02))


def box(w,d,z,h,x=0,y=0):
    return cq.Solid.makeBox(w,d,h,cq.Vector(x-w/2,y-d/2,z))


def tube_along(d, start, direction, length):
    return cq.Solid.makeCylinder(d/2,length,cq.Vector(*start),cq.Vector(*direction))


def overlap(a,b):
    return max(0., a.intersect(b).Volume())


def dist(a,b):
    return float(a.distance(b))


def disc_horizontal_sweep(d, z, h, travel_y):
    """Exact solid-disc sweep from (0, +travel_y) to the fixture axis."""
    return cyl(d,z,h).fuse(cyl(d,z,h,0,travel_y),
                           box(d,travel_y,z,h,0,travel_y/2))


def build():
    spec=importlib.util.spec_from_file_location("ring_fixture_analysis", STUDY)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    result=module.evaluate_real_fixture()
    inp=result["inputs"]; anchors=result["anchors"]["coordinates_mm"]
    cone=cq.Solid.makeCone(inp["cone_bottom_diameter_mm"]/2,inp["cone_top_diameter_mm"]/2,
                           15.4,cq.Vector(0,0,99.8))
    base=box(460,400,-100,80).fuse(cyl(144,-20,100),cyl(96,80,19.8),cone)
    bed=box(460,400,-200,100)
    anchor_shapes=[]
    for x,y in anchors:
        base=base.cut(cyl(33,-100.01,80.02,x,y))
        bed=bed.cut(cyl(27,-160,60.01,x,y))
        anchor_shapes.append(cyl(29.4,-160,140,x,y).fuse(cyl(45,-20,30,x,y)))
    # Separate wet/dry cross drilling is entirely below the independent A ring.
    water_points=[]
    for q in range(4):
        a=math.radians(45+90*q); direction=(math.cos(a),math.sin(a),0)
        for r in (52.,58.):
            for t in (-4.,4.):
                x=r*math.cos(a)-t*math.sin(a); y=r*math.sin(a)+t*math.cos(a)
                z=-40. if r==52 else -30.
                base=base.cut(cyl(4,z,80-z+.01,x,y))
                base=base.cut(tube_along(4,(x,y,z),direction,400))
                water_points.append((x,y,r,z))
    for x in (-62.,62.):
        base=base.cut(cyl(6,-55,135.01,x,0))
        base=base.cut(tube_along(6,(x,0,-55),(1 if x>0 else -1,0,0),200))
    columns=[]
    bridge=box(340,220,400,80).cut(cyl(110,399.99,80.02))
    bridge_bolts=[]
    for x in (-140.,140.):
        p=cyl(70,-20,420,x)
        for y in (-18.,18.):
            p=p.cut(cyl(13,370,30.01,x,y))
            bridge=bridge.cut(cyl(17.5,399.99,80.02,x,y))
            bridge_bolts.append(cyl(15.5,370,110,x,y).fuse(cyl(24,480,16,x,y)))
        columns.append(p)
    stops=[]; open_stops=[]
    for sign in (-1,1):
        low=42 if sign>0 else -104
        bridge=bridge.cut(cq.Solid.makeBox(62,30,20.01,cq.Vector(low,-15,460)))
        stop=cq.Solid.makeBox(26,30,20,cq.Vector(42 if sign>0 else -68,-15,460))
        stops.append(stop); open_stops.append(stop.translate((sign*30,0,0)))
    # Slotted, positive-withdrawal sleeve with a real annular neck and root.
    working=cyl(40,99.8,15.6).cut(cone)
    working=working.fuse(ring(38.34,39.94,115.4,30),ring(38.34,46,145.4,10))
    collapsed_cone=cq.Solid.makeCone(inp["cone_bottom_diameter_mm"]/2-.03,
                         inp["cone_top_diameter_mm"]/2-.03,15.4,cq.Vector(0,0,99.8))
    collapsed=cyl(39.94,99.8,15.6).cut(collapsed_cone)
    collapsed=collapsed.fuse(ring(38.34,39.94,115.4,30),ring(38.34,46,145.4,10))
    for a in range(0,360,60):
        slit=cq.Solid.makeBox(25,.8,50.6,cq.Vector(0,-.4,99.79)).rotate((0,0,0),(0,0,1),a)
        working=working.cut(slit); collapsed=collapsed.cut(slit)
    stem=ring(24,70,155.4,284.6).fuse(ring(24,100,440,20))
    pressure=ring(48,100,115,8).fuse(ring(72,100,123,32))
    actuator=ring(72,100,155,20)  # purchased annular actuator envelope
    collar=ring(70,100,175,5)
    holder=ring(150.2,180,-20,20)
    for a in range(0,360,60):
        slot=cq.Solid.makeBox(4,8.2,2.4,cq.Vector(87,-4.1,-12.2)).rotate((0,0,0),(0,0,1),a)
        holder=holder.cut(slot)
    # Fixed pan: continuously welded central Ø96 neck, raised outer carrier.
    pan=ring(96,148,83.59,1).fuse(ring(133,148,84.59,4.31),cq.Shape.cast(backing_ring()))
    blocks=[cq.Shape.cast(s) for s in water_bulkheads()]
    for block in blocks: pan=pan.fuse(block)
    # Bore the 16 stationary sealed water risers through the pan and water blocks.
    risers=[]
    for x,y,r,z in water_points:
        height=94.0 if r==52 else 92.0
        pan=pan.cut(cyl(3,83.58,height-83.58+.01,x,y))
        # Blind vertical bore meets a tangential side outlet. No open hole in
        # the block top; the four streams in each block remain separate.
        # The ports were created at quadrant bisectors 45+90*q.
        nearest=min((math.radians(45+90*q) for q in range(4)),
                    key=lambda t: abs(math.atan2(math.sin(math.atan2(y,x)-t),math.cos(math.atan2(y,x)-t))))
        tangent=(-math.sin(nearest),math.cos(nearest),0)
        tangential=x*tangent[0]+y*tangent[1]
        sign=1 if tangential>0 else -1
        pan=pan.cut(tube_along(2.5,(x,y,height),tuple(sign*v for v in tangent),5.0))
        risers.append(ring(2.5,4,80,3.59).translate((x,y,0)))
    gas_risers=[]
    for x in (-62.,62.):
        pan=pan.cut(cyl(6,83.58,1.03,x,0))
        gas_risers.append(ring(4,6,80,6).translate((x,0,0)))
    copper=[cq.Shape.cast(s) for s in sectors(stroke=0)]
    copper_open=[cq.Shape.cast(s) for s in sectors(stroke=1.1)]
    elbows=[cq.Shape.cast(s) for s in moving_elbow_envelopes()]
    unions=[cq.Shape.cast(s) for s in moving_union_envelopes()]
    curves,radii,lengths=bends(count=41)
    hoses=[]
    for curve in curves:
        pts=[cq.Vector(*p) for p in curve]
        path=cq.Wire.assembleEdges([cq.Edge.makeSpline(pts)])
        tangent=pts[1]-pts[0]
        plane=cq.Plane(origin=pts[0],normal=tangent)
        hoses.append(cq.Workplane(plane).circle(1.5).sweep(path,isFrenet=True).val())
    shell=ring(150,160,0,200); seat=ring(40,149.96,100,15)
    # No-hole lid cannot rise vertically through the fixed reverse taper.
    # After product lift, it enters laterally at lower z116.7 and rises 0.8.
    cover=cyl(180,117.5,2)
    gasket=ring(156,172,119.5,.5)
    rows=[]
    def add(code,name,material,shapes,scope="fabricated"):
        if not isinstance(shapes,list): shapes=[shapes]
        density={"45钢":7.85e-6,"Q355B":7.85e-6,"17-4PH":7.75e-6,
                 "C11000":8.96e-6,"304":7.93e-6,"8.8":7.85e-6,"PTFE":2.2e-6}.get(material)
        rows.append({"code":code,"name":name,"material":material,"quantity":len(shapes),
                     "shapes":shapes,"scope":scope,
                     "nominal_solid_mass_kg":sum(s.Volume() for s in shapes)*density if density else None})
    add("RF01","整体下背承座；含3°反锥和分区内钻气水路","45钢",base)
    add("RF02","连续贴合钢床座；下机台另核刚度","Q355B",bed,"machine_bed")
    add("RF03","双立柱Ø70×420；连接面磨削","45钢",columns)
    add("RF04","上桥340×220×80；中央Ø110","45钢",bridge)
    add("RF05","六指胀套；17-4PH热处理后配锥精磨","17-4PH",working)
    add("RF06","上承力筒Ø70/24；Ø100头部止挡","45钢",stem)
    add("RF07","双正向止挡26×30×20；外退30","45钢",stops)
    add("RF08","独立压环OD100/ID48；500N球面推力","304",pressure)
    add("RF09","压环气缸安装包络OD100/ID72×20","采购件",actuator,"purchased_envelope")
    add("RF10","气缸反力 collar；径向浮动连接","304",collar)
    add("RF11","A基准托环OD180/ID150.20±0.04×20","45钢",holder)
    add("RF12","铜瓣屏障；现有四瓣与水口接口","C11000",copper)
    add("RF13","固定接料盘、铜背承、水口块；中央Ø96气密焊接","C11000",pan)
    add("RF14","底座18-M30×140，100±10kN/只","8.8",anchor_shapes,"standard_part_envelope")
    add("RF15","上桥4-M16×110，20±2kN/只","8.8",bridge_bolts,"standard_part_envelope")
    add("RF16","水管接头及刚性端口安装包络","采购件",elbows+unions,"purchased_envelope")
    add("RF17","PFA短软管16根OD3；恒长弯曲路径","采购件",hoses,"purchased_envelope")
    add("RF18","密封水立管16根OD4/ID2.5×3.59","304",risers)
    add("RF19","独立气立管2根OD6/ID4×6","304",gas_risers)
    add("RF20","转运洁净底盖OD180×2","304",cover,"transfer_accessory")
    add("RF21","转运静密封圈；干净软接触","PTFE",gasket,"transfer_accessory")
    # nominal interference between mating threads is intentional and excluded.
    fixed=[base,bed,*columns,bridge,*anchor_shapes,*bridge_bolts,pan,*risers,*gas_risers]
    upper=[working,stem,pressure,actuator,collar]
    work=[*fixed,*stops,holder,*copper,*elbows,*unions,*hoses,*upper,shell,seat]
    open_work=[*fixed,*open_stops,holder,*copper_open,*upper,shell,seat]
    raised_upper=[s.translate((0,0,260)) for s in [collapsed,stem,pressure,actuator,collar]]
    raised_holder=holder.translate((0,0,140)); raised_shell=shell.translate((0,0,140)); raised_seat=seat.translate((0,0,140))
    released=[*fixed,*open_stops,*copper_open,*raised_upper,raised_holder,raised_shell,raised_seat,cover,gasket]
    body_union=base.fuse(pan,*risers,*gas_risers)
    active_gaps={"shell_to_main_column_mm":75-72,"water_block_to_neck_mm":dist(cq.Compound.makeCompound(blocks),cyl(96,80,19.8)),
                 "copper_top_to_ring_bottom_mm":100-99.5,"neck_top_to_ring_bottom_mm":100-99.8,
                 "pressure_to_weld_inner_edge_mm":70.7-50,"collapsed_sleeve_to_bore_radial_mm":(40-39.94)/2,
                 "raised_shell_top_to_bridge_bottom_mm":400-340,"raised_holder_bottom_to_cone_top_mm":120-115.2,
                 "raised_sleeve_bottom_to_product_top_mm":359.8-340,
                 "raised_pressure_bottom_to_product_top_mm":375-340,"head_to_open_stop_radial_mm":72-50,
                 "transfer_gripper_envelope_to_column_mm":140-35-103,
                 "transfer_lid_bottom_to_cone_top_mm":117.5-115.2,
                 "lid_lateral_entry_bottom_to_cone_top_mm":116.7-115.2,
                 "lid_lateral_entry_gasket_top_to_holder_bottom_mm":120-(120-.8),
                 "lid_installation_radius_to_column_inner_edge_mm":140-35-90}
    shell_sweep=ring(150,160,0,340)
    seat_sweep=ring(40,149.96,100,155)
    holder_sweep=ring(150.16,180,-20,160)
    radial_fixture=cq.Compound.makeCompound([body_union,*copper_open,*columns])
    intersections={"raised_product_shell_vs_fixed_sweep_mm3":overlap(shell_sweep,radial_fixture),
                   "raised_product_ring_vs_fixed_sweep_mm3":overlap(seat_sweep,radial_fixture),
                   "raised_A_holder_vs_fixed_sweep_mm3":overlap(holder_sweep,radial_fixture),
                   "collapsed_sleeve_after_1_5mm_vs_fixed_core_mm3":overlap(collapsed.translate((0,0,1.5)),cone),
                   "working_seat_vs_fixed_cartridge_mm3":overlap(seat,body_union),
                   "product_vs_raised_upper_mm3":overlap(cq.Compound.makeCompound([raised_shell,raised_seat]),cq.Compound.makeCompound(raised_upper))}
    # Continuous swept solids, not just endpoint poses. RF20's disc sweep is
    # exact; RF21 horizontal sweep uses the full OD172 disc as a conservative
    # superset of its annular geometry. The vertical sweep retains its real ID.
    lid_lateral=disc_horizontal_sweep(180,116.7,2,200).fuse(
        disc_horizontal_sweep(172,118.7,.5,200))
    lid_press=cyl(180,116.7,2.8).fuse(ring(156,172,118.7,1.3))
    lid_targets={
        "fixed_lower_tools":cq.Compound.makeCompound([base,bed,*anchor_shapes,pan,
            *risers,*gas_risers,*copper_open,*elbows,*unions,*hoses]),
        "columns_bridge_and_stops":cq.Compound.makeCompound([
            *columns,bridge,*bridge_bolts,*open_stops]),
        "raised_product":cq.Compound.makeCompound([raised_shell,raised_seat]),
        "raised_A_holder":raised_holder,
        "raised_upper_tools":cq.Compound.makeCompound(raised_upper),
    }
    for stage,sweep in (("lateral",lid_lateral),("vertical_press",lid_press)):
        if not sweep.isValid(): raise RuntimeError(f"Invalid lid {stage} swept solid")
        for target,geometry in lid_targets.items():
            intersections[f"RF20_RF21_{stage}_vs_{target}_sweep_mm3"]=overlap(sweep,geometry)
    result["lid_installation"]={
        "preconditions":"上工具累计升260、产品与A托环升140并接管；在洁净罩内执行",
        "lateral_start_center_xy_mm":[0,200],"lateral_end_center_xy_mm":[0,0],
        "lateral_lid_lower_z_mm":116.7,"lateral_gasket_top_z_mm":119.2,
        "final_vertical_lift_mm":.8,"final_lid_lower_z_mm":117.5,
        "final_gasket_top_z_mm":120.,
        "path":"盖从+y≥200在下表面z116.7横插至轴心，再升0.8贴合/锁定；不得从站底竖直穿过固定反锥",
        "sweep_method":"RF20横插为精确圆盘扫掠；RF21横插采用外径172实心圆盘保守包络；竖向0.8为圆盘与真实环形密封的连续扫掠",
        "qualification_scope":"名义刚性几何；RF21终态与托环下面仅接触，密封压缩/锁扣反馈/安装公差由首件确认",
    }
    if max(intersections.values())>1e-5 or min(active_gaps.values())<=0:
        raise RuntimeError(f"Fixture motion/interference failure: {intersections}; {active_gaps}")
    return rows,work,open_work,released,result,active_gaps,intersections,{"minimum_bend_radius_mm":min(radii),"maximum_hose_length_mm":max(lengths),"hose_outer_diameter_mm":3,"flow_pressure_qualification":"水路为分区安装设计；流量/压降/气密性按水路卡及整站资格检查"}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows,working,unlocked,released,result,gaps,intersections,water=build()
    exports=[]
    for name,shapes in [("ring-fixture-assembly.step",working),("HJ-F-S01-ring-fixture-unlocked.step",unlocked),("HJ-F-S01-ring-fixture-release.step",released)]:
        for shape in shapes:
            if not shape.isValid() or len(shape.Solids())!=1: raise RuntimeError(f"Invalid or multibody component in {name}")
        target=OUT/name
        export_step(target,[s.wrapped for s in shapes]); exports.append(recheck_step(target,len(shapes)))
    for row in rows:
        target=OUT/f"{row['code']}.step"
        export_step(target,[s.wrapped for s in row["shapes"]]); recheck_step(target,len(row["shapes"]))
    public=[{k:v for k,v in row.items() if k!="shapes"} for row in rows]
    fabricated=sum(row["nominal_solid_mass_kg"] for row in rows if row["scope"]=="fabricated")
    bed=sum(row["nominal_solid_mass_kg"] for row in rows if row["scope"]=="machine_bed")
    standard=sum(row["nominal_solid_mass_kg"] for row in rows if row["scope"]=="standard_part_envelope")
    manifest={"version":"HJ-F-S01-R2","design_identity":result["design_identity"],"bom":public,
              "working_solid_count":len(working),"step_rechecks":exports,
              "mass_summary_kg":{"fabricated_fixture_components":fabricated,"supplied_steel_machine_bed":bed,
                                 "standard_hardware_solid_envelopes":standard,"fabricated_plus_bed":fabricated+bed},
              "mass_scope":"CAD实体质量；采购气缸、PFA管、安装接头包络不按实心质量累计；机器人、机台、泵箱、罩体及转运器不属于本质量范围",
              "clearances_mm":gaps,"sweep_intersection_volumes_mm3":intersections,"water_route":water,
              "motion_certificate":{"fixed_items":"RF01/RF02/RF03/RF04/RF13、下反锥与铜瓣保持站内原位；铜瓣仅径退1.10",
                                    "upper_lift_mm":260,"product_and_A_holder_lift_mm":140,"stop_retraction_mm":30,
                                    "lid_installation":result["lid_installation"],
                                    "product_horizontal_exit":"升140并封底后沿+y横移360；外包络R103与双柱内缘R105相差2mm，顶部z340低于桥底400",
                                    "upper_lift":"塌缩Ø39.94在Ø40孔内径向净隙0.03；根部/压环均始于孔上方，Ø100头通过Ø110桥孔；止挡先外退",
                                    "core_withdrawal":"1.5mm主动上退给3°锥径向释放0.0786mm，高于Ø40.04→39.94所需0.05mm；µ>tan3°时须动力退锥",
                                    "cleanliness":"停弧后盘仍朝上接退工具落物；抬离在洁净罩内执行，升140后RF20在z116.7由+y200横插、升0.8封底再横移；不得从产品内清盘或磨削",
                                    "scope":"所列名义部件连续轴向扫掠与横移包络；机器人运动学、管路连接力和制造公差按首件执行"}}
    (OUT/"geometry-quality-and-bom.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    with (OUT/"HJ-F-S01-BOM.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["code","name","material","quantity","scope","nominal_solid_mass_kg"]);writer.writeheader();writer.writerows(public)
    result["cad_assembly"]={"manifest":"cad/generated/ring-fixture/geometry-quality-and-bom.json","working_solid_count":len(working),
                           "all_exported_solids_valid":True,"mass_summary_kg":manifest["mass_summary_kg"],"mass_scope":manifest["mass_scope"]}
    result["motion_clearances_mm"]=gaps
    (ROOT/"studies/COMPETITION-DESIGN/results/ring-fixture-feasibility.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    spec=importlib.util.spec_from_file_location("fixture_drawings",Path(__file__).with_name("drawings.py")); drawings=importlib.util.module_from_spec(spec);spec.loader.exec_module(drawings)
    drawings.create(OUT,manifest,result)
    print(json.dumps({"fixture_directory":str(OUT),"working_solids":len(working),"mass":manifest["mass_summary_kg"],"cold_with_seating_um":result["cold_structural_plus_seating_allocation_um"]},ensure_ascii=False))


if __name__=="__main__": main()
