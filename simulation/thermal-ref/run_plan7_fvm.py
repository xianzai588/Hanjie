"""Plan 7 的 FVM 对照分支；复用既有 FVM 内核，不被 Elmer 构造器导入。"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

import numpy as np
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/"simulation/thermal-v5"), str(ROOT/"src")]
import run_mass_closed04 as core
from credibility_source import projected_boundary_faces, boundary_face_source_power
from mass_closed_geometry import longitudinal_integral
from hanjie.simulation.thermal_ledgers import build_material_point_stencil


def preborn_power(g,bare,bead,start,end,center,source,power):
    """预出生仅改变可见表面分段，保留原热源积分与守恒散射。"""
    s=g["s_edges"]
    args=(center,source["a_front_mm"],source["a_rear_mm"],source["front_fraction"],source["rear_fraction"])
    whole=longitudinal_integral(s[:-1],s[1:],*args)
    lo=np.maximum(s[:-1],start)
    deposited=longitudinal_integral(lo,np.maximum(lo,np.minimum(s[1:],end)),*args)
    q=np.zeros(len(g["ids"]))
    for faces,along in ((bare,whole-deposited),(bead,deposited)):
        cells=g["lattice"][:,faces["j"],faces["k"]]
        if np.any(cells<0):
            raise ValueError("预出生热流无相邻控制体")
        np.add.at(q,cells.ravel(),(power*along[:,None]*faces["fraction"][None,:]).ravel())
    return q


def run(out,preborn,*,end_time_s=None,constant_properties=False,observer_factory=None):
    out.mkdir(parents=True,exist_ok=False)
    plan=core.load(ROOT/"project/thermal-boundary-neumann-v5.7.yaml")
    spec=core.load(ROOT/plan["baseline"])
    refspec=core.load(ROOT/"project/thermal-reference-elmer.yaml")
    mesh={**refspec["mesh"],**refspec["cases"]["REF-C"]}
    spec["mesh"].update(mesh,bead_strips=6,cross_local_base_spacing_mm=mesh["near_spacing_mm"])
    config=core.load(ROOT/spec["inputs"])
    process=core.load(ROOT/spec["process_input"])
    g=core.build_geometry(config,process,spec)
    tables,lengths,rho=core.material_tables(core.load(ROOT/spec["material_input"])["materials"],core.load(ROOT/spec["thermal_properties"])["materials"])
    if constant_properties:
        # 最后一个控制组冻结每种材料150°C的k/cp，保持密度和异材身份。
        for m,count in enumerate(lengths):
            cp=float(np.interp(150.,tables[m,0,:count],tables[m,1,:count]))
            k=float(np.interp(150.,tables[m,0,:count],tables[m,4,:count]))
            tables[m,1,:count]=cp; tables[m,2,:count]=0.
            tables[m,3,:count]=cp*(tables[m,0,:count]-20.); tables[m,4,:count]=k
    ids=g["ids"]; reference_mass=rho[ids-1]*g["volumes"]
    p,source,path=config["process"],config["heat_source"],config["heat_source_path"]
    start,end=path["source_start_s_mm"],path["source_end_s_mm"]
    duration=(end-start)/p["travel_speed_mm_s"]
    dt=refspec["solver"]["time_step_s"]; total=refspec["solver"]["duration_s"]
    if end_time_s is not None:
        total=float(end_time_s)
    if not np.isclose(p["net_power_w"],p["efficiency"]*p["voltage_v"]*p["current_a"]):
        raise ValueError("冻结功率不一致")
    bare,bead=[projected_boundary_faces(g,b,source["b_radial_mm"],**plan["sources"]["surface45"]) for b in (False,True)]
    fraction=core.filled_fraction(g,start,end,end-start if preborn else 0.)
    mass=reference_mass*fraction
    temperature=np.where(fraction>0,p["preheat_temperature_c"],20.)
    initial=float(np.dot(mass,core.material_state(temperature,ids,tables,lengths)[0]))
    deposit_h=core.material_state(np.full(len(ids),20.),ids,tables,lengths)[0]
    stencils=[build_material_point_stencil(g,point["coordinate_s_n_z_mm"],point["material_id"],point["stencil_neighbours"]) for point in plan["observation_points"]]
    names=[point["name"] for point in plan["observation_points"]]
    rows=[]; history=[]; qsum=csum=rsum=bsum=0.; max_residual=0.
    files=[Path(__file__),ROOT/"simulation/thermal-v5/run_mass_closed04.py",ROOT/"simulation/thermal-v5/mass_closed_geometry.py",ROOT/"simulation/thermal-v5/physics.py",ROOT/"simulation/thermal-v5/credibility_source.py",ROOT/"src/hanjie/simulation/thermal_ledgers.py",*[ROOT/spec[k] for k in ("inputs","process_input","material_input","thermal_properties")],ROOT/"project/thermal-boundary-neumann-v5.7.yaml",ROOT/"project/thermal-reference-elmer.yaml"]
    core.write_json(out/"run-inputs.json",dict(stage="THERMAL-REF-PLAN8" if observer_factory else "THERMAL-REF-PLAN7",mesh=spec["mesh"],preborn=preborn,constant_properties=constant_properties,initial_temperature_c=150.,
                    cell_count=len(ids),initial_enthalpy_j=initial,source="surface45 explicit boundary face Neumann",time_step_s=dt,duration_s=total,
                    input_hashes={str(f.relative_to(ROOT)).replace('\\','/'):core.digest(f) for f in files},thermal_1_allowed=False))
    np.savez_compressed(out/"grid-axes.npz",s_edges=g["s_edges"],n_edges=g["n_edges"],z_edges=g["z_edges"])
    observer=observer_factory(out,g,tables,lengths,rho,dt) if observer_factory else None
    clock=time.perf_counter()
    for step in range(1,round(total/dt)+1):
        finish=step*dt
        new_fraction=fraction if preborn else core.filled_fraction(g,start,end,min(finish,duration)*p["travel_speed_mm_s"])
        new_mass=reference_mass*new_fraction
        oldh,_,k=core.material_state(temperature,ids,tables,lengths)
        born=(new_mass-mass)*deposit_h
        matrix,exposed=core._conductance_matrix(g,new_fraction,k,dt)
        qc=p["convection_coefficient_w_m2k"]*(temperature-p["cooling_environment_c"])*exposed/1.e6
        qr=p["emissivity"]*5.670374419e-14*((temperature+273.15)**4-(p["cooling_environment_c"]+273.15)**4)*exposed
        q=np.zeros(len(ids))
        if finish-dt<duration-1.e-10:
            fn=preborn_power if preborn else boundary_face_source_power
            q=fn(g,bare,bead,start,end,start+p["travel_speed_mm_s"]*(finish-dt/2),source,p["net_power_w"])
            if np.any(q < -1.e-10) or np.any((new_fraction==0)&(q>1.e-12)) or not np.isclose(q.sum(),p["net_power_w"],rtol=1.e-8):
                raise ValueError("热源空间积分或活动域不匹配")
        temperature,iterations,residual=core.enthalpy_step(temperature,new_mass,mass*oldh+born,matrix,dt*(q-qc-qr),ids,tables,lengths,spec["solver"]["nonlinear_residual_j"],spec["solver"]["maximum_newton_iterations"])
        mass,fraction=new_mass,new_fraction
        qsum+=float(q.sum()*dt); csum+=float(qc.sum()*dt); rsum+=float(qr.sum()*dt); bsum+=float(born.sum())
        energy=float(np.dot(mass,core.material_state(temperature,ids,tables,lengths)[0]))-initial
        balance=qsum+bsum-csum-rsum-energy
        max_residual=max(max_residual,residual)
        rows.append([finish,*[float(np.dot(temperature[s["cell_indices"]],s["weights"])) for s in stencils]])
        history.append([finish,qsum,csum+rsum,bsum,energy,balance,float(np.sum(g["volumes"][ids==3]*fraction[ids==3])),float(temperature[fraction>0].min()),float(temperature.max())])
        if observer is not None:
            observer.record(finish,temperature,fraction,mass,q,qc+qr,born,matrix)
        if step%100==0:
            print(out.name,finish,round(time.perf_counter()-clock,1),balance,flush=True)
    np.savetxt(out/"sensors.dat",rows,fmt="%.15g")
    np.savetxt(out/"history.csv",history,delimiter=",",comments="",header="time_s,source_j,loss_j,birth_j,energy_change_j,residual_j,deposit_volume_mm3,min_c,max_c",fmt="%.15g")
    core.write_json(out/"execution.json",dict(returncode=0,wall_seconds=time.perf_counter()-clock,maximum_nonlinear_residual_j=max_residual,points=names))
    if observer is not None:
        observer.finish()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=["dynamic","preborn"])
    parser.add_argument("--output-dir",type=Path)
    args=parser.parse_args()
    with threadpool_limits(limits=1):
        run((args.output_dir or Path(__file__).parent/"results/plan7"/f"fvm-{args.mode}").resolve(),args.mode=="preborn")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
