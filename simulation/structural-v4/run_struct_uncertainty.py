"""Route B非正式敏感性：真实热历史驱动已有J2材料点和候选3D弹性链。"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

import gmsh
import numpy as np
from scipy.sparse import diags
from scipy.sparse.linalg import splu
from threadpoolctl import threadpool_limits

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"simulation/thermal-ref")]
import elmer_reference as ref
import run_plan7_fvm as fvm
import run_static_screening as screen
from hanjie.simulation.constitutive3d import instantaneous_thermal_strain,j2_update
from hanjie.simulation.structural_prep import fit_position_diameter

SPEC=ROOT/"project/struct-uncertainty-route-b.yaml"
OUTPUT=ROOT/"simulation/structural-v4/results/struct-uncertainty"
TIMES=np.unique(np.round(np.r_[0.,5.,10.,np.arange(15.,26.001,.1),30.,35.,40.,45.,50.,55.,60.],10))


class PlaneRecorder:
    def __init__(self,out,g,tables,lengths,rho,dt):
        self.out=out; self.times=[]; self.rows=[]
        s0=int(np.searchsorted(g["s_edges"],0.)-1)
        left=np.flatnonzero((g["ids"]==2)&(g["index"][:,0]==s0))
        right=g["lattice"][s0+1,g["index"][left,1],g["index"][left,2]]
        self.pairs=np.column_stack([left,right])
        self.index=g["index"][left,1:]
        self.coords=np.column_stack([((g["n_edges"][:-1]+g["n_edges"][1:])/2)[self.index[:,0]],((g["z_edges"][:-1]+g["z_edges"][1:])/2)[self.index[:,1]]])

    def record(self,t,temp,*unused):
        if np.any(np.isclose(t,TIMES,atol=1.e-8,rtol=0)):
            self.times.append(t); self.rows.append(temp[self.pairs].mean(axis=1))

    def finish(self):
        np.savez_compressed(self.out/"plane-history.npz",times=np.r_[0.,self.times],temperature=np.vstack([np.full(len(self.pairs),150.),self.rows]),coordinates=self.coords,index=self.index)


def drivers(out):
    target=out/"thermal-drivers.npz"
    if target.exists():
        saved=ref.load(out/"thermal-driver-inputs.json")
        if saved.get("driver_sha256")!=ref.digest(target) or not saved.get("source_input_hashes"):
            raise ValueError("热历史检查点缺少有效来源记录")
        if any(ref.digest(ROOT/path)!=digest for path,digest in saved["source_input_hashes"].items()):
            raise ValueError("热历史输入已改变，禁止复用旧检查点")
        return np.load(target)
    thermal=out/"fvm-history"
    if not (thermal/"plane-history.npz").exists():
        fvm.run(thermal,False,observer_factory=PlaneRecorder)
    fv=np.load(thermal/"plane-history.npz")
    base=ROOT/"simulation/thermal-ref/results/REF-C"
    replay=ROOT/"simulation/thermal-ref/results/plan8/elmer-dynamic"
    mesh=np.load(replay/"mesh-data.npz")
    lookup={tuple(index):i for i,index in enumerate(mesh["index"])}
    s0=int(np.searchsorted(mesh["s_edges"],0.)-1)
    pairs=np.array([[lookup[s0,int(j),int(k)],lookup[s0+1,int(j),int(k)]] for j,k in fv["index"]])
    history=[]; sources=[]
    for t in TIMES:
        if t==0:
            history.append(np.full(len(pairs),150.)); continue
        source=replay/f"field-{round((t-15.)*10):05d}.dat" if 15.<t<=26.+1.e-8 else base/f"field-{round(t*10):05d}.dat"
        field=np.loadtxt(source)[:,0]
        history.append(field[mesh["conn"][pairs]-1].mean(axis=(1,2)))
        sources.append(dict(path=source.relative_to(ROOT).as_posix(),sha256=ref.digest(source)))
    if not np.allclose(fv["times"],TIMES,rtol=0,atol=1.e-8):
        raise ValueError("两套材料点热历史时间层不匹配")
    np.savez_compressed(target,times=TIMES,coordinates=fv["coordinates"],index=fv["index"],elmer=history,fvm=fv["temperature"],n_edges=mesh["n_edges"],z_edges=mesh["z_edges"])
    thermal_inputs=ref.load(thermal/"run-inputs.json")["input_hashes"]
    ref.write_json(out/"thermal-driver-inputs.json",dict(sources=sources,fvm_execution=ref.digest(thermal/"execution.json"),driver_sha256=ref.digest(target),
                   source_input_hashes={k:v for k,v in thermal_inputs.items() if k.endswith(".yaml")},
                   projection="QT P0 means averaged across adjacent s=-1/+1 mm C cells; no sensor reconstruction",formal_thermal_history=False,
                   outside_window_time_spacing_s=5.,near_peak_time_spacing_s=.1,maximum_elmer_qt_c=float(np.max(history)),maximum_fvm_qt_c=float(fv["temperature"].max())))
    return np.load(target)


def plastic_profiles(data,spec,out):
    target=out/"plastic-profiles.npz"
    mat=ref.load(ROOT/spec["material_input"])["materials"][spec["material"]]
    table=mat["temperature_dependent"]; profiles={}; checks=[]
    for source in ("fvm","elmer"):
        # 末端冷却是机械端点情景，不把补出的时间或温度冒充热求解输出。
        history=np.vstack([np.full(data[source].shape[1],20.),data[source],np.linspace(data[source][-1],np.full(data[source].shape[1],20.),41)[1:]])
        alpha=instantaneous_thermal_strain(history,table["temperatures_c"],table["alpha_per_k"])
        E=np.interp(history,table["temperatures_c"],table["elastic_modulus_gpa"])*1000
        yield_base=np.interp(history,table["temperatures_c"],table["yield_strength_mpa"])
        for scenario,bounds in spec["material_scenarios"].items():
            eth=alpha*bounds["alpha_scale"]; ys=yield_base*bounds["yield_scale"]
            for restraint in spec["restraint_fractions"]:
                result=np.zeros((history.shape[1],3)); work=0.; maxtrace=0.
                for point in range(history.shape[1]):
                    if np.max(E[:,point]/1.27*restraint*abs(eth[:,point])/ys[:,point])<=1.:
                        continue
                    state={}
                    for step in range(len(history)):
                        thermal=float(eth[step,point]); strain=np.diag([thermal,(1-restraint)*thermal,thermal])
                        state=j2_update(strain,thermal,state,elastic_modulus_mpa=E[step,point],poisson_ratio=.27,yield_strength_mpa=ys[step,point],hardening_modulus_mpa=spec["hardening_modulus_mpa"])
                    result[point]=np.diag(state["plastic_strain"])
                    work+=state["plastic_dissipation_mj_mm3"]; maxtrace=max(maxtrace,abs(float(np.trace(state["plastic_strain"]))))
                key=f"{source}__{scenario}__{restraint}"
                profiles[key]=result
                checks.append(dict(profile=key,plastic_work_sum_mj_mm3=work,maximum_plastic_trace=maxtrace,active_points=int(np.count_nonzero(np.linalg.norm(result,axis=1)>0))))
                print("J2 profile",key,checks[-1]["active_points"],flush=True)
    np.savez_compressed(target,**profiles)
    ref.write_json(out/"material-point-checks.json",dict(checks=checks,passed=all(c["plastic_work_sum_mj_mm3"]>=0 and c["maximum_plastic_trace"]<1.e-10 for c in checks),
                   model="Existing 3D J2 update under prescribed tangential restraint; not a coupled structural solution"))
    return profiles


def load_mesh(model,resolution):
    folder=model.lower().replace("_","-"); path=ROOT/"simulation/structural-v4/meshes"/folder/f"{resolution}.msh"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal",0); gmsh.open(str(path))
        tags,points,_=gmsh.model.mesh.getNodes(); lookup={int(tag):i for i,tag in enumerate(tags)}
        _,tet=gmsh.model.mesh.getElementsByType(4); _,tri=gmsh.model.mesh.getElementsByType(2)
        return screen.VolumeMesh(points.reshape(-1,3),np.array([lookup[int(t)] for t in tet]).reshape(-1,4),np.array([lookup[int(t)] for t in tri]).reshape(-1,3)),path
    finally:
        gmsh.finalize()


def support_areas(mesh):
    radii=np.linalg.norm(mesh.points[:,:2],axis=1)
    faces=mesh.boundary_triangles[np.all(np.isclose(radii[mesh.boundary_triangles],74.98,atol=1.e-5,rtol=0),axis=1)]
    points=mesh.points[faces]
    area=np.linalg.norm(np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0]),axis=1)/2
    weights=np.zeros(len(mesh.points)); np.add.at(weights,faces.ravel(),np.repeat(area/3,3))
    if weights.sum()<=0:
        raise ValueError("未找到真实圆柱连接面")
    return weights


def operators(mesh,data,E,nu):
    xyz=mesh.points[mesh.tetrahedra]
    inverse=np.linalg.inv(np.concatenate([np.ones((*xyz.shape[:2],1)),xyz],axis=2))
    gradient=inverse[:,1:,:].transpose(0,2,1)
    volume=abs(np.linalg.det(xyz[:,1:]-xyz[:,:1]))/6
    centres=xyz.mean(axis=1); radius=np.linalg.norm(centres[:,:2],axis=1); angle=np.arctan2(centres[:,1],centres[:,0])
    j=np.searchsorted(data["n_edges"],radius-75.,side="right")-1
    k=np.searchsorted(data["z_edges"],centres[:,2]-12.,side="right")-1
    lookup={tuple(idx):i for i,idx in enumerate(data["index"])}
    mapping=np.array([lookup.get((int(a),int(b)),-1) for a,b in zip(j,k)])
    # 内圈无热源域不作温度外推，固有应变显式置零并登记其体积。
    def force(profile_low,profile_high,pattern):
        selected=np.maximum(mapping,0)
        if pattern=="uniform_half":
            local=profile_low[selected].copy()
        elif pattern=="uniform_full":
            local=profile_high[selected].copy()
        else:
            direction=np.deg2rad(float(pattern.split("_")[1]))
            local=np.where((np.cos(angle-direction)>=0)[:,None],profile_high[selected],profile_low[selected])
        local[mapping<0]=0.
        cr,sr=np.cos(angle),np.sin(angle); p=np.zeros((len(local),3,3))
        p[:,0,0]=local[:,0]*cr**2+local[:,1]*sr**2; p[:,1,1]=local[:,0]*sr**2+local[:,1]*cr**2
        p[:,0,1]=p[:,1,0]=(local[:,0]-local[:,1])*cr*sr; p[:,2,2]=local[:,2]
        shear=E/(2*(1+nu)); lam=E*nu/((1+nu)*(1-2*nu))
        stress=2*shear*p+lam*np.trace(p,axis1=1,axis2=2)[:,None,None]*np.eye(3)
        nodal=np.einsum("eij,enj->eni",stress,gradient)*volume[:,None,None]
        result=np.zeros_like(mesh.points); np.add.at(result,mesh.tetrahedra.ravel(),nodal.reshape(-1,3))
        return result.ravel()
    return force,dict(total_volume_mm3=float(volume.sum()),mapped_volume_mm3=float(volume[mapping>=0].sum()),zero_inherent_strain_outside_domain_mm3=float(volume[mapping<0].sum()))


def position(mesh,u):
    angle=np.linspace(0,2*np.pi,64,endpoint=False)
    datum_a=np.column_stack([77.5*np.cos(angle),77.5*np.sin(angle),np.zeros(64)])
    datum_b=np.vstack([np.column_stack([80*np.cos(angle),80*np.sin(angle),np.full(64,z)]) for z in (0.,200.)])
    bore=np.isclose(np.linalg.norm(mesh.points[:,:2],axis=1),20.,atol=1.e-5,rtol=0)
    return fit_position_diameter(datum_a,datum_b,mesh.points[bore]+u.reshape(-1,3)[bore])


def run(out):
    out.mkdir(parents=True,exist_ok=True); spec=ref.load(SPEC)
    data=drivers(out); profiles=plastic_profiles(data,spec,out)
    material=ref.load(ROOT/spec["material_input"])["materials"]["qt450_10"]["nominal_properties_20c"]
    E=material["elastic_modulus_gpa"]*1000; nu=material["poisson_ratio"]
    screen.YOUNG_MODULUS_MPA=E; screen.POISSON_RATIO=nu
    rows=[]; meshes=[]
    for model in spec["candidates"]:
        for resolution in spec["meshes"]:
            mesh,path=load_mesh(model,resolution)
            basis,elastic,_,_=screen._assemble_system(mesh,0.)
            if not np.array_equal(basis.nodal_dofs.T.ravel(),np.arange(basis.N)):
                raise ValueError("结构自由度顺序改变")
            weights=support_areas(mesh); force,mapping=operators(mesh,data,E,nu)
            meshes.append(dict(candidate=model,resolution=resolution,mesh_sha256=ref.digest(path),nodes=len(mesh.points),elements=len(mesh.tetrahedra),interface_area_mm2=float(weights.sum()),**mapping))
            loads=[]; cases=[]
            for source in ("fvm","elmer"):
                for scenario in spec["material_scenarios"]:
                    low=profiles[f"{source}__{scenario}__0.5"]; high=profiles[f"{source}__{scenario}__1.0"]
                    for pattern in spec["restraint_patterns"]:
                        loads.append(force(low,high,pattern)); cases.append((source,scenario,pattern))
            loads=np.column_stack(loads)
            for foundation in spec["foundation_stiffness_n_mm3"]:
                stiffness=elastic+diags(np.repeat(weights*foundation,3))
                solution=splu(stiffness.tocsc()).solve(loads)
                for column,(source,scenario,pattern) in enumerate(cases):
                    u=solution[:,column]; load=loads[:,column]
                    relative=float(np.linalg.norm(stiffness@u-load)/max(np.linalg.norm(load),1.))
                    if relative>spec["checks"]["relative_linear_residual_limit"]:
                        raise RuntimeError("结构线性平衡残差未通过")
                    fit=position(mesh,u)
                    rows.append(dict(candidate=model,resolution=resolution,thermal_source=source,material_scenario=scenario,restraint_pattern=pattern,
                                     foundation_n_mm3=foundation,position_sensitivity_diameter_mm=fit["position_diameter_mm"],bore_fit_rms_mm=fit["bore_fit_rms_mm"],
                                     relative_linear_residual=relative,maximum_displacement_mm=float(np.max(np.linalg.norm(u.reshape(-1,3),axis=1))),
                                     formal_welding_residual_prediction=False))
            print("structure",model,resolution,len(rows),flush=True)
            with (out/"cases.csv").open("w",newline="",encoding="utf-8") as f:
                writer=csv.DictWriter(f,fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
    ref.write_json(out/"run-inputs.json",dict(specification=spec,spec_sha256=ref.digest(SPEC),meshes=meshes,
                   thermal_driver_sha256=ref.digest(out/"thermal-drivers.npz"),material_input_sha256=ref.digest(ROOT/spec["material_input"]),
                   source_code_hashes={p.relative_to(ROOT).as_posix():ref.digest(p) for p in [Path(__file__),ROOT/"simulation/structural-v4/run_static_screening.py",ROOT/"src/hanjie/simulation/constitutive3d.py",ROOT/"src/hanjie/simulation/structural_prep.py"]}))
    return rows


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--output-dir",type=Path,default=OUTPUT)
    args=parser.parse_args()
    with threadpool_limits(limits=1):
        run(args.output_dir.resolve())
