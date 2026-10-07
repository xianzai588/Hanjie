"""Volume-equivalent one-wing MMA deposit on the actual R1.5 pocketed seat.

This is a mass-closed numerical envelope for model setup, not an actual bead
shape or a proven fused area. The 0.70 mm layer is only the later retained CAD.
"""
from pathlib import Path
import json
import math
import gmsh
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'cad/generated/mma-mass-envelope'


def build(candidate,mesh_h=None,single_track=False):
    budget=json.loads((ROOT/'studies/COMPETITION-DESIGN/results/precoat-input-budget.json').read_text(encoding='utf8'))
    row=budget['candidates'][candidate];rho=row['input']['nominal_density_kg_m3']*1e-6
    target_volume=row['nominal_deposited_mass_per_wing_g']/rho
    out=OUT/(candidate+'-single-track' if single_track else candidate);out.mkdir(parents=True,exist_ok=True)
    if (out/'geometry-audit.json').exists():raise ValueError('Preserve the completed envelope; use a fresh case')
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0);occ=gmsh.model.occ
        imported=occ.importShapes(str(ROOT/'cad/generated/independent-precoat-curved/precoat-stack-R15-R08.brep'))
        occ.synchronize()
        qt_tags={tag for dim,tag in imported if dim==3 and occ.getMass(dim,tag)>10000}
        positive=lambda ent:occ.getCenterOfMass(*ent)[0]>65 and abs(occ.getCenterOfMass(*ent)[1])<.01
        base=[ent for ent in imported if ent[0]==3 and ent[1] not in qt_tags and positive(ent)]
        if len(qt_tags)!=1 or len(base)!=2:raise RuntimeError('The saved conformal one-wing layers were not identified')
        single_inputs=None
        if single_track:
            radius_track=71.98
            first=next(tag for dim,tag in base if gmsh.model.isInside(3,tag,[radius_track,0.,113.85]))
            ends=[]
            for sign in (-1,1):
                lo,hi=0.,.3
                for _ in range(38):
                    mid=(lo+hi)/2
                    if gmsh.model.isInside(3,first,[radius_track*math.cos(mid),sign*radius_track*math.sin(mid),113.85]):lo=mid
                    else:hi=mid
                ends.append(sign*(lo+hi)/2)
            length=radius_track*(ends[1]-ends[0]);speed=100/60;mass_rate=.17
            target_volume=mass_rate*length/speed/rho
            single_inputs=dict(radius_mm=radius_track,length_mm=length,travel_mm_s=speed,
                deposited_mass_rate_g_s=mass_rate,arc_time_s=length/speed,
                meaning='single6mm groove coverage hypothesis; mass rate is within the previous engineering interval, not a measured rate')
        top=115.;radius=1.5
        roofs=[ent for body in base for ent in gmsh.model.getBoundary([body],False,False)
               if ent[0]==2 and abs(occ.getCenterOfMass(*ent)[2]-top)<1e-7]
        plan_area=sum(occ.getMass(*roof) for roof in roofs)
        pocket_volume=sum(occ.getMass(*body) for body in base)
        height=(target_volume-pocket_volume)/plan_area
        if height<=0:raise ValueError('This envelope construction requires enough metal to fill the complete pocket')
        print('Reuse saved R1.5 substrate; first-envelope overfill',height,flush=True)
        # Extrude the existing roof faces directly. They remain shared by the
        # original pocket filling and the added overfill. No duplicate cut/
        # full-circle boolean is needed for the already validated substrate.
        cap=[ent for ent in occ.extrude(roofs,0,0,height) if ent[0]==3]
        ni_tags={ent[1] for ent in base+cap}
        keep=qt_tags|ni_tags
        unused=[ent for ent in occ.getEntities(3) if ent[1] not in keep]
        if unused:occ.remove(unused,recursive=True)
        occ.synchronize()
        volumes={name:sum(occ.getMass(3,t) for t in tags) for name,tags in [('QT',qt_tags),('MMA',ni_tags)]}
        if abs(volumes['MMA']-target_volume)>1e-4:raise RuntimeError('Nominal deposition mass and CAD volume do not close')
        groups={1:qt_tags,3:ni_tags}
        for number,tags in groups.items():
            pg=gmsh.model.addPhysicalGroup(3,sorted(tags),number)
            gmsh.model.setPhysicalName(3,pg,'QT450-10' if number==1 else candidate+' nominal deposit envelope')
        gmsh.write(str(out/'first-mass-envelope.brep'));gmsh.write(str(out/'first-mass-envelope.step'))
        audit=dict(candidate=candidate,source='simulation/competition-r4/geometry/8P-R2-t15.step',
            source_inputs='project/independent-precoat-candidates.yaml',plan_area_one_wing_mm2=plan_area,
            pocket_volume_one_wing_mm3=pocket_volume,target_deposited_volume_one_wing_mm3=target_volume,
            nominal_overfill_above_z115_mm=height,volume_equivalent_floor_to_top_mm=radius+height,
            nominal_top_z_mm=top+height,material_volumes_mm3=volumes,
            deposited_mass_one_wing_g=volumes['MMA']*rho,
            mass_closure_error_g=(volumes['MMA']-target_volume)*rho,
            geometry_state='before first-layer machining; one wing deposited and all eight pockets cut',
            shape_interpretation='volume-equivalent uniform overfill, not actual bead geometry or a conservative thermal bound',
            fusion_assigned=False,physical_bead_shape_verified=False,
            residual_state_assigned=False,mesh_generated=False)
        if single_inputs:audit['single_track_inputs']=single_inputs
        if mesh_h:
            surfaces=[s[1] for t in ni_tags for s in gmsh.model.getBoundary([(3,t)],False,False) if s[0]==2]
            distance=gmsh.model.mesh.field.add('Distance')
            gmsh.model.mesh.field.setNumbers(distance,'FacesList',sorted(set(surfaces)))
            gmsh.model.mesh.field.setNumber(distance,'Sampling',60)
            threshold=gmsh.model.mesh.field.add('Threshold')
            for key,value in dict(InField=distance,SizeMin=mesh_h,SizeMax=2.4,DistMin=1.,DistMax=18.).items():gmsh.model.mesh.field.setNumber(threshold,key,value)
            gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
            for key,value in [('Mesh.MeshSizeFromPoints',0),('Mesh.MeshSizeFromCurvature',0),
                 ('Mesh.MeshSizeExtendFromBoundary',0),('Mesh.MeshSizeMin',mesh_h*.8),
                 ('Mesh.MeshSizeMax',2.4),('Mesh.MinimumCirclePoints',40),('Mesh.Algorithm3D',1)]:gmsh.option.setNumber(key,value)
            print('Generate the one-wing mass-envelope mesh',flush=True)
            gmsh.model.mesh.generate(3)
            tags,xyz,_=gmsh.model.mesh.getNodes();index={int(t):i for i,t in enumerate(tags)}
            x=np.asarray(xyz).reshape(-1,3);elements=[];materials=[]
            for material,entities in groups.items():
                for tag in entities:
                    _,conn=gmsh.model.mesh.getElementsByType(4,tag)
                    local=np.array([index[int(t)] for t in conn]).reshape(-1,4)
                    elements.extend(local);materials.extend([material]*len(local))
            e=np.asarray(elements);m=np.asarray(materials,np.int8)
            used=np.unique(e);remap=np.full(len(x),-1,int);remap[used]=np.arange(len(used));x=x[used];e=remap[e]
            np.savez_compressed(out/'mesh.npz',x=x,e=e,material=m)
            audit.update(mesh_generated=True,layer_mesh_h_mm=mesh_h,nodes=len(x),tetrahedra=len(e))
        (out/'geometry-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
        return audit
    finally:gmsh.finalize()


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--candidate',choices=['CI-A1','CI-A2'],required=True)
    p.add_argument('--mesh-h',type=float)
    p.add_argument('--single-track',action='store_true')
    a=p.parse_args();print(json.dumps(build(a.candidate,a.mesh_h,a.single_track),ensure_ascii=False,indent=2))
