"""Read saved manufacturing evidence and independently check revision arithmetic."""
from pathlib import Path
import json
import math
import yaml
from scipy.optimize import brentq

ROOT=Path(__file__).resolve().parents[2]


def run():
    spec=yaml.safe_load((ROOT/'project/competition-design.yaml').read_text(encoding='utf8'))
    current=spec['postweld_drain']
    family=json.loads((ROOT/'simulation/competition-r4/results/design-repair-status-20261005.json').read_text(encoding='utf8'))
    records=family['records']; by_name={r['case']:r for r in records}
    cases=family['current_case_family']['cases']; base,space,time=[by_name[name] for name in cases]
    position=lambda row:row['position_mm']*1000
    spread=(time['bore_max_mm']-time['bore_min_mm'])*1000
    # Find the flow from the dimensional pressure-loss expression rather
    # than reusing the production closed-form quadratic implementation.
    d=current['inside_diameter_min_mm']/1000; area=math.pi*d*d/4
    def loss(q):
        velocity=q/area
        return 32*current['newtonian_viscosity_max_Pa_s']*current['line_length_max_m']*velocity/d**2+current['local_loss_K_max']*current['density_kg_m3']*velocity**2/2
    flows=[]
    for pressure in (1800.,2000.,current['net_differential_pressure_min_Pa']):
        q=brentq(lambda flow:loss(flow)-pressure,0.,1e-4,xtol=1e-16)
        flows.append(dict(net_pressure_Pa=pressure,flow_ml_min=q*60e6,pressure_residual_Pa=loss(q)-pressure))
    f=current['fault_containment']
    area_min=math.pi*(f['cup_inside_diameter_mm']-f['cup_inside_diameter_tolerance_mm'])**2/4
    capacity=area_min*(f['cup_liquid_depth_mm']-f['cup_liquid_depth_tolerance_mm'])/1000-f['tool_displacement_max_ml']
    pipe=math.pi*current['inside_diameter_max_mm']**2/4*f['return_wet_length_max_m']
    required=pipe+sum(f[k] for k in ('operating_inventory_max_ml','fittings_and_upper_tool_drainback_max_ml','supply_downstream_of_shutoff_max_ml','reserve_ml'))+current['supply_limit_ml_min']/60*f['shutdown_latency_max_s']
    old_capacity=(math.pi*22**2*10-3000)/1000
    old_required=math.pi*4**2/4+0.1+2
    p=spec['precision']; fxt=spec['fixture']
    support_radial=p['bore_length_mm']*2*p['support_height_spread_limit_mm']/(3*fxt['support_radius_mm'])
    nonthermal_um=2000*(sum(v for k,v in p['radial_allocations_mm'].items() if k!='thermal_residual_target')+support_radial)
    thermal_target_um=2000*p['radial_allocations_mm']['thermal_residual_target']
    uncertainty_um=1000*p['measurement_expanded_uncertainty_diameter_target_mm']
    honing_um=1000*p['honing_axis_allocation_diameter_mm']
    output=dict(date='2026-10-06',reviewed_commit='b9053c8',
        attachment_use='Attachment statements are hypotheses; arithmetic reads current configuration and saved raw-family records.',
        old_manufacturing=dict(source='simulation/competition-r4/results/design-repair-status-20261005.json',
            spatial_response_difference_pct=100*abs(position(base)-position(space))/max(position(base),position(space)),
            temporal_response_difference_pct=100*abs(position(base)-position(time))/max(position(base),position(time)),
            worst_listed_position_um=max(position(r) for r in records),
            worst_full_budget_um=28+2+6.5+max(position(r) for r in records),
            temporal_bore_spread_um=spread,target_window_um=25.,guarded_measured_window_um=24.,
            accepted=False),
        old_return_counterexample=dict(cup_ml=old_capacity,requirement_ml=old_required,deficit_ml=old_required-old_capacity),
        revised_drain=dict(independent_flow_roots=flows,maximum_full_pipe_return_ml=pipe,
            minimum_cup_capacity_ml=capacity,required_ml=required,margin_ml=capacity-required),
        revised_precision_budget=dict(nonthermal_um=nonthermal_um,thermal_target_um=thermal_target_um,
            uncertainty_um=uncertainty_um,honing_um=honing_um,
            full_target_budget_um=nonthermal_um+thermal_target_um+uncertainty_um+honing_um,
            thermal_allowance_with_honing_um=50-nonthermal_um-uncertainty_um-honing_um,
            thermal_allowance_without_removal_um=50-nonthermal_um-uncertainty_um,
            manufacturing_pass_assigned=False),
        scope='Arithmetic and saved-evidence review; no new welding FE or measured results.')
    out=ROOT/'studies/COMPETITION-DESIGN/results/independent-revision-audit.json'
    out.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf8')
    return output


if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,indent=2))
