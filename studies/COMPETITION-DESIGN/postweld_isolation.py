"""Geometry/hold-up checks for local cold PT/UT and bore finishing tools."""
from pathlib import Path
import json,math

ROOT=Path(__file__).resolve().parents[2]


def evaluate():
    shell_radius=75.
    # Actual CAD outer wing arc is only 18 mm. A 38+ mm single-wing hood
    # has no two-sided sealing land. Use a continuous under-seat catch pan.
    pan_radius=74.7;pan_wall=1.;pan_inside_radius=pan_radius-pan_wall
    pan_depth=3.;pan_floor=2.
    inflatable_pressure_MPa=.03;seal_profile_radius=2.;seal_wall=.4-.02
    seal_membrane_stress=inflatable_pressure_MPa*seal_profile_radius/seal_wall
    # A thickened seal collar intrudes over z96..97: include its real volume.
    collar_inside_radius=pan_radius-2.
    pan_capacity=math.pi*(collar_inside_radius**2+2*pan_inside_radius**2)/1000-3
    groove_depth=.75;groove_depth_tol=.02;collapsed_profile_height=.80
    collapsed_radius=pan_radius+.025-(groove_depth-groove_depth_tol)+collapsed_profile_height
    groove_minimum_ligament=2.-.05-(groove_depth+groove_depth_tol)
    entry_eccentricity=.10;entry_tilt_deg=.05;collar_height=11.
    entry_margin=shell_radius-collapsed_radius-entry_eccentricity-collar_height*math.tan(math.radians(entry_tilt_deg))
    cartridge_inside_min=152.-.05
    withdrawal_stroke=125.;stroke_tol=.1
    withdrawn_lip_max=99.1-(withdrawal_stroke-stroke_tol)
    cartridge_clearance=(cartridge_inside_min-2*collapsed_radius)/2-entry_eccentricity
    pressure_load=.005*math.pi*pan_radius**2
    lift_design_load=1.5*(pressure_load+10.)
    seal_force=inflatable_pressure_MPa*2*math.pi*shell_radius*6
    cup_inner_radius=22.;cup_depth=10.;occupied_volume=3000.
    effective_hold=(math.pi*cup_inner_radius**2*cup_depth-occupied_volume)/1000
    liquid_flow=60.;stop_latency=.10;line_drain_volume=5.;reserve=2.
    required_hold=line_drain_volume+liquid_flow/60*stop_latency+reserve
    gravity_flow=.6*math.pi*(4e-3)**2/4*math.sqrt(2*9.81*.005)*60*1e6
    cover_load=120;gasket_radius=27.;gasket_width=1.0
    seal_pressure=cover_load/(2*math.pi*gasket_radius*gasket_width)
    cord=1.;cord_tol=.02;groove=.7;groove_tol=.01;stop_gap=.1;stop_tol=.01
    squeeze_min=(cord-cord_tol)-(groove+groove_tol)-(stop_gap+stop_tol)
    squeeze_max=(cord+cord_tol)-(groove-groove_tol)-(stop_gap-stop_tol)
    squeeze_ratio=[squeeze_min/(cord+cord_tol),squeeze_max/(cord-cord_tol)]
    checks=dict(collapsed_pan_no_scrape_pass=entry_margin>0,
        seal_gland_ligament_pass=groove_minimum_ligament>=1.,
        cartridge_no_scrape_pass=cartridge_clearance>0,
        entire_pan_inside_cartridge_pass=withdrawn_lip_max<-20.-5.,
        vertical_support_capacity_pass=lift_design_load<=200.,
        under_seat_pan_clearance_pass=99.0<100.0,
        PT_seal_membrane_strength_pass=seal_membrane_stress<=2/3,
        PT_fault_hold_up_pass=pan_capacity>=required_hold,
        cup_below_hub_no_slot_pass=30<39,
        gravity_drain_capacity_pass=gravity_flow>=2*liquid_flow,
        retained_liquid_capacity_pass=effective_hold>=required_hold,
        low_cold_face_clamp_pressure_pass=seal_pressure<1,
        face_seal_extreme_squeeze_pass=squeeze_ratio[0]>=.15 and squeeze_ratio[1]<=.30)
    return dict(PT_UT=dict(pan_outer_diameter_mm=149.4,collapsed_seal_envelope_mm=149.6,
        pan_wall_thickness_mm=pan_wall,pan_inside_diameter_mm=2*pan_inside_radius,
        pan_outer_diameter_tolerance_mm=.05,
        pan_floor_thickness_mm=pan_floor,pan_floor_top_z_mm=96,pan_upper_lip_z_mm=99,
        retained_liquid_depth_mm=pan_depth,effective_hold_up_ml=pan_capacity,
        seal_inflation_pressure_kPa=[20,30],seal_axial_width_mm=6,seal_wall_nominal_mm=.4,seal_wall_tolerance_mm=.02,
        seal_membrane_stress_bound_MPa=seal_membrane_stress,seal_minimum_procurement_tensile_MPa=2,
        seal_total_distributed_radial_load_bound_N=seal_force,
        seal_gland=dict(collar_z_mm=[88,97],collar_wall_mm=2.,groove_center_z_mm=93.,
            groove_axial_width_mm=6.20,groove_axial_width_tolerance_mm=.05,groove_radial_depth_mm=groove_depth,
            groove_depth_tolerance_mm=groove_depth_tol,minimum_remaining_metal_wall_mm=groove_minimum_ligament,
            seal_captive_heel='moulded twin base heels in continuous dovetail lips; replaceable split clamp belowz88; no adhesive in the cavity',
            port='one radialØ1 inflation hole atz93 connected to weldedØ2 stainless tube below the pan; separate fromØ4 liquid drain',
            maximum_collapsed_radius_mm=collapsed_radius,minimum_entry_clearance_mm=entry_margin,
            inflated_profile_radial_reach_mm=1.25,shell_inside_diameter_design_mm=[150,150.02]),
        support_and_cartridge=dict(station='separate cold NDT nest after shell is lifted off the fixed welding core; empty open bottom',
            pan_stem_diameter_mm=12,nominal_stem_length_mm=258,stem_top_z_mm=88,cartridge_floor_z_mm=-170,
            lift_capacity_N=200,pressure_and_weight_design_load_N=lift_design_load,
            dual_guide_spacing_mm=50,entry_center_error_limit_mm=entry_eccentricity,entry_tilt_limit_deg=entry_tilt_deg,
            cartridge_inside_diameter_mm=152,cartridge_inside_diameter_tolerance_mm=.05,
            cartridge_upper_interface_z_mm=-20,cartridge_flange_outer_diameter_mm=174,
            flange_face_seal_radius_mm=83,flange_face_cord_mm=2,flange_groove_depth_mm=1.5,flange_stop_gap_mm=.1,
            withdrawal_stroke_mm=withdrawal_stroke,stroke_tolerance_mm=stroke_tol,
            withdrawn_pan_lip_maximum_z_mm=withdrawn_lip_max,minimum_cartridge_radial_clearance_mm=cartridge_clearance,
            feedthrough='welded metal bellows with130mm rated travel; drive and guide below closed cartridge; bottle and vacuum remain connected',
            closure='clamped flange mates with underside of independentOD180/ID150.20 datum nest; external face seal, product wall untouched'),
        insertion='transfer shell off fixed welding core to independent NDT nest; vertical from open bottom with seal collapsed; inflate only atz90..96 afterpanfacez96 is positioned',
        withdrawal='drain and dry pan in place; cover bottom exit with closed collection cartridge; maintain upward pan and suction, deflate to OD<=149.6, lower without tilt or wall scrape',
        method='continuous closed-bottom 316L under-seat pan, non-sliding inflatable low-outgassing FFKM seal, PT swab/UT metered gel above pan, separate sealed recovery bottle'),
        honing=dict(lower_cup_outer_diameter_mm=60,lower_cup_inside_diameter_mm=44,
        liquid_depth_mm=10,drain_bore_mm=4,liquid_supply_limit_ml_min=liquid_flow,
        gravity_drain_at_5mm_head_ml_min=gravity_flow,
        effective_liquid_hold_up_ml=effective_hold,required_fault_hold_up_ml=required_hold,
        maximum_line_drain_ml=line_drain_volume,supply_shutdown_s=stop_latency,
        suction_pressure_kPa=[-5,-2],axial_clamp_N=cover_load,average_seal_land_pressure_MPa=seal_pressure,
        lower_face_seal_radius_mm=gasket_radius,face_seal_cord_mm=cord,
        lower_face_seal_groove_depth_mm=groove,metal_stop_gap_mm=stop_gap,
        face_squeeze_mm=cord-groove-stop_gap,face_cord_tolerance_mm=cord_tol,groove_depth_tolerance_mm=groove_tol,
        stop_gap_tolerance_mm=stop_tol,face_squeeze_extremes_mm=[squeeze_min,squeeze_max],
        face_squeeze_ratio_extremes=squeeze_ratio,
        procurement_squeeze_design_range=[.15,.30],
        lower_cup_removal='drain, dry/wipe in place, close drain; lower vertically through open shell bottom; upper tool withdrawn upwards in closed capture sleeve'),
        checks=checks,geometry_and_liquid_capacity_design_pass=all(checks.values()),
        physical_qualification='fluorescent liquid and 5/10/25 um reference particles; normal, lost-suction, shutdown and full withdrawal; inspect untouched lower cavity on sacrificial unit',
        scope='cold postweld isolation geometry and retained-volume design calculation; no measured leakage or cleanliness result')


if __name__=='__main__':
    result=evaluate();out=ROOT/'studies/COMPETITION-DESIGN/results/postweld-isolation.json'
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
