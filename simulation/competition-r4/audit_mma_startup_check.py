"""Audit the three frozen startup cases and the actual pWPS/CAD interface."""
import argparse,json
from pathlib import Path
import numpy as np
import yaml
from mma_literature_profile import ROOT
from mma_conservative_birth import clipped_moments

BASE=ROOT/'simulation/competition-r4/results/mma-startup-20261007'
CASES=['aggregate-h065-dt0125','aggregate-h065-dt00625','aggregate-h045-dt0125']


def audit(base=BASE,cases=CASES,stop_time=None):
    # Exact geometric cases exercise all three nontrivial tetrahedron cuts.
    expected=[([0.,1.,1.,1.],[.078125,.015625,.015625,.015625]),
              ([0.,0.,0.,1.],[.234375,.234375,.234375,.171875]),
              ([0.,0.,1.,1.],[.171875,.171875,.078125,.078125])]
    for values,answer in expected:
        np.testing.assert_allclose(clipped_moments(np.array(values),.5),answer,atol=1e-14)
    rows=[]
    for name in cases:
        folder=base/name
        source=json.loads((folder/'input.json').read_text())
        result=json.loads((folder/'result.json').read_text())
        history=np.loadtxt(folder/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
        mass=np.loadtxt(folder/'deposition-history.csv',delimiter=',',skiprows=1,ndmin=2)
        heat=np.loadtxt(folder/'source-partition-history.csv',delimiter=',',skiprows=1,ndmin=2)
        prefix=stop_time is not None and result['time_s']>stop_time+1e-9
        if stop_time is not None:
            history=history[history[:,0]<=stop_time+1e-9];mass=mass[mass[:,0]<=stop_time+1e-9];heat=heat[heat[:,0]<=stop_time+1e-9]
        with np.load(folder/'thermal-fields.npz') as field:
            present=np.unique(field['e'][field['thermal_active']])
            minimum=float(field['temperature'][present].min())
            coverage=result['actual_area_above_both_solidus_mm2']
            if prefix:
                chunks=json.loads((folder/'nodal-thermal-history/manifest.json').read_text())['chunks']
                temp=[];fronts=[];fractions=[]
                for chunk in chunks:
                    if chunk['first_s']>stop_time+1e-9:continue
                    with np.load(folder/'nodal-thermal-history'/chunk['file']) as trace:
                        mask=trace['time_s']<=stop_time+1e-9
                        temp.extend(trace['temperature_C'][mask]);fronts.extend(trace['front_level_rad'][mask]);fractions.extend(trace['deposit_fraction'][mask])
                temp=np.array(temp);fronts=np.array(fronts)
                active=field['material']==1;active[active==False]=np.array(fractions[-1])>1e-14
                present=np.unique(field['e'][active]);minimum=float(temp[-1,present].min())
                from mma_conservative_birth import ConservativeBirth
                state=ConservativeBirth(field['x'],field['e'],field['material'],field['volume_mm3'],np.ones(len(field['e'])),source['tracks'][0]['radius_mm'],source['source_width_mm'])
                faces=field['interface_nodes'];bary=np.full((3,3),1/6);np.fill_diagonal(bary,2/3)
                qp_phi=state.nodal_values[faces]@bary.T
                qp_T=temp[:,faces]@bary.T
                qp_peak=np.where(qp_phi[None,:,:]<=fronts[:,None,None],qp_T,20.).max(axis=0)
                coverage=float(np.sum(field['interface_area_mm2']*np.mean(qp_peak>=result['both_solidus_threshold_C'],axis=1)))
        row=dict(case=name,time_s=float(history[-1,0]),peak_C=float(history[:,4].max()),
            QT_peak_C=float(history[:,5].max()),active_final_minimum_C=minimum,
            interface_thermal_coverage_mm2=coverage,
            path_count=len(source['tracks']),path_length_mm=sum(t['length_mm'] for t in source['tracks']),
            full_arc_duration_s=sum(t['arc_duration_s'] for t in source['tracks']),
            target_cumulative_g=float(mass[-1,4]),actual_cumulative_g=float(mass[-1,5]),
            maximum_step_mass_error_g=float(np.max(np.abs(mass[:,2]-mass[:,3]))),
            maximum_cumulative_mass_error_g=float(np.max(np.abs(mass[:,4]-mass[:,5]))),
            disconnected_deposit_mm3=float(mass[:,9].max()),
            input_J=float(history[:,7].sum()),entering_J=float(history[:,8].sum()),loss_J=float(history[:,9].sum()),
            maximum_balance_error_J=float(np.abs(history[:,10]).max()),
            maximum_source_partition_error_J=float(np.abs(heat[:,5]-heat[:,4]-heat[:,6]-heat[:,7]).max()),
            maximum_parent_pool_partition_error_J=float(np.abs(heat[:,6]-heat[:,10]-heat[:,11]).max()),
            deposit_CAD_quadrature_factor=source['CAD_volume_quadrature_factor'],
            prefix_from_complete_nodal_trace=prefix,
            temperature_domain_pass=bool((prefix or result['error'] is None) and minimum>=20.-1e-4 and history[:,4].max()<2800.))
        rows.append(row)
    comparisons={}
    reference=np.loadtxt(base/cases[0]/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
    if stop_time is not None:reference=reference[reference[:,0]<=stop_time+1e-9]
    for row,label in zip(rows[1:],['time_half','local_space']):
        comparisons[label]={key:abs(row[key]-rows[0][key])/rows[0][key] for key in ['peak_C','QT_peak_C','interface_thermal_coverage_mm2']}
        other=np.loadtxt(base/row['case']/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
        for key,column in [('common_time_peak_history',4),('common_time_QT_history',5)]:
            comparisons[label][key]=float(np.max(np.abs(np.interp(reference[:,0],other[:,0],other[:,column])-reference[:,column])/reference[:,column]))
    card=yaml.safe_load((ROOT/'project/precoat-process-design.yaml').read_text(encoding='utf8'))['first']
    # Independent constant-property Gaussian surface heating scale. The
    # half-space excludes groove geometry, latent heat and evolving deposit;
    # it is a magnitude check, not a calibrated source or a strict bound.
    k=.033;cp=545.;density=7200e-9;alpha=k/(density*cp);width=3.2
    power=card['current_A']*card['voltage_V_reference']*card['efficiency_for_design_accounting']
    entering_power=rows[0]['entering_J']/rows[0]['time_s']
    delta=(power-entering_power)/(np.pi**1.5*k*width)*np.arctan(2*np.sqrt(alpha*.125)/width)
    result=dict(cases=rows,relative_differences=comparisons,
        startup_discretization_pass=all(row['temperature_domain_pass'] and row['disconnected_deposit_mm3']<1e-8
            and row['maximum_step_mass_error_g']<1e-10 and row['maximum_balance_error_J']<1e-4 for row in rows)
            and all(value<=.05 for group in comparisons.values() for value in group.values()),
        independent_scale_check=dict(QT_diffusivity_mm2_s=alpha,diffusion_length_sqrt_alpha_dt_mm=float(np.sqrt(alpha*.125)),
            gaussian_halfspace_surface_temperature_at_0125_C=300.+delta,assumptions='k33 W/mK,cp545 J/kgK,rho7200; stationary infinite half-space with parent/pool power',
            equation='DeltaT(0,t)=P/(pi^(3/2)*k*a)*atan(2*sqrt(alpha*t)/a)',
            scope='dimensional/energy scale only; not a strict bound or CI-A1 source calibration'),
        full_first_layer_verified=False,full_manufacturing_verified=False,PMZ_capacity_assigned=False,
        applicable_domain='one wing, current pWPS, first0..1s, progressive occupied-volume thermal model with liquid factor3 method hypothesis')
    (base/'startup-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=lambda s:ROOT/s,default=BASE)
    p.add_argument('--cases',nargs=3,default=CASES);p.add_argument('--stop-time',type=float)
    a=p.parse_args();audit(a.base,a.cases,a.stop_time)
