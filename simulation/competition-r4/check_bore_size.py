"""Manufacturing size chain from actual cold fields, including finite honing.

The 40.006/40.008 endpoints are recomputed FE geometries. Both axes and
their numerical qualifications are required. Endpoint response differences
are sensitivity observations, not a conservative bound on interval interiors.
"""
from pathlib import Path
import json,math
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent/'results'
LOWER='8p-bore006-h15-dt025-s05'
UPPER='8p-bore008-h15-dt025-s05'


def finish_geometry(row):
    """Nominal outward-only selective finishing about the existing bore axis.

    This is a geometric stock-removal calculation, not a honing-machine FE
    or a measured finished part. The independent centre-change allowance and
    before/after inspection remain mandatory.
    """
    from postprocess import section_axis_envelope
    from hanjie.simulation.structural_prep import fit_position_diameter
    fit=row['fit'];samples=row['measurement_samples_mm']
    a=np.array(samples['datum_A']);b=np.array(samples['datum_B']);hole=np.array(samples['bore'])
    frame=np.array(fit['datum_frame']);origin=np.array(fit['datum_A_origin_mm'])
    local=(hole-origin)@frame
    local[:,:2]-=np.array(fit['datum_B_center_in_A_frame_mm'])+np.array(fit['bore_axis_center_in_datum_frame_mm'])
    local[:,2]-=fit['bore_axis_z_reference_mm']
    axis=np.array([*fit['bore_axis_slopes'],1.]);axis/=np.linalg.norm(axis)
    radial=local-np.outer(local@axis,axis);r=np.linalg.norm(radial,axis=1)
    stock=np.maximum(0,20.0005-r)
    moved=hole+(radial/np.maximum(r[:,None],1e-12)*stock[:,None])@frame.T
    protocol=row['measurement_sampling']['selected_protocol']
    final=fit_position_diameter(a,b,moved)
    final.update(section_axis_envelope(a,b,moved,protocol['section_count'],protocol['angular_count']))
    final['position_diameter_mm']=max(final['position_diameter_mm'],final['section_axis_envelope_diameter_mm'])
    return dict(maximum_local_radial_stock_mm=float(stock.max()),final_sampled_fit=final,
                scope='nominal selective removal to tool diameter40.001 about the existing fitted axis; not measured data')


def honing_axis_bound(row,radial_stock):
    """First-order centre and line-fit bound for this actual sampling protocol.

    Any outward radial removal 0..s has first-harmonic centre amplitude
    <=2*s/(N*sin(pi/N)). Least-squares endpoint weights are recomputed for
    all axial sections; the three-section 4/3 factor is not reused.
    """
    protocol=row['measurement_sampling']['selected_protocol']
    n=protocol['angular_count'];nz=protocol['section_count']
    z=np.linspace(-1,1,nz);design=np.c_[np.ones(nz),z]
    weights=np.array([[1,-1],[1,1]])@np.linalg.pinv(design)
    centre=2*radial_stock/(n*math.sin(math.pi/n))
    amplification=float(np.sum(abs(weights),axis=1).max())
    return dict(angular_count=n,section_count=nz,first_harmonic_centre_bound_mm=centre,
                axial_endpoint_weight_L1=amplification,
                first_order_position_diameter_bound_mm=2*centre*amplification,
                nonlinear_circle_reserve_mm=.0002)


def endpoint_quality(case,row,inp):
    """Check the lower endpoint itself; upper-family booleans do not replace it."""
    def read(name):
        path=OUT/case/name
        return json.loads(path.read_text(encoding='utf8')) if path.exists() else {}
    birth=read('birth-continuation-verification.json');pad=read('pad-contact-audit.json')
    event=read('mechanical-integration-audit.json')
    from check_carrier import evaluate as carrier_check
    carrier=carrier_check(OUT/case) if pad else {}
    fixture={}
    if inp.get('fixture_thermal') and (OUT/case/'fixture-boundary-trace.npz').exists():
        from check_fixture_thermal import evaluate as fixture_check
        fixture=fixture_check(case)
    return dict(cold_free_equilibrium=bool(row.get('released') and row.get('final_max_C',999)<=21
        and row.get('max_equilibrium_residual_N',999)<.05 and abs(row.get('energy_balance_relative',1))<1e-5
        and row.get('cold_shell_clamp_release',{}).get('free_shell_release_pass',False)),
        birth=bool(birth.get('rigid_motion_patch_pass') and inp['interface_patch']['rigid_translation_and_rotation_patch_pass']),
        support=bool(pad.get('analytic_geometry_contact_checks_pass') and pad.get('compression_only_reactions_pass')
            and pad.get('maximum_pressure_MPa',999)<=355/1.5 and carrier.get('carrier_design_pass')),
        thermal_events=bool(event and all(v==0 for v in event['missed_above_annealing_mm3'].values())),
        thermal_limits=bool(row.get('seal_thermal_limits_pass') and row.get('max_mandrel_reaction_N',99999)<=5000),
        sampling=bool(row.get('measurement_sampling',{}).get('sampling_stability_pass')),
        fixture=bool(fixture.get('fixture_thermal_discretization_pass') and fixture.get('support_thermal_height_budget_pass')))


