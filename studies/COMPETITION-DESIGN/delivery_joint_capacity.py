"""Actual arc geometry, conservative weld-group equilibrium and fatigue demand.

These are nominal section demands, not measured properties or local notch stresses.
Axial force and bending normal stress add before von Mises combination with shear.
"""
from pathlib import Path
import json
import math
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('results')


def integrate(radius, bounds):
    length = 0.0
    tensor = np.zeros((2, 2))
    for lo, hi in bounds:
        length += radius * (hi - lo)
        ss = (hi-lo)/2 - (math.sin(2*hi)-math.sin(2*lo))/4
        cc = (hi-lo)/2 + (math.sin(2*hi)-math.sin(2*lo))/4
        sc = (math.sin(hi)**2-math.sin(lo)**2)/2
        tensor += radius**3 * np.array([[ss, -sc], [-sc, cc]])
    # An independent quadrature checks length and inertia, without the primitives.
    x, weights = np.polynomial.legendre.leggauss(32)
    quad = np.zeros((2, 2))
    qlength = 0.0
    for lo, hi in bounds:
        theta = (lo+hi)/2 + (hi-lo)*x/2
        dl = radius*(hi-lo)*weights/2
        xy = np.column_stack((radius*np.sin(theta), -radius*np.cos(theta)))
        quad += np.einsum('n,ni,nj->ij', dl, xy, xy)
        qlength += sum(dl)
    error = max(abs(qlength-length)/length,
                np.linalg.norm(quad-tensor)/np.linalg.norm(tensor))
    if error > 1e-10:
        raise ValueError('Arc integrals disagree with independent quadrature')
    return length, tensor, error


def demand(radius, bounds, leg, spectrum):
    length, tensor, error = integrate(radius, bounds)
    throat = leg/math.sqrt(2)
    area = throat*length
    inertia = throat*np.linalg.eigvalsh(tensor)[0]
    # Peak at radius is the conservative envelope over moment direction and sign.
    normal = 5000/area + 250000*radius/inertia
    shear = 5000/area
    peak = math.hypot(normal, math.sqrt(3)*shear)
    fatigue = []
    for block in spectrum:
        ds = 2*(block['Fa_amp']/area + block['M_amp']*radius/inertia)
        dt = 2*block['Fr_amp']/area
        equivalent = math.hypot(ds, math.sqrt(3)*dt)
        damage = block['cycles']/2e6*(equivalent/30)**3
        fatigue.append({**block, 'normal_range_MPa': ds,
                        'shear_range_MPa': dt, 'equivalent_range_MPa': equivalent,
                        'conditional_damage_at_30MPa_target': damage})
    damage = sum(x['conditional_damage_at_30MPa_target'] for x in fatigue)
    return dict(effective_length_mm=length, minimum_leg_mm=leg,
                effective_throat_mm=throat, throat_area_mm2=area,
                line_group_tensor_mm3=tensor.tolist(), minimum_throat_inertia_mm4=inertia,
                quadrature_relative_error=error, static_normal_MPa=normal,
                static_shear_MPa=shear, required_nominal_static_capacity_MPa=peak,
                fatigue=fatigue, conditional_Miner_at_30MPa_target=damage,
                required_reference_range_MPa_at_2e6=30*damage**(1/3),
                mean_stress_scope='No mean-stress correction: qualification target applies to the as-welded detail, including its residual-stress state. No measured S-N curve is supplied.',
                scope='Conservative synchronized nominal force/moment envelope. Weld ends, local toe/root stress, PMZ and manufacturing damage require their own verification.')


def main():
    manifest = json.loads((ROOT/'simulation/competition-r4/geometry/8P-R2-t15-manifest.json').read_text(encoding='utf-8'))
    old = json.loads((OUT/'engineering-checks-r3.json').read_text(encoding='utf-8'))
    radius = manifest['seat']['outer_radius_mm']
    actual = []
    for s in manifest['manufacturing']['weld_segments']:
        lo, hi = np.deg2rad([s['start_angle_deg'], s['end_angle_deg']])
        if hi <= lo:
            hi += 2*math.pi
        actual.append((float(lo), float(hi)))
    stable = [(lo+1/radius, hi-1/radius) for lo, hi in actual]
    length, _, _ = integrate(radius, actual)
    six = [(i*math.pi/3-8/radius, i*math.pi/3+8/radius) for i in range(6)]
    rows = {f'8P_leg_{leg:.1f}': demand(radius, stable, leg, old['load_spectrum'])
            for leg in (3.5, 3.8, 4.0)}
    rows['6P_16mm_leg_3.8'] = demand(radius, six, 3.8, old['load_spectrum'])
    rows['Continuous_leg_3.8'] = demand(radius, [(0, 2*math.pi)], 3.8, old['load_spectrum'])
    p = json.loads((ROOT/'deliverables/process/joint-process-card.json').read_text(encoding='utf-8'))['process']
    result = dict(version='DELIVERY-8P-20261008', geometry_source='simulation/competition-r4/geometry/8P-R2-t15-manifest.json',
        actual_segment_length_mm=18.0, start_transition_mm=1.0, end_transition_mm=1.0,
        stable_segment_length_mm=16.0, total_actual_per_pass_mm=length,
        total_stable_connection_mm=integrate(radius, stable)[0], pass_count=2,
        total_actual_path_mm=2*length, nominal_net_heat_kJ=2*length*.300,
        arc_time_s=2*length/1.65,
        pass_wire_feed_mm_s=dict(root=3.42, cover=3.78),
        pass_wire_length_mm=dict(root=length/1.65*3.42, cover=length/1.65*3.78),
        wire_length_mm=length/1.65*(3.42+3.78),
        static_reference_loads=dict(radial_N=5000, axial_N=5000, moment_N_mm=250000),
        load_basis='Designer-selected envelope and two fatigue blocks; official problem supplies no service spectrum.',
        equations=dict(normal='sigma = Fa/A + M*r/I_min', shear='tau = Fr/A',
            equivalent='sqrt(sigma^2 + 3*tau^2)', range='normal RANGE = 2*(Fa_amp/A + M_amp*r/I_min); shear RANGE = 2*Fr_amp/A',
            fatigue='D = sum(n/2e6*(Delta_sigma_eq/30)^3); required target = 30*D^(1/3)'),
        fatigue_target=dict(reference_range_MPa=30, reference_cycles=2000000, slope=3,
            status='Proposed as-welded qualification target, not an IIW class or measured NiFe/QT curve'),
        rows=rows, selected_minimum_leg_mm=3.8,
        supply_geometry=dict(equivalent_leg_range_mm=p['equivalent_leg_range_mm'],
            margin_above_selected_minimum_mm=min(p['equivalent_leg_range_mm'])-3.8,
            scope='Volume conservation supports geometric filling only; continuous fusion and effective throat must be verified separately.'),
        revision='Exclude both transitions from capacity; add axial normal stress to bending. Raise stable minimum leg from 3.50 to 3.80 mm within the existing calculated 3.828..4.186 mm feed envelope; nominal leg remains 4.00 mm. Heat/path/feed settings unchanged.',
        verified_current_joint_capacity=False)
    OUT.mkdir(exist_ok=True)
    path=OUT/'delivery-joint-capacity-20261008.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:{x:r[x] for x in ('required_nominal_static_capacity_MPa','conditional_Miner_at_30MPa_target','required_reference_range_MPa_at_2e6')} for k,r in rows.items()},indent=2))


if __name__ == '__main__':
    main()
