"""Manufacturing size chain from actual cold fields, including finite honing.

The 40.006/40.008 endpoints are recomputed FE geometries. No old result is
renamed or shifted into an alleged new simulation. The small interval uses
the measured endpoint response difference as a conservative interpolation
allowance; full spatial/time verification remains a separate requirement.
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
    final=fit_position_diameter(a,b,moved);final.update(section_axis_envelope(a,b,moved))
    final['position_diameter_mm']=max(final['position_diameter_mm'],final['section_axis_envelope_diameter_mm'])
    return dict(maximum_local_radial_stock_mm=float(stock.max()),final_sampled_fit=final,
                scope='nominal selective removal to tool diameter40.001 about the existing fitted axis; not measured data')


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
    fields=('sampled_bore_two_point_diameter_min_mm','sampled_bore_two_point_diameter_max_mm')
    response_change=max(abs((lower['fit'][k]-li['initial_bore_diameter_mm'])-
                            (upper['fit'][k]-ui['initial_bore_diameter_mm'])) for k in fields)
    allowance=response_change+.0001
    # Completed fields stop below20.5 C. Diameter inspection is at20±0.2 C;
    # bound the entire possible cooling to20 C using alpha<=12.5e-6/K.
    reference_temperature_allowance=40*12.5e-6*.5
    minimum=40.006+min(r['fit'][fields[0]]-40.008 for r in upper_rows)-allowance-reference_temperature_allowance
    maximum=max(r['fit'][fields[1]] for r in upper_rows)+allowance+reference_temperature_allowance
    finish=finish_geometry(lower)
    # Expanded uncertainty is a method qualification target, not the gauge
    # resolution. Manufacturer repeatability is treated as a bounded input.
    u_components_um=dict(repeatability_bound=.25/math.sqrt(3),reference_ring=.20/2,
                         resolution=.10/math.sqrt(12),residual_temperature=40*11.5e-3*.2/math.sqrt(3),
                         alignment=.05,local_linearity=.05)
    calculated_U=2*math.sqrt(sum(v*v for v in u_components_um.values()))/1000
    U=.0005;target_measured=40.0010
    required_stock=max(0,target_measured-(minimum-U))
    removal_diameter_limit=.006
    # Short-bore centre change must be budgeted. For the 12 equispaced points,
    # outward radial removal 0..3 um gives a first-harmonic centre bound below
    # 1.94 um. The fitted endpoint weights (5/6,1/3,-1/6) enlarge that by 4/3.
    # A 6 um position-diameter allowance includes this 5.16 um bound and the
    # small nonlinear-circle correction; no axis correction is credited.
    centre_bound=2/12*(removal_diameter_limit/2)/math.sin(math.pi/12)
    endpoint_position_bound=2*centre_bound*4/3
    honing_position_allowance=.006
    post_position=verification['position_budget_mm']+honing_position_allowance
    def response_error(i,j,k):
        a=upper_rows[i]['fit'][k]-40.008;b=upper_rows[j]['fit'][k]-40.008
        return abs(a-b)/max(abs(a),abs(b),1e-12)
    size_errors={kind:{k:response_error(i,j,k) for k in fields}
                 for kind,i,j in [('spatial',0,1),('temporal',0,2)]}
    checks=dict(endpoint_inputs_match_except_bore=matching,
        endpoint_cold_release_pass=all(r.get('cold_shell_clamp_release',{}).get('free_shell_release_pass',False) for r in (lower,upper)),
        endpoint_sensitivity_small=response_change<=.0002,
        declared_diameter_uncertainty_budget_pass=calculated_U<=U,
        upper_size_with_guard_pass=maximum+U<=40.025,
        limited_honing_stock_pass=required_stock<=removal_diameter_limit,
        nominal_local_radial_stock_pass=finish['maximum_local_radial_stock_mm']+(allowance+reference_temperature_allowance)/2<=removal_diameter_limit/2,
        nominal_selective_finish_size_pass=finish['final_sampled_fit'][fields[0]]>=40.0005 and finish['final_sampled_fit'][fields[1]]+U<=40.025,
        short_bore_axis_change_bound_pass=endpoint_position_bound+.0002<=honing_position_allowance,
        final_position_budget_pass=post_position<=.05,
        size_spatial_and_time_precision_pass=all(v<=.05 for z in size_errors.values() for v in z.values()),
        position_precision_and_welded_axis_pass=verification['position_design_pass'])
    return dict(scope=pending['scope'],manufacturing_window_mm=[40.006,40.008],endpoint_cases=[LOWER,UPPER],
        endpoint_response_change_mm=response_change,interpolation_allowance_mm=allowance,
        reference_temperature_diameter_allowance_mm=reference_temperature_allowance,
        cold_diameter_envelope_before_finish_mm=[minimum,maximum],
        nominal_selective_finish=finish,
        diameter_uncertainty_components_standard_um=u_components_um,
        calculated_expanded_diameter_uncertainty_mm=calculated_U,
        diameter_method_expanded_uncertainty_limit_mm=U,
        maximum_required_diameter_stock_mm=required_stock,maximum_allowed_diameter_stock_mm=removal_diameter_limit,
        honing_measured_lower_target_mm=target_measured,minimum_measured_final_diameter_mm=40.0005,
        maximum_measured_final_diameter_mm=40.0245,
        short_bore_axis_position_bound_mm=endpoint_position_bound,
        honing_position_allowance_mm=honing_position_allowance,post_finish_position_budget_mm=post_position,
        size_response_relative_errors=size_errors,checks=checks,
        qualification='comparative bore gauge with diameter extension and traceable reference ring; 20±0.2 C; validate method U<=0.5 um; CMM before and after optional short-bore honing; no heavy rebore or axis correction',
        bore_size_design_pass=all(checks.values()))


if __name__=='__main__':
    verification=json.loads((OUT/'verification.json').read_text(encoding='utf8'))
    result=evaluate(verification)
    (OUT/'bore-size-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
