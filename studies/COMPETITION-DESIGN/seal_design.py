"""Dimensioned seal envelope and lumped copper/water circuit; SI heat units."""
import math

def evaluate():
    ro,ri,height=74.8,71.8,9.0
    cord,depth,width=2.5,1.875,3.75
    steel_growth=75*12e-6*(180-20)
    copper_growth=ro*17e-6*(45-20)
    rubber_growth=cord*3e-4*(180-20)
    protrusion=cord-depth
    cold_min=ro+protrusion-75.01
    cold_max=ro+protrusion-75.00
    minimum=cold_min-steel_growth
    maximum=cold_max+(ro+.01)*17e-6*(45-20)+2.53*3e-4*(180-20)
    # 15% set allowance is a design allowance, informed by supplier typical data;
    # final incoming/cyclic fixture checks must establish the usable seal life.
    retained=minimum*.85-.02
    fill=math.pi*cord**2/4/(depth*width)
    hot_fill=fill*(1+3e-4*(180-20))**3
    worst_hot_fill=(math.pi*2.53**2/4/(1.835*3.73))*(1+3e-4*(180-20))**3
    free_hot=75.01+cold_max+(ro+.01)*17e-6*(45-20)+2.53*3e-4*(180-20)
    stroke=1.1-.05
    withdrawn=math.sqrt(free_hot**2+stroke**2-2*free_hot*stroke*math.cos(math.pi/4))
    water_length=8*(73.3*math.radians(84)+7.0) # per channel: 84deg arc + two 3.5mm port legs
    water_volume=math.pi*(.55**2+.70**2)*(water_length/2)
    groove_volume=depth*width*2*math.pi*(ro-depth/2)
    lower_groove_volume=.40*1.40*2*math.pi*72.8
    split_volume_upper=4*2.0*(ro-ri)*height/math.sqrt(1-(1.0/ri)**2)
    boss_volume=8*2*4*6
    bridge_pocket_volume=4*14*.53*3.75
    port_counterbore_extra_volume=8*math.pi*((.9**2-.55**2)+(.9**2-.7**2))*3
    copper_volume=math.pi*(ro**2-ri**2)*height-water_volume-groove_volume-split_volume_upper+boss_volume-bridge_pocket_volume-port_counterbore_extra_volume
    sector_gap_min=1.95-2*1.15/math.sqrt(2)
    # Lower gland is carried by a separate continuous 17-4PH backing ring.
    # Port-boss additions and removal of the copper lower groove preserve the
    # original conservative Cu capacity, even with seams/ports deducted.
    actual_min_mass=.0675956937095338+lower_groove_volume*8.96e-6+8*1.9*3.9*5.9*8.96e-6-4*2.05*3.08*9.1*8.96e-6-.00065-4*14*.54*3.77*8.96e-6
    mass=copper_volume*8.96e-6
    # Conservative thermal capacity includes allowance for ports and clamp recesses.
    capacity=.0675956937095338*385
    # Fully developed laminar circular-channel UA is Nu*k*pi*L; the diameter
    # cancels. Check both new diameters remain in the laminar regime.
    ua=3.66*.59*math.pi*water_length/1000
    branch_flow=.6/8/60/1000
    # Conservative water envelope through 35 C: rho <=1000 kg/m3, mu >=0.70 mPa s.
    channel_reynolds=[4*1000*branch_flow*1.05/(math.pi*.00070*d) for d in (.0011,.0014)]
    microtube_reynolds=4*1000*branch_flow/(math.pi*.00070*.001)
    microtube_pressure_drop_Pa=128*.001053*.2*branch_flow/(math.pi*.001**4)
    microtube_velocity=4*branch_flow/(math.pi*.001**2)
    worst_velocity=4*branch_flow*1.05/(math.pi*.00095**2)
    hydraulic_upper_Pa=(.06*.21/.00095+15)*.5*1000*worst_velocity**2+5000
    # Centres ±0.02, bore +0.02/0, upper groove centre ±0.01 and width ±0.02,
    # lower groove depth ±0.01, all measured from the same copper bottom face.
    water_ligaments=[(92-90.5)-(.55+.01)-.02-0.,
                     (97.125-90.5)-.01-(3.75+.02)/2-((94-90.5)+.02+.70+.01),
                     2-.04-(.55+.01)-(.70+.01)]
    flow_capacity=.6/60*4180
    effective_water=flow_capacity*(1-math.exp(-ua/flow_capacity))
    area=2*math.pi*75*height/1e6
    # Capacity envelope for a single thermally isolated quarter; all 10 W
    # incident radiation is conservatively concentrated in that quarter.
    conductance=150*area/4
    water_h=5.6
    copper_limit_case=(water_h/4*22+conductance*180+10)/(water_h/4+conductance)
    lower_retained=(.28-9*17e-6*28)*.85-.01
    lower_hot_fraction=(.29+.99*3e-4*28)/(.99*(1+3e-4*28))
    lower_hot_fill=(math.pi*.5**2/(1.4*.71))*(1+3e-4*28)**3
    lower_worst_hot_fill=max(math.pi*d*d/4/(1.38*(d-.29)) for d in (.99,1.01))*(1+3e-4*28)**3
    return dict(copper_mass_kg=mass,copper_heat_capacity_J_K=capacity,
        copper_height_mm=height,copper_bottom_z_mm=90.5,copper_top_z_mm=99.5,
        minimum_copper_mass_kg=.0675956937095338,
        lower_face_seal_cord_mm=1.0,lower_face_groove_depth_mm=.4,
        lower_face_groove_width_mm=1.4,lower_face_seal_radius_mm=72.8,
        plate_top_z_mm=88.59,metal_slide_gap_mm=.31,
        copper_to_backing_ring_clearance_mm=.10,
        lower_backing_ring_thickness_mm=1.5,lower_backing_ring_top_z_mm=90.4,
        lower_backing_ring_bottom_z_mm=88.9,lower_face_temperature_limit_C=48,
        backing_ring_material='17-4PH H900; continuous lower gland, 8 inner tabs and blind M3 screws',
        pan_under_rim_thickness_mm=6,pan_under_rim_inner_radius_mm=66.5,
        retention_screw_radius_mm=69,retention_screw_radius_tolerance_mm=.05,
        retention_screw='M3x6 ISO10642 stainless; maximum head diameter6.72 and height1.86; fitted flush or recessed0..0.02 mm',
        screw_blind_drill_depth_maximum_from_pan_top_mm=5.5,
        screw_blind_hole_bottom_ligament_minimum_mm=(1-.02)+(6-.02)-5.5,
        screw_inner_side_ligament_minimum_mm=69-.05-1.5-(66.5+.05),
        screw_to_lower_gland_ligament_minimum_mm=72.8-.01-1.42/2-(69+.05+6.72/2-(1.48-.41-.02)/math.tan(math.radians(46))),
        pan_countersink_relief_depth_maximum_mm=.15,
        lower_stop_radii_mm=[73.7,74],lower_stop_nominal_height_mm=.31,
        lower_stop_average_pressure_MPa=1000/(math.pi*(74**2-73.7**2)),
        lower_gland_local_bending_MPa=6*(1000/(2*math.pi*72.8))*.9/1.5**2,
        copper_sector_gap_mm=2,sector_gap_tolerance_mm=.05,
        upper_bridge_material='316L; 0.50 +/-0.02 mm radial thickness; one end fixed, other end slides in a 6 mm pocket; pocket radial depth 0.53 +0.01/0 from actual gland floor',
        upper_bridge_minimum_copper_inner_wall_mm=74.79-1.915-.54-71.825,
        upper_bridge_pocket_removed_volume_mm3=bridge_pocket_volume,
        minimum_sector_gap_during_retraction_mm=sector_gap_min,
        port_boss_count=8,port_boss_dimensions_mm=[2,4,6],port_boss_angle_from_seam_deg=3,
        port_tube_outer_diameter_mm=1.8,port_tube_insertion_mm=3,
        water_bulkheads='4 welded sealed 316L blocks at R55/45+90i deg, 12 radial x16 tangential, z83.59..99; 4 hose ports per block and independent down-facing supply/return',
        microtube_design='PFA TLM0201 or equivalent, OD2/ID1; manufacturer recommended static bend R10, design installed R>=12 with 1.15 mm stroke qualification; each hose <=100 mm',
        copper_water_port_radial_stagger_mm=10,
        water_port_local_xyz_mm=[[58,-8,92],[52,-8,94],[58,8,92],[52,8,94]],
        water_port_union='custom 316L M4x0.5 compression union, OD<=5 and length<=8; PFA insertion >=4, low-outgassing ferrule; machined Cu5x5x5 L-port block and integral M4 nipple, no cyclic metal bending; round nut OD5 with flats4.5, engagement>=2; installed PFA outside envelope<=2.20 mm',
        microtube_Re_upper=microtube_reynolds,microtube_pair_pressure_drop_Pa=microtube_pressure_drop_Pa,
        hydraulic_design_upper_Pa=hydraulic_upper_Pa,pump_differential_design_minimum_Pa=80000,
        microtube_hydraulic_envelope='effective bore >=0.95 mm; each circuit two hoses <=105 mm each; per-channel 0.075..0.07875 L/min; Darcy f=0.06 and local K=15 design bounds cover microtube transition; water channel laminar check uses maximum flow',
        channel_arc_angle_deg=84,channel_straight_length_each_end_mm=3.5,
        actual_copper_minimum_with_ports_kg=actual_min_mass,
        lower_ring_incident_heat_limit_W=2,lower_ring_copper_link_W_K=.75,
        lower_ring_temperature_bound_C=45+2/.75,
        shell_copper_heat_transfer_reference='effective conductance normalized to nominal full circumference; actual copper gap area is not presented as a meshed contact surface', 
        lower_face_cold_compression_mm=.29,
        lower_face_retained_compression_mm=lower_retained,
        lower_face_hot_max_compression_fraction=lower_hot_fraction,
        lower_face_hot_gland_fill_fraction=lower_hot_fill,
        lower_face_worst_hot_gland_fill_fraction=lower_worst_hot_fill,
        lower_face_cord_acceptance_mm=[.99,1.01],
        copper_temperature_limit_C=45,shell_seal_band_temperature_limit_C=180,
        seal_material='low-outgassing FFKM, Kalrez 7075UP or qualified equivalent',
        cord_diameter_mm=cord,groove_radial_depth_mm=depth,groove_axial_width_mm=width,
        groove_center_z_mm=97.125,elastomer_CTE_upper_per_K=3e-4,
        cold_squeeze_mm=[cold_min,cold_max],hot_squeeze_min_mm=minimum,
        hot_squeeze_max_mm=maximum,hot_squeeze_fraction=[minimum/2.53,maximum/2.47],
        retained_squeeze_with_set_and_wear_allowance_mm=retained,
        cold_gland_fill_fraction=fill,hot_gland_fill_fraction=hot_fill,
        worst_hot_gland_fill_fraction=worst_hot_fill,
        upper_cord_acceptance_mm=[2.47,2.53],
        upper_groove_matched_depth_range_mm=[1.835,1.915],
        sector_count=4,sector_angle_deg=90,radial_retraction_mm=1.1,
        retraction_tolerance_mm=.05,withdrawn_max_radius_mm=withdrawn,
        minimum_withdrawal_clearance_mm=75-withdrawn,
        water_channels_per_sector=2,channel_diameters_mm=[1.1,1.4],
        channel_diameter_upper_tolerance_mm=.02,channel_center_tolerance_mm=.02,
        minimum_copper_ligaments_with_tolerance_mm=water_ligaments,
        channel_reynolds=channel_reynolds,
        water_conductivity_lower_W_mK=.59,water_viscosity_lower_Pa_s=.00070,
        channel_center_radius_mm=73.3,channel_center_z_mm=[92,94],
        water_flow_L_min=.6,water_inlet_C=[18,22],water_outlet_limit_C=35,
        water_channel_UA_W_K=ua,water_effective_W_K=effective_water,
        water_lumped_design_W_K=water_h,
        copper_upper_bound_C=copper_limit_case,
        copper_upper_bound_scope='single isolated quarter, shell 180C, inlet 22C, h 150 W/m2K, all 10 W incident heat in this quarter',
        copper_upper_bound_incident_radiation_W=10,
        copper_upper_bound_water_heat_W=water_h/4*(copper_limit_case-22),
        steel_copper_effective_h_W_m2K=[50,150],
        copper_effective_area_mm2=area*1e6,
        seal_radial_force_design_limit_N=1500,
        checks_pass=bool(retained>=.2 and maximum/2.47<=.25 and worst_hot_fill<=.85
                        and 75-withdrawn>=.1 and copper_limit_case<=45
                        and lower_retained>=.2 and lower_hot_fraction<=.30
                        and lower_worst_hot_fill<=.85
                        and min(water_ligaments)>=.5-1e-12
                        and 74.79-1.915-.54-71.825>=.5-1e-12
                        and max(channel_reynolds)<2300 and effective_water>=water_h
                        and hydraulic_upper_Pa<80000
                        and (1-.02)+(6-.02)-5.5>=1.4
                        and 69-.05-1.5-(66.5+.05)>=.9-1e-12
                        and 72.8-.01-1.42/2-(69+.05+6.72/2-(1.48-.41-.02)/math.tan(math.radians(46)))>=.5
                        and sector_gap_min>=.1 and actual_min_mass>=.0675956937095338
                        and 45+2/.75<=48))

if __name__=='__main__':
    import json
    print(json.dumps(evaluate(),ensure_ascii=False,indent=2))
