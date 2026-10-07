"""One published nodular-iron arc benchmark and an untuned transport check.

The finite moving surface-point solution is deliberately a scale check. It
does not fit the unpublished Goldak dimensions or claim CI-A1 calibration.
"""
import json
import numpy as np
from scipy.integrate import quad
from scipy.optimize import minimize_scalar
from mma_literature_profile import ROOT


def run():
    source = 'https://doi.org/10.1007/s00170-024-14487-7'
    power = 190 * 27.2 * .85
    speed = 250 / 60
    length = 150.
    density = 7200e-9
    cp = 710.
    conductivity = .0305
    diffusivity = conductivity / (density * cp)
    duration = length / speed

    def temperature(t, y):
        if t <= 0:
            return 20.
        def kernel(tau):
            age = t-tau
            if age <= 0:
                return 0.
            radius2 = (75-speed*tau)**2 + y*y + 2**2
            return np.exp(-radius2/(4*diffusivity*age))/age**1.5
        integral = quad(kernel, 0., min(t, duration), epsabs=1e-10)[0]
        return 20 + 2*power/(density*cp*(4*np.pi*diffusivity)**1.5)*integral

    rows = []
    for distance, measured in [(10., [320., 330.]), (15., [225., 230.])]:
        peak = minimize_scalar(lambda t: -temperature(t, distance),
                               bounds=(1., 80.), method='bounded')
        rows.append(dict(distance_y_mm=distance, depth_mm=2.,
                         assumed_track_midpoint_x_mm=75.,
                         peak_C=float(-peak.fun), peak_from_arc_start_s=float(peak.x),
                         measured_peak_approximate_graph_read_C=measured,
                         relative_difference_from_measured_midpoint=float(
                             -peak.fun/np.mean(measured)-1)))
    inputs = json.loads((ROOT/'simulation/competition-r4/results/mma-first-end80-r12-phase-front-dt0125-20261007/input.json').read_text())
    # Same saved input table as the manufacturing heat calculation. No new
    # material curve or fitted source is introduced for the energy comparison.
    qt = inputs['materials'][1]
    knots = qt['temperature_dependent']['temperatures_c']
    values = qt['temperature_dependent']['specific_heat_j_kgk']
    sensible = quad(lambda t: np.interp(t, knots, values), 300., 1180.)[0]
    melt_mass_kg = 7.410758488e-3
    energy = melt_mass_kg*(sensible+qt['fusion_enthalpy']['latent_heat_J_kg'])
    result = dict(source=source, benchmark_material='GJS500-14; MCAW NiFe, Table1/Fig1/Fig3/Fig6',
        benchmark_input=dict(current_A=190., voltage_V=27.2, efficiency=.85,
            speed_mm_s=speed, arc_length_mm=length, net_power_W=power,
            net_line_energy_J_mm=power/speed, plate_mm=[250.,140.,22.],
            initial_C=20., density_kg_m3=density*1e9, cp_J_kgK=cp,
            conductivity_W_mK=conductivity*1000, diffusivity_mm2_s=diffusivity),
        model='finite-duration moving point on a semi-infinite surface; reflected heat kernel; constant Fig3 representative properties; no latent heat or boundary losses',
        results=rows,
        scope=dict(unpublished_Goldak_dimensions=True,
            paper_thermal_plate_thickness_mm=22., paper_RS_FE_plate_thickness_mm=50.,
            published_3D_temperature_average_error_fraction=.17,
            probe_longitudinal_position_unpublished=True,
            temperature_figure_time_origin_not_arc_start=True,
            calibrated_to_current_CI_A1=False,
            interpretation='15mm thermal-transport magnitude agrees; 10mm near-field peak is overpredicted by this untuned point-source check, so it is not an accepted melt-pool calibration'),
        current_QT_liquid_energy_lower_requirement=dict(temperature_interval_C=[300.,1180.],
            simultaneous_liquid_mass_kg=melt_mass_kg, sensible_J_kg=sensible,
            latent_J_kg=qt['fusion_enthalpy']['latent_heat_J_kg'], requirement_J=energy,
            actual_one_wing_net_input_J=23084.49093448182,
            interpretation='energy magnitude alone does not exclude the saved deep-remelt result; finite source distribution and actual material consequences still govern design'),
        full_manufacturing_verified=False)
    folder=ROOT/'simulation/competition-r4/results/mma-continuous-end80-r12-20261007'
    path=folder/'cast-iron-arc-physical-scale.json'
    if path.exists():
        raise ValueError('Preserve prior physical benchmark evidence')
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    run()
