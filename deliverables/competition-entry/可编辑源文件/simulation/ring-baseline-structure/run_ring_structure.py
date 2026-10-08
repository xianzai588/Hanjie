"""Cold elastic FE for the complete-ring nominal design, with eight real joints.

The imported 17-solid retained precoat partition is explicitly elastic and bonded
only at its own shared faces.  This is a qualification-conditioned structural
model, not a thermal manufacturing run or proof of interface fusion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import gmsh
import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import cg
import pyamg

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CAD = ROOT / "cad/generated/ring-baseline"
from model_inputs import MATERIALS, step_geometry_digest
LEVELS = {"coarse": (6., .9), "medium": (4.5, .65), "fine": (3.0, .45)}
MESH_SCHEMA = "RING-COLD-EXPLICIT-JOINT-MESH-2"
from geometry_audit import audit_unwelded_gap


def mesh_inputs(level, leg):
    far, local = LEVELS[level]
    source = CAD / "ring-precoat-eight-windows-17solids.step"
    return {"schema": MESH_SCHEMA, "level": level, "leg_mm": leg,
            "precoat_STEP_geometry_sha256": step_geometry_digest(source),
            "bulk_size_mm": far, "local_size_mm": local,
            "shell_surface_size_function": f"Min({far}, 2.0 + Max(0, Abs(z-107.5)-17.5)*0.3)",
            "algorithm_3D": 1, "netgen_optimization": False,
            "shell_geometry_mm": [75.,80.,200.], "effective_length_mm":18.,
            "segments":8, "interfaces":"only conforming shared material faces; unwelded radial gap=.02mm"}


def analysis_inputs(level, leg):
    version=(ROOT/"project/submission-baseline.yaml").read_text().splitlines()[0].split(":",1)[1].strip()
    return {"schema":"RING-P1-COLD-ELASTIC-ASSEMBLY-2", "process_version":version,
            "mesh_inputs":mesh_inputs(level,leg), "materials":MATERIALS,
            "loads":[5000.,5000.,250000.], "fixed_boundary":"complete shell bottom z=0 all translations",
            "CG_relative_tolerance":1e-9}


def fillet(angle: float, leg: float):
    span = 18. / 75.
    p = [gmsh.model.occ.addPoint(r, 0., z) for r, z in
         ((75.-leg, 115.), (75., 115.), (75., 115.+leg))]
    edges = [gmsh.model.occ.addLine(p[i], p[(i+1) % 3]) for i in range(3)]
    face = gmsh.model.occ.addPlaneSurface([gmsh.model.occ.addCurveLoop(edges)])
    gmsh.model.occ.rotate([(2, face)], 0., 0., 0., 0., 0., 1., angle-span/2)
    return [x for x in gmsh.model.occ.revolve([(2, face)], 0., 0., 0., 0., 0., 1., span)
            if x[0] == 3][0]


def boundary(v):
    return {tag for dim, tag in gmsh.model.getBoundary([v], oriented=False) if dim == 2}


def build_mesh(level: str, leg: float, outdir=None):
    out = Path(outdir) if outdir is not None else HERE / "results" / level
    out.mkdir(parents=True, exist_ok=True)
    meshfile = out / "mesh.npz"
    if meshfile.exists():
        saved=json.loads((out / "mesh-summary.json").read_text())
        if saved.get("mesh_inputs") != mesh_inputs(level,leg):
            raise RuntimeError(f"{level} mesh input identity differs or is absent; use --rebuild to generate the requested mesh")
        d = dict(np.load(meshfile))
        saved["actual_faceted_gap_audit"] = audit_unwelded_gap(d, reject=True)
        return d, saved
    far, local = LEVELS[level]
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        gmsh.option.setNumber("Mesh.MeshSizeMin", local)
        gmsh.option.setNumber("Mesh.MeshSizeMax", far)
        gmsh.option.setNumber("Mesh.Algorithm3D", 1)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.option.setNumber("Mesh.Binary", 1)
        gmsh.model.add(f"ring-{level}")
        precoat = gmsh.model.occ.importShapes(str(CAD / "ring-precoat-eight-windows-17solids.step"))
        precoat = [v for v in precoat if v[0] == 3]
        if len(precoat) != 17:
            raise RuntimeError(f"Expected 17 precoat solids, got {len(precoat)}")
        shell = gmsh.model.occ.cut(
            [(3, gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, 200, 80))],
            [(3, gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, 200, 75))])[0]
        weld = [fillet(i*math.pi/4, leg) for i in range(8)]
        sources = precoat + shell + weld
        mids = [1 if gmsh.model.occ.getMass(*v) > 1000 else
                (3 if gmsh.model.occ.getMass(*v) > 100 else 4) for v in precoat] + [2] + [5]*8
        _, mapping = gmsh.model.occ.fragment(sources, [])
        gmsh.model.occ.synchronize()
        region = {mid: [] for mid in MATERIALS}
        for mid, mapped in zip(mids, mapping):
            region[mid].extend(v for v in mapped if v[0] == 3)
        all_volumes = [v for vs in region.values() for v in vs]
        if len(set(all_volumes)) != len(all_volumes):
            raise RuntimeError("Material regions overlap after fragmentation")
        region_surfaces = {mid: set().union(*(boundary(v) for v in vs)) for mid, vs in region.items()}
        interfaces = {
            "QT_first": sorted(region_surfaces[1] & region_surfaces[3]),
            "first_second": sorted(region_surfaces[3] & region_surfaces[4]),
            "second_final": sorted(region_surfaces[4] & region_surfaces[5]),
            "final_shell": sorted(region_surfaces[5] & region_surfaces[2]),
            "QT_final": sorted(region_surfaces[1] & region_surfaces[5]),
        }
        if not all(interfaces[k] for k in ("QT_first", "first_second", "second_final", "final_shell")):
            raise RuntimeError(f"Missing load-path interfaces {interfaces}")
        if interfaces["QT_final"]:
            raise RuntimeError("Final fillet has direct QT interface: check pocket/leg")
        for mid, vs in region.items():
            gmsh.model.addPhysicalGroup(3, [v[1] for v in vs], mid)
            gmsh.model.setPhysicalName(3, mid, MATERIALS[mid]["name"])
        small = region_surfaces[3] | region_surfaces[4] | region_surfaces[5]
        points = sorted({tag for surface in small for dim, tag in
                         gmsh.model.getBoundary([(2, surface)], recursive=True) if dim == 0})
        gmsh.model.mesh.setSize([(0, tag) for tag in points], local)
        # A coarse faceted inner shell can protrude through a real 0.02 mm
        # circular gap (sagitta h^2/8R).  Bound shell surface chord error without
        # changing gap geometry or merging its two independent surfaces.
        constant = gmsh.model.mesh.field.add("MathEval")
        gmsh.model.mesh.field.setString(constant, "F", f"Min({far}, 2.0 + Max(0, Abs(z-107.5)-17.5)*0.3)")
        restrict = gmsh.model.mesh.field.add("Restrict")
        gmsh.model.mesh.field.setNumber(restrict, "InField", constant)
        gmsh.model.mesh.field.setNumbers(restrict, "SurfacesList", sorted(region_surfaces[2]))
        gmsh.model.mesh.field.setAsBackgroundMesh(restrict)
        gmsh.model.mesh.generate(3)
        gmsh.write(str(out / "ring-cold-effective-joints.msh"))
        tags, coords, _ = gmsh.model.mesh.getNodes()
        lookup = {int(t): i for i, t in enumerate(tags)}
        p = np.asarray(coords).reshape(-1, 3)
        ts, ms, etags = [], [], []
        volumes = {}
        for mid, vs in region.items():
            volumes[str(mid)] = sum(gmsh.model.occ.getMass(*v) for v in vs)
            for v in vs:
                tetags, nodes = gmsh.model.mesh.getElementsByType(4, v[1])
                ts.extend([[lookup[int(t)] for t in q] for q in np.asarray(nodes).reshape(-1, 4)])
                ms.extend([mid]*len(tetags)); etags.extend(tetags)
        t = np.asarray(ts, dtype=np.int32)
        m = np.asarray(ms, dtype=np.int8)
        _, snodes = gmsh.model.mesh.getElementsByType(2)
        tris = np.asarray([[lookup[int(t)] for t in q] for q in np.asarray(snodes).reshape(-1, 3)], dtype=np.int32)
        quality = np.asarray(gmsh.model.mesh.getElementQualities(etags, "minSICN"))
        summary = {"mesh_inputs":mesh_inputs(level,leg), "level": level, "bulk_size_mm": far, "local_size_mm": local,
                   "nodes": len(p), "tetrahedra": len(t), "tetrahedra_by_material":
                   {str(mid): int(np.count_nonzero(m == mid)) for mid in MATERIALS},
                   "volumes_mm3": volumes, "quality_min": float(quality.min()),
                   "quality_p01": float(np.quantile(quality, .01)),
                   "nonpositive_quality_count": int(np.count_nonzero(quality <= 0)),
                   "interface_surfaces": interfaces,
                   "effective_segment_length_mm": 18., "effective_segment_count": 8,
                   "fillet_leg_mm": leg, "unwelded_radial_gap_mm": .02,
                   "model": "five-material conforming tetrahedral solids; bonded qualified interfaces; open unwelded gap"}
        if summary["nonpositive_quality_count"]:
            raise RuntimeError("Invalid tetrahedra")
        d = {"points": p, "tetrahedra": t, "material_ids": m, "triangles": tris}
        summary["actual_faceted_gap_audit"] = audit_unwelded_gap(d, reject=True)
        np.savez_compressed(meshfile, **d)
        (out / "mesh-summary.json").write_text(json.dumps(summary, indent=2))
        print(json.dumps({"event": "mesh_complete", **summary}), flush=True)
        return d, summary
    finally:
        gmsh.finalize()


def surface_load(p, tri, direction, target):
    """Consistent constant traction or z traction affine in x for pure My."""
    xyz = p[tri]
    area = .5*np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0], xyz[:,2]-xyz[:,0]), axis=1)
    f = np.zeros((len(p), 3))
    if direction == "moment":
        # Shape-function exact integrals for t_z = a+b*x.  Solve to give Fz=0,
        # My=-sum(x*fz)=target on this actual faceted bore surface.
        x = xyz[:, :, 0]
        intx = np.sum(area*x.mean(axis=1))
        intx2 = np.sum(area*(np.sum(x*x, axis=1)+x[:,0]*x[:,1]+x[:,1]*x[:,2]+x[:,2]*x[:,0])/6.)
        a, b = np.linalg.solve([[area.sum(), intx], [-intx, -intx2]], [0., target])
        nodal = area[:,None]*(a/3.+b*(x+x.sum(axis=1)[:,None])/12.)
        np.add.at(f[:,2], tri.ravel(), nodal.ravel())
    else:
        nodal = area/3.*target/area.sum()
        for axis, value in enumerate(direction):
            np.add.at(f[:,axis], tri.ravel(), np.repeat(nodal*value, 3))
    return f


def bore_metrics(p, u, bore):
    """Linearized least-squares cylinder, then true radial residual metrics."""
    nodes = np.unique(bore)
    q, v = p[nodes], u[nodes]
    r = np.linalg.norm(q[:,:2], axis=1)
    nx, ny = q[:,0]/r, q[:,1]/r
    zz = q[:,2]-107.5
    radial = nx*v[:,0]+ny*v[:,1]
    design = np.column_stack([nx, ny, nx*zz, ny*zz, np.ones(len(q))])
    fit = np.linalg.lstsq(design, radial, rcond=None)[0]
    residual = radial-design@fit
    end = fit[:2][None,:] + np.array([-7.5,7.5])[:,None]*fit[2:4][None,:]
    return {"axis_center_radial_um": float(np.linalg.norm(fit[:2])*1000),
            "axis_tilt_urad": float(np.linalg.norm(fit[2:4])*1e6),
            "axis_diameter_envelope_um": float(2*np.max(np.linalg.norm(end,axis=1))*1000),
            "mean_bore_diameter_change_um": float(2*fit[4]*1000),
            "cylindrical_radial_peak_to_valley_um": float(np.ptp(residual)*1000),
            "axis_fit_coefficients_mm": fit.tolist(),
            "bore_node_count": len(nodes)}


def solve(level: str, leg: float):
    out = HERE / "results" / level
    if (out / "result.json").exists():
        cached=json.loads((out / "result.json").read_text())
        # JSON string normalization also normalizes integer material-map keys.
        if json.dumps(cached.get("analysis_inputs"),sort_keys=True) != json.dumps(analysis_inputs(level,leg),sort_keys=True):
            raise RuntimeError(f"{level} result input identity differs or is absent; use --rebuild to run the requested analysis")
        return cached
    tstart = time.time()
    d, meshsummary = build_mesh(level, leg)
    p, t, mids = d["points"], d["tetrahedra"], d["material_ids"]
    ndof = len(p)*3
    nodal_dofs = np.arange(ndof).reshape(-1, 3).T
    # Constant-strain linear tetrahedra, assembled in bounded chunks.  This
    # avoids allocating the full vector basis for a million-element thin-layer mesh.
    inv = np.linalg.inv(np.concatenate([np.ones((len(t),4,1)),p[t]],axis=2))
    grad = inv[:,1:,:].transpose(0,2,1)
    volumes = abs(np.linalg.det(p[t[:,1:]]-p[t[:,0,None]]))/6.
    K = csr_matrix((ndof,ndof))
    E=np.array([MATERIALS[int(mid)]["E_MPa"] for mid in mids])
    nu=np.array([MATERIALS[int(mid)]["nu"] for mid in mids])
    lam,mu=E*nu/((1+nu)*(1-2*nu)), E/(2*(1+nu))
    for start in range(0,len(t),12000):
        stop=min(start+12000,len(t)); g=grad[start:stop]
        kl=lam[start:stop,None,None,None,None]*np.einsum("nai,nbj->naibj",g,g)
        kl+=mu[start:stop,None,None,None,None]*np.einsum("naj,nbi->naibj",g,g)
        kl+=mu[start:stop,None,None,None,None]*np.einsum("nab,ij->naibj",np.einsum("nak,nbk->nab",g,g),np.eye(3))
        kl=kl.reshape(-1,12,12)*volumes[start:stop,None,None]
        edof=(3*t[start:stop,:,None]+np.arange(3)).reshape(-1,12)
        row=np.repeat(edof,12,axis=1).ravel()
        col=np.tile(edof,(1,12)).ravel()
        K+=coo_matrix((kl.ravel(),(row,col)),shape=(ndof,ndof)).tocsr()
    print(json.dumps({"event":"stiffness_complete","level":level,"dofs":ndof,"nonzeros":K.nnz}),flush=True)
    tri = d["triangles"]
    trir = np.linalg.norm(p[tri, :2], axis=2)
    bore = tri[np.all(np.abs(trir-20.) < 1e-5, axis=1)]
    if not len(bore):
        raise RuntimeError("No bore triangles")
    fixednodes = np.flatnonzero(np.abs(p[:,2]) < 1e-5)
    fixed = nodal_dofs[:, fixednodes].ravel()
    free = np.setdiff1d(np.arange(ndof), fixed)
    kfree = K[free,:][:,free].tocsr()
    # The six analytical rigid body modes improve smoothed aggregation near-nullspace.
    mode = np.zeros((ndof, 6))
    for axis in range(3): mode[nodal_dofs[axis], axis] = 1.
    for j, direction in enumerate(np.eye(3)):
        rot = np.cross(np.broadcast_to(direction,p.shape), p-np.array([0,0,107.5]))
        mode[nodal_dofs.T.ravel(),3+j] = rot.ravel()
    ml = pyamg.smoothed_aggregation_solver(kfree, B=mode[free], symmetry="symmetric",
                                          max_coarse=300, max_levels=12)
    precon = ml.aspreconditioner()
    fxyz = {"radial": surface_load(p,bore,[1.,0.,0.],5000.),
            "axial": surface_load(p,bore,[0.,0.,1.],5000.),
            "overturning": surface_load(p,bore,"moment",250000.)}
    fxyz["combined"] = sum(fxyz.values())
    result = {"analysis_inputs":analysis_inputs(level,leg), "mesh": meshsummary, "material_inputs": MATERIALS,
              "boundary": "all translations fixed on complete Q235B bottom annulus z=0; top edge free; unwelded gap has no ties/contact",
              "load_application": "constant bore-surface traction for radial/axial, affine axial traction t_z=a+b*x for pure My; actual force/moment checked",
              "initial_state": "cold unstressed ideal qualified joint; no precoat or welding residual stresses transferred",
              "cases": {}, "scope": "cold elastic service response under reference envelope; not post-weld position tolerance or strength certification"}
    for name, f in fxyz.items():
        fv = np.zeros(ndof); fv[nodal_dofs.T.ravel()] = f.ravel()
        count = [0]
        def callback(x): count[0]+=1
        ur, info = cg(kfree, fv[free], M=precon, rtol=1e-9, atol=1e-10, maxiter=2000, callback=callback)
        if info: raise RuntimeError(f"CG failed {name}: {info}")
        U = np.zeros(ndof); U[free] = ur
        u = U[nodal_dofs].T
        res = K@U-fv
        du = np.einsum("nki,nkj->nij", grad, u[t])
        strain = (du+du.transpose(0,2,1))/2.
        stress = np.empty_like(strain)
        for mid, props in MATERIALS.items():
            ix = mids == mid; E, nu = props["E_MPa"],props["nu"]
            lam, mu = E*nu/((1+nu)*(1-2*nu)),E/(2*(1+nu))
            stress[ix] = 2*mu*strain[ix]+lam*np.trace(strain[ix],axis1=1,axis2=2)[:,None,None]*np.eye(3)
        dev = stress-np.trace(stress,axis1=1,axis2=2)[:,None,None]/3.*np.eye(3)
        vm = np.sqrt(1.5*np.sum(dev*dev,axis=(1,2)))
        principal = np.linalg.eigvalsh(stress)[:,-1]
        reaction = res[nodal_dofs].T
        fsum = f.sum(axis=0); msum = np.cross(p-[0,0,107.5], f).sum(axis=0)
        rsum = reaction.sum(axis=0); rmsum = np.cross(p-[0,0,107.5],reaction).sum(axis=0)
        response = {**bore_metrics(p,u,bore), "elastic_strain_energy_N_mm":float(U@fv/2.),
                    "applied_force_N":fsum.tolist(), "applied_moment_N_mm":msum.tolist(),
                    "reaction_force_N":rsum.tolist(), "reaction_moment_N_mm":rmsum.tolist(),
                    "force_balance_relative_error":float(np.linalg.norm(fsum+rsum)/5000.),
                    "moment_balance_relative_error":float(np.linalg.norm(msum+rmsum)/250000.),
                    "free_residual_relative_norm":float(np.linalg.norm(res[free])/np.linalg.norm(fv[free])),
                    "CG_iterations":count[0], "max_displacement_um":float(np.max(np.linalg.norm(u,axis=1))*1000),
                    "raw_element_stress_by_material": {str(mid):{
                        "von_mises_max_MPa":float(vm[mids==mid].max()),
                        "maximum_principal_max_MPa":float(principal[mids==mid].max()),
                        "peak_centroid_mm":p[t[np.flatnonzero(mids==mid)[np.argmax(vm[mids==mid])]]].mean(axis=0).tolist()
                    } for mid in MATERIALS}}
        result["cases"][name] = response
        np.savez_compressed(out/f"{name}-field.npz", displacement_mm=u, element_stress_MPa=stress,
                            element_von_mises_MPa=vm, element_max_principal_MPa=principal)
        print(json.dumps({"event":"case_complete","level":level,"case":name,**response}),flush=True)
    result["elapsed_seconds"] = time.time()-tstart
    (out/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels",nargs="+",default=["coarse","medium"])
    parser.add_argument("--leg",type=float,default=3.5)
    parser.add_argument("--rebuild",action="store_true",help="explicitly rebuild this level's cached mesh and result")
    args=parser.parse_args()
    if args.leg<=0 or args.leg>3.5:
        parser.error("This calculation family uses positive minimum fillet legs <=3.5 mm, within the Ni second-layer top footprint")
    for level in args.levels:
        if args.rebuild:
            for name in ("mesh.npz","mesh-summary.json","result.json"):
                path=HERE/"results"/level/name
                if path.exists():path.unlink()
        solve(level,args.leg)


if __name__ == "__main__": main()
