"""Small-lot work, WIP and direct operating cost; thermal reserves explicit."""
import json,math
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studies/COMPETITION-DESIGN/results/pilot-production-20261007.json'


def main():
    p=yaml.safe_load((ROOT/'project/pilot-production-design.yaml').read_text(encoding='utf8'))
    card=yaml.safe_load((ROOT/'project/precoat-process-design.yaml').read_text(encoding='utf8'))
    interval=p['shift_s']/p['target_parts_per_shift']
    first=p['first_preheat_s']+p['first_arc_to_cold_s']
    second=p['second_preheat_s_planning']+p['second_arc_to_cold_reserved_s']
    resources=dict(first_cycle_positions=math.ceil(first/interval),second_cycle_reserved_positions=math.ceil(second/interval),
                   delayed_PT_wait_positions=math.ceil(p['delayed_PT_wait_s']/interval),
                   first_MMA_stations=math.ceil((p['first_mma_station_thermal_occupancy_s']+p['first_clean_handle_allowance_s'])/interval),
                   second_GTAW_reserved_stations=math.ceil(p['second_GTAW_station_reserved_s']/interval),
                   milling_stations=math.ceil((p['middle_normal_machining_planning_s']+p['final_machining_planning_s'])/interval),
                   final_weld_stations=math.ceil((p['assembly_planning_s']+p['final_single_head_station_s'])/interval),
                   PT_operation_stations=1,PT_wait_positions_per_PT_stage=math.ceil(p['middle_PT_elapsed_upper_s']/interval),
                   UT_stations=math.ceil(p['UT_station_s']/interval),CMM_stations=math.ceil(p['CMM_if_microhone_station_s']/interval))
    active_names=['first_clean_handle_allowance_s','middle_normal_machining_planning_s','middle_PT_manual_s',
                 'second_GTAW_clean_handle_allowance_s','final_machining_planning_s','wash_dry_pack_planning_s',
                 'delayed_PT_manual_s','assembly_planning_s','final_PT_manual_s','UT_station_s',
                 'CMM_if_microhone_station_s','microhone_station_s','dry_cleanliness_station_s']
    work=sum(p[k] for k in active_names)
    # Full MMA thermal occupancy conservatively counts as attended time.
    work+=p['first_mma_station_thermal_occupancy_s']+p['second_GTAW_arc_s']+p['final_single_head_station_s']
    people=math.ceil(work/(interval*p['working_utilization_for_manual_tasks']))
    c=p['cost_scenarios']
    mass1=card['first']['deposited_mass_per_wing_g']*8
    mass2=math.pi/4*card['second']['diameter_mm']**2*card['second']['feed_mm_s']*card['second']['track_length_per_wing_mm']/card['second']['travel_mm_s']*8*.00889
    mass3=math.pi/4*1.6**2*3.5*(288/1.65)*.0082
    argon=(10*p['second_GTAW_arc_s']/60+ (10+15+12)*(p['final_single_head_station_s']+120)/60)/1000
    furnace=c['first_furnace_average_allocated_kW']*first/3600+c['second_furnace_average_allocated_kW']*second/3600
    arc_kwh=((184675.927/.8)+(76356.57/.6)+(86400/.55))/3.6e6
    costs=dict(labor_CNY=work/3600*c['labor_CNY_h'],
               first_electrode_CNY=mass1/1000/c['SMAW_deposition_efficiency_for_purchasing']*c['consumable_purchase_factor']*c['CI_A1_CNY_kg'],
               second_wire_CNY=mass2/1000*c['consumable_purchase_factor']*c['low_C_Ni99_CNY_kg'],
               final_wire_CNY=mass3/1000*c['consumable_purchase_factor']*c['NiFe55_CNY_kg'],
               argon_CNY=argon*c['argon_CNY_m3'],furnace_and_arc_electricity_CNY=(furnace+arc_kwh)*c['electricity_CNY_kWh'],
               PT_UT_consumable_reserve_CNY=c['reserved_PT_UT_consumables_CNY_part'])
    for_baseline={}
    for name,takt in [('single_head',462.5),('double_head',231.3)]:
        for_baseline[name]=dict(first_cycle_positions=math.ceil(first/takt),second_reserved_positions=math.ceil(second/takt),
                               delayed_PT_wait_positions=math.ceil(86400/takt))
    result=dict(input_source='project/pilot-production-design.yaml',target_interval_s=interval,
                first_cycle_known_thermal_s=first,second_cycle_reserved_s=second,
                planning_thermal_and_delay_elapsed_subtotal_s=first+second+86400,
                resources=resources,active_work_s_part=work,manual_people_at_80pct_design_utilization=people,
                operating_cost_scenario=costs,direct_operating_cost_scenario_CNY=sum(costs.values()),
                furnace_energy_scenario_kWh_part=furnace,argon_scenario_m3_part=argon,
                nominal_material_purchase_basis_g=dict(CI_A1_deposited=mass1,low_C_Ni99_feed=mass2,NiFe55_feed=mass3),
                legacy_weld_station_intervals_WIP_demand=for_baseline,
                actual_capacity_verified=False,second_layer_thermal_reservation_qualified=False,
                cost_excludes='equipment capital, tooling depreciation, wash/milling machine power, material rejects, destructive sampling and fatigue qualification',
                production_choice='single-head final GTAW for8parts/8h trial design; double-head brings no bottleneck benefit at3600s design interval')
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
