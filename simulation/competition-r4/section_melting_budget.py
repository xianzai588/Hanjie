"""Relate Ni-layer remelting depth to dilution mass for the two-pass section.

This section budget is an engineering calculation, not a melt-pool solution.
Deposition, effective fusion throat and Ni-layer mass are kept distinct.
"""
from pathlib import Path
import json
import numpy as np
import yaml
import math
import itertools

ROOT=Path(__file__).resolve().parents[2]


def evaluate():
    pre=yaml.safe_load((ROOT/'project/independent-precoat-candidates.yaml').read_text(encoding='utf8'))
    spec=yaml.safe_load((ROOT/'project/competition-design.yaml').read_text(encoding='utf8'))
    nominal=yaml.safe_load((ROOT/spec['process_source']).read_text(encoding='utf8'))['process']['nominal']
    s=pre['section_interface'];p=spec['process'];mix=pre['mixing_diagnostic']
    first_min,first_max=pre['common']['first_machined_normal_thickness_mm']
    total_min=s['finished_total_thickness_mm'][0]
    second_min=total_min-first_max
    areas=[eta*math.pi*diam**2/4*feed/speed for eta,diam,feed,speed in itertools.product(
        p['deposition_efficiency_range'],
        [p['wire_diameter_mm']-p['wire_diameter_tolerance_mm'],p['wire_diameter_mm']+p['wire_diameter_tolerance_mm']],
        [p['feed_nominal_mm_s']-p['feed_tolerance_mm_s'],p['feed_nominal_mm_s']+p['feed_tolerance_mm_s']],
        [nominal['travel_speed_mm_s']*(1-p['travel_relative_tolerance']),nominal['travel_speed_mm_s']*(1+p['travel_relative_tolerance'])])]
    area_min,area_max=min(areas),max(areas)
    root_leg=s['root_contact_width_mm'];final_leg=s['final_contact_width_mm']
    root_area=root_leg**2/2;total_area=final_leg**2/2
    # Densities are design inputs. Ni99 nominally 8.9 g/cm3; allow 8.8..9.0
    # for the diluted surface layer. Use the actual NiFe input 8.2 g/cm3.
    filler_density=s['final_filler_density_g_cm3'];ni_density_range=s['second_density_range_g_cm3']
    steel_fraction_range=mix['steel_into_final']
    root_max_depth=.40
    def fraction(area,width,depth,ni_density,steel_fraction):
        ni_mass=width*depth*ni_density;filler_mass=area*filler_density
        return (1-steel_fraction)*ni_mass/(ni_mass+filler_mass)
    # First and second pass can remelt the same lower layer. The cumulative
    # melted union is counted once, from the same finished reference surface.
    root_fractions=[fraction(root_area,root_leg,root_max_depth,rho,steel)
                    for rho in ni_density_range for steel in steel_fraction_range]
    whole_fractions=[fraction(total_area,final_leg,.40,rho,steel)
                     for rho in ni_density_range for steel in steel_fraction_range]
    max_depth_for20=[.20*area*filler_density/
        ((1-steel-.20)*root_leg*rho) for rho,steel,area in itertools.product(ni_density_range,steel_fraction_range,[area_min,area_max])]
    root_required_max_depth=min(max_depth_for20)
    root_design_max_depth=s['final_root_remelt_depth_max_mm']
    root_design_worst=fraction(area_min,root_leg,root_design_max_depth,max(ni_density_range),min(steel_fraction_range))
    union_depth=s['final_union_remelt_depth_max_mm']
    union_fractions=[fraction(2*area,s['final_contact_width_mm'],union_depth,rho,steel)
                     for area,rho,steel in itertools.product([area_min,area_max],ni_density_range,steel_fraction_range)]
    # Common-width strip: d=rho1*p/(rho1*p+rho2*h_added). This is a
    # conditional uniform-mixing requirement, not a transport prediction.
    added_second_min=s['second_deposited_top_from_QT_floor_min_mm']-first_max
    d2max=mix['first_into_second'][1]
    second_depth_limit=d2max/(1-d2max)*min(ni_density_range)/max(s['diluted_first_density_range_g_cm3'])*added_second_min
    result=dict(reference='finished QT/Ni99 connecting surface after preform machining; local thickness/depth minima/maxima include machining and identification uncertainty',
        nominal_triangle_root_area_mm2=root_area,nominal_triangle_cap_area_mm2=total_area-root_area,nominal_triangle_total_area_mm2=total_area,
        root_contact_width_mm=root_leg,final_contact_width_mm=final_leg,
        NiFe_density_g_cm3=filler_density,Ni_layer_density_design_range_g_cm3=list(ni_density_range),
        steel_dilution_mass_fraction_range=list(steel_fraction_range),
        geometric_ideal_throat_mm=3.5/np.sqrt(2),
        throat_scope='3.5 mm minimum leg gives this ideal 45-degree throat only if both-side fusion is demonstrated; deposited area is not a fusion measurement',
        Ni_layer_mass_fraction_at_root_depth_0_40_mm=[min(root_fractions),max(root_fractions)],
        Ni_layer_mass_fraction_at_total_union_depth_0_40_mm=[min(whole_fractions),max(whole_fractions)],
        maximum_root_depth_for_20pct_Ni_layer_mm=root_required_max_depth,
        proposed_maximum_root_depth_mm=root_design_max_depth,
        proposed_root_worst_Ni_layer_mass_fraction=root_design_worst,
        steel_density_g_cm3=s['steel_density_g_cm3'],
        required_root_steel_remelt_area_scenarios_mm2=[steel/(1-steel)*(area*filler_density+
            root_leg*root_design_max_depth*rho)/s['steel_density_g_cm3'] for area,rho,steel in itertools.product([area_min,area_max],ni_density_range,steel_fraction_range)],
        final_two_pass_union_depth_limit_mm=union_depth,minimum_finished_second_layer_mm=second_min,
        minimum_second_layer_remaining_mm=second_min-union_depth,minimum_total_layer_remaining_mm=total_min-union_depth,
        per_pass_actual_added_area_range_mm2=[area_min,area_max],
        total_actual_added_area_range_mm2=[2*area_min,2*area_max],
        final_union_second_origin_mass_fraction_range=[min(union_fractions),max(union_fractions)],
        second_added_height_min_mm=added_second_min,
        first_remelt_depth_for_diagnostic_15pct_mm=second_depth_limit,
        first_geometric_remaining_at_that_depth_mm=first_min-second_depth_limit,
        root_mass_window_design_pass=root_design_worst<=.20,
        scope='Declared flat contact widths and density scenarios; uniform mixing averages are not local concentrations or true transport bounds. Nominal 2.8/4mm triangle areas are reference shapes; robust limits use actual feed corners.',
        continuous_connection_verified=False,actual_dilution_verified=False)
    # Independent tracer ledger ties the entire chemistry chain to origins.
    mats=yaml.safe_load((ROOT/'project/materials.yaml').read_text(encoding='utf8'))['materials']
    sources={'QT':mats['qt450_10']['composition_nominal_wt_pct'],
        'CI_A1':pre['candidates']['CI-A1']['typical_deposit_wt_pct'],
        'bare_Ni99':mix['bare_Ni99'],'NiFe55':mats['ernife_ci']['composition_nominal_wt_pct'],
        'steel':mats['q235b']['composition_nominal_wt_pct']}
    ledger=[]
    for d1,d2,dn,ds in itertools.product(mix['QT_into_first'],mix['first_into_second'],mix['second_into_final'],mix['steel_into_final']):
        weights=dict(QT=dn*d2*d1,CI_A1=dn*d2*(1-d1),bare_Ni99=dn*(1-d2),NiFe55=1-dn-ds,steel=ds)
        assert abs(sum(weights.values())-1)<1e-12
        composition={element:sum(weights[k]*sources[k][element] for k in weights) for element in ['C','Si','Mn','Ni']}
        ledger.append(dict(d1=d1,d2=d2,dn=dn,ds=ds,origin_mass_fractions=weights,final_composition_wt_pct=composition))
    result['chemistry_origin_ledger']=ledger
    result['final_carbon_diagnostic_wt_pct']=[min(c['final_composition_wt_pct']['C'] for c in ledger),max(c['final_composition_wt_pct']['C'] for c in ledger)]
    return result


if __name__=='__main__':
    result=evaluate();path=ROOT/'studies/COMPETITION-DESIGN/results/current-section-interface.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='chemistry_origin_ledger'},ensure_ascii=False,indent=2))
