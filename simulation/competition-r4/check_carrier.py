"""Carrier bending and bolted-root compliance under actual unilateral pad loads.

Classical small-deflection calculations in N/mm/MPa. The mounting table is a
rigid boundary; its motion is checked against the fixture-axis setting allocation.
Peening is an adverse peak load, never a residual-stress reduction credit.
"""
from pathlib import Path
import argparse,json,math
import yaml

ROOT=Path(__file__).resolve().parents[2]


def evaluate(case=None):
    spec=yaml.safe_load((ROOT/'project/competition-design.yaml').read_text(encoding='utf8'))
    f=spec['fixture'];E=f['carrier_post_modulus_mpa'];r=f['carrier_post_radius_mm']
    L=f['carrier_disk_z_mm'][0]-f['carrier_post_bottom_z_mm']
    hole=f['carrier_post_maximum_auxiliary_bore_mm']/2
    I=math.pi*(r**4-hole**4)/4;A=math.pi*(r*r-hole*hole)
    lever=115.-f['carrier_disk_z_mm'][0]
    heads=2;moment=f['carrier_design_moment_n_mm'];load=f['carrier_pad_load_design_n']
    scope='design capacity envelope, not observed pad reactions'
    if case is not None:
        inp=json.loads((case/'input.json').read_text(encoding='utf8'))
        audit=json.loads((case/'pad-contact-audit.json').read_text(encoding='utf8'))
        if not inp.get('unilateral_pads') or not audit['compression_only_reactions_pass']:
            raise ValueError('actual unilateral pad audit required')
        heads=inp['maximum_simultaneous_heads'];moment=audit['maximum_carrier_moment_N_mm']
        load=audit['maximum_total_upward_reaction_N'];scope=str(case)
    peak_impact=spec['peening']['contact_force_peak_limit_N']
    # Bound |r x F| for any contact-force direction. The bead is inclined;
    # using the radial lever alone would miss its radial-force bending component.
    impact_lever=math.hypot(75.,118.-f['carrier_post_bottom_z_mm'])
    impact_moment=heads*peak_impact*impact_lever
    impact_force=heads*peak_impact
    total_load=load+impact_force
    mandrel_force=f['mandrel_backstop_capacity_n']
    mandrel_height=115.-f['carrier_post_bottom_z_mm']
    M=moment+impact_moment+mandrel_force*mandrel_height
    n=f['carrier_base_bolt_count'];rb=f['carrier_base_bolt_radius_mm']
    bolt_area=f['carrier_base_bolt_tensile_area_mm2'];grip=f['carrier_base_bolt_elastic_grip_mm']
    bolt_k=E*bolt_area/grip
    bolt_moment_k=bolt_k*n*rb**2/2
    bolt_max_delta=M/(n*rb/2)+total_load/n
    overhang=rb-r;flange_h=f['carrier_base_flange_height_mm'];strip_width=f['carrier_base_bolt_diameter_mm']
    strip_I=strip_width*flange_h**3/12
    bolt_bending_load=M/(n*rb/2)
    root_bolt_rotation=M/bolt_moment_k
    flange_rotation=bolt_bending_load*overhang**2/(2*E*strip_I)
    # Integrate the linearly varying bending moment of the lateral mandrel load.
    post_rotation=((moment+impact_moment)*L+mandrel_force*L*(L+2*lever)/2)/(E*I)
    # A short, thick flange needs transverse shear as well as bending.
    G=E/(2*(1+.30))
    flange_shear_rotation=bolt_bending_load/((5/6)*G*strip_width*flange_h)
    post_shear=(impact_force+mandrel_force)*L/(.9*G*A)
    components=dict(post_end_translation=((moment+impact_moment)*L**2/2+mandrel_force*L**2*(2*L+3*lever)/6)/(E*I),post_rotation=post_rotation*lever,
        post_transverse_shear=post_shear,bolt_root=root_bolt_rotation*(L+lever),
        flange_bending=flange_rotation*(L+lever),flange_transverse_shear=flange_shear_rotation*(L+lever))
    # The column reaches beyond every pad; no unsupported disk lip under a pad.
    disk_overhang=max(0.,f['support_radius_mm']+f['support_pad_radius_mm']-r)
    bolt_proof=f['carrier_base_bolt_proof_stress_mpa']
    post_normal=M*r/I+total_load/A
    post_shear=4*(impact_force+mandrel_force)/(3*A)
    post_vm=math.sqrt(post_normal**2+3*post_shear**2)
    fixture_fe=None;fixture_fe_pass=True
    if f.get('fixed_cone'):
        paths=[ROOT/f'simulation/competition-r4/results/fixture-axis-solid-core-h{h:g}/result.json' for h in (2.,1.5)]
        if not all(p.exists() for p in paths):
            fixture_fe_pass=False
        else:
            fe=[json.loads(p.read_text(encoding='utf8')) for p in paths]
            shifts=[r['maximum_radial_axis_shift_mm'] for r in fe]
            difference=abs(shifts[0]-shifts[1])/max(shifts)
            fixture_fe_pass=(difference<=.05 and all(r['linear_equilibrium_residual_N']<.001
                 and r['max_von_mises_MPa']<=f['carrier_post_minimum_yield_mpa']/1.5 for r in fe)
                 and moment<=170000 and mandrel_force<=5000 and heads<=2)
            fixture_fe=dict(cases=[str(p.relative_to(ROOT)) for p in paths],
                maximum_bulk_axis_shift_mm=max(shifts),spatial_relative_error=difference,
                model_E_MPa=180000,mesh_response_limit=.05,precision_design_pass=fixture_fe_pass)
            # Bulk solid FE already includes column, disk, solid reverse cone,
            # 170 kN mm pad bound and two-peener adverse loads. Add the actual
            # root connection flexibility, which is absent from that fixed-base FE.
            components={k:components[k] for k in ('bolt_root','flange_bending','flange_transverse_shear')}
            components['bulk_solid_FE']=max(shifts)
            components['microscopic_face_axis_allowance']=.00025
    else:
        raise ValueError('the sliding-core prototype is superseded; integral fixed cone required')
    checks=dict(fixture_solid_FE_precision_pass=fixture_fe_pass,
        column_covers_pad_radial_envelope=disk_overhang==0,
        radial_clamp_allocation_pass=sum(components.values())<=spec['precision']['radial_allocations_mm']['clamp_elastic_shift'],
        post_strength_pass=post_vm<=f['carrier_post_minimum_yield_mpa']/1.5,
        flange_strength_pass=6*bolt_bending_load*overhang/(strip_width*flange_h**2)<=f['carrier_post_minimum_yield_mpa']/1.5,
        preloaded_joint_remains_closed=bolt_max_delta<f['carrier_base_bolt_preload_n'],
        bolt_strength_pass=(f['carrier_base_bolt_preload_n']+bolt_max_delta)/bolt_area<=bolt_proof/1.5,
        bolt_head_post_clearance_pass=rb-f['carrier_base_bolt_head_envelope_mm']/2-r>=1.)
    return dict(scope=scope,units='N, mm, MPa',post_diameter_mm=2*r,effective_column_length_mm=L,
        post_second_moment_mm4=I,base_flange_diameter_mm=2*f['carrier_base_flange_radius_mm'],
        base_flange_thickness_mm=flange_h,bolts=dict(count=n,grade='8.8',diameter_mm=f['carrier_base_bolt_diameter_mm'],
            PCD_mm=2*rb,tensile_area_mm2=bolt_area,elastic_grip_mm=grip,preload_per_bolt_N=f['carrier_base_bolt_preload_n']),
        mandrel_lateral_force_design_N=mandrel_force,mandrel_lateral_root_lever_mm=mandrel_height,guide_body_z_mm=f['mandrel_lower_guide_z_mm'],pad_moment_N_mm=moment,peening_peak_moment_N_mm=impact_moment,peening_force_lever_bound_mm=impact_lever,combined_adverse_moment_N_mm=M,
        total_pad_force_N=load,radial_axis_deflection_components_mm=components,
        fixture_solid_FE=fixture_fe,total_radial_axis_deflection_mm=sum(components.values()),radial_clamp_allocation_mm=spec['precision']['radial_allocations_mm']['clamp_elastic_shift'],
        post_maximum_combined_normal_MPa=post_normal,post_maximum_von_mises_bound_MPa=post_vm,
        flange_strip_root_bending_MPa=6*bolt_bending_load*overhang/(strip_width*flange_h**2),
        largest_adverse_bolt_load_increment_N=bolt_max_delta,
        assumptions=['solid integral column, disk, neck and reverse cone; no shrink-fit or moving guide interface',
            'full post end translation and rotation included; no credit for pad tangential slip',
            f'flange per-bolt bending strip conservatively {strip_width:g} mm wide; other plate sectors omitted',
            'Timoshenko shear flexibility: flange kappa=5/6, circular post kappa=.9, nu=.30; radial peening force bounded by its full resultant',
            'all twelve bolts remain preloaded; rigid machine table; table motion checked during fixture-axis acceptance',
            'lateral mandrel resultant bounded by the full 5000 N compression sum; actual sampled vector is not treated as the full peak',
            'upper sleeve retracts upward off the fixed reverse cone; lower body is an integral steel part',
            'peak 200 N per peener, arbitrary force direction; full 3D root lever and simultaneous adverse bounds; no peening benefit in welding FE'],
        checks=checks,carrier_design_pass=all(checks.values()))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path);a=p.parse_args()
    result=evaluate(a.case)
    target=a.case/'carrier-verification.json' if a.case else ROOT/'output/review/carrier-design-envelope.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
