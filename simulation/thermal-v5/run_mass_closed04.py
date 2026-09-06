"""THERMAL0.4：质量闭合角焊道、表面热流和隐式相变焓的单工况验证。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
from numba import njit
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import cg
from threadpoolctl import threadpool_limits

from mass_closed_geometry import build_geometry, filled_fraction, surface_weights, source_power, face_geometry
from physics import material_tables
from run_physics03 import ROOT, digest, load, write_json

SPEC = ROOT/"project/thermal-mass-closed-v5.4.yaml"
OUTPUT = ROOT/"simulation/thermal-v5/results/mass-closed04"


@njit(cache=True)
def material_state(temperature, ids, tables, lengths):
    h,cp,k = np.empty(len(ids)),np.empty(len(ids)),np.empty(len(ids))
    for cell in range(len(ids)):
        t = temperature[cell]
        if not 20.-1e-9<=t<=3000.:
            raise ValueError("温度超出20–3000°C物性域，不能静默截断")
        m = ids[cell]-1
        i = 0
        while i<lengths[m]-2 and t>=tables[m,0,i+1]:
            i += 1
        delta = t-tables[m,0,i]
        h[cell] = tables[m,3,i]+tables[m,1,i]*delta+.5*tables[m,2,i]*delta**2
        cp[cell] = tables[m,1,i]+tables[m,2,i]*delta
        k[cell] = tables[m,4,i]+(tables[m,4,i+1]-tables[m,4,i])*delta/(tables[m,0,i+1]-tables[m,0,i])
    return h,cp,k


def enthalpy_step(temperature,mass,old_energy,conductance,external_energy,ids,tables,lengths,tolerance,max_iterations):
    """隐式解m*h(T)+dt*K*T=U_old+E_birth+E_external；K已包含dt。"""
    target = old_energy+external_energy
    current = temperature.copy()
    inactive = mass==0
    current[inactive] = 20.
    for iteration in range(max_iterations):
        h,cp,_ = material_state(current,ids,tables,lengths)
        residual = mass*h+conductance@current-target
        residual[inactive] = current[inactive]-20.
        norm = float(np.max(np.abs(residual)))
        if norm<=tolerance:
            return current,iteration+1,norm
        matrix = conductance+diags(np.where(inactive,1.,mass*cp))
        update,info = cg(matrix,-residual,M=diags(1/matrix.diagonal()),rtol=1e-10,atol=1e-12,maxiter=1000)
        if info!=0:
            raise RuntimeError(f"隐式热方程线性解未收敛：{info}")
        step = 1.
        accepted = False
        for _ in range(30):
            candidate = current+step*update
            if candidate.min()>=20.-1e-9 and candidate.max()<=3000.:
                new_h,_,_ = material_state(candidate,ids,tables,lengths)
                trial = mass*new_h+conductance@candidate-target
                trial[inactive] = candidate[inactive]-20.
                if np.max(np.abs(trial))<norm or np.max(np.abs(trial))<=tolerance:
                    current = candidate
                    accepted = True
                    break
            step *= .5
        if not accepted:
            raise RuntimeError("非线性焓更新无法收敛或温度超出物性范围")
    raise RuntimeError("达到相变焓非线性迭代上限")


def _conductance_matrix(geometry,fraction,conductivity,dt):
    area,distance,exposed = face_geometry(geometry,fraction)
    i,j = geometry["edge_i"],geometry["edge_j"]
    value = dt*area/distance*2*conductivity[i]*conductivity[j]/(conductivity[i]+conductivity[j])
    size = len(fraction)
    matrix = coo_matrix((np.r_[value,value,-value,-value],(np.r_[i,j,i,j],np.r_[i,j,j,i])),shape=(size,size)).tocsr()
    return matrix,exposed


def run(spec,output):
    config = load(ROOT/spec["inputs"])
    process_input = load(ROOT/spec["process_input"])
    materials = load(ROOT/spec["material_input"])["materials"]
    physics = load(ROOT/spec["thermal_properties"])
    geometry = build_geometry(config,process_input,spec)
    tables,lengths,rho = material_tables(materials,physics["materials"])
    ids = geometry["ids"]
    reference_mass = rho[ids-1]*geometry["volumes"]
    p,source,path = config["process"],config["heat_source"],config["heat_source_path"]
    start,end = path["source_start_s_mm"],path["source_end_s_mm"]
    duration = (end-start)/p["travel_speed_mm_s"]
    total = duration+spec["solver"]["cooling_after_source_s"]
    power = p["efficiency"]*p["current_a"]*p["voltage_v"]
    if not np.isclose(power,p["net_power_w"]) or not np.isclose(power/p["travel_speed_mm_s"],p["net_line_energy_j_per_mm"]):
        raise ValueError("冻结工艺的功率定义不一致")
    bare = surface_weights(geometry,False,source["b_radial_mm"])
    bead = surface_weights(geometry,True,source["b_radial_mm"])
    fraction = filled_fraction(geometry,start,end,0.)
    mass = reference_mass*fraction
    temperature = np.where(ids==3,spec["deposition"]["temperature_c"],p["preheat_temperature_c"])
    deposit_h = material_state(np.full(len(ids),spec["deposition"]["temperature_c"]),ids,tables,lengths)[0]
    initial_energy = float(np.sum(mass*material_state(temperature,ids,tables,lengths)[0]))
    parent_mass = float(mass[ids!=3].sum())
    peak = temperature.copy()
    t800,t500 = np.full(len(ids),np.nan),np.full(len(ids),np.nan)
    maximum_cooling = np.zeros(len(ids))
    peak_time = np.zeros(len(ids))
    accumulated_source,absorbed_source,birth_energy,conv_energy,rad_energy = 0.,0.,0.,0.,0.
    maximum_mass_error,maximum_parent_mass_error = 0.,0.
    min_capture = 1.
    max_newton,max_residual = 0,0.
    elapsed,steps,next_progress = 0.,0,0.
    history = []
    wall_start = time.perf_counter()
    while elapsed<total-1e-10:
        dt = min(spec["solver"]["time_step_s"],total-elapsed)
        if elapsed<duration:
            dt = min(dt,duration-elapsed)
        finish = elapsed+dt
        new_fraction = filled_fraction(geometry,start,end,min(finish,duration)*p["travel_speed_mm_s"])
        new_mass = reference_mass*new_fraction
        expected_volume = geometry["wire_area_per_length_mm2"]*min(finish,duration)*p["travel_speed_mm_s"]
        deposited_volume = float(np.sum(geometry["volumes"][ids==3]*new_fraction[ids==3]))
        mass_error = abs(deposited_volume-expected_volume)/max(expected_volume,1e-30)
        maximum_mass_error = max(maximum_mass_error,mass_error)
        maximum_parent_mass_error = max(maximum_parent_mass_error,abs(float(new_mass[ids!=3].sum())-parent_mass)/parent_mass)
        old_h,_,k = material_state(temperature,ids,tables,lengths)
        born = (new_mass-mass)*deposit_h
        energy = mass*old_h+born
        matrix,exposed = _conductance_matrix(geometry,new_fraction,k,dt)
        qc = p["convection_coefficient_w_m2k"]*(temperature-p["cooling_environment_c"])/1e6*exposed
        qr = p["emissivity"]*5.670374419e-14*((temperature+273.15)**4-(p["cooling_environment_c"]+273.15)**4)*exposed
        q = np.zeros(len(ids))
        if elapsed<duration:
            center = start+p["travel_speed_mm_s"]*(elapsed+dt/2)
            q = source_power(geometry,bare,bead,start,end,center,source,power)
            if np.any((new_fraction==0)&(q>1e-12)):
                raise ValueError("热源沉积到尚未出生的填丝")
            min_capture = min(min_capture,float(q.sum()/power))
            accumulated_source += power*dt
        temperature_new,iterations,residual = enthalpy_step(temperature,new_mass,energy,matrix,dt*(q-qc-qr),ids,tables,lengths,
            spec["solver"]["nonlinear_residual_j"],spec["solver"]["maximum_newton_iterations"])
        cooling = (temperature-temperature_new)/dt
        maximum_cooling = np.maximum(maximum_cooling,cooling)
        # 再加热超过800°C时重启冷却周期，避免拼接两次独立热循环。
        reheated = (temperature<800)&(temperature_new>=800)
        t800[reheated],t500[reheated] = np.nan,np.nan
        down800 = (temperature>=800)&(temperature_new<800)
        t800[down800] = elapsed+dt*(temperature[down800]-800)/(temperature[down800]-temperature_new[down800])
        down500 = (temperature>=500)&(temperature_new<500)&np.isfinite(t800)
        t500[down500] = elapsed+dt*(temperature[down500]-500)/(temperature[down500]-temperature_new[down500])
        higher = temperature_new>peak
        peak[higher],peak_time[higher] = temperature_new[higher],finish
        temperature,mass,fraction = temperature_new,new_mass,new_fraction
        absorbed_source += float(q.sum()*dt)
        birth_energy += float(born.sum())
        conv_energy += float(qc.sum()*dt)
        rad_energy += float(qr.sum()*dt)
        max_newton,max_residual = max(max_newton,iterations),max(max_residual,residual)
        elapsed,steps = finish,steps+1
        if elapsed>=next_progress-1e-10 or elapsed>=total-1e-10:
            current_energy = float(np.sum(mass*material_state(temperature,ids,tables,lengths)[0]))
            balance = absorbed_source+birth_energy-conv_energy-rad_energy-(current_energy-initial_energy)
            history.append(dict(time_s=elapsed,deposit_volume_mm3=deposited_volume,expected_deposit_volume_mm3=expected_volume,
                parent_mass_kg=parent_mass,peak_temperature_c=float(peak.max()),source_j=accumulated_source,
                absorbed_source_j=absorbed_source,energy_residual_j=balance))
            print(json.dumps(dict(time_s=round(elapsed,4),peak_c=round(float(peak.max()),3),deposit_mm3=round(deposited_volume,5),
                energy_residual_j=balance,wall_s=round(time.perf_counter()-wall_start,2))),flush=True)
            next_progress = elapsed+5.
    final_energy = float(np.sum(mass*material_state(temperature,ids,tables,lengths)[0]))
    residual = absorbed_source+birth_energy-conv_energy-rad_energy-(final_energy-initial_energy)
    active = fraction>0
    valid = active&(peak>800)&np.isfinite(t800)&np.isfinite(t500)&(t500>t800)
    stats = {}
    ss = geometry["s_left"]+geometry["dims"][:,0]/2
    nc = (geometry["n_edges"][:-1]+geometry["n_edges"][1:])/2
    zc = (geometry["z_edges"][:-1]+geometry["z_edges"][1:])/2
    nn,zz = nc[geometry["index"][:,1]],zc[geometry["index"][:,2]]
    for name,code in (("q235b",1),("qt450_10",2),("ernife_ci",3)):
        mask = (ids==code)&active
        phase = physics["materials"][name]["phase_change"]
        melted = mask&(peak>phase["solidus_c"])
        liquid = mask&(peak>=phase["liquidus_c"])
        volumes = geometry["volumes"]*fraction
        melt_volume = float(volumes[melted].sum())
        section_areas = np.bincount(geometry["index"][melted,0],weights=volumes[melted]/geometry["dims"][melted,0],minlength=len(geometry["s_edges"])-1)
        stats[name] = dict(peak_temperature_c=float(peak[mask].max()),solidus_c=phase["solidus_c"],liquidus_c=phase["liquidus_c"],
            ever_solidus_exceeded_volume_mm3=melt_volume,ever_liquidus_exceeded_volume_mm3=float(volumes[liquid].sum()),
            maximum_cross_section_solidus_area_mm2=float(section_areas.max()),
            solidus_region_n_extent_mm=[float(nn[melted].min()),float(nn[melted].max())] if melted.any() else None,
            solidus_region_z_extent_mm=[float(zz[melted].min()),float(zz[melted].max())] if melted.any() else None,
            t8_5_valid_count=int((valid&mask).sum()),
            exposure_above_400c_volume_mm3=float(volumes[mask&(peak>=400)].sum()))
    both = all(stats[k]["ever_solidus_exceeded_volume_mm3"]>0 for k in ("qt450_10","q235b"))
    checks = dict(weld_mass_consistency=maximum_mass_error<=spec["solver"]["mass_relative_tolerance"],
        parents_always_present=maximum_parent_mass_error<=1e-12,
        source_deposition_on_active_material=min_capture>=spec["source"]["minimum_active_source_fraction"],
        energy_conservation=abs(residual)/accumulated_source*100<=spec["solver"]["energy_residual_pct_limit"],
        material_specific_enthalpy_implemented=True,phase_change_triggered=any(v["ever_solidus_exceeded_volume_mm3"]>0 for v in stats.values()),
        two_parent_solidus_exceeded=both,plausible_two_sided_fusion=False,
        evidence_supported_high_temperature_properties=False,progressive_mesh_convergence=False)
    summary = dict(stage="THERMAL-0.4-MASS-CLOSED",evidence_level="solver_result_unvalidated",geometry=dict(
        cell_count=len(ids),grid_shape=list(geometry["lattice"].shape),bead_area_mm2=geometry["bead_area_mm2"],
        deposited_equivalent_leg_mm=geometry["deposited_leg_mm"],nominal_design_leg_mm=spec["geometry"]["nominal_design_leg_mm"],
        parent_material_ids_preserved=True,gap_mm=geometry["gap_mm"]),
        process=p,source_model=spec["source"],material_statistics=stats,
        mass=dict(final_deposit_volume_mm3=deposited_volume,expected_deposit_volume_mm3=expected_volume,
            final_deposit_mass_kg=float(mass[ids==3].sum()),parent_mass_kg=parent_mass,maximum_relative_deposit_error=maximum_mass_error,
            maximum_relative_parent_mass_error=maximum_parent_mass_error),
        energy=dict(nominal_source_j=accumulated_source,absorbed_source_j=absorbed_source,uncaptured_source_j=accumulated_source-absorbed_source,
            minimum_active_source_fraction=min_capture,birth_enthalpy_j=birth_energy,convection_j=conv_energy,radiation_j=rad_energy,
            internal_energy_change_j=final_energy-initial_energy,residual_j=residual,residual_pct=abs(residual)/accumulated_source*100),
        solver=dict(steps=steps,time_step_s=spec["solver"]["time_step_s"],maximum_newton_iterations=max_newton,
            maximum_nonlinear_residual_j=max_residual,wall_seconds=time.perf_counter()-wall_start),checks=checks,
        thermal_1_allowed=False,formal_struct_0_allowed=False,
        evidence_boundary=["阶梯三角截面只闭合名义送丝量，尚非实测焊道形状或设计3.5mm焊脚。",
            "表面双高斯为显式新热源假设，未做峰温拟合；不再使用体积Goldak的c参数。",
            "超过固相线的母材体积是热学熔化暴露量，不等于实测混合/稀释率。",
            "物性沿用0.3情景；网格、时间步及熔合几何仍需新模型验证。"])
    write_json(output/"summary.json",summary)
    write_json(output/"history.json",history)
    write_json(output/"G-PHYSICS-R1.json",dict(stage="G-PHYSICS-R1",gate_status="REVIEW",checks=checks,
        thermal_1_allowed=False,formal_struct_0_allowed=False,
        next_action="补充高温物性证据并验证新网格与熔合几何；禁止按单个峰温调参"))
    np.savez_compressed(output/"field.npz",s=ss,n=nn,z=zz,material_id=ids,temperature_final=temperature,
        temperature_peak=peak,peak_time_s=peak_time,cell_volume_mm3=geometry["volumes"],filled_fraction=fraction,
        t8_5_s=np.where(valid,t500-t800,np.nan),t8_5_valid=valid,max_cooling_rate_c_s=maximum_cooling,
        s_edges=geometry["s_edges"],n_edges=geometry["n_edges"],z_edges=geometry["z_edges"],material_cross_section=geometry["ids2"])
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=OUTPUT)
    args = parser.parse_args()
    spec = load(SPEC)
    sources = [SPEC,Path(__file__),Path(__file__).with_name("mass_closed_geometry.py"),Path(__file__).with_name("physics.py"),Path(__file__).with_name("run_physics03.py")]
    sources += [ROOT/spec[k] for k in ("inputs","process_input","material_input","thermal_properties")]
    write_json(args.output_dir/"run-inputs.json",dict(specification=spec,hashes={str(p.relative_to(ROOT)).replace("\\","/"):digest(p) for p in sources}))
    # 限制BLAS线程，避免稀疏CG在小向量归约中反复调度线程。
    with threadpool_limits(limits=1):
        summary = run(spec,args.output_dir)
    paths = [args.output_dir/name for name in ("summary.json","history.json","G-PHYSICS-R1.json","field.npz","run-inputs.json")]
    write_json(args.output_dir/"manifest.json",dict(files={p.name:digest(p) for p in paths},evidence_level="solver_result_unvalidated"))
    print(json.dumps(summary["checks"]),flush=True)


if __name__=="__main__":
    main()