def lower_discretization(case,row,inp,comparison_cases=None):
    """Recompute response differences from completed lower-bore fields."""
    comparisons=(comparison_cases[1:] if comparison_cases is not None else
        [case.replace('h15-dt025-s05','h1125-dt025-s05'),
         case.replace('h15-dt025-s05','h15-dt0125-s025')])
    pending=dict(comparison_cases=[case,*comparisons],spatial_and_time_response_difference_pass=False,
                 reason='completed manufacturing-lower spatial/time fields are required; upper-endpoint precision is not inherited')
    if len(comparisons)!=2 or len(set([case,*comparisons]))!=3:
        return {**pending,'reason':'three distinct actual lower-endpoint space/time cases are required; repeated base fields are not refinement'}
    if any(not (OUT/c/'free-release-fields.npz').exists() for c in comparisons):return pending
    from postprocess import measure
    rows=[row];inputs=[inp];quality=[]
    for name in comparisons:
        rr,_,ii=measure(OUT/name,free_shell=True);rows.append(rr);inputs.append(ii)
        quality.append(endpoint_quality(name,rr,ii))
    keys=('materials','fusion_enthalpy_model','stage_sequence','seat_geometry','initial_bore_diameter_mm',
          'travel_mm_s','net_W','root_leg_mm','leg_mm','source_r_mm','source_radius_mm','source_depth_mm',
          'copper_water_model','fixture_thermal','fixture_thermal_coupling_policy','mandrel_penalty_N_mm3',
          'initial_radial_preload_N','copper_contact_W_m2K','weld_mesh_mm','Ni99_thin_layer_mm','annealing_C')
    identical=all(all(ii.get(k)==inp.get(k) for k in keys) for ii in inputs)
    spatial_steps_same=all(inputs[0].get(k)==inputs[1].get(k) for k in
                          ('dt_s','structural_step_s','cold_structural_step_s','mechanical_event_temperature_increment_C'))
    with np.load(OUT/case/'mesh.npz') as base,np.load(OUT/comparisons[1]/'mesh.npz') as fine:
        temporal_mesh_same=np.array_equal(base['x'],fine['x']) and np.array_equal(base['e'],fine['e'])
    metrics=('position_diameter_mm','sampled_bore_two_point_diameter_min_mm','sampled_bore_two_point_diameter_max_mm')
    differences={}
    for name,index in [('spatial',1),('temporal',2)]:
        differences[name]={}
        for key in metrics:
            a=rows[0]['fit'][key];b=rows[index]['fit'][key]
            if key!='position_diameter_mm':a-=inp['initial_bore_diameter_mm'];b-=inp['initial_bore_diameter_mm']
            differences[name][key]=abs(a-b)/max(abs(a),abs(b),1e-12)
    passed=bool(identical and spatial_steps_same and temporal_mesh_same and
                all(all(q.values()) for q in quality) and all(v<=.05 for group in differences.values() for v in group.values()))
    return dict(comparison_cases=[case,*comparisons],physics_identical=identical,
        spatial_steps_identical=spatial_steps_same,temporal_mesh_identical=bool(temporal_mesh_same),
        response_relative_differences=differences,comparison_quality=quality,
        spatial_and_time_response_difference_pass=passed,records=rows)


