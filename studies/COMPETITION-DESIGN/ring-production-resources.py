"""Ring-specific planning: material, direct operating cost and real work slots.

Prices/power/operation times are replaceable budget inputs, not quotes or logs.
"""
from pathlib import Path
import json
import math
import yaml

ROOT = Path(__file__).resolve().parents[2]


def calculate():
    spec = yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text())
    pre = json.loads((ROOT/'cad/generated/ring-baseline/ring-precoat-design.json').read_text())
    old = yaml.safe_load((ROOT/'project/pilot-production-design.yaml').read_text())
    c = old['cost_scenarios']
    interval = 3600
    work = {
        'first_loading_and_unloading': 600, 'first_arc': pre['first_layer']['arc_time_eight_windows_s'],
        'first_clean_handle': 480, 'normal_layer_machining': 600, 'middle_PT_manual': 480,
        'second_loading_and_unloading': 600, 'second_arc': pre['second_layer']['arc_time_eight_windows_s'],
        'second_clean_handle': 480, 'final_machining': 900, 'wash_dry_pack': 600,
        'delayed_PT_manual': 480, 'assembly_and_final_station': 900,
        'final_PT_manual': 480, 'UT': 600, 'CMM': 360, 'dry_cleanliness': 300,
    }
    active = sum(work.values())
    people = math.ceil(active / (interval*0.8))
    m1 = pre['first_layer']['mass_eight_windows_g']['nominal']
    t2 = pre['second_layer']['arc_time_eight_windows_s']
    m2 = math.pi*spec['material_route']['second_layer']['wire_diameter_mm']**2/4 * spec['material_route']['second_layer']['wire_feed_mm_s']*t2*0.00889
    final = spec['final_GTAW']
    m3 = math.pi*final['wire_diameter_mm']**2/4*final['nominal_wire_consumption_length_mm']*0.0082
    purchase = c['consumable_purchase_factor']
    argon = (t2 + 900)*10/60/1000
    # Allocate mean power across the full 10h + 10h thermal residence.
    furnace = (c['first_furnace_average_allocated_kW']+c['second_furnace_average_allocated_kW'])*10
    arc = (pre['combined_nominal']['net_heat_J'] + final['net_energy_kJ']*1000)/3.6e6
    # Net heat is NOT purchased electricity: divide each stage by arc eta,
    # then by the design power-source wall efficiency (0.85).
    electrical = (pre['first_layer']['net_heat_eight_windows_J']/0.8 + pre['second_layer']['net_heat_eight_windows_J']/0.6 + final['net_energy_kJ']*1000/0.55)/3.6e6/0.85
    nonlabor = {
        'CI_A1': m1/1000/c['SMAW_deposition_efficiency_for_purchasing']*purchase*c['CI_A1_CNY_kg'],
        'low_C_Ni99': m2/1000*purchase*c['low_C_Ni99_CNY_kg'],
        'NiFe55': m3/1000*purchase*c['NiFe55_CNY_kg'],
        'argon': argon*c['argon_CNY_m3'],
        'furnace_and_arc_electricity': (furnace+electrical)*c['electricity_CNY_kWh'],
        'PT_UT_consumables': c['reserved_PT_UT_consumables_CNY_part'],
    }
    dedicated = people*8*c['labor_CNY_h']/8
    shared = active/3600*c['labor_CNY_h']
    return {'process_version': spec['version'], 'physical_object':'complete_ring',
            'source_type':'design_planning', 'target_parts_per_shift':8, 'feed_interval_s':interval,
            'resources':{'first_thermal_positions':10,'second_thermal_positions':10,'delayed_PT_positions':24,'thermal_and_delay_positions':44,
                         'PT_hold_positions_each_stage':math.ceil(4080/interval),'final_weld_station_s':900},
            'active_work_s':work,'active_work_total_s':active,'people_at_80pct_utilization':people,
            'nominal_material_g':{'CI_A1_deposited':m1,'low_C_Ni99_fed':m2,'NiFe55_fed':m3},
            'consumable_purchase_factor':purchase,'nominal_argon_m3':argon,
            'thermal_residence_h_each':10,'furnace_allocated_energy_kWh':furnace,
            'arc_net_heat_kWh':arc,'arc_wall_electricity_kWh':electrical,'power_source_wall_efficiency_assumption':0.85,
            'nonlabor_cost_CNY':nonlabor,'dedicated_labor_CNY':dedicated,'shared_active_labor_CNY':shared,
            'dedicated_direct_cost_CNY':dedicated+sum(nonlabor.values()),'shared_direct_cost_CNY':shared+sum(nonlabor.values()),
            'budget_inputs':c,'actual_capacity_verified':False,'actual_cost_measured':False,
            'excludes':'设备/工装折旧、加工/清洗机电耗、毛坯、报废、取样及疲劳评定',
            'condition':'全班专线人工与共享实际工时分别核算；温控等待不删去，10h为计划时隙。'}


if __name__=='__main__':
    out=ROOT/'studies/COMPETITION-DESIGN/results/ring-production-resources.json'
    out.write_text(json.dumps(calculate(),ensure_ascii=False,indent=2)+'\n')
    print(out)
