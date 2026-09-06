"""三维小应变 J2 材料点与仿射四面体网格验证工具。"""

from __future__ import annotations

import numpy as np


def interpolate_curve(temperature_c, temperatures_c, values, *, out_of_range="error"):
    temperature = np.asarray(temperature_c,float)
    knots = np.asarray(temperatures_c,float)
    data = np.asarray(values,float)
    if knots.ndim!=1 or data.shape!=knots.shape or len(knots)<2 or np.any(np.diff(knots)<=0):
        raise ValueError("温变曲线必须为等长、严格递增的一维数据")
    if out_of_range=="error" and (np.any(temperature<knots[0]) or np.any(temperature>knots[-1])):
        raise ValueError("温度超出材料曲线范围，禁止静默外推")
    if out_of_range not in ("error","clip"):
        raise ValueError("未知温度越界策略")
    return np.interp(temperature,knots,data)


def instantaneous_thermal_strain(temperature_c, temperatures_c, alpha_per_k, reference_temperature_c=20.0):
    """分段线性积分瞬时线膨胀系数；不把平均 alpha 当瞬时值混用。"""
    query = np.asarray(temperature_c,float)
    knots = np.asarray(temperatures_c,float)
    alpha = np.asarray(alpha_per_k,float)
    if np.any(query<knots[0]) or np.any(query>knots[-1]) or not knots[0]<=reference_temperature_c<=knots[-1]:
        raise ValueError("温度超出 alpha 曲线范围，禁止静默外推")

    def integral(value):
        points=np.unique(np.r_[reference_temperature_c,knots[(knots>min(reference_temperature_c,value))&(knots<max(reference_temperature_c,value))],value])
        area=float(np.trapezoid(np.interp(points,knots,alpha),points))
        return area if value>=reference_temperature_c else -area
    return np.asarray([integral(float(value)) for value in query.flat]).reshape(query.shape)


def elastic_constants(elastic_modulus_mpa,poisson_ratio):
    elastic=float(elastic_modulus_mpa); poisson=float(poisson_ratio)
    if elastic<=0 or not -1.0<poisson<0.5:
        raise ValueError("各向同性弹性参数无效")
    return elastic/(2*(1+poisson)),elastic/(3*(1-2*poisson))


def j2_update(total_strain,thermal_strain,state,elastic_modulus_mpa,poisson_ratio,yield_strength_mpa,hardening_modulus_mpa=0.0):
    """三维径向返回；张量剪切分量采用真实应变 εxy，不采用工程剪应变。"""
    strain=np.asarray(total_strain,float)
    if strain.shape!=(3,3) or not np.allclose(strain,strain.T,atol=1e-12):
        raise ValueError("总应变必须为对称 3x3 张量")
    plastic=np.asarray(state.get("plastic_strain",np.zeros((3,3))),float)
    equivalent=float(state.get("equivalent_plastic_strain",0.0))
    dissipation=float(state.get("plastic_dissipation_mj_mm3",0.0))
    if plastic.shape!=(3,3) or not np.allclose(plastic,plastic.T,atol=1e-12) or equivalent<0 or dissipation<0:
        raise ValueError("J2 状态无效")
    thermal=np.eye(3)*float(thermal_strain) if np.ndim(thermal_strain)==0 else np.asarray(thermal_strain,float)
    if thermal.shape!=(3,3):
        raise ValueError("热应变必须为标量或 3x3 张量")
    shear,bulk=elastic_constants(elastic_modulus_mpa,poisson_ratio)
    elastic_trial=strain-thermal-plastic
    stress_trial=2*shear*(elastic_trial-np.trace(elastic_trial)/3*np.eye(3))+bulk*np.trace(elastic_trial)*np.eye(3)
    deviator=stress_trial-np.trace(stress_trial)/3*np.eye(3)
    equivalent_trial=float(np.sqrt(1.5*np.sum(deviator*deviator)))
    current_yield=float(yield_strength_mpa)+float(hardening_modulus_mpa)*equivalent
    increment=max(0.0,(equivalent_trial-current_yield)/(3*shear+float(hardening_modulus_mpa)))
    if increment>0:
        direction=1.5*deviator/equivalent_trial
        plastic=plastic+increment*direction
        equivalent=equivalent+increment
        deviator=deviator*(1-3*shear*increment/equivalent_trial)
    stress=deviator+np.trace(stress_trial)/3*np.eye(3)
    updated_yield=float(yield_strength_mpa)+float(hardening_modulus_mpa)*equivalent
    dissipation += updated_yield*increment
    elastic_strain=strain-thermal-plastic
    return {
        "stress_mpa":stress,
        "plastic_strain":plastic,
        "equivalent_plastic_strain":equivalent,
        "plastic_dissipation_mj_mm3":dissipation,
        "elastic_energy_mj_mm3":float(0.5*np.sum(stress*elastic_strain)),
        "equivalent_stress_mpa":float(np.sqrt(1.5*np.sum((stress-np.trace(stress)/3*np.eye(3))**2))),
        "plastic_increment":increment,
    }


def tetrahedral_cube():
    nodes=np.array([[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]],float)
    elements=np.array([[0,1,2,6],[0,2,3,6],[0,3,7,6],[0,7,4,6],[0,4,5,6],[0,5,1,6]],int)
    return nodes,elements


def affine_mesh_response(strain,thermal_strain,material,state=None):
    """六四面体立方体的实际单元积分与内力装配，用于整体平衡基准。"""
    strain=np.asarray(strain,float)
    nodes,elements=tetrahedral_cube()
    displacement=nodes@strain.T
    force=np.zeros_like(nodes)
    volume_total=0.0
    states=[]
    state=state or {}
    for element in elements:
        coordinates=nodes[element]
        matrix=np.column_stack((np.ones(4),coordinates))
        gradients=np.linalg.inv(matrix)[1:,:].T
        volume=abs(np.linalg.det((coordinates[1:]-coordinates[0]).T))/6
        gradient_u=displacement[element].T@gradients
        element_strain=(gradient_u+gradient_u.T)/2
        result=j2_update(element_strain,thermal_strain,state,**material)
        for local,node in enumerate(element):
            force[node]+=volume*result["stress_mpa"]@gradients[local]
        volume_total+=volume
        states.append(result)
    resultant=force.sum(axis=0)
    moment=np.cross(nodes,force).sum(axis=0)
    return {"nodes":nodes,"elements":elements,"displacement":displacement,"nodal_internal_force_n":force,
            "resultant_internal_force_n":resultant,"resultant_internal_moment_n_mm":moment,
            "volume_mm3":volume_total,"element_states":states}
