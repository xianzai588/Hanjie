"""Complete-ring 20 mm root/cap conforming mesh with the real open fit gap."""
import hashlib
import json
import math
from pathlib import Path
import gmsh
import numpy as np
import yaml
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'simulation/ring-baseline-structure'))
from geometry_audit import audit_unwelded_gap
LEVELS={'coarse':(6.,1.),'medium':(4.5,.75)}

def key(level):
    cad=ROOT/'cad/generated/ring-baseline/ring-precoat-eight-windows-17solids.step'
    return dict(schema='ring-final-conforming-v3',process_version=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text())['version'],
      cad_data_sha256=hashlib.sha256(cad.read_bytes().split(b'DATA;',1)[1].split(b'ENDSEC;',1)[0]).hexdigest(),
      bulk_mm=LEVELS[level][0],local_mm=LEVELS[level][1],arc_length_mm=20.,root_leg_mm=2.8,cap_leg_mm=4.,
      shell_surface='2mm z90..125; smoothly coarsen away from open fit-gap band',interface='conforming_shared_nodes')

def build(level):
    folder=HERE/'results'/level;folder.mkdir(parents=True,exist_ok=True);cache=key(level)
    if (folder/'mesh.npz').exists():
        summary=json.loads((folder/'mesh-summary.json').read_text())
        if summary.get('cache_key')!=cache:raise RuntimeError('stale mesh cache: CAD/process/discretization differs; rebuild this level')
        d=dict(np.load(folder/'mesh.npz'))
        summary['actual_faceted_gap_audit']=audit_unwelded_gap(dict(points=d['x'],tetrahedra=d['e'],material_ids=d['material'],triangles=d['boundary']),reject=True)
        (folder/'mesh-summary.json').write_text(json.dumps(summary,indent=2))
        return d,summary
    far,local=LEVELS[level];gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0);gmsh.option.setNumber('General.NumThreads',1)
        gmsh.model.add('ring-final-conforming');occ=gmsh.model.occ
        parents=[v for v in occ.importShapes(str(ROOT/'cad/generated/ring-baseline/ring-precoat-eight-windows-17solids.step')) if v[0]==3]
        if len(parents)!=17:raise RuntimeError('17 retained-material solids required')
        mids=[1 if occ.getMass(*v)>1000 else 3 if occ.getMass(*v)>100 else 4 for v in parents]
        shell=occ.cut([(3,occ.addCylinder(0,0,0,0,0,200,80))],[(3,occ.addCylinder(0,0,0,0,0,200,75))])[0]
        roots=[];caps=[]
        for j in range(8):
            for dst,leg in ((roots,2.8),(caps,4.)):
                ps=[occ.addPoint(r,0,z) for r,z in [(75-leg,115),(75,115),(75,115+leg)]]
                es=[occ.addLine(ps[i],ps[(i+1)%3]) for i in range(3)]
                face=occ.addPlaneSurface([occ.addCurveLoop(es)]);span=20/74.98
                occ.rotate([(2,face)],0,0,0,0,0,1,j*math.pi/4-span/2)
                dst.append([v for v in occ.revolve([(2,face)],0,0,0,0,0,1,span) if v[0]==3][0])
        _,maps=occ.fragment(parents+shell+roots+caps,[]);occ.synchronize()
        mapped=[{tag for dim,tag in row if dim==3} for row in maps]
        roots=set().union(*mapped[18:26]);caps=set().union(*mapped[26:34])-roots
        regions={i:set() for i in range(1,6)}
        for mid,tags in zip(mids,mapped[:17]):regions[mid]|=tags
        regions[2]=mapped[17];regions[5]=roots|caps
        if any(regions[a]&regions[b] for a in regions for b in regions if a<b):raise RuntimeError('ambiguous material partition')
        surfs={mid:{tag for v in vs for dim,tag in gmsh.model.getBoundary([(3,v)],oriented=False) if dim==2} for mid,vs in regions.items()}
        interfaces={name:surfs[a]&surfs[b] for name,a,b in [('QT_first',1,3),('first_second',3,4),('second_final',4,5),('final_shell',5,2),('QT_final',1,5)]}
        if any(not interfaces[k] for k in ('QT_first','first_second','second_final','final_shell')) or interfaces['QT_final']:raise RuntimeError('nominal layer path invalid')
        gmsh.option.setNumber('Mesh.MeshSizeMin',local);gmsh.option.setNumber('Mesh.MeshSizeMax',far);gmsh.option.setNumber('Mesh.Algorithm3D',1)
        points={tag for f in surfs[3]|surfs[4]|surfs[5] for dim,tag in gmsh.model.getBoundary([(2,f)],recursive=True) if dim==0}
        gmsh.model.mesh.setSize([(0,p) for p in points],local)
        field=gmsh.model.mesh.field.add('MathEval');gmsh.model.mesh.field.setString(field,'F',f'Min({far},2+Max(0,Abs(z-107.5)-17.5)*0.3)')
        restriction=gmsh.model.mesh.field.add('Restrict');gmsh.model.mesh.field.setNumber(restriction,'InField',field);gmsh.model.mesh.field.setNumbers(restriction,'SurfacesList',sorted(surfs[2]))
        gmsh.model.mesh.field.setAsBackgroundMesh(restriction);gmsh.model.mesh.generate(3);gmsh.model.mesh.optimize('Netgen')
        tags,xyz,_=gmsh.model.mesh.getNodes();idx={int(t):i for i,t in enumerate(tags)};x=np.asarray(xyz).reshape(-1,3)
        elems=[];material=[];weldpass=[];quality=[]
        for mid,vs in regions.items():
            for v in vs:
                et,co=gmsh.model.mesh.getElementsByType(4,v);elems.extend(np.asarray([idx[int(n)] for n in co]).reshape(-1,4));material.extend([mid]*len(et));weldpass.extend([0 if v in roots else 1 if v in caps else -1]*len(et));quality.extend(gmsh.model.mesh.getElementQualities(et,'minSICN'))
        e=np.asarray(elems,np.int32);m=np.asarray(material,np.int8);wp=np.asarray(weldpass,np.int8);used=np.unique(e);remap=np.full(len(x),-1,int);remap[used]=np.arange(len(used));x=x[used];e=remap[e]
        faces=np.sort(np.vstack([e[:,p] for p in ([0,1,2],[0,1,3],[0,2,3],[1,2,3])]),axis=1);own0=np.tile(np.arange(len(e)),4)
        faces,inv,count=np.unique(faces,axis=0,return_inverse=True,return_counts=True);order=np.argsort(inv,kind='stable');start=np.r_[0,np.cumsum(count)[:-1]];owners=np.full((len(faces),2),-1,int);owners[:,0]=own0[order[start]];shared=count==2;owners[shared,1]=own0[order[start[shared]+1]]
        if count.max()>2 or min(quality)<=0:raise RuntimeError('invalid tetrahedral manifold')
        # A coarse circular chord cannot cut across the real 0.02 mm fit gap.
        boundary=faces[count==1];shellfaces=boundary[np.all(m[owners[count==1,0]][:,None]==2,axis=1)];fc=x[shellfaces].mean(axis=1);rr=np.linalg.norm(x[shellfaces,:2],axis=2)
        gapband=np.all(abs(rr-75)<1e-5,axis=1)&(fc[:,2]>100)&(fc[:,2]<115)
        min_shell_chord_r=float(np.linalg.norm(fc[gapband,:2],axis=1).min())
        if min_shell_chord_r<=74.98:raise RuntimeError('shell inner-face chord crosses the fit gap')
        d=dict(x=x,e=e,material=m,weld_pass=wp,faces=faces,owners=owners,boundary=boundary,
               link_nodes=np.empty((0,17),int),link_weights=np.empty((0,17)),link_area=np.empty(0))
        summary=dict(level=level,nodes=len(x),tetrahedra=len(e),bulk_mm=far,local_mm=local,quality_min=float(min(quality)),
          material_volumes_mm3={str(k):sum(occ.getMass(3,v) for v in vs) for k,vs in regions.items()},
          interfaces={k:len(v) for k,v in interfaces.items()},arc_length_mm=20.,effective_connection_length_mm=18.,root_leg_mm=2.8,thermal_fillet_leg_mm=4.,
          fit_gap_mm=.02,minimum_inner_shell_face_centroid_radius_mm=min_shell_chord_r,interface_method='shared conforming material-interface nodes; unconnected fit gap is open',
          cache_key=cache,qualification='geometry establishes nominal contact paths, not continuous fusion or retained residual stress')
        summary['actual_faceted_gap_audit']=audit_unwelded_gap(dict(points=x,tetrahedra=e,material_ids=m,triangles=boundary),reject=True)
        np.savez_compressed(folder/'mesh.npz',**d);(folder/'mesh-summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps({'event':'mesh_complete',**summary}),flush=True)
        return d,summary
    finally:gmsh.finalize()
