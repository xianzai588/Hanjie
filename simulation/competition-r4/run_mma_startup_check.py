"""Bounded CI-A1 startup replay; reads the current pWPS and saved CAD inputs."""
import argparse
import json
from types import SimpleNamespace
import numpy as np
import yaml
from threadpoolctl import threadpool_limits
from mma_literature_profile import ROOT, configure
from ni99_local_thermal import tables
from run_ni99_precoat_first import run


def arguments(mesh, output, dt, legacy=False, stop_time=1., liquid_transport=1., growth='angular'):
    card = yaml.safe_load((ROOT/'project/precoat-process-design.yaml').read_text(encoding='utf8'))['first']
    if mesh is None:mesh=ROOT/('cad/generated/mma-mass-envelope/CI-A1-single-track' if legacy else card['geometry_model_path'])
    geometry = json.loads((mesh/'geometry-audit.json').read_text(encoding='utf8'))
    path = geometry['single_track_inputs']
    profile=path.get('end_control') if not legacy else None
    if not legacy and profile!=card.get('end_control'):raise ValueError('pWPS and CAD end-control profiles differ')
    for card_key, cad_key in [('track_radius_mm', 'radius_mm'), ('track_length_per_wing_mm', 'length_mm'),
                               ('travel_mm_s', 'travel_mm_s'), ('deposited_mass_rate_g_s', 'deposited_mass_rate_g_s')]:
        if abs(card[card_key]-path[cad_key]) > 1e-9:
            raise ValueError('pWPS and CAD differ: '+card_key)
    _, t, h, _ = configure(tables(1300., .75), 'CI-A1')
    entry = float(np.interp(1250000+np.interp(25, t, h), h, t))
    return SimpleNamespace(mesh=mesh, output=output,
        power=2025. if legacy else card['current_A']*card['voltage_V_reference']*card['efficiency_for_design_accounting'],
        travel=card['travel_mm_s'], width=3.2, depth=geometry['volume_equivalent_floor_to_top_mm'],
        dt=dt, deposition_temperature=entry, initial_temperature=300., source_drop=0., ni1_solidus=1300.,
        ni_k_scale=.75, half_overlap=0., radial_tracks=1, radial_order='inner_first', start_ramp=0., start_fraction=1.,
        end_ramp=profile['ramp_duration_s'] if profile else 0.,end_fraction=profile['final_current_A']/card['current_A'] if profile else .35,
        mass_current_exponent=profile['melting_rate_current_exponent'] if profile else 0,
        source_model='mma_volume', surface_grid_step=.15, thermal_bounds='nominal', first_geometry='full_pocket',
        pure_filler_birth=False, resume_from=None, phase_carbon_corner=None, phase_graphite_limit='graphite_allowed',
        phase_temperature_shift=0., stop_after_tracks=None, mma_profile='CI-A1',
        continuous_track=not legacy, track_radius_mm=path['radius_mm'], track_length_mm=path['length_mm'],
        mass_rate_g_s=path['deposited_mass_rate_g_s'], conservative_birth=not legacy, stop_time_s=stop_time,
        liquid_transport_factor=liquid_transport,deposition_growth=growth,record_nodal_history=stop_time is None)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--mesh', type=lambda s: ROOT/s)
    p.add_argument('--output', type=lambda s: ROOT/s, required=True)
    p.add_argument('--dt', type=float, default=.125)
    p.add_argument('--legacy', action='store_true')
    p.add_argument('--stop-time', type=float, default=1.)
    p.add_argument('--liquid-transport', type=float, choices=[1., 3.], default=1.)
    p.add_argument('--growth', choices=['angular','bottom_up'], default='angular')
    a = p.parse_args()
    with threadpool_limits(limits=1):
        run(arguments(a.mesh, a.output, a.dt, a.legacy, a.stop_time, a.liquid_transport, a.growth))
