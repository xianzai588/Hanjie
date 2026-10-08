"""Bounded P2 quarter-symmetry check of cold ring bending stiffness.

Uses the same material partition and effective joints as the full P1 runs.
Quadratic displacement on straight-sided tetrahedra uses four exact degree-two integration points.
Radial/overturning loads are antisymmetric about x=0; axial is symmetric.
All are symmetric about y=0.  Full-ring responses are reconstructed by parity.
"""
from pathlib import Path
import argparse
import csv
import json
import hashlib
import math
import time
import yaml
import gmsh
import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import cg
import pyamg
import run_ring_structure as base
from geometry_audit import audit_unwelded_gap

HERE=Path(__file__).resolve().parent
from model_inputs import P2_LEVELS as LEVELS, REFERENCE_LOADS, p2_cache_inputs as cache_inputs, current_publication_identity
EDGES=((0,1),(1,2),(2,0),(0,3),(2,3),(1,3))
Q=np.full((4,4),.1381966011250105)
np.fill_diagonal(Q,.5854101966249685)


def shape(L,edges=EDGES):
    derivative=np.array([[-1.,-1.,-1.],[1,0,0],[0,1,0],[0,0,1]])
    N=np.array([v*(2*v-1) for v in L]+[4*L[a]*L[b] for a,b in edges])
    D=np.array([(4*L[i]-1)*derivative[i] for i in range(4)]+
               [4*(L[a]*derivative[b]+L[b]*derivative[a]) for a,b in edges])
    return N,D


