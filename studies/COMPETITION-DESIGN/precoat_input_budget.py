"""Finite first-layer input budgets: source, mass, heat and inherited chemistry.

This script does not solve fusion or assign an interface capacity. It keeps
engineering intervals and manufacturer values separate in the saved input.
"""
from pathlib import Path
import itertools
import json
import math
import numpy as np
import yaml
from scipy.integrate import solve_ivp
import gmsh

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studies/COMPETITION-DESIGN/results/precoat-input-budget.json'


def track_geometry(geometry,common):
    """Measure centreline arc extents in the actual retained first-layer CAD.

    z113.85 lies inside the flat first layer at both chosen radii. Its side
    boundary is the real wing planform, not the outer 18 mm weld arc.
    Radial bead width, curved-floor coverage and start/stop fusion remain
    separate requirements for the subsequent local model.
    """
    gmsh.initialize()
    try:
        gmsh.option.setNumber('General.Terminal',0)
        path=ROOT/'cad/generated/independent-precoat-curved/precoat-stack-R15-R08.brep'
        gmsh.model.occ.importShapes(str(path));gmsh.model.occ.synchronize()
        expected=geometry['material_volumes_mm3']['first_CI_A1']/8
        tags=[tag for dim,tag in gmsh.model.getEntities(3)
              if abs(gmsh.model.occ.getMass(dim,tag)-expected)<.001]
        if len(tags)!=8:raise RuntimeError('The eight first-layer CAD patches were not identified')
        records=[]
        for tag in tags:
            centre=gmsh.model.occ.getCenterOfMass(3,tag)
            direction=math.atan2(centre[1],centre[0])
            tracks=[]
            for radius in common['radial_track_centres_mm']:
                def inside(delta):
                    theta=direction+delta
                    return bool(gmsh.model.isInside(3,tag,
                        [radius*math.cos(theta),radius*math.sin(theta),113.85]))
                if not inside(0) or inside(.3) or inside(-.3):
                    raise RuntimeError('CAD track did not have the expected finite angular interval')
                ends=[]
                for sign in (-1,1):
                    low,high=0.,.3
                    for _ in range(38):
                        mid=(low+high)/2
                        if inside(sign*mid):low=mid
                        else:high=mid
                    ends.append(sign*(low+high)/2)
                tracks.append(dict(radius_mm=radius,angular_offsets_rad=ends,
                    arc_length_mm=radius*(ends[1]-ends[0])))
            records.append(dict(imported_first_layer_volume_tag=tag,wing_centre_angle_rad=direction,
                tracks=tracks,arc_length_sum_mm=sum(t['arc_length_mm'] for t in tracks)))
        return dict(source=str(path.relative_to(ROOT)),slice_z_mm=113.85,wings=records,
            all_wings_arc_length_mm=sum(row['arc_length_sum_mm'] for row in records),
            scope='Actual CAD centreline lengths only; no heat-source width, start/stop or fusion qualification.')
    finally:gmsh.finalize()


