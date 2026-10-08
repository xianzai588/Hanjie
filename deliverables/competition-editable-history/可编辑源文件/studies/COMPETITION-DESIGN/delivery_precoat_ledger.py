"""Integrate the actual eight-wing precoat current ramp and feed envelope."""
from pathlib import Path
import json, math
import yaml

ROOT=Path(__file__).resolve().parents[2]

def main():
    cfg=yaml.safe_load((ROOT/'project/precoat-process-design.yaml').read_text(encoding='utf-8'))
    a,b=cfg['first'],cfg['second']
    t=a['track_length_per_wing_mm']/a['travel_mm_s']
    ramp=a['end_control']['ramp_duration_s']
    ratio=a['end_control']['final_current_A']/a['current_A']
    equiv_current=t-ramp+ramp*(1+ratio)/2
    equiv_mass=t-ramp+ramp*(1+ratio+ratio**2)/3
    q=a['current_A']*a['voltage_V_reference']*a['efficiency_for_design_accounting']
    geometry=json.loads((ROOT/'cad/generated/precoat-tolerance-family-20261007/geometry-and-feed-audit.json').read_text(encoding='utf-8'))
    # Exact maximum slot from the previously exported and independently read CAD.
    demand=176.157710*.00889
    rows=[]
    for speed in (100.,120.):
        for factor in (1.,1.02):
            duration=a['track_length_per_wing_mm']/(speed/60*factor)
            mass=.15*(duration-ramp+ramp*(1+ratio+ratio**2)/3)
            rows.append(dict(speed_mm_min=speed,speed_factor=factor,low_feed_g_s=.15,
                             deposited_mass_per_wing_g=mass,maximum_slot_demand_g=demand,
                             remaining_mass_per_wing_g=mass-demand))
    time2=8*b['track_length_per_wing_mm']/b['travel_mm_s']
    supply=json.loads((ROOT/'studies/COMPETITION-DESIGN/results/second-layer-supply-decision-20261008.json').read_text(encoding='utf-8'))
    for key in ('diameter_mm','feed_mm_s','current_A','voltage_V_reference','travel_mm_s'):
        if b[key] != supply['selected_input'][key]:
            raise ValueError('Current second-layer supply decision differs from process input: '+key)
    result=dict(version='DELIVERY-PRECOAT-20261008',parameters=cfg,
        first=dict(actual_path_mm=8*a['track_length_per_wing_mm'],arc_time_s=8*t,
                   net_heat_kJ=8*q*equiv_current/1000,deposited_mass_g=8*a['deposited_mass_rate_g_s']*equiv_mass,
                   arc_efficiency=a['efficiency_for_design_accounting'],heat_current_exponent=1,mass_current_exponent=2,
                   mass_law_scope='Conservative uncalibrated I-squared end-ramp feed scenario; not a measured electrode deposition law'),
        second=dict(actual_path_mm=8*b['track_length_per_wing_mm'],arc_time_s=time2,
                    net_heat_kJ=time2*b['current_A']*b['voltage_V_reference']*b['efficiency_for_design_accounting']/1000,
                    wire_length_mm=time2*b['feed_mm_s'],
                    consumed_wire_mass_g=supply['nominal']['incoming_consumed_mass_eight_wings_g'],
                    stock_purchase_mass_g=supply['rod_preparation']['purchased_full_stock_mass_g'],
                    stock_purchase_length_mm=supply['rod_preparation']['purchased_full_stock_length_mm'],
                    entering_enthalpy_nominal_eta_range_kJ=supply['heat']['incoming_enthalpy_nominal_mass_eta_range_kJ'],
                    parent_pool_and_loss_remainder_kJ=supply['heat']['parent_pool_and_loss_remainder_nominal_mass_kJ'],
                    current_supply_source='studies/COMPETITION-DESIGN/results/second-layer-supply-decision-20261008.json'),
        first_supply_sensitivity=rows,
        geometry_source='cad/generated/precoat-tolerance-family-20261007/geometry-and-feed-audit.json',
        state='Supply and net source energy accounting; not fusion, dilution or manufacturing residual-state verification',
        legacy_correction='Includes final 1.2 s current ramp; replaces obsolete no-ramp 187.325527 kJ / 15.733863 g bookkeeping.')
    path=ROOT/'studies/COMPETITION-DESIGN/results/precoat-process-design.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('first','second','first_supply_sensitivity')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
