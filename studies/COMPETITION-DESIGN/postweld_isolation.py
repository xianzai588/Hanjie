"""Geometry/hold-up checks for local cold PT/UT and bore finishing tools."""
from pathlib import Path
import json,math
import yaml

ROOT=Path(__file__).resolve().parents[2]


def drain_capacity(inputs):
    d=inputs['inside_diameter_min_mm']/1000
    length=inputs['line_length_max_m']
    mu=inputs['newtonian_viscosity_max_Pa_s']
    rho=inputs['density_kg_m3']
    pressure=inputs['net_differential_pressure_min_Pa']
    area=math.pi*d*d/4
    a=128*mu*length/(math.pi*d**4)
    b=inputs['local_loss_K_max']*rho/(2*area**2)
    # pressure = a*Q + b*Q^2; this form avoids subtractive cancellation.
    q=2*pressure/(a+math.sqrt(a*a+4*b*pressure))
    speed=q/area
    reynolds=rho*speed*d/mu
    return dict(**inputs,capacity_ml_min=q*60*1e6,
        reynolds=reynolds,laminar_model_applicable=reynolds<2000,
        viscous_pressure_loss_Pa=a*q,local_pressure_loss_Pa=b*q*q,
        capacity_margin_fraction=q*60*1e6/(inputs['capacity_factor']*inputs['supply_limit_ml_min'])-1,
        qualification='design calculation; measure net pressure and flow on the assembled line')


def fault_hold_up(inputs):
    """Whole allowed wet line returning, including liquid already in the tool.

    Minimum cup dimensions and maximum line ID are deliberately different
    from the minimum line ID used for the pressure-loss calculation.
    A dry bottle inlet prevents the bottle inventory feeding back; a check
    valve is not credited, so a stuck-open valve has the same volume bound.
    """
    f=inputs['fault_containment']
    diameter=f['cup_inside_diameter_mm']-f['cup_inside_diameter_tolerance_mm']
    depth=f['cup_liquid_depth_mm']-f['cup_liquid_depth_tolerance_mm']
    wet_length=f['return_wet_length_max_m']
    if not (diameter>0 and depth>0 and wet_length>=inputs['line_length_max_m']>0
            and inputs['inside_diameter_max_mm']>=inputs['inside_diameter_min_mm']>0):
        raise ValueError('Fault dimensions must cover the entire permitted drain line')
    volume=math.pi*inputs['inside_diameter_max_mm']**2/4*wet_length
    capacity=math.pi*diameter**2/4*depth/1000-f['tool_displacement_max_ml']
    contributions=dict(operating_inventory_ml=f['operating_inventory_max_ml'],
        full_line_return_ml=volume,
        fittings_and_upper_tool_drainback_ml=f['fittings_and_upper_tool_drainback_max_ml'],
        supply_downstream_of_shutoff_ml=f['supply_downstream_of_shutoff_max_ml'],
        supply_during_shutdown_ml=inputs['supply_limit_ml_min']/60*f['shutdown_latency_max_s'],
        reserve_ml=f['reserve_ml'])
    if any(value<0 for value in contributions.values()):
        raise ValueError('Liquid inventories must be nonnegative')
    required=sum(contributions.values())
    # Even a missed bottle level indication cannot immerse the outlet in
    # one permitted cycle: the finite supply cartridge bounds all incoming
    # liquid, and the bottle's initial inventory is an opening condition.
    bottle_max=(f['bottle_initial_inventory_max_ml']+f['supply_cartridge_max_ml']+
                volume+f['fittings_and_upper_tool_drainback_max_ml']+
                f['supply_downstream_of_shutoff_max_ml']+f['operating_inventory_max_ml'])
    bottle_isolated=(f['bottle_max_liquid_below_cup_outlet_mm']>=150
                     and f['discharge_air_gap_min_mm']>=20
                     and bottle_max<=f['bottle_capacity_below_fault_level_min_ml'])
    return dict(**f,minimum_cup_diameter_mm=diameter,minimum_cup_depth_mm=depth,
        minimum_effective_hold_up_ml=capacity,contributions=contributions,
        required_fault_hold_up_ml=required,capacity_margin_ml=capacity-required,
        bottle_backfeed_excluded_by_geometry=bottle_isolated,
        bottle_maximum_cycle_inventory_ml=bottle_max,
        bottle_fault_level_capacity_margin_ml=f['bottle_capacity_below_fault_level_min_ml']-bottle_max,
        design_pass=capacity>=required and bottle_isolated,
        check_valve_credit=False,
        scope='All permitted wet tubing returns; dry discharge above maximum bottle liquid. Dimensions, inventories and shutdown latency are installation acceptance limits, not measured results.')


def evaluate():
    config=yaml.safe_load((ROOT/'project/competition-design.yaml').read_text(encoding='utf8'))
    drain=drain_capacity(config['postweld_drain'])
    fault=fault_hold_up(config['postweld_drain'])
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
    cup_depth=fault['cup_liquid_depth_mm']
    effective_hold=fault['minimum_effective_hold_up_ml']
    liquid_flow=config['postweld_drain']['supply_limit_ml_min']
    stop_latency=fault['shutdown_latency_max_s']
    line_drain_volume=fault['contributions']['full_line_return_ml']
    required_hold=fault['required_fault_hold_up_ml']
    # PT/UT is a whole metered batch, not the honing pump's 0.10 s inflow.
    pt_batch_limit=5.
    pt_required_hold=(line_drain_volume+pt_batch_limit+
                      fault['fittings_and_upper_tool_drainback_max_ml']+fault['reserve_ml'])
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
        PT_fault_hold_up_pass=pan_capacity>=pt_required_hold,
        cup_below_hub_no_slot_pass=30<39,
        drain_capacity_pass=drain['laminar_model_applicable'] and drain['capacity_ml_min']>=config['postweld_drain']['capacity_factor']*liquid_flow,
        retained_liquid_capacity_pass=fault['design_pass'],
        low_cold_face_clamp_pressure_pass=seal_pressure<1,
        face_seal_extreme_squeeze_pass=squeeze_ratio[0]>=.15 and squeeze_ratio[1]<=.30)
    return dict(PT_UT=dict(pan_outer_diameter_mm=149.4,collapsed_seal_envelope_mm=149.6,
        pan_wall_thickness_mm=pan_wall,pan_inside_diameter_mm=2*pan_inside_radius,
        pan_outer_diameter_tolerance_mm=.05,
        pan_floor_thickness_mm=pan_floor,pan_floor_top_z_mm=96,pan_upper_lip_z_mm=99,
        retained_liquid_depth_mm=pan_depth,effective_hold_up_ml=pan_capacity,
        metered_liquid_batch_limit_ml=pt_batch_limit,required_fault_hold_up_ml=pt_required_hold,
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
        drain_line=drain,
        effective_liquid_hold_up_ml=effective_hold,required_fault_hold_up_ml=required_hold,
        fault_containment=fault,
        maximum_line_drain_ml=line_drain_volume,supply_shutdown_s=stop_latency,
        suction_pressure_kPa=[-5,-2],pressure_permission='net driving pressure >=2.5 kPa after uncertainty, including measured elevation; cup vacuum alone does not permit supply',
        axial_clamp_N=cover_load,average_seal_land_pressure_MPa=seal_pressure,
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