def run():
    config=yaml.safe_load((ROOT/'project/independent-precoat-candidates.yaml').read_text(encoding='utf8'))
    geometry=json.loads((ROOT/config['geometry_source']).read_text(encoding='utf8'))
    materials=yaml.safe_load((ROOT/'project/materials.yaml').read_text(encoding='utf8'))['materials']
    common=config['common']; mix=config['mixing_diagnostic']
    parent=materials['qt450_10']['composition_nominal_wt_pct']
    steel=materials['q235b']['composition_nominal_wt_pct']
    final_filler=materials['ernife_ci']['composition_nominal_wt_pct']
    bare=mix['bare_Ni99']
    keys=('C','Si','Mn','Ni')
    paths=track_geometry(geometry,common)
    length=paths['all_wings_arc_length_mm']/8
    results={}
    for name,candidate in config['candidates'].items():
        I=candidate['calculation_current_A']['nominal']; U=common['arc_voltage_V']['nominal']
        speed=common['travel_mm_s']['nominal']; eta=common['total_heat_efficiency']['nominal']
        arc_time=length/speed
        rate=candidate['deposited_mass_rate_g_s']['nominal']
        rates=candidate['deposited_mass_rate_g_s']['engineering_interval']
        # Total engineering retained power includes hot droplets. Subtract
        # their enthalpy before assigning the remainder to a spatial source.
        entering=[rate/1000*h for h in common['entering_deposit_enthalpy_J_kg']]
        matrix=[]
        for i,u,v,e,r,h in itertools.product(candidate['calculation_current_A']['engineering_interval'],
                common['arc_voltage_V']['engineering_interval'],common['travel_mm_s']['engineering_interval'],
                common['total_heat_efficiency']['engineering_interval'],rates,
                common['entering_deposit_enthalpy_J_kg']):
            matrix.append(dict(gross_J_mm=i*u/v,net_J_mm=e*i*u/v,
                remaining_source_W=e*i*u-r/1000*h,
                deposited_mass_g=r*length/v))
        compositions=[]
        for d1,d2,dn,ds in itertools.product(mix['QT_into_first'],mix['first_into_second'],
                mix['second_into_final'],mix['steel_into_final']):
            first={k:(1-d1)*candidate['typical_deposit_wt_pct'][k]+d1*parent[k] for k in keys}
            second={k:(1-d2)*bare[k]+d2*first[k] for k in keys}
            final={k:(1-dn-ds)*final_filler[k]+dn*second[k]+ds*steel[k] for k in keys}
            compositions.append(dict(d1=d1,d2=d2,dn=dn,ds=ds,first=first,second=second,final=final))
        ranges={stage:{k:[min(c[stage][k] for c in compositions),max(c[stage][k] for c in compositions)]
                       for k in keys} for stage in ('first','second','final')}
        retained_volume=geometry['material_volumes_mm3']['first_CI_A1']
        retained_mass=retained_volume*candidate['nominal_density_kg_m3']*1e-6
        results[name]=dict(input=candidate,track_count=2,requested_width_mm=3.5,
            path_length_per_wing_mm=length,arc_time_per_wing_s=arc_time,
            all_wings_first_layer_arc_time_s=arc_time*8,
            nominal_deposited_mass_per_wing_g=rate*arc_time,
            nominal_deposited_mass_all_wings_g=rate*arc_time*8,
            nominal_final_retained_first_mass_g=retained_mass,
            nominal_mean_volume_to_retained_volume_ratio=rate*arc_time*8/retained_mass,
            gross_line_energy_J_mm=I*U/speed,net_line_energy_J_mm=eta*I*U/speed,
            electrical_power_W=I*U,total_retained_power_W=eta*I*U,
            entering_deposit_power_range_W=entering,
            remaining_spatial_source_power_range_W=[eta*I*U-entering[1],eta*I*U-entering[0]],
            input_corner_ranges={key:[min(row[key] for row in matrix),max(row[key] for row in matrix)]
                                 for key in matrix[0]},
            positive_remaining_energy_at_all_input_corners=all(row['remaining_source_W']>0 for row in matrix),
            diagnostic_composition_ranges_wt_pct=ranges,diagnostic_composition_corners=compositions,
            geometry_coverage_is_a_requirement_not_fusion_evidence=True,
            ready_for_mass_and_energy_screen=True,ready_for_fusion_qualification=False)
    transfer=[]
    props=materials['qt450_10']['temperature_dependent']
    for target in common['oven_candidates_C']:
        folder=ROOT/f'simulation/competition-r4/results/design-precoat-warmup-{int(target)}-r12-dt30'
        state=json.loads((folder/'result.json').read_text(encoding='utf8'))
        history=np.genfromtxt(folder/'history.csv',delimiter=',',names=True)
        initial=float(history['mass_mean_C'][-1])
        for air_h in common['transfer_air_h_W_m2K']:
            def cooling(_,t):
                value=float(t[0]);ambient=common['transfer_ambient_C']
                heat_loss=(state['exposed_area_mm2']*1e-6*(air_h*(value-ambient)+
                    common['transfer_emissivity']*5.670374419e-8*((value+273.15)**4-(ambient+273.15)**4)))
                cp=np.interp(value,props['temperatures_c'],props['specific_heat_j_kgk'])
                return [-heat_loss/(state['pocketed_seat_mass_kg']*cp)]
            t=np.array([0.,15.,common['transfer_max_s']])
            solution=solve_ivp(cooling,(0,t[-1]),[initial],t_eval=t,rtol=1e-8,atol=1e-8)
            if not solution.success:raise RuntimeError(solution.message)
            transfer.append(dict(oven_C=target,source=str(folder.relative_to(ROOT)),
                air_h_W_m2K=air_h,time_s=t.tolist(),mean_C=solution.y[0].tolist(),
                scope='Lumped mean-temperature energy budget, free-air surfaces only. Not a minimum nodal temperature, support-contact bound or full transfer FE.'))
    result=dict(date='2026-10-06',inputs=config,track_geometry=paths,candidates=results,transfer=transfer,
        scope='Source-grounded pWPS input budgets; intervals include stated engineering assumptions. No fusion, transport dilution, PMZ or manufacturing qualification assigned.',
        first_interface_continuous_fusion_pass=False)
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    r=run()
    print(json.dumps({k:{field:row[field] for field in ('gross_line_energy_J_mm','net_line_energy_J_mm',
        'all_wings_first_layer_arc_time_s','nominal_deposited_mass_all_wings_g',
        'positive_remaining_energy_at_all_input_corners','diagnostic_composition_ranges_wt_pct')}
        for k,row in r['candidates'].items()},ensure_ascii=False,indent=2))
    print('Transfer mean temperatures:',r['transfer'])
