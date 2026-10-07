"""One molecular-transport branch plus measured-Ni convection scale.

Dimensionless transport checks explain the need for liquid convection; they
do not calibrate an isotropic factor, bead shape, or chemistry transport.
"""
import json
import numpy as np
from mma_literature_profile import ROOT


def run():
    molecular=ROOT/'simulation/competition-r4/results/mma-end80-r12-molecular-transport-first1s-20261007'
    failure=json.loads((molecular/'failure.json').read_text())
    inputs=json.loads((molecular/'input.json').read_text())
    curve=inputs['materials'][3]['temperature_dependent']
    T=1800.;Tm=1728.;gas_constant=8.31446261815324
    density=7890-.65*(T-Tm)
    cp=(36.2+1.9e-3*(T-Tm))/.0586934
    viscosity=.07e-3*np.exp(67000/(gas_constant*T))
    k=float(np.interp(T-273.15,curve['temperatures_c'],curve['thermal_conductivity_w_mk']))
    diffusivity=k/(density*cp)
    L=3.2e-3;H=inputs['source_depth_mm']*1e-3
    #100K lies inside the original viscosity/surface-tension data span.
    #It is a scale interval, not the measured current CI-A1 surface gradient.
    delta_T=100.;gamma_derivative=2.2e-4
    Ma=gamma_derivative*delta_T*L/(viscosity*diffusivity)
    traction=gamma_derivative*delta_T/L
    inertial_speed=np.sqrt(traction*L/(density*H))
    result=dict(measured_Ni_source='https://doi.org/10.2320/jinstmet.68.781',
        reference_state_K=T,measurement_scope='pure Ni electrostatic levitation; density/Cp1420..1850K, viscosity/surface tension1553..1963K; not CI-A1/Fe-Ni-C-S-O flux-covered pool measurements',
        reference_properties=dict(density_kg_m3=density,cp_J_kgK=cp,viscosity_Pa_s=float(viscosity),
            surface_tension_temperature_derivative_N_mK=-gamma_derivative,
            conductivity_W_mK=k,conductivity_scope='same molecular CI-A1 engineering conductivity table; not a measured alloy conductivity',
            diffusivity_m2_s=diffusivity),
        scale_case=dict(L_m=L,H_m=H,assumed_delta_T_K=delta_T,Marangoni_number=float(Ma),
            surface_traction_scale_Pa=traction,inertia_surface_traction_balance_speed_m_s=float(inertial_speed),
            Peclet_number_from_that_scale=float(inertial_speed*L/diffusivity),
            time_for_that_scale_to_cross_L_s=float(L/inertial_speed)),
        molecular_branch=dict(source=str(molecular),liquid_transport_factor=1.,
            saved_thermal_step_s=failure['time_s'],temperature_C=failure['maximum_temperature_C'],
            QT_temperature_C=failure['maximum_QT_C'],guard_C=2800.,
            domain_check_pass=False,temperature_clipped=False,
            chemistry_or_vaporization_solved=False),
        interpretation='Surface-tension transport can compete with molecular diffusion at this sourced pure-Ni scale; the molecular-only branch is insufficient for the saved high-power pool. This does not determine the actual alloy/flux surface gradient, factor3, mixing, flow direction, or melt-pool contour.',
        isotropic_factor3_calibrated=False,strict_physical_bounds_established=False,
        process_window_frozen_for_production=False,full_manufacturing_verified=False)
    path=ROOT/'simulation/competition-r4/results/mma-continuous-end80-r12-20261007/liquid-transport-physical-scale.json'
    if path.exists():raise ValueError('Preserve prior transport-scale evidence')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':run()
