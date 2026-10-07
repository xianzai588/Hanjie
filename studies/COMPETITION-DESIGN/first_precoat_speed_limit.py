"""One manufacturable first-layer speed revision from actual pocket mass.

No fitted heat source or blanket fusion is inferred from this volume screen.
The sole evaluated revision retains current/electrode/path and increases speed
to 120 mm/min, below the exact full-pocket mass limit.
"""
import json
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/review/first-precoat-speed120-20261007'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    original=yaml.safe_load((ROOT/'project/precoat-process-design.yaml').read_text(encoding='utf8'))
    geom=json.loads((ROOT/'cad/generated/mma-mass-envelope/CI-A1-single-track-end80-r12/geometry-audit.json').read_text(encoding='utf8'))
    f=original['first'];rho=.00889;L=f['track_length_per_wing_mm'];rate=f['deposited_mass_rate_g_s']
    r=f['end_control']['final_current_A']/f['current_A'];ramp=f['end_control']['ramp_duration_s']
    equivalent_lost_time=ramp*(1-(1+r+r*r)/3)
    m_pocket=geom['pocket_volume_one_wing_mm3']*rho
    t_min=m_pocket/rate+equivalent_lost_time
    speed_limit=60*L/t_min
    speed=120/60;t=L/speed;m=rate*(t-equivalent_lost_time);V=m/rho
    eta=f['efficiency_for_design_accounting'];voltage=f['voltage_V_reference'];I=f['current_A'];Iend=f['end_control']['final_current_A']
    energy=eta*voltage*(I*(t-ramp)+.5*(I+Iend)*ramp)
    entry=m*1250
    cap=(V-geom['pocket_volume_one_wing_mm3'])/geom['plan_area_one_wing_mm2']
    # Algebraic boundary checks only. Neither the historical low feed nor
    # +2% speed nor a uniform +0.10 depth estimate is a measured tolerance.
    low_rate=0.15
    uniform_deeper_volume=geom['pocket_volume_one_wing_mm3']+.10*geom['plan_area_one_wing_mm2']
    scenarios=[]
    for q in [rate,low_rate]:
        for eps in [0.,.02]:
            effective_time=L/(speed*(1+eps))-equivalent_lost_time
            for volume,label in [(geom['pocket_volume_one_wing_mm3'],'actual_nominal_R1.5_CAD'),
                                 (uniform_deeper_volume,'conditional_uniform_0.10mm_deeper_estimate_not_tolerance_CAD')]:
                scenarios.append(dict(rate_g_s=q,speed_mm_min=120*(1+eps),volume_basis=label,
                    pocket_volume_mm3=volume,deposited_mass_g=q*effective_time,
                    fill_mass_margin_g=q*effective_time-volume*rho,
                    required_rate_g_s=volume*rho/effective_time))
    supply=dict(historical_rate_interval_g_s=[.15,.3333333333],
        historical_interval_source='project/independent-precoat-candidates.yaml; engineering sensitivity, not supplier guarantee',
        actual_feed_lower_bound_verified=False,first_speed_tolerance_frozen=False,
        actual_R1_5_tolerance_volume_CAD_available=False,
        required_rate_at_nominal_speed_and_pocket_g_s=m_pocket/(t-equivalent_lost_time),
        conditional_speed_limit_at_0_15_g_s_mm_min=60*L/(m_pocket/low_rate+equivalent_lost_time),
        boundary_formula='q_lower * (L / (v_nominal*(1+eps_upper)) - delta_t) >= rho_upper * V_pocket_upper; additional local retained-envelope coverage is required',
        scenarios=scenarios,
        local_contour_requirement='Complete actual pocket coverage and continuous coverage outside the maximum 0.75mm normal retained envelope at every wing/end/R1.5 corner. Positive machining stock and no cracks/slag in retained metal must be checked; average mass or overfill does not establish this.',
        decision='Retain120 as a conditional design candidate; do not adopt it as production window. Historical low-feed scenario fails nominal full-pocket mass and actual speed/feed/tolerance/contour bounds are not yet verified.')
    if not (ramp<t and speed*60<speed_limit and cap>0):raise RuntimeError('Selected revision cannot fill the actual pocket')
    result=dict(original_speed_mm_min=100,selected_speed_mm_min=120,
                unchanged_current_A=I,end_current_A=Iend,ramp_s=ramp,track_length_mm=L,
                actual_CAD_pocket_volume_mm3=geom['pocket_volume_one_wing_mm3'],
                CAD_pocket_minimum_mass_g=m_pocket,
                conditional_nominal_zero_overfill_speed_limit_mm_min=speed_limit,
                arc_time_s=t,deposited_mass_g=m,cold_equivalent_volume_mm3=V,
                uniform_envelope_overfill_above_z115_mm=cap,
                uniform_envelope_floor_to_top_mm=1.5+cap,
                steady_net_line_energy_J_mm=f['net_power_W_for_design_accounting']/speed,
                ramp_integrated_net_energy_J=energy,filler_entry_enthalpy_J=entry,
                remaining_arc_heat_J=energy-entry,
                original_net_energy_J=23084.49093448,
                energy_reduction_fraction=1-energy/23084.49093448,
                hypothetical_200_mm_min_mass_g=rate*(L/(200/60)-equivalent_lost_time),
                full_pocket_volume_screen_passed=True,actual_fusion_verified=False,
                actual_cold_mechanical_state_qualified=False,full_manufacturing_chain_passed=False,
                limits='0.17 g/s and I-squared endpoint supply are explicit engineering inputs. The CAD mass screen covers the full R1.5 pocket; overfill is a uniform mass-equivalent shape, not measured bead or a guaranteed end fill. The single 120 mm/min revision must pass the actual complete arc/connection calculation before changing current pWPS.',
                source_geometry='cad/generated/mma-mass-envelope/CI-A1-single-track-end80-r12/geometry-audit.json')
    (OUT/'speed-volume-energy-screen.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
    (OUT/'speed120-supply-window.json').write_text(json.dumps(supply,indent=2,ensure_ascii=False),encoding='utf8')
    candidate=original
    candidate['state']='one_bounded_speed_revision_pending_complete_arc_connection_and_manufacturing'
    f['travel_mm_s']=speed;f['arc_duration_per_wing_s']=t;f['deposited_mass_per_wing_g']=m
    f['net_line_energy_J_mm_calculated']=f['net_power_W_for_design_accounting']/speed
    f['reference_line_energy_J_mm_rounded']=1012
    f['geometry_model_path']='cad/generated/mma-mass-envelope/CI-A1-single-track-speed120-end80-r12-h065'
    candidate['speed_revision_basis']='Speed changes from100 to120 mm/min under the same mass-envelope/source rule: deposited height, effective source depth and source anchor also change. The130.804629 mm/min zero-overfill limit is conditional on0.17g/s, design density and nominal full R1.5 pocket. No new current/furnace/source/transport matrix.'
    candidate['supply_window_evidence']='output/review/first-precoat-speed120-20261007/speed120-supply-window.json'
    candidate['production_adoption_decision']=supply['decision']
    (ROOT/'project/precoat-speed120-candidate.yaml').write_text(yaml.safe_dump(candidate,allow_unicode=True,sort_keys=False),encoding='utf8')
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
