"""Relate Ni-layer remelting depth to dilution mass for the two-pass section.

This section budget is an engineering calculation, not a melt-pool solution.
Deposition, effective fusion throat and Ni-layer mass are kept distinct.
"""
from pathlib import Path
import json
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def evaluate():
    root_leg=2.8;final_leg=4.
    root_area=root_leg**2/2;total_area=final_leg**2/2
    # Densities are design inputs. Ni99 nominally 8.9 g/cm3; allow 8.8..9.0
    # for the diluted surface layer. Use the actual NiFe input 8.2 g/cm3.
    filler_density=8.2;ni_density_range=(8.8,9.0)
    steel_fraction_range=(.05,.10)
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
    max_depth_for20=[.20*root_area*filler_density/
        ((1-steel-.20)*root_leg*rho) for rho in ni_density_range for steel in steel_fraction_range]
    root_required_max_depth=min(max_depth_for20)
    root_design_max_depth=.30
    root_design_worst=fraction(root_area,root_leg,root_design_max_depth,max(ni_density_range),min(steel_fraction_range))
    result=dict(reference='finished QT/Ni99 connecting surface after preform machining; local thickness/depth minima/maxima include machining and identification uncertainty',
        root_filler_area_mm2=root_area,cap_added_filler_area_mm2=total_area-root_area,total_added_filler_area_mm2=total_area,
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
        steel_density_g_cm3=7.85,
        required_root_steel_remelt_area_mm2=[steel/(1-steel)*(root_area*filler_density+
            root_leg*root_design_max_depth*rho)/7.85 for rho in ni_density_range for steel in steel_fraction_range],
        final_two_pass_union_depth_limit_mm=.40,minimum_finished_second_layer_mm=.50,
        minimum_second_layer_remaining_mm=.50-.40,minimum_total_layer_remaining_mm=1.20-.40,
        root_mass_window_design_pass=root_design_worst<=.20,
        scope='planar full-footprint maximum-depth union envelope and declared design densities; actual cross-section/melt-pool and thermal-cycle verification required to freeze parameters')
    return result


if __name__=='__main__':
    result=evaluate();path=ROOT/'output/review/两道截面重熔与稀释预算.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
