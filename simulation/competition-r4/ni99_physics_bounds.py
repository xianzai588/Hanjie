"""Decision-scale thermal hypotheses, with primary-source end members.

These intervals are sensitivity hypotheses, not measured weld-metal properties.
In particular neither a room-temperature Ni80Fe20 datum nor the JANAF pure-Ni
table establishes a complete diluted Ni-C-Fe-Si-Mn property envelope.
"""
import copy
import numpy as np

JANAF_NI_T_K=np.array([298.15,300,350,400,450,500,600,631,700,800,900,
                      1000,1100,1200,1300,1400,1500,1600,1700,1728.])
JANAF_NI_CP_MOLAR=np.array([25.987,26.024,27.294,28.693,29.623,31.045,
    34.853,39.832,30.794,31.003,31.589,32.217,32.928,33.681,34.518,
    35.397,36.317,37.279,38.284,38.535])
NI_MOLAR_KG=.05869


def apply_bounds(tables,case):
    if case=='legacy':return copy.deepcopy(tables)
    if case not in ['nominal','low_k','high_k','pure_Ni_endmember']:raise ValueError(case)
    out=copy.deepcopy(tables)
    # Keep the magnetic heat-capacity peak of the primary pure-Ni data.
    T=np.unique(np.r_[20.,JANAF_NI_T_K-273.15,1000.,1330.,1400.,1440.,
                      1455.,1500.,1800.,2500.,2800.])
    cp_Ni=np.where(T<1454.85,np.interp(T+273.15,JANAF_NI_T_K,JANAF_NI_CP_MOLAR)/NI_MOLAR_KG,
                   38.91103/NI_MOLAR_KG)
    qt=out[1]['temperature_dependent']
    cp_QT=np.interp(T,qt['temperatures_c'],qt['specific_heat_j_kgk'])
    # 10--20 wt% QT is the intended chemical window, not a solved dilution.
    # Low/high k also change cp and latent to bracket energy requirements.
    d={'nominal':.15,'low_k':.20,'high_k':.10,'pure_Ni_endmember':0.}[case]
    if case=='nominal':k=np.interp(T,[20,1000,1400,1500,2800],[30,42,45,30,30])
    elif case=='low_k':k=np.interp(T,[20,1000,1400,1500,2800],[20,28,30,25,25])
    elif case=='high_k':k=np.interp(T,[20,1000,1400,1500,2800],[55,65,68.2,40,40])
    else:
        # Nickel200 is a solid conductivity end member, not a diluted deposit.
        # Liquid30 W/mK remains a stated hypothesis, not a measured bound.
        k=np.interp(T,[20,100,200,300,400,500,600,700,800,900,1000,1454.85,1458.85,2800],
                      [70.3,66.5,61.6,56.8,55.4,57.6,59.7,61.8,64,66.1,68.2,68.2,30,30])
    cp=(1-d)*cp_Ni+d*cp_QT
    cp*= {'nominal':1.,'low_k':1.10,'high_k':.90,'pure_Ni_endmember':1.}[case]
    out[3]['nominal_properties_20c']['density_kg_m3']=1/((1-d)/8890+d/7200)
    out[3]['temperature_dependent']=dict(temperatures_c=T.tolist(),
        thermal_conductivity_w_mk=k.tolist(),specific_heat_j_kgk=cp.tolist())
    out[3]['fusion_enthalpy']['latent_heat_J_kg']={'nominal':285000.,'low_k':310000.,'high_k':260000.,'pure_Ni_endmember':17150/NI_MOLAR_KG}[case]
    if case=='pure_Ni_endmember':
        # Eight-kelvin regularization centred at the JANAF1728 K melting point.
        # Clear a previously selected diluted-alloy equilibrium curve.
        out[3]['fusion_enthalpy'].pop('liquid_fraction_curve',None)
        out[3]['fusion_enthalpy'].pop('phase_source',None)
        out[3]['fusion_enthalpy'].update(solidus_C=1450.85,liquidus_C=1458.85,
            remelt_solidus_C=1450.85,basis='pure incoming Ni JANAF1728 K melting,8 K numerical regularization; no dilution inferred')
    out[3]['basis']='2026-10-05 thermal sensitivity hypotheses; JANAF Ni cp including magnetic peak; intended QT mass fraction and +/-10% cp; documented alloy k hypotheses and latent bracket. Not measured Ni99 weld metal.'
    out[3]['thermal_bounds_case']=case
    if case=='pure_Ni_endmember':out[3]['basis']='Zero-QT composition end member independent of target dilution; JANAF cp/latent, Nickel200 solid conductivity, stated liquid-k hypothesis. Not actual diluted coating or a global envelope.'
    return out
