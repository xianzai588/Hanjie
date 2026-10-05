"""Cross-check source concentration, filler mass and heat-transfer scales.

Does not infer transported dilution or establish FE mesh/time convergence.
"""
from pathlib import Path
import argparse,json
import numpy as np
from ni99_physics_bounds import JANAF_NI_T_K,JANAF_NI_CP_MOLAR,NI_MOLAR_KG
from run_candidate_solver import operators


def run(case,out):
    inp=json.loads((case/'input.json').read_text(encoding='utf8'))
    with np.load(case/'mesh.npz',allow_pickle=False) as f:x,e,m=f['x'],f['e'],f['material']
    _,vol,_,_=operators(x,e,mechanical=False);centre=x[e].mean(axis=1)
    r=np.linalg.norm(centre[:,:2],axis=1);angle=np.arctan2(centre[:,1],centre[:,0])
    track=inp['tracks'][0];strip=track['strip']-1;edges=inp['radial_strip_edges_mm'];sr=track['radius_mm']
    target=(m==3)&(r>=edges[strip]-1e-8)&(r<=edges[strip+1]+1e-8)&(angle<=track['angle_end']+1e-10)
    rows=[];prev=m==1
    dt=inp['dt_s'];w=inp['source_width_mm'];d=inp['source_depth_mm'];tab=inp['materials'][3]
    knots=np.array(tab['temperature_dependent']['temperatures_c']);cp=np.array(tab['temperature_dependent']['specific_heat_j_kgk'])
    fine=np.unique(np.r_[20.,knots[(knots>20)&(knots<inp['entering_Ni99_C'])],inp['entering_Ni99_C']])
    # Entering temperature is above the selected full-liquid temperature.
    incoming=np.trapezoid(np.interp(fine,knots,cp),fine)+tab['fusion_enthalpy']['latent_heat_J_kg']
    rho=tab['nominal_properties_20c']['density_kg_m3']*1e-9
    times=np.r_[np.arange(dt,track['arc_duration_s'],dt),track['arc_duration_s']]
    last=0.
    for t in times:
        active=(m==1)|(target&(angle<=track['angle_begin']+2*t/sr+1e-10));born=active&~prev
        theta=track['angle_begin']+(last+t)/sr
        src=np.array([sr*np.cos(theta),sr*np.sin(theta),inp['source_z_mm']]);diff=centre-src
        raw=np.exp(-np.sum(diff[:,:2]**2,axis=1)/w**2-(diff[:,2]/d)**2)*vol*active
        frac=float(raw.sum()/(np.pi**1.5*w*w*d))
        rows.append(dict(t_s=float(t),dt_s=float(t-last),born_volume_mm3=float(vol[born].sum()),
            fullspace_gaussian_capture=frac,legacy_normalization_multiplier=1/frac,
            legacy_arc_fraction_to_QT=float(raw[m==1].sum()/raw.sum()),
            wire_J=float(vol[born].sum()*rho*incoming)))
        last=t;prev=active
    firstvol=float(vol[target].sum());wire=firstvol*rho*incoming
    first_top=float(x[np.unique(e[m==3]),2].max());floor=float(x[np.unique(e[m==3]),2].min())
    duration=track['arc_duration_s'];command=inp['arc_power_W']*(duration-.25*inp['start_ramp_s']-.325*inp['end_ramp_s'])
    # The deposited geometry is an alloy volume. Feed must use pure-filler density.
    equivalent_wire_mm=firstvol*rho/(8890e-9*np.pi*1.2**2/4*.94)
    coat_thickness=first_top-floor
    scale=[]
    for k in [20.,30.,55.]:
        alpha=k/(8500*650)*1e6;tau=w/2
        scale.append(dict(k_W_mK=k,alpha_mm2_s=alpha,residence_s=tau,
            diffusion_length_sqrt4alpha_tau_mm=float(np.sqrt(4*alpha*tau)),
            layer_diffusion_time_s=coat_thickness**2/alpha,
            stationary_semiinfinite_surface_centre_rise_K=inp['arc_power_W']/(2*np.sqrt(np.pi)*(k/1000)*w)))
    # Direct JANAF crystalline integral, independently compared with tabulated H.
    ni_cp_integral=np.trapezoid(JANAF_NI_CP_MOLAR/NI_MOLAR_KG,JANAF_NI_T_K)
    result=dict(case=str(case),first_short_track_born_alloy_volume_mm3=firstvol,
        modeled_as_deposited_thickness_mm=coat_thickness,modeled_retained_same_as_deposited=True,
        entering_alloy_enthalpy_J_kg=float(incoming),first_short_wire_J=wire,command_J=command,
        wire_fraction_command=wire/command,
        equivalent_1p20mm_filler_feed_mm_s_at_efficiency_0p94=equivalent_wire_mm/duration,
        pure_Ni_JANAF_fusion_J_kg=17150/NI_MOLAR_KG,
        pure_Ni_JANAF_liquid_cp_J_kgK=38.91103/NI_MOLAR_KG,
        pure_Ni_boiling_C=3156.584-273.15,
        pure_Ni_crystal_cp_integral_298p15_to_1728_J_kg=float(ni_cp_integral),
        pure_Ni_tabulated_H_1728_minus_298p15_J_kg=47361/NI_MOLAR_KG,
        cp_trapezoid_relative_difference=float(abs(ni_cp_integral-47361/NI_MOLAR_KG)/(47361/NI_MOLAR_KG)),
        source_samples=[rows[0],rows[len(rows)//2],rows[-1]],
        maximum_legacy_multiplier=max(row['legacy_normalization_multiplier'] for row in rows),
        thermal_scales=scale,source_domain_note='full-space multiplier includes missing air and substrate geometry; size alone is not proof of model invalidity. Time-dependence and parent/pool share need physical boundary comparison.',
        deposition_note='born-alloy geometry and diluted density do not independently establish actual filler addition or precoat contour; reconstructed feed must be checked against WPS',
        model_applicability_verified=False,transported_dilution_computed=False)
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2),encoding='utf8')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(run(a.case,a.output),indent=2))