def build(level):
    out=HERE/"results"/f"p2-linear-{level}";out.mkdir(parents=True,exist_ok=True)
    cached=out/"mesh.npz"
    if cached.exists():
        meta=json.loads((out/"mesh-summary.json").read_text())
        if json.dumps(meta.get("input_identity"),sort_keys=True)!=json.dumps(cache_inputs(level),sort_keys=True):
            raise RuntimeError("Quadratic mesh inputs changed: use --rebuild")
        mesh = dict(np.load(cached))
        meta["actual_faceted_gap_audit"] = audit_unwelded_gap(mesh, reject=True)
        return mesh,meta
    far,local=LEVELS[level]
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal",1)
        gmsh.option.setNumber("Mesh.MeshSizeMin",local)
        gmsh.option.setNumber("Mesh.MeshSizeMax",far)
        gmsh.option.setNumber("Mesh.Algorithm3D",1)
        gmsh.option.setNumber("Mesh.Optimize",1)
        gmsh.option.setNumber("Mesh.Binary",1)
        gmsh.option.setNumber("Mesh.SecondOrderLinear",1)
        gmsh.model.add(f"p2-quarter-{level}")
        precoat=[v for v in gmsh.model.occ.importShapes(str(base.CAD/"ring-precoat-eight-windows-17solids.step")) if v[0]==3]
        mids=[1 if gmsh.model.occ.getMass(*v)>1000 else (3 if gmsh.model.occ.getMass(*v)>100 else 4) for v in precoat]
        shell=gmsh.model.occ.cut([(3,gmsh.model.occ.addCylinder(0,0,0,0,0,200,80))],[(3,gmsh.model.occ.addCylinder(0,0,0,0,0,200,75))])[0]
        src=precoat+shell+[base.fillet(i*math.pi/4,3.5) for i in range(8)]
        mids += [2]+[5]*8
        box=(3,gmsh.model.occ.addBox(0,0,-1,81,81,202))
        _,maps=gmsh.model.occ.intersect(src,[box])
        regions={mid:[] for mid in base.MATERIALS}
        for mid,entities in zip(mids,maps):regions[mid].extend(v for v in entities if v[0]==3)
        src=[v for vs in regions.values() for v in vs]
        srcmid=[mid for mid,vs in regions.items() for v in vs]
        _,maps=gmsh.model.occ.fragment(src,[])
        regions={mid:[] for mid in base.MATERIALS}
        for mid,entities in zip(srcmid,maps):regions[mid].extend(v for v in entities if v[0]==3)
        gmsh.model.occ.synchronize()
        ss={mid:set().union(*(base.boundary(v) for v in vs)) for mid,vs in regions.items()}
        if ss[1]&ss[5]:raise RuntimeError("QT has bypass contact with final weld")
        for mid,vs in regions.items():gmsh.model.addPhysicalGroup(3,[v[1] for v in vs],mid)
        small=ss[3]|ss[4]|ss[5]
        pt=sorted({tag for s in small for dim,tag in gmsh.model.getBoundary([(2,s)],recursive=True) if dim==0})
        gmsh.model.mesh.setSize([(0,p) for p in pt],local)
        con=gmsh.model.mesh.field.add("MathEval")
        gmsh.model.mesh.field.setString(con,"F",f"Min({far},2.0+Max(0,Abs(z-107.5)-17.5)*.3)")
        restr=gmsh.model.mesh.field.add("Restrict");gmsh.model.mesh.field.setNumber(restr,"InField",con)
        gmsh.model.mesh.field.setNumbers(restr,"SurfacesList",sorted(ss[2]));gmsh.model.mesh.field.setAsBackgroundMesh(restr)
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.setOrder(2)
        gmsh.write(str(out/"quarter-p2.msh"))
        # Use Gmsh's own local-node coordinates to check the edge ordering.
        props=gmsh.model.mesh.getElementProperties(11)
        localcoords=np.asarray(props[4]).reshape(-1,3)
        bary=np.column_stack([1-localcoords.sum(axis=1),localcoords])
        actualedges=[tuple(np.flatnonzero(L>.1).tolist()) for L in bary[4:]]
        expected=[tuple(sorted(e)) for e in EDGES]
        if [tuple(sorted(e)) for e in actualedges]!=expected:
            raise RuntimeError(f"Unexpected Gmsh tetra10 edge order {actualedges}")
        tag,coord,_=gmsh.model.mesh.getNodes();p=np.asarray(coord).reshape(-1,3);lookup={int(v):i for i,v in enumerate(tag)}
        tet=[];material=[];element_tags=[]
        for mid,vs in regions.items():
            for v in vs:
                ids,nodes=gmsh.model.mesh.getElementsByType(11,v[1])
                tet.extend([[lookup[int(q)] for q in row] for row in np.asarray(nodes).reshape(-1,10)])
                material.extend([mid]*len(ids))
                element_tags.extend(ids)
        _,nodes=gmsh.model.mesh.getElementsByType(9)
        tri=np.array([[lookup[int(q)] for q in row] for row in np.asarray(nodes).reshape(-1,6)],dtype=np.int32)
        # CAD bore entities are identified before meshing; curved midnodes need
        # not be mistaken for the P1 straight chord radius.
        bore=[]
        for s in ss[1]:
            _,nn=gmsh.model.mesh.getElementsByType(9,s)
            rows=np.asarray(nn).reshape(-1,6)
            q=np.array([[p[lookup[int(v)]] for v in row[:3]] for row in rows])
            if len(q) and np.max(abs(np.linalg.norm(q[:,:,:2],axis=2)-20))<1e-5:
                bore.extend([[lookup[int(v)] for v in row] for row in rows])
        if not bore:raise RuntimeError("No quadratic bore surface")
        tet=np.array(tet,dtype=np.int32);material=np.array(material,dtype=np.int8)
        min_determinants=np.asarray(gmsh.model.mesh.getElementQualities(element_tags,"minDetJac"))
        if np.any(min_determinants<=0):
            failure={"input_identity":cache_inputs(level),"stage":"straight-sided P2 geometry quality",
                     "minimum_Jacobian":float(min_determinants.min()),"inverted_count":int(np.count_nonzero(min_determinants<=0))}
            (out/"failed-curved-mesh.json").write_text(json.dumps(failure,indent=2))
            raise RuntimeError("P2 mesh has inverted Jacobians; no structural qualification")
        mesh={"points":p,"tetrahedra10":tet,"material_ids":material,"triangles6":tri,"bore_triangles6":np.asarray(bore,dtype=np.int32)}
        meta={"input_identity":cache_inputs(level),"nodes":len(p),"tetrahedra":len(tet),"element_order":2,
              "tetrahedra_by_material":{str(mid):int(np.count_nonzero(material==mid)) for mid in base.MATERIALS},
              "quarter_material_volumes_mm3":{str(mid):sum(gmsh.model.occ.getMass(*v) for v in vs) for mid,vs in regions.items()},
              "minimum_element_Jacobian_mm3":float(min_determinants.min()),"inverted_element_count":int(np.count_nonzero(min_determinants<=0)),
              "bore_triangles":len(bore),"full_ring_reconstruction":"exact symmetry/antisymmetry of specified geometry, loads and clamped base"}
        meta["actual_faceted_gap_audit"] = audit_unwelded_gap(mesh, reject=True)
        np.savez_compressed(cached,**mesh);(out/"mesh-summary.json").write_text(json.dumps(meta,indent=2))
        print(json.dumps({"event":"p2_mesh",**meta}),flush=True)
        return mesh,meta
    finally:gmsh.finalize()


