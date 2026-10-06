"""Independent oven warmup of the actual pocketed QT seat; no weld heat/reset."""
from pathlib import Path
import argparse
import json
import time
import numpy as np
import yaml
from scipy.sparse import coo_matrix, diags, triu
import pypardiso
from threadpoolctl import threadpool_limits
from run_candidate_solver import operators

ROOT = Path(__file__).resolve().parents[2]


def run(mesh, output, target, dt, ramp_C_min=3):
    if (output / 'result.json').exists():
        raise ValueError('Preserve completed physical evidence')
    output.mkdir(parents=True, exist_ok=True)
    with np.load(mesh / 'mesh.npz', allow_pickle=False) as data:
        x, e = data['x'], data['e'][data['material'] == 1]
    used = np.unique(e)
    remap = np.full(len(x), -1, int); remap[used] = np.arange(len(used))
    x, e = x[used], remap[e]
    gradient, volume, _, _ = operators(x, e, mechanical=False)
    faces = np.sort(np.vstack([e[:, p] for p in ([0,1,2], [0,1,3], [0,2,3], [1,2,3])]), axis=1)
    faces, count = np.unique(faces, axis=0, return_counts=True)
    faces = faces[count == 1]
    tri = x[faces]
    area = np.linalg.norm(np.cross(tri[:,1]-tri[:,0], tri[:,2]-tri[:,0]), axis=1)/2
    surface = np.bincount(faces.ravel(), weights=np.repeat(area/3, 3), minlength=len(x))
    material = yaml.safe_load((ROOT / 'project/materials.yaml').read_text(encoding='utf8'))['materials']['qt450_10']
    props = material['temperature_dependent']
    rho = material['nominal_properties_20c']['density_kg_m3'] * 1e-9
    lumped_mass = np.bincount(e.ravel(), weights=np.repeat(rho*volume/4, 4), minlength=len(x))
    rr = np.repeat(e, 4, axis=1).ravel(); cc = np.tile(e, (1,4)).ravel()
    unit_k = np.einsum('eik,ejk,e->eij', gradient, gradient, volume)
    unit_K = coo_matrix((unit_k.ravel(), (rr, cc)), shape=(len(x), len(x))).tocsr()
    engine = pypardiso.PyPardisoSolver(mtype=2)
    engine.set_iparm(2, 3)
    ambient, ramp = 20., ramp_C_min/60
    temperature = np.full(len(x), 20.)
    history, elapsed, absorbed, balance_max = [], 0., 0., 0.
    started = time.perf_counter()
    while elapsed < 18000:
        next_time = elapsed + dt
        chamber = min(target, ambient+ramp*next_time)
        old = temperature.copy()
        cp = np.interp(old, props['temperatures_c'], props['specific_heat_j_kgk'])
        conductivity = float(np.interp(old.mean(), props['temperatures_c'], props['thermal_conductivity_w_mk']))/1000
        capacity = lumped_mass*cp
        K = unit_K*conductivity
        # Radiation is Picard-linearized against the physical chamber temperature.
        for iteration in range(12):
            radiation = .7*5.670374419e-14*((temperature+273.15)**2+(chamber+273.15)**2)*(temperature+chamber+546.3)
            exchange = surface*(20e-6+radiation)
            A = diags(capacity/dt+exchange)+K
            rhs = capacity/dt*old+exchange*chamber
            temperature_new = pypardiso.spsolve(triu(A, format='csr'), rhs, solver=engine)
            if np.linalg.norm(A@temperature_new-rhs) > 1e-5:
                raise RuntimeError('Warmup linear equilibrium residual exceeds 1e-5 W')
            change = float(abs(temperature_new-temperature).max())
            temperature = temperature_new
            if change < 1e-5:
                break
        else:
            raise RuntimeError('Warmup radiation iteration failed')
        net = float(exchange @ (chamber-temperature))
        balance = float(capacity @ (temperature-old))-net*dt
        balance_max = max(balance_max, abs(balance))
        absorbed += net*dt; elapsed = next_time
        history.append([elapsed, chamber, temperature.min(), temperature.max(),
                        float(lumped_mass @ temperature/lumped_mass.sum()), net, absorbed, balance])
        if len(history) % 20 == 0:
            print(target, dt, round(elapsed), round(temperature.min(),3), round(temperature.max(),3), flush=True)
        if chamber == target and temperature.min() >= target-10 and np.ptp(temperature) <= 10:
            break
    else:
        raise RuntimeError('Warmup did not meet the frozen uniformity criterion within five hours')
    np.savez_compressed(output / 'warmup-state.npz', x=x, e=e, temperature=temperature, boundary_faces=faces)
    np.savetxt(output / 'history.csv', history, delimiter=',', comments='',
               header='t_s,chamber_C,min_QT_C,max_QT_C,mass_mean_C,net_into_part_W,absorbed_J,balance_J')
    result = dict(target_C=target, dt_s=dt, ramp_C_min=ramp_C_min, convection_W_m2K=20, emissivity=.7,
                  mesh=str(mesh.relative_to(ROOT)), nodes=len(x), tetrahedra=len(e),
                  pocketed_seat_mass_kg=float(lumped_mass.sum()), exposed_area_mm2=float(area.sum()),
                  warmup_time_s=elapsed, soak_after_chamber_reaches_target_s=elapsed-(target-20)/ramp,
                  minimum_QT_C=float(temperature.min()), maximum_QT_C=float(temperature.max()),
                  uniformity_C=float(np.ptp(temperature)), absorbed_sensible_kJ=absorbed/1000,
                  maximum_through_cycle_gradient_C=max(row[3]-row[2] for row in history),
                  maximum_absorbed_power_W=max(row[5] for row in history),
                  maximum_step_energy_balance_error_J=balance_max,
                  temperature_maximum_principle_pass=bool(temperature.min()>=20-1e-5 and temperature.max()<=target+1e-5),
                  elapsed_wall_s=time.perf_counter()-started,
                  scope='Actual pocketed QT only, no shell, filler or tools; ideal all-surface oven exposure with stated engineering h/emissivity. Predicted chamber programme, not measured furnace cycle/electricity. No stress/annealing reset or weld qualification.',
                  first_interface_continuous_fusion_pass=False,
                  precoat_residual_state_transfer_pass=False)
    knots = np.asarray(props['temperatures_c'])
    cp_values = np.asarray(props['specific_heat_j_kgk'])
    enthalpy = np.zeros(len(x))
    for low, high, c_low, c_high in zip(knots, knots[1:], cp_values, cp_values[1:]):
        increment = np.clip(temperature-low, 0, high-low)
        enthalpy += c_low*increment + (c_high-c_low)*increment**2/(2*(high-low))
    exact_sensible = float(lumped_mass @ enthalpy)
    result['integrated_Cp_sensible_kJ'] = exact_sensible/1000
    result['Cp_time_lag_energy_error_pct'] = 100*abs(exact_sensible-absorbed)/exact_sensible
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps(result, indent=2), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mesh', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', type=float, choices=[200,300], required=True)
    parser.add_argument('--dt', type=float, default=60)
    parser.add_argument('--ramp', type=float, default=3)
    args = parser.parse_args()
    if args.dt <= 0 or args.ramp <= 0:
        raise ValueError('Positive time step and ramp required')
    with threadpool_limits(limits=1):
        run(args.mesh.resolve(), args.output.resolve(), args.target, args.dt, args.ramp)
