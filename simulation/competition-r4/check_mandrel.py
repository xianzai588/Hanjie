"""Classical compliance of the locked collet, independently of weld FE.

The slotted neck sets the free expansion. A full-length mating cone backs the
terminal band after setting; its annular stem bears on a hard axial shoulder.
Dimensions and interface compliance are manufacturing/qualification inputs.
"""
from pathlib import Path
import json,math
import yaml

ROOT=Path(__file__).resolve().parents[2]

def evaluate():
    spec=yaml.safe_load((ROOT/'project/competition-design.yaml').read_text(encoding='utf8'))
    f=spec['fixture'];F=f['mandrel_backstop_capacity_n'];E=f['mandrel_hot_modulus_lower_mpa'];nu=.3;mu=.2
    # Adverse manufacturing envelope, hot modulus lower design bound.
    b=f['mandrel_cone_minor_radius_mm']-.02;a=f['mandrel_core_bore_diameter_mm']/2+.01;band=f['mandrel_backing_length_mm']-.04;angle=math.radians(f['internal_cone_half_angle_deg']+.1)
    area=.9*math.pi*40.005*band
    shaft_area=math.pi*(35.98**2-24.02**2)/4
    pressure=F/(.9*2*math.pi*b*band)
    core=pressure*b/E*((1-nu)*b*b+(1+nu)*a*a)/(b*b-a*a)
    axial=F*(math.tan(angle)+mu)/(1-mu*math.tan(angle))
    # The fixed cone is integral with the lower column. The sleeve's axial
    # reaction goes to the upper hard stop, tube and portal, not an actuator rod.
    upper_axial=axial+500
    tube_area=math.pi*((f['upper_stop_tube_outer_diameter_mm']-.02)**2-(f['upper_stop_tube_inner_diameter_mm']+.02)**2)/4
    tube=upper_axial*f['upper_stop_tube_length_mm']/(E*tube_area)
    portal_I=f['upper_portal_effective_strip_width_mm']*f['upper_portal_plate_thickness_mm']**3/12
    portal_plate=upper_axial*f['upper_portal_clear_span_mm']**3/(48*200000*portal_I)
    keeper=upper_axial/2*13**3/(3*200000*(30*20**3/12))
    stop_head=upper_axial/2*15**3/(3*200000*(30*20**3/12))
    portal_columns=upper_axial*f['upper_portal_column_length_mm']/(f['upper_portal_column_count']*200000*math.pi*f['upper_portal_column_diameter_mm']**2/4)
    stem=math.tan(angle)*(tube+portal_plate+portal_columns+keeper+stop_head)
    terminal=F/area*(20.02-b)/E
    # Incremental cone/shoulder face compliance after the 100 N seating state.
    faces=F*f['mandrel_face_incremental_compliance_um_per_kn']*1e-6
    total=core+stem+terminal+faces
    I=19*.8**3/12;neck=30;arm=f['mandrel_neck_bottom_z_mm']-107.5
    free_k=6*200000*I/(neck**3/3+arm*neck**2+arm*arm*neck)
    machining_margin=(f['mandrel_cone_machined_length_mm']-f['mandrel_backing_length_mm'])/2
    driving_stroke=(f['maximum_sleeve_diameter_mm']-f['collapsed_sleeve_diameter_mm'])/2/math.tan(math.radians(f['internal_cone_half_angle_deg']))
    checks=dict(full_band_cone_support=f['mandrel_backing_length_mm']>=14.6 and machining_margin>=driving_stroke+.05,
                matching_nominal_cone=abs(f['mandrel_cone_minor_radius_mm']-16.5)<1e-9,
                stem_length_covers_load_path=f['upper_stop_tube_length_mm']>=400-f['mandrel_axial_stop_z_mm']-1e-8,
                model_density_is_conservative=F/area/total>=2000,
                force_within_stop_capacity=F<=5000,
                keeper_and_head_strength_pass=6*(upper_axial/2)*15/(30*20**2)<=355/1.5,
                free_setting_force_below_preload_limit=free_k*.0425<100)
    return dict(scope='engineering prediction and fixture qualification targets; no measured fixture curve',
        cone=dict(half_angle_deg=10,effective_length_mm=14.6,minor_radius_mm=16.50,
                  major_radius_mm=16.50+14.6*math.tan(math.radians(10)),internal_radius_mm=f['mandrel_core_bore_diameter_mm']/2,
                  terminal_minimum_nominal_wall_mm=19.97-16.50-14.6*math.tan(math.radians(10))),
        contact_area_adverse_mm2=area,hot_modulus_lower_MPa=E,friction_upper=mu,
        upper_stop_tube_length_mm=f['upper_stop_tube_length_mm'],upper_axial_load_including_pressure_N=upper_axial,upper_stop_axial_compliance_components_mm=dict(tube=tube,portal_plate=portal_plate,portal_columns=portal_columns,keeper=keeper,stop_head=stop_head),axial_hard_stop_z_mm=f['mandrel_axial_stop_z_mm'],
        cone_end_margin_mm=machining_margin,maximum_setting_axial_stroke_mm=driving_stroke,
        axial_load_at_5000N_radial_N=axial,
        radial_compliance_components_mm_at5000N=dict(core_lame=core,locked_stem=stem,
            terminal_block=terminal,cone_and_shoulder_faces=faces),
        total_radial_compression_mm_at5000N=total,
        equivalent_density_N_mm3=F/area/total,FE_density_N_mm3=2000,
        free_neck_radial_stiffness_N_mm=free_k,free_setting_force_at_maximum_gap_N=free_k*.0425,
        qualification=['full contact band from z100.2 to114.8; neck length30 above the band, thickness0.80, width>=19',
            'mating cone and shoulder Ra<=0.2; incremental radial face compliance <=0.05 um/kN from seated100 to5000 N',
            'solid fixed reverse cone; sleeve shoulder, Ø70/Ø24 tube and portal carry axial reaction; M12 sets/returns only',
            'fixture test separates elastic compression, rigid-axis shift and six-finger setting repeatability',
            'equivalent uniform compression density>=2000 N/mm3 over the stated temperature range; no claim of measured data'],
        checks=checks,mandrel_compliance_design_pass=all(checks.values()))

if __name__=='__main__':
    r=evaluate();out=ROOT/'simulation/competition-r4/results/mandrel-compliance-verification.json'
    out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(r,ensure_ascii=False,indent=2))