def evaluate(verification):
    upper_rows=verification['records']
    UPPER=verification['cases'][0]
    LOWER=UPPER.replace('bore008','bore006')
    if LOWER==UPPER:
        return dict(bore_size_design_pass=False,reason='explicit bore008/bore006 endpoint identity required')
    inputs=[json.loads((OUT/case/'input.json').read_text(encoding='utf8')) for case in verification['cases']]
    pending=dict(bore_size_design_pass=False,scope='manufacturing size-chain verification, not a measured honing result')
    if not all(abs(inp['initial_bore_diameter_mm']-40.008)<1e-8 for inp in inputs):
        return {**pending,'reason':'the current three-mesh family is not the proposed 40.008 manufacturing upper endpoint'}
    if not (OUT/LOWER/'measurement.json').exists() or not (OUT/UPPER/'measurement.json').exists():
        return {**pending,'reason':'both actual cold and completely released manufacturing endpoint runs are required'}
    lower=json.loads((OUT/LOWER/'measurement.json').read_text(encoding='utf8'))
    upper=json.loads((OUT/UPPER/'measurement.json').read_text(encoding='utf8'))
    li=json.loads((OUT/LOWER/'input.json').read_text(encoding='utf8'))
    ui=json.loads((OUT/UPPER/'input.json').read_text(encoding='utf8'))
    keys=('materials','fusion_enthalpy_model','stage_sequence','seat_geometry','h_mm','dt_s',
          'structural_step_s','cold_structural_step_s','mechanical_event_temperature_increment_C',
          'source_r_mm','source_radius_mm','source_depth_mm','copper_water_model','mandrel_penalty_N_mm3')
    matching=all(li[k]==ui[k] for k in keys) and li.get('fixture_thermal')==ui.get('fixture_thermal')
    matching=matching and all(li.get(k)==ui.get(k) for k in ('paired_opposed_sources','maximum_simultaneous_heads',
        'net_W_per_head','travel_mm_s','net_W','root_leg_mm','leg_mm','initial_radial_preload_N',
        'stress_free_birth','stress_free_interface_birth','fixture_thermal_coupling_policy','unilateral_pads',
        'copper_contact_W_m2K','copper_water_inlet_C','fixture_cooling_removed_on_release',
        'weld_mesh_mm','annealing_C','Ni99_thin_layer_mm','Ni99_conductivity_W_mK'))
    matching=matching and abs(li['initial_bore_diameter_mm']-40.006)<1e-8
    if not all(r.get('measurement_sampling',{}).get('sampling_stability_pass') for r in [lower,*upper_rows]):
        return {**pending,'reason':'all manufacturing endpoint fields require dense/phase sampling qualification'}
    fields=('sampled_bore_two_point_diameter_min_mm','sampled_bore_two_point_diameter_max_mm')
    response_change=max(abs((lower['fit'][k]-li['initial_bore_diameter_mm'])-
                            (upper['fit'][k]-ui['initial_bore_diameter_mm'])) for k in fields)
    allowance=response_change+.0001
    # Completed fields stop below20.5 C. Diameter inspection is at20±0.2 C;
    # bound the entire possible cooling to20 C using alpha<=12.5e-6/K.
    reference_temperature_allowance=40*12.5e-6*.5
    lower_comparisons=[case.replace('bore008','bore006') for case in verification['cases']]
    lower_precision=lower_discretization(LOWER,lower,li,lower_comparisons)
    endpoint_rows=[*lower_precision.get('records',[lower]),*upper_rows]
    minimum=min(r['fit'][fields[0]] for r in endpoint_rows)-allowance-reference_temperature_allowance
    maximum=max(r['fit'][fields[1]] for r in endpoint_rows)+allowance+reference_temperature_allowance
    finishes=[finish_geometry(row) for row in endpoint_rows];finish=finishes[0]
    # Expanded uncertainty is a method qualification target, not the gauge
    # resolution. Manufacturer repeatability is treated as a bounded input.
    u_components_um=dict(repeatability_bound=.25/math.sqrt(3),reference_ring=.20/2,
                         resolution=.10/math.sqrt(12),residual_temperature=40*11.5e-3*.2/math.sqrt(3),
                         alignment=.05,local_linearity=.05)
    calculated_U=2*math.sqrt(sum(v*v for v in u_components_um.values()))/1000
    U=.0005;target_measured=40.0010
    required_stock=max(0,target_measured-(minimum-U))
    removal_diameter_limit=.006
    bounds=[honing_axis_bound(row,removal_diameter_limit/2) for row in endpoint_rows]
    endpoint_position_bound=max(bound['first_order_position_diameter_bound_mm'] for bound in bounds)
    honing_position_allowance=.0065
    raw_axis=max(row['fit']['position_diameter_mm'] for row in endpoint_rows)
    nominal_finished_axis=max(item['final_sampled_fit']['position_diameter_mm'] for item in finishes)
    # The allowance already covers all permitted stock-removal patterns,
    # including the nominal geometric finish. Do not add its centre movement
    # a second time. Neither pre- nor post-finish endpoint can escape the gate.
    position_base=max(raw_axis,nominal_finished_axis-honing_position_allowance)
    post_position=.028+.002+position_base+honing_position_allowance
    lower_quality=endpoint_quality(LOWER,lower,li)
    # A full non-linear manufacturing interval needs a separate quantitative
    # audit. A 0.1 um increment over two endpoint differences is not that audit.
    interval_path=OUT/'manufacturing-interval-verification.json'
    interval=json.loads(interval_path.read_text(encoding='utf8')) if interval_path.exists() else {}
    numerical_bounds=interval.get('numerical_bounds',{})
    bound_keys=('minimum_diameter_mm','maximum_diameter_mm','maximum_raw_position_mm',
        'maximum_nominal_finished_position_mm','maximum_nominal_radial_stock_mm')
    valid_numbers=all(isinstance(numerical_bounds.get(k),(int,float)) and
        not isinstance(numerical_bounds.get(k),bool) and math.isfinite(numerical_bounds[k]) for k in bound_keys)
    valid_numbers=bool(valid_numbers and numerical_bounds.get('minimum_diameter_mm',1)>0 and
        numerical_bounds.get('minimum_diameter_mm',1)<=numerical_bounds.get('maximum_diameter_mm',0))
    # Stored records are recomputed by the interval audit. Validate their actual
    # inputs and metrology, rather than trusting nonempty names/booleans.
    interior_rows=interval.get('records',[])
    interval_inputs=interval.get('inputs',[])
    interval_physics=bool(interval_inputs) and len(interior_rows)==len(interval_inputs) and all(
        all(ii.get(k)==ui.get(k) for k in interval.get('physics_keys',[])) for ii in interval_inputs)
    interval_physics=interval_physics and bool(interval.get('physics_keys')) and all(
        r.get('cold_shell_clamp_release',{}).get('free_shell_release_pass') and
        r.get('measurement_sampling',{}).get('sampling_stability_pass') for r in interior_rows)
    interval_pass=bool(interval.get('endpoint_cases')==[LOWER,UPPER]
        and interval.get('contact_and_plastic_path_checks_pass')
        and interval.get('response_envelope_validation_pass')
        and interval.get('response_bound_basis') and interval.get('interior_cases')
        and valid_numbers and interval_physics)
    if valid_numbers:
        minimum=min(minimum,numerical_bounds['minimum_diameter_mm']-reference_temperature_allowance)
        maximum=max(maximum,numerical_bounds['maximum_diameter_mm']+reference_temperature_allowance)
        raw_axis=max(raw_axis,numerical_bounds['maximum_raw_position_mm'])
        nominal_finished_axis=max(nominal_finished_axis,numerical_bounds['maximum_nominal_finished_position_mm'])
    required_stock=max(0,target_measured-(minimum-U))
    no_honing_size_pass=minimum-U>=40.000 and maximum+U<=40.025
    finishing_branch='direct_size_no_honing' if no_honing_size_pass else 'limited_honing_required'
    # Optional stock removal is prohibited on the direct-size branch. A bore
    # requiring size recovery can never use the looser 20 um axis allowance.
    selected_honing_allowance=0. if no_honing_size_pass else honing_position_allowance
    position_base=max(raw_axis,nominal_finished_axis-honing_position_allowance) if not no_honing_size_pass else raw_axis
    post_position=.028+.002+position_base+selected_honing_allowance
    interval_stock_pass=bool(valid_numbers and numerical_bounds['maximum_nominal_radial_stock_mm']+
        reference_temperature_allowance/2<=removal_diameter_limit/2)
    def response_error(i,j,k):
        a=upper_rows[i]['fit'][k]-40.008;b=upper_rows[j]['fit'][k]-40.008
        return abs(a-b)/max(abs(a),abs(b),1e-12)
    size_errors={kind:{k:response_error(i,j,k) for k in fields}
                 for kind,i,j in [('spatial',0,1),('temporal',0,2)]}
    checks=dict(endpoint_inputs_match_except_bore=matching,
        lower_endpoint_quality_pass=all(lower_quality.values()),
        lower_endpoint_discretization_pass=bool(lower_precision.get('spatial_and_time_response_difference_pass')
            and lower_precision.get('comparison_cases') and lower_precision.get('physics_identical')),
        manufacturing_interval_bound_pass=interval_pass,
        endpoint_cold_release_pass=all(r.get('cold_shell_clamp_release',{}).get('free_shell_release_pass',False) for r in endpoint_rows),
        endpoint_sensitivity_small=response_change<=.0002,
        declared_diameter_uncertainty_budget_pass=calculated_U<=U,
        upper_size_with_guard_pass=maximum+U<=40.025,
        limited_honing_stock_pass=required_stock<=removal_diameter_limit,
        nominal_local_radial_stock_pass=no_honing_size_pass or (interval_stock_pass and all(item['maximum_local_radial_stock_mm']+(allowance+reference_temperature_allowance)/2<=removal_diameter_limit/2 for item in finishes)),
        nominal_selective_finish_size_pass=no_honing_size_pass or all(item['final_sampled_fit'][fields[0]]>=40.0005 and item['final_sampled_fit'][fields[1]]+U<=40.025 for item in finishes),
        short_bore_axis_change_bound_pass=endpoint_position_bound+.0002<=honing_position_allowance,
        nominal_finish_within_axis_bound_pass=nominal_finished_axis<=raw_axis+honing_position_allowance,
        welded_endpoints_position_budget_pass=.028+.002+raw_axis<=.05,
        final_position_budget_pass=post_position<=.05,
        size_spatial_and_time_precision_pass=all(v<=.05 for z in size_errors.values() for v in z.values()),
        position_precision_and_welded_axis_pass=verification['position_design_pass'])
    return dict(scope=pending['scope'],manufacturing_window_mm=[40.006,40.008],endpoint_cases=[LOWER,UPPER],
        endpoint_response_change_mm=response_change,interpolation_allowance_mm=allowance,
        interpolation_allowance_scope='endpoint sensitivity estimate only; interval validation remains independently required',
        reference_temperature_diameter_allowance_mm=reference_temperature_allowance,
        cold_diameter_envelope_before_finish_mm=[minimum,maximum],
        nominal_selective_finish=finish,nominal_selective_finish_all_endpoints=finishes,
        lower_endpoint_quality=lower_quality,lower_endpoint_discretization=lower_precision,
        manufacturing_interval_verification=interval,
        interval_numerical_bounds_consumed=numerical_bounds if valid_numbers else {},
        finishing_branch=finishing_branch,direct_size_no_honing_pass=no_honing_size_pass,
        selected_honing_position_allowance_mm=selected_honing_allowance,
        selected_welding_position_limit_mm=.020-selected_honing_allowance,
        diameter_uncertainty_components_standard_um=u_components_um,
        calculated_expanded_diameter_uncertainty_mm=calculated_U,
        diameter_method_expanded_uncertainty_limit_mm=U,
        maximum_required_diameter_stock_mm=required_stock,maximum_allowed_diameter_stock_mm=removal_diameter_limit,
        honing_measured_lower_target_mm=target_measured,minimum_measured_final_diameter_mm=40.0005,
        maximum_measured_final_diameter_mm=40.0245,
        short_bore_axis_position_bound_mm=endpoint_position_bound,
        short_bore_axis_bound_protocols=bounds,worst_welded_endpoint_axis_mm=raw_axis,
        worst_nominal_finished_endpoint_axis_mm=nominal_finished_axis,
        honing_position_allowance_mm=honing_position_allowance,post_finish_position_budget_mm=post_position,
        size_response_relative_errors=size_errors,checks=checks,
        qualification='comparative bore gauge with diameter extension and traceable reference ring; 20±0.2 C; validate method U<=0.5 um; CMM before and after optional short-bore honing; no heavy rebore or axis correction',
        bore_size_design_pass=all(checks.values()))


if __name__=='__main__':
    verification=json.loads((OUT/'verification.json').read_text(encoding='utf8'))
    result=evaluate(verification)
    (OUT/'bore-size-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
