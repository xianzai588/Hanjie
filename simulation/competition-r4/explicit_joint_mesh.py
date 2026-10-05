"""Conforming QT / two real Ni99 layers / NiFe / steel assembly geometry.

Ni99 replaces the shallow-pocket QT volume below the finished z=115 plane.
No elastic penalty link substitutes for its constitutive response. QT-PMZ
state mapping is a subsequent thermal-field operation, not an assigned strength.
"""
from pathlib import Path
import argparse,json
import gmsh
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def build(n=8,h=1.125,layer_h=.30,total=1.5,first=.656,seat_path=None,output=None,whole_wing=False):
    if not 1.4<=total<=1.6 or not 0<first<total-.5:raise ValueError('layer stack outside the flush-pocket design')
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0);gmsh.model.add('explicit-welded-stack');occ=gmsh.model.occ
        seat=occ.importShapes(str(seat_path or ROOT/'simulation/competition-r4/geometry/8P-R2-t15.step'))
        occ.translate(seat,0,0,100)
        shell=occ.importShapes(str(ROOT/'simulation/structural-v4/common/shell.step'))
        initial_seat_mass=sum(occ.getMass(*ent) for ent in seat if ent[0]==3)
        initial_shell_mass=sum(occ.getMass(*ent) for ent in shell if ent[0]==3)
        ni1=[];ni2=[];roots=[];caps=[];top=115.;angle=18/74.98
        # The pocket must reach the actual wing edge. A 74.97 mm outer
        # radius left a 0.01 mm bare QT strip under the NiFe root.
        pocket_inner=68.98;pocket_outer=74.98
        if whole_wing:
            # Intersect annular bands with the actual wings. Equal angles
            # at all radii leave QT land beside the inward part of a wing.
            for target,z,height in [(ni1,top-total,first),(ni2,top-total+first,total-first)]:
                ring=occ.addCylinder(0,0,z,0,0,height,pocket_outer)
                inner=occ.addCylinder(0,0,z-.01,0,0,height+.02,pocket_inner)
                annulus,_=occ.cut([(3,ring)],[(3,inner)])
                patches,_=occ.intersect(annulus,seat,removeObject=True,removeTool=False)
                target.extend([ent for ent in patches if ent[0]==3])
            if len(ni1)!=n or len(ni2)!=n:raise RuntimeError('whole-wing layer must produce exactly eight actual pocket volumes')
            ni_expected=sum(occ.getMass(*ent) for ent in ni1+ni2)
        for j in range(n):
            for target,z,height in ([] if whole_wing else [(ni1,top-total,first),(ni2,top-total+first,total-first)]):
                rect=occ.addRectangle(pocket_inner,0,z,pocket_outer-pocket_inner,height)
                # A radial-z rectangle lies in y=0, so rotate from x-y plane.
                # addRectangle's height originally advances y; turn it onto z.
                occ.rotate([(2,rect)],pocket_inner,0,z,1,0,0,np.pi/2)
                occ.rotate([(2,rect)],0,0,0,0,0,1,j*2*np.pi/n-angle/2)
                target.append([d for d in occ.revolve([(2,rect)],0,0,0,0,0,1,angle) if d[0]==3][0])
            for target,leg in [(roots,2.8),(caps,4.)]:
                pts=[occ.addPoint(r,0,z) for r,z in [(75-leg,top),(75,top),(75,top+leg)]]
                ls=[occ.addLine(pts[k],pts[(k+1)%3]) for k in range(3)]
                surf=occ.addPlaneSurface([occ.addCurveLoop(ls)])
                occ.rotate([(2,surf)],0,0,0,0,0,1,j*2*np.pi/n-angle/2)
                target.append([d for d in occ.revolve([(2,surf)],0,0,0,0,0,1,angle) if d[0]==3][0])
        objects=seat+shell;tools=ni1+ni2+roots+caps
        ents,maps=occ.fragment(objects,tools)
        occ.synchronize()
        def mapped(start,count):return {tag for row in maps[start:start+count] for dim,tag in row if dim==3}
        qs=mapped(0,len(seat));ss=mapped(len(seat),len(shell));b0=len(objects)
        ns1=mapped(b0,n);ns2=mapped(b0+n,n);ws=mapped(b0+2*n,2*n)
        groups={0:ss,1:qs-ns1-ns2-ws,2:ws,3:ns1,4:ns2}
        if any(not ids for ids in groups.values()):raise RuntimeError('missing explicit material volume')
        if any(groups[a]&groups[b] for a in groups for b in groups if a<b):raise RuntimeError('ambiguous material fragment')
        volumes={str(k):sum(occ.getMass(3,tag) for tag in tags) for k,tags in groups.items()}
        if not whole_wing:ni_expected=n*angle*(pocket_outer**2-pocket_inner**2)/2*total
        # Ni solids must replace QT, not project outside an actual wing.
        closure=(float(volumes['1'])+float(volumes['3'])+float(volumes['4'])-initial_seat_mass)
        if abs(closure)>1e-6 or abs(float(volumes['3'])+float(volumes['4'])-ni_expected)>1e-6:
            raise RuntimeError(f'Ni99 pocket not contained in actual QT seat: volume difference{closure:g}')
        fine=[]
        for tag in ns1|ns2:
            fine += [t for d,t in gmsh.model.getBoundary([(3,tag)],False,False) if d==2]
        distance=gmsh.model.mesh.field.add('Distance');gmsh.model.mesh.field.setNumbers(distance,'FacesList',sorted(set(fine)))
        gmsh.model.mesh.field.setNumber(distance,'Sampling',50)
        threshold=gmsh.model.mesh.field.add('Threshold')
        for key,value in dict(InField=distance,SizeMin=layer_h,SizeMax=min(h*2,2.4),DistMin=.35,DistMax=12).items():gmsh.model.mesh.field.setNumber(threshold,key,value)
        gmsh.model.mesh.field.setAsBackgroundMesh(threshold)
        gmsh.option.setNumber('Mesh.MeshSizeMin',layer_h*.8);gmsh.option.setNumber('Mesh.MeshSizeMax',min(h*2,2.4))
        gmsh.option.setNumber('Mesh.MinimumCirclePoints',200)
        # The real 0.03 mm fit edge needs local short edges, but propagating
        # their size across the entire shell created 2.48 million tetrahedra.
        # Let the explicit distance field govern interior resolution instead.
        gmsh.option.setNumber('Mesh.MeshSizeFromPoints',0)
        gmsh.option.setNumber('Mesh.MeshSizeFromCurvature',0)
        gmsh.option.setNumber('Mesh.MeshSizeExtendFromBoundary',0)
        gmsh.option.setNumber('Mesh.Algorithm3D',1)
        if output:
            Path(output).mkdir(parents=True,exist_ok=True);gmsh.write(str(Path(output)/'explicit-stack.brep'))
        try:gmsh.model.mesh.generate(3)
        except Exception as exc:
            if output:(Path(output)/'mesh-failure.json').write_text(json.dumps(dict(error=str(exc),h=h,layer_h=layer_h,volumes=volumes)),encoding='utf8')
            raise
        tags,xyz,_=gmsh.model.mesh.getNodes();index={int(tag):i for i,tag in enumerate(tags)}
        x=np.array(xyz).reshape(-1,3);elems=[];mats=[]
        for material,entities in groups.items():
            for tag in entities:
                _,conn=gmsh.model.mesh.getElementsByType(4,tag)
                local=np.array([index[int(k)] for k in conn]).reshape(-1,4)
                elems.extend(local);mats.extend([material]*len(local))
        e=np.asarray(elems);m=np.asarray(mats,np.int8)
        used=np.unique(e);remap=np.full(len(x),-1,int);remap[used]=np.arange(len(used));x=x[used];e=remap[e]
        faces=np.sort(np.vstack([e[:,p] for p in [[0,1,2],[0,1,3],[0,2,3],[1,2,3]]]),axis=1)
        uf,cnt=np.unique(faces,axis=0,return_counts=True)
        if cnt.max()>2:raise RuntimeError('non-manifold tetrahedral face')
        bd=uf[cnt==1]
        audit=dict(material_ids={'0':'Q235B','1':'QT450-10','2':'NiFe55','3':'first Ni99','4':'second Ni99'},
            solid_volumes_mm3=volumes,Ni99_replacement_volume_error_mm3=closure,
            expected_Ni99_volume_mm3=ni_expected,original_QT_volume_mm3=initial_seat_mass,original_shell_volume_mm3=initial_shell_mass,
            expected_volume_basis='OCC intersection of annular layer and actual wings' if whole_wing else 'analytic annular-sector volume',
            total_layer_mm=total,first_layer_mm=first,finished_top_z_mm=top,layer_mesh_mm=layer_h,
            pocket_inner_radius_mm=pocket_inner,pocket_outer_radius_mm=pocket_outer,
            pocket_coverage='actual entire wing radial band' if whole_wing else '18 mm angular patch',
            nodes=len(x),tetrahedra=len(e),constitutive_interface='shared conforming nodes; no penalty springs',
            PMZ_state_or_capacity_assigned=False)
        if output:
            output=Path(output);output.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(output/'mesh.npz',x=x,e=e,material=m,boundary=bd)
            (output/'geometry-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
        return x,e,m,bd,audit
    finally:gmsh.finalize()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--h',type=float,default=1.125)
    p.add_argument('--layer-h',type=float,default=.30);p.add_argument('--total',type=float,default=1.5);p.add_argument('--first',type=float,default=.656)
    p.add_argument('--whole-wing',action='store_true')
    a=p.parse_args();*_,audit=build(h=a.h,layer_h=a.layer_h,total=a.total,first=a.first,output=a.output,whole_wing=a.whole_wing)
    print(json.dumps(audit,indent=2))