def assemble(mesh):
    p,t,m=mesh["points"],mesh["tetrahedra10"],mesh["material_ids"]
    ndof=len(p)*3;K=csr_matrix((ndof,ndof));minimum=1e99;volume=0.
    E=np.array([base.MATERIALS[int(mid)]["E_MPa"] for mid in m]);nu=np.array([base.MATERIALS[int(mid)]["nu"] for mid in m])
    lam,mu=E*nu/((1+nu)*(1-2*nu)),E/(2*(1+nu))
    for start in range(0,len(t),1800):
        stop=min(start+1800,len(t));x=p[t[start:stop]];kl=np.zeros((len(x),30,30))
        for L in Q:
            N,D=shape(L);J=np.einsum("nai,aj->nij",x,D);det=np.linalg.det(J)
            minimum=min(minimum,float(det.min()))
            if np.any(det<=0):raise RuntimeError("Inverted quadratic tetrahedron at integration point")
            g=np.einsum("ak,nki->nai",D,np.linalg.inv(J))
            k=lam[start:stop,None,None,None,None]*np.einsum("nai,nbj->naibj",g,g)
            k+=mu[start:stop,None,None,None,None]*np.einsum("naj,nbi->naibj",g,g)
            k+=mu[start:stop,None,None,None,None]*np.einsum("nab,ij->naibj",np.einsum("nak,nbk->nab",g,g),np.eye(3))
            kl+=k.reshape(-1,30,30)*det[:,None,None]/24.
            volume+=float(det.sum()/24.)
        dof=(3*t[start:stop,:,None]+np.arange(3)).reshape(-1,30)
        K+=coo_matrix((kl.ravel(),(np.repeat(dof,30,axis=1).ravel(),np.tile(dof,(1,30)).ravel())),shape=(ndof,ndof)).tocsr()
    return K,{"minimum_quadrature_Jacobian_mm3":minimum,"integrated_quarter_volume_mm3":volume,"nonzeros":K.nnz}


def loads(mesh):
    radial_N,axial_N,moment_N_mm=REFERENCE_LOADS
    p,tri=mesh["points"],mesh["bore_triangles6"]
    llist=[([1/3]*3,.225/2)]
    for a,b,w in [(.05971587178977,.470142064105115,.132394152788506/2),(.797426985353087,.101286507323456,.125939180544827/2)]:
        for i in range(3):
            L=[b]*3;L[i]=a;llist.append((L,w))
    derivative=np.array([[-1.,-1.],[1,0],[0,1]])
    records=[];area=0.;intx2=0.
    for L,w in llist:
        N=np.array([v*(2*v-1) for v in L]+[4*L[a]*L[b] for a,b in ((0,1),(1,2),(2,0))])
        D=np.array([(4*L[i]-1)*derivative[i] for i in range(3)]+[4*(L[a]*derivative[b]+L[b]*derivative[a]) for a,b in ((0,1),(1,2),(2,0))])
        J=np.einsum("nai,aj->nij",p[tri],D)
        weight=w*np.linalg.norm(np.cross(J[:,:,0],J[:,:,1]),axis=1)
        position=np.einsum("a,nai->ni",N,p[tri]);area+=weight.sum();intx2+=np.sum(weight*position[:,0]**2)
        records.append((N,weight,position))
    f={name:np.zeros((len(p),3)) for name in ("radial","axial","overturning")}
    for N,w,pos in records:
        for name,component,val in [("radial",0,np.full(len(tri),radial_N/(4*area))),
                                    ("axial",2,np.full(len(tri),axial_N/(4*area))),
                                    ("overturning",2,-moment_N_mm/(4*intx2)*pos[:,0])]:
            nodal=w[:,None]*N[None,:]*val[:,None]
            np.add.at(f[name][:,component],tri.ravel(),nodal.ravel())
    return f,{"quarter_bore_area_mm2":float(area),"quarter_integral_x_squared_mm4":float(intx2),"surface_quadrature":"7-point degree-5 triangle rule; straight-sided P2 face geometry"}


def full_bore(p,u,bore,name):
    nodes=np.unique(bore);q=p[nodes];v=u[nodes]
    coords=[];displ=[]
    for sx,sy in [(1,1),(-1,1),(-1,-1),(1,-1)]:
        R=np.array([sx,sy,1.]);parity=sx if name in ("radial","overturning") else 1
        coords.append(q*R);displ.append(v*R*parity)
    coords=np.concatenate(coords);displ=np.concatenate(displ)
    # Delete duplicated symmetry-plane nodes so each FE point has one weight.
    _,ix=np.unique(np.round(coords,10),axis=0,return_index=True)
    return coords[ix],displ[ix]


