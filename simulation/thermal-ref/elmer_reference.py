"""独立构造 Elmer 热参考；仅共享冻结输入，不导入自研热求解代码。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

import numpy as np
import yaml
from scipy.special import erf

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SPEC = ROOT / "project/thermal-reference-elmer.yaml"
DEFAULT_HOME = Path("E:/OpenSource/ElmerFEM-26.1/ElmerFEM-gui-nompi-Windows-AMD64")
NAMES = ("q235b", "qt450_10", "ernife_ci")
CORNERS = np.array([[0,0,0], [1,0,0], [1,1,0], [0,1,0],
                    [0,0,1], [1,0,1], [1,1,1], [0,1,1]])
FACE_NODES = {(0,-1): [0,4,7,3], (0,1): [1,2,6,5],
              (1,-1): [0,1,5,4], (1,1): [3,7,6,2],
              (2,-1): [0,3,2,1], (2,1): [4,5,6,7]}


def load(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def subdivide(anchors, near, far, zone, local_zone=None, factor=1):
    anchors = sorted(set(anchors + ([] if local_zone is None else local_zone)))
    values = [anchors[0]]
    for a,b in zip(anchors[:-1], anchors[1:]):
        h = near if a >= zone[0] and b <= zone[1] else far
        count = max(1, math.ceil((b-a)/h))
        if local_zone is not None and local_zone[0] <= (a+b)/2 <= local_zone[1]:
            count *= factor
        values.extend(np.linspace(a,b,count+1)[1:])
    return np.asarray(values)


def geometry(config, process, mesh):
    p, grid, path = config["process"], config["thermal_grid"], config["heat_source_path"]
    wire = process["process"]["nominal"]
    area = math.pi*wire["filler_diameter_mm"]**2/4*wire["filler_feed_rate_mm_s"]/p["travel_speed_mm_s"]
    leg = math.sqrt(2*area)
    zbead = np.linspace(0, leg, mesh["bead_geometry_strips"]+1)
    widths = leg-(zbead[:-1]+zbead[1:])/2
    gap = config["geometry"]["interface_gap_nominal_mm"]
    n = subdivide([grid["radial_min_offset_mm"],-5.,-leg,*(-widths),-gap,0.,grid["radial_max_offset_mm"]],
                  mesh["near_spacing_mm"],mesh["far_spacing_mm"],[-5,5],mesh["radial_local_zone_mm"],mesh["cross_local_subdivision_factor"])
    z = subdivide([grid["axial_min_offset_mm"],-4.,*zbead,4.,grid["axial_max_offset_mm"]],
                  mesh["near_spacing_mm"],mesh["far_spacing_mm"],[-4,4],mesh["axial_local_zone_mm"],mesh["cross_local_subdivision_factor"])
    s = subdivide([grid["arc_min_offset_mm"],path["source_start_s_mm"],path["source_end_s_mm"],grid["arc_max_offset_mm"]],
                  mesh["arc_spacing_mm"],mesh["arc_spacing_mm"],[-np.inf,np.inf])
    nn,zz = np.meshgrid((n[:-1]+n[1:])/2,(z[:-1]+z[1:])/2,indexing="ij")
    cross = np.zeros(nn.shape,dtype=int)
    cross[(nn<=-gap)&(zz<0)] = 2
    cross[nn>0] = 1
    strips = np.clip(np.searchsorted(zbead,zz,side="right")-1,0,len(widths)-1)
    cross[(zz>0)&(zz<leg)&(nn<0)&(nn>=-widths[strips])] = 3
    material = np.broadcast_to(cross,(len(s)-1,*cross.shape)).copy()
    # 路径外从不出生的填丝不进入参考域，避免虚材料桥接远场。
    active_s = (s[:-1]>=path["source_start_s_mm"]-1e-10)&(s[1:]<=path["source_end_s_mm"]+1e-10)
    material[(material==3)&~active_s[:,None,None]] = 0
    index = np.argwhere(material>0)
    ids = material[tuple(index.T)]
    lattice = np.full(material.shape,-1,dtype=int)
    lattice[tuple(index.T)] = np.arange(len(index))
    raw = index[:,None,:]+CORNERS
    node_index, inverse = np.unique(raw.reshape(-1,3),axis=0,return_inverse=True)
    nodes = np.column_stack([axis[node_index[:,i]] for i,axis in enumerate((s,n,z))])
    conn = inverse.reshape(-1,8)+1
    dims = np.column_stack([np.diff(axis)[index[:,i]] for i,axis in enumerate((s,n,z))])
    return dict(axes=(s,n,z),index=index,ids=ids,lattice=lattice,nodes=nodes,conn=conn,
                dims=dims,volume=dims.prod(axis=1),cross=cross,leg=leg,area=area)


def visible_faces(g, with_bead, width):
    """独立按射线先后次序裁剪投影区间，返回每条原始边的积分份额。"""
    _,n,z = g["axes"]
    occupied = (g["cross"]>0)&((g["cross"]!=3)|with_bead)
    edges = []
    rt = math.sqrt(2)
    for j,k in np.argwhere(occupied):
        if j==0 or not occupied[j-1,k]:
            edges.append(((n[j]+z[k])/rt,(n[j]+z[k+1])/rt,1.,-rt*n[j],(j,k,1,-1)))
        if k==occupied.shape[1]-1 or not occupied[j,k+1]:
            edges.append(((n[j]+z[k+1])/rt,(n[j+1]+z[k+1])/rt,-1.,rt*z[k+1],(j,k,2,1)))
    breaks = sorted(set(v for edge in edges for v in edge[:2]))
    result = {}
    for a,b in zip(breaks[:-1],breaks[1:]):
        mid = (a+b)/2
        candidates = [edge for edge in edges if edge[0]<mid<edge[1]]
        if candidates:
            front = max(candidates,key=lambda edge: edge[2]*mid+edge[3])
            key = front[-1]
            result[key] = result.get(key,0.)+.5*(erf(math.sqrt(3)*b/width)-erf(math.sqrt(3)*a/width))
    return result


def boundaries(g, config):
    bare = visible_faces(g,False,config["heat_source"]["b_radial_mm"])
    bead = visible_faces(g,True,config["heat_source"]["b_radial_mm"])
    rows, faces = [], []
    shape = g["lattice"].shape
    for e,(idx,mat) in enumerate(zip(g["index"],g["ids"])):
        for axis in range(3):
            for sign in (-1,1):
                neighbour = idx.copy(); neighbour[axis] += sign
                other = int(g["lattice"][tuple(neighbour)]) if np.all(neighbour>=0) and np.all(neighbour<shape) else -1
                othermat = int(g["ids"][other]) if other>=0 else 0
                # 母材内部不需要边界；保留可因出生而暴露的两侧面。
                if other>=0 and (mat!=3 and othermat!=3 or mat==othermat and axis!=0):
                    continue
                artificial = (axis==0 and idx[0]+(sign==1) in (0,shape[0])) or (axis==1 and idx[1]==0 and sign==-1) or (mat==1 and axis==2 and idx[2]+(sign==1) in (0,shape[2]))
                face_area = g["volume"][e]/g["dims"][e,axis]
                key = (int(idx[1]),int(idx[2]),axis,sign)
                rows.append([e+1,other+1,axis+1,sign,face_area,float(not artificial),bare.get(key,0.) if mat!=3 else 0.,bead.get(key,0.)])
                faces.append(g["conn"][e,FACE_NODES[axis,sign]])
    return np.asarray(rows),np.asarray(faces)


def material_data(materials, physics):
    result = []
    for name in NAMES:
        mat, phy = materials["materials"][name],physics["materials"][name]
        thermal = phy["high_temperature"] if name=="ernife_ci" else mat["temperature_dependent"]
        phase = phy["phase_change"]
        ts,tl,latent = (phase[k] for k in ("solidus_c","liquidus_c","latent_heat_j_kg"))
        knots = np.unique([20.,*thermal["temperatures_c"],ts,tl,3000.])
        cp = np.interp(knots,thermal["temperatures_c"],thermal["specific_heat_j_kgk"])
        conduct = np.interp(knots,thermal["temperatures_c"],thermal["thermal_conductivity_w_mk"])/1000
        result.append(dict(rho=mat["nominal_properties_20c"]["density_kg_m3"]/1e9,
                           ts=ts,tl=tl,latent=latent,knots=knots,cp=cp,k=conduct))
    return result


def sensor_stencils(g, points):
    result = []
    for point in points:
        xyz = np.asarray(point["coordinate_s_n_z_mm"])
        idx = tuple(np.searchsorted(axis,value,side="right")-1 for axis,value in zip(g["axes"],xyz))
        if any(i<0 or i>=len(axis)-1 for i,axis in zip(idx,g["axes"])):
            raise ValueError("固定测点在域外")
        e = int(g["lattice"][idx])
        if e<0 or g["ids"][e]!=point["material_id"]:
            raise ValueError("固定测点材料不匹配")
        local = (xyz-g["nodes"][g["conn"][e,0]-1])/g["dims"][e]
        weights = np.prod(np.where(CORNERS,local,1-local),axis=1)
        result.append(dict(name=point["name"],coordinate=xyz.tolist(),element=e+1,
                           nodes=g["conn"][e].tolist(),weights=weights.tolist()))
    return result


def prepare(out, case, spec, smoke=False):
    config,process,materials,physics = [load(ROOT/spec[k]) for k in ("inputs","process_input","material_input","thermal_properties")]
    plan = load(ROOT/spec["baseline"])
    baseline=load(ROOT/plan["baseline"])
    p=config["process"]; source=plan["sources"]["surface45"]
    heating=(config["heat_source_path"]["source_end_s_mm"]-config["heat_source_path"]["source_start_s_mm"])/p["travel_speed_mm_s"]
    dt=spec["solver"]["time_step_s"]
    if not np.isclose(p["net_power_w"],p["current_a"]*p["voltage_v"]*p["efficiency"]):
        raise ValueError("冻结功率不闭合")
    if source["angle_deg"]!=45 or source["penetration_fraction"]!=0 or baseline["deposition"]["efficiency"]!=1 or baseline["deposition"]["temperature_c"]!=20:
        raise ValueError("当前独立参考只接受冻结的 surface45 与 20°C、效率1填丝，禁止静默替换情景")
    if dt<=0 or not np.isclose(heating/dt,round(heating/dt)) or not np.isclose(spec["solver"]["duration_s"],heating+baseline["solver"]["cooling_after_source_s"]):
        raise ValueError("时间步必须对齐热源结束，且总时长必须匹配冻结冷却段")
    out.mkdir(parents=True,exist_ok=False)
    mesh = {**spec["mesh"],**spec["cases"][case]}
    g = geometry(config,process,mesh)
    boundary,faceconn = boundaries(g,config)
    points = sensor_stencils(g,plan["observation_points"])
    meshdir = out/"mesh"; meshdir.mkdir()
    np.savetxt(meshdir/"mesh.nodes",np.column_stack([np.arange(1,len(g["nodes"])+1),np.full(len(g["nodes"]),-1),g["nodes"]]),fmt=["%d","%d","%.16g","%.16g","%.16g"])
    np.savetxt(meshdir/"mesh.elements",np.column_stack([np.arange(1,len(g["ids"])+1),g["ids"],np.full(len(g["ids"]),808),g["conn"]]),fmt="%d")
    np.savetxt(meshdir/"mesh.boundary",np.column_stack([np.arange(1,len(boundary)+1),np.ones(len(boundary)),boundary[:,0],np.zeros(len(boundary)),np.full(len(boundary),404),faceconn]),fmt="%d")
    (meshdir/"mesh.header").write_text(f"{len(g['nodes'])} {len(g['ids'])} {len(boundary)}\n2\n808 {len(g['ids'])}\n404 {len(boundary)}\n",encoding="ascii")
    np.savez_compressed(out/"mesh-data.npz",nodes=g["nodes"],conn=g["conn"],material=g["ids"],volume=g["volume"],index=g["index"],s_edges=g["axes"][0],n_edges=g["axes"][1],z_edges=g["axes"][2],boundary=boundary)
    p,src,path = config["process"],config["heat_source"],config["heat_source_path"]
    solver = spec["solver"]
    with (out/"reference.dat").open("w",encoding="ascii") as f:
        f.write(f"{len(g['nodes'])} {len(g['ids'])} {len(boundary)} {len(points)}\n")
        f.write(" ".join(str(x) for x in [p["net_power_w"],p["travel_speed_mm_s"],path["source_start_s_mm"],path["source_end_s_mm"],p["preheat_temperature_c"],20.,p["cooling_environment_c"],p["convection_coefficient_w_m2k"]/1e6,p["emissivity"]*5.670374419e-14,src["a_front_mm"],src["a_rear_mm"],src["front_fraction"],src["rear_fraction"],solver["inactive_fraction"],solver["output_interval_steps"]])+"\n")
        for mat in material_data(materials,physics):
            f.write(f"{mat['rho']} {mat['ts']} {mat['tl']} {mat['latent']} {len(mat['knots'])}\n")
            np.savetxt(f,np.column_stack([mat['knots'],mat['cp'],mat['k']]),fmt="%.16g")
        np.savetxt(f,np.column_stack([g["ids"],g["nodes"][g["conn"][:,0]-1,0],g["dims"][:,0],g["volume"],g["conn"]]),fmt=["%d","%.16g","%.16g","%.16g"]+["%d"]*8)
        np.savetxt(f,np.column_stack([boundary,faceconn]),fmt=["%d"]*4+["%.16g"]*4+["%d"]*4)
        for point in points:
            f.write(" ".join(map(str,[point['element'],*point['nodes'],*point['weights']]))+"\n")
    steps = 3 if smoke else round(solver["duration_s"]/solver["time_step_s"])
    (out/"case.sif").write_text(sif(solver,steps,p["preheat_temperature_c"]),encoding="ascii")
    (out/"ELMERSOLVER_STARTINFO").write_text("case.sif\n",encoding="ascii")
    inputs = [SPEC,ROOT/spec["baseline"],*[ROOT/spec[k] for k in ("inputs","process_input","material_input","thermal_properties")],Path(__file__),HERE/"ReferenceCallbacks.F90"]
    record = dict(stage="THERMAL-REF",case=case,smoke=smoke,solver="Elmer native HeatSolve/HeatSolver",mesh=mesh,
                  nodes=len(g["nodes"]),elements=len(g["ids"]),boundaries=len(boundary),bead_area_mm2=g["area"],leg_mm=g["leg"],
                  sensor_stencils=points,specification=spec,config=config,input_hashes={str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in inputs},
                  independence="No imports from FVM geometry, source, property, assembly, time integration or reconstruction code.",
                  discretization_differences=["Hex8 Galerkin temperature interpolation versus cell-centred finite volumes.","Continuous deposition uses volume fraction in density and isotropic conductivity on a fixed mesh; partial-cell contact is homogenized, not geometrically remeshed.","Inactive weld conductivity and mass use a recorded epsilon; pure dormant nodes are held at birth temperature and sensitivity is required before admission.","Native lumped FE mass with temporal secant heat capacity; birth load is reconstructed to match nodal mass addition; independently integrated enthalpy balance is audited."])
    write_json(out/"run-inputs.json",record)
    return record


def sif(solver,steps,preheat=150.):
    text = f'''Header
  CHECK KEYWORDS Warn
  Mesh DB "." "mesh"
End
Simulation
  Max Output Level = 3
  Coordinate System = Cartesian 3D
  Simulation Type = Transient
  Timestepping Method = BDF
  BDF Order = 1
  Timestep Sizes = {solver['time_step_s']}
  Timestep Intervals = {steps}
  Output Intervals = 1
End
Equation 1
  Active Solvers(3) = 1 2 3
  Convection = None
End
Solver 1
  Exec Solver = Before Timestep
  Equation = ReferencePrepare
  Procedure = "ReferenceCallbacks" "ReferencePrepare"
End
Solver 2
  Equation = Heat Equation
  Procedure = "HeatSolve" "HeatSolver"
  Variable = Temperature
  Variable DOFs = 1
  Linear System Solver = Iterative
  Linear System Iterative Method = BiCGStab
  Linear System Preconditioning = ILU0
  Linear System Max Iterations = 1500
  Linear System Convergence Tolerance = {solver['linear_tolerance']}
  Linear System Abort Not Converged = True
  Nonlinear System Max Iterations = {solver['nonlinear_iterations']}
  Nonlinear System Convergence Tolerance = {solver['nonlinear_tolerance']}
  Nonlinear System Abort Not Converged = True
  Nonlinear System Relaxation Factor = 1.0
  Nonlinear System Newton After Iterations = 1000
  Steady State Convergence Tolerance = 1.0e-12
  Stabilize = False
  Bubbles = False
  Optimize Bandwidth = True
  Lumped Mass Matrix = True
End
Solver 3
  Exec Solver = After Timestep
  Equation = ReferenceObserve
  Procedure = "ReferenceCallbacks" "ReferenceObserve"
End
Body Force 1
  Temperature = Real 20.0
  Temperature Condition = Variable Temperature
    Real Procedure "ReferenceCallbacks" "DormantCondition"
  Volumetric Heat Source = Variable Temperature
    Real Procedure "ReferenceCallbacks" "BirthSource"
End
Initial Condition 1
  Temperature = Real {preheat}
End
Boundary Condition 1
  Target Boundaries(1) = 1
  Heat Flux = Variable Temperature
    Real Procedure "ReferenceCallbacks" "SurfaceFlux"
End
'''
    for i in range(1,4):
        text += f'''Body {i}
  Equation = 1
  Material = {i}
  Body Force = 1
  Initial Condition = 1
End
Material {i}
  Density = Variable Temperature
    Real Procedure "ReferenceCallbacks" "ReferenceDensity"
  Heat Capacity = Variable Temperature
    Real Procedure "ReferenceCallbacks" "SecantCapacity"
  Heat Conductivity = Variable Temperature
    Real Procedure "ReferenceCallbacks" "ReferenceConductivity"
End
'''
    return text


def environment(home):
    env = os.environ.copy()
    env.update(ELMER_HOME=str(home),ELMER_LIB=str(home/"share/elmersolver/lib"),OMP_NUM_THREADS="1")
    env["PATH"] = str(home/"bin")+os.pathsep+str(home/"stripped_gfortran/bin")+os.pathsep+env.get("PATH","")
    return env


def run(out,home):
    env = environment(home)
    compiler = home/"stripped_gfortran/bin/x86_64-w64-mingw32-gfortran.exe"
    command = [str(compiler),str(HERE/"ReferenceCallbacks.F90"),"-O2","-shared","-fallow-argument-mismatch","-ffree-line-length-none",f"-I{home/'share/elmersolver/include'}",f"-L{home/'bin'}","-lelmersolver","-o","ReferenceCallbacks.dll"]
    result = subprocess.run(command,cwd=out,env=env,capture_output=True,text=True)
    (out/"compile.log").write_text(result.stdout+result.stderr,encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stdout+result.stderr)
    start = time.perf_counter()
    with (out/"solver.log").open("w",encoding="utf-8") as log:
        result = subprocess.run([str(home/"bin/ElmerSolver.exe"),"case.sif"],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
    write_json(out/"execution.json",dict(returncode=result.returncode,wall_seconds=time.perf_counter()-start,
                                       executable=str(home/"bin/ElmerSolver.exe"),executable_sha256=digest(home/"bin/ElmerSolver.exe")))
    if result.returncode:
        raise RuntimeError(f"Elmer failed ({result.returncode}); see {out/'solver.log'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",choices=["REF-C","REF-M","REF-F","REF-VF"],default="REF-C")
    parser.add_argument("--elmer-home",type=Path,default=Path(os.environ.get("ELMER_HOME",str(DEFAULT_HOME))))
    parser.add_argument("--output-dir",type=Path)
    parser.add_argument("--prepare-only",action="store_true")
    parser.add_argument("--smoke",action="store_true")
    args = parser.parse_args()
    out = (args.output_dir or HERE/"results"/args.case).resolve()
    record = prepare(out,args.case,load(SPEC),args.smoke)
    print(json.dumps({k:record[k] for k in ('case','nodes','elements','boundaries')},ensure_ascii=False),flush=True)
    if not args.prepare_only:
        run(out,args.elmer_home)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