def run(level):
    out=HERE/"results"/f"p2-linear-{level}"
    if (out/"result.json").exists():
        d=json.loads((out/"result.json").read_text())
        wanted_version=(base.ROOT/"project/submission-baseline.yaml").read_text().splitlines()[0].split(":",1)[1].strip()
        if d.get("process_version")!=wanted_version or json.dumps(d["input_identity"],sort_keys=True)!=json.dumps(cache_inputs(level),sort_keys=True):raise RuntimeError("P2 result geometry/process identity changed: --rebuild")
        return d
    execution_start_time=time.time();mesh,meta=build(level);p=mesh["points"];t=mesh["tetrahedra10"];m=mesh["material_ids"]
    K,qmeta=assemble(mesh);f,lmeta=loads(mesh);ndof=len(p)*3
    print(json.dumps({"event":"p2_stiffness","level":level,"dofs":ndof,**qmeta}),flush=True)
    mode=np.zeros((ndof,6))
    for i in range(3):mode[3*np.arange(len(p))+i,i]=1.
    for i,direction in enumerate(np.eye(3)):mode[:,i+3]=np.cross(np.broadcast_to(direction,p.shape),p-[0,0,107.5]).ravel()
    bottom=np.flatnonzero(abs(p[:,2])<1e-7);xp=np.flatnonzero(abs(p[:,0])<1e-7);yp=np.flatnonzero(abs(p[:,1])<1e-7)
    solved={};metrics={};preconditions={}
    for name in ("radial","axial","overturning"):
        symmetry="symmetric" if name=="axial" else "antisymmetric"
        fixed=np.concatenate([(3*bottom[:,None]+np.arange(3)).ravel(),3*yp+1,
                              3*xp if symmetry=="symmetric" else (3*xp[:,None]+[1,2]).ravel()])
        free=np.setdiff1d(np.arange(ndof),fixed)
        if symmetry not in preconditions:
            kr=K[free,:][:,free].tocsr()
            ml=pyamg.smoothed_aggregation_solver(kr,B=mode[free],symmetry="symmetric",max_coarse=300,max_levels=12)
            preconditions[symmetry]=(kr,ml.aspreconditioner())
        kr,pre=preconditions[symmetry];fv=f[name].ravel();counter=[0]
        def count(x):counter[0]+=1
        ur,info=cg(kr,fv[free],M=pre,rtol=1e-9,atol=1e-10,maxiter=2000,callback=count)
        if info:raise RuntimeError(f"P2 solve failed {info}")
        U=np.zeros(ndof);U[free]=ur;u=U.reshape(-1,3);solved[name]=U
        fullp,fullu=full_bore(p,u,mesh["bore_triangles6"],name)
        applied=np.zeros(3);reaction=np.zeros(3);applied_m=np.zeros(3);reaction_m=np.zeros(3)
        local_reaction=(K@U-fv).reshape(-1,3)
        for sx,sy in [(1,1),(-1,1),(-1,-1),(1,-1)]:
            R=np.array([sx,sy,1.]);parity=sx if name in ("radial","overturning") else 1
            coords=p*R;ff=f[name]*R*parity;rr=local_reaction*R*parity
            applied+=ff.sum(axis=0);reaction+=rr.sum(axis=0)
            applied_m+=np.cross(coords-[0,0,107.5],ff).sum(axis=0)
            reaction_m+=np.cross(coords-[0,0,107.5],rr).sum(axis=0)
        metrics[name]={**base.bore_metrics(fullp,fullu,np.arange(len(fullp))),
                       "elastic_strain_energy_N_mm":float(4*U@fv/2),"CG_iterations":counter[0],
                       "applied_force_N":applied.tolist(),"reaction_force_N":reaction.tolist(),
                       "applied_moment_N_mm":applied_m.tolist(),"reaction_moment_N_mm":reaction_m.tolist(),
                       "force_balance_relative_error":float(np.linalg.norm(applied+reaction)/5000.),
                       "moment_balance_relative_error":float(np.linalg.norm(applied_m+reaction_m)/250000.),
                       "free_residual_relative_norm":float(np.linalg.norm((K@U-fv)[free])/np.linalg.norm(fv[free]))}
        with (out/f"{name}-bore-displacement.csv").open("w") as stream:
            writer=csv.writer(stream);writer.writerow(["x_mm","y_mm","z_mm","ux_um","uy_um","uz_um"])
            writer.writerows(np.column_stack([fullp,1000*fullu]))
        np.savez_compressed(out/f"{name}-quarter-displacement.npz",displacement_mm=u)
        print(json.dumps({"event":"p2_case","level":level,"case":name,**metrics[name]}),flush=True)
    # Combined reconstruction: symmetric axial and antisymmetric radial/moment
    # fields have different x-plane parity and must be mirrored separately.
    fulls=[full_bore(p,solved[name].reshape(-1,3),mesh["bore_triangles6"],name) for name in ("radial","axial","overturning")]
    fullp=fulls[0][0];fullu=sum(v for q,v in fulls)
    combined_energy=sum(metrics[n]["elastic_strain_energy_N_mm"] for n in metrics)+4*float(solved["radial"]@f["overturning"].ravel())
    metrics["combined"]={**base.bore_metrics(fullp,fullu,np.arange(len(fullp))),"elastic_strain_energy_N_mm":combined_energy}
    for key in ("applied_force_N","reaction_force_N","applied_moment_N_mm","reaction_moment_N_mm"):
        metrics["combined"][key]=sum(np.array(metrics[n][key]) for n in solved).tolist()
    metrics["combined"]["force_balance_relative_error"]=float(np.linalg.norm(np.array(metrics["combined"]["applied_force_N"])+metrics["combined"]["reaction_force_N"])/5000.)
    metrics["combined"]["moment_balance_relative_error"]=float(np.linalg.norm(np.array(metrics["combined"]["applied_moment_N_mm"])+metrics["combined"]["reaction_moment_N_mm"])/250000.)
    with (out/"combined-bore-displacement.csv").open("w") as stream:
        writer=csv.writer(stream);writer.writerow(["x_mm","y_mm","z_mm","ux_um","uy_um","uz_um"]);writer.writerows(np.column_stack([fullp,1000*fullu]))
    # Raw stresses at quadrature points, including each reconstructed quadrant.
    raw={str(mid):{"von_mises_max_MPa":0.,"maximum_principal_max_MPa":0.} for mid in base.MATERIALS}
    for sx,sy in [(1,1),(-1,1),(-1,-1),(1,-1)]:
        uq=sum(solved[n].reshape(-1,3)*(sx if n in ("radial","overturning") else 1) for n in solved)
        for start in range(0,len(t),20000):
            stop=min(start+20000,len(t));x=p[t[start:stop]];v=uq[t[start:stop]];mi=m[start:stop]
            for L in Q:
                _,D=shape(L);J=np.einsum("nai,aj->nij",x,D);g=np.einsum("ak,nki->nai",D,np.linalg.inv(J))
                du=np.einsum("nai,naj->nij",g,v);strain=(du+du.transpose(0,2,1))/2.
                for mid,prop in base.MATERIALS.items():
                    ix=mi==mid
                    if not ix.any():continue
                    E,nu=prop["E_MPa"],prop["nu"];lam,mu=E*nu/((1+nu)*(1-2*nu)),E/(2*(1+nu))
                    stress=2*mu*strain[ix]+lam*np.trace(strain[ix],axis1=1,axis2=2)[:,None,None]*np.eye(3)
                    dev=stress-np.trace(stress,axis1=1,axis2=2)[:,None,None]/3.*np.eye(3)
                    vm=np.sqrt(1.5*np.sum(dev*dev,axis=(1,2)));principal=np.linalg.eigvalsh(stress)[:,-1]
                    raw[str(mid)]["von_mises_max_MPa"]=max(raw[str(mid)]["von_mises_max_MPa"],float(vm.max()))
                    raw[str(mid)]["maximum_principal_max_MPa"]=max(raw[str(mid)]["maximum_principal_max_MPa"],float(principal.max()))
    result={"process_version":(base.ROOT/"project/submission-baseline.yaml").read_text().splitlines()[0].split(":",1)[1].strip(),
            "input_identity":cache_inputs(level),"mesh":meta,"quadrature_geometry":qmeta,"load_integration":lmeta,
            "cases":metrics,"combined_raw_quadrature_stress_by_material":raw,
            "method":"3D straight-sided quadratic displacement tetrahedra, quarter-symmetry, full-ring bore reconstructed by exact load parity; 4 volume and 7 surface quadrature points",
            "strength_verified":False,"postweld_position_verified":False,"elapsed_seconds":time.time()-execution_start_time}
    (out/"result.json").write_text(json.dumps(result,indent=2));return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--levels",nargs="+",default=["coarse","medium"]);parser.add_argument("--rebuild",action="store_true");args=parser.parse_args()
    for level in args.levels:
        if args.rebuild:
            for name in ("mesh.npz","mesh-summary.json","result.json"):
                path=HERE/"results"/f"p2-linear-{level}"/name
                if path.exists():path.unlink()
        run(level)


if __name__=="__main__":main()
