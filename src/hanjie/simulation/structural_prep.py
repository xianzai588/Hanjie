"""STRUCT-0-PREP 独立评价模块；不产生热—结构求解结果。"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares


def uniaxial_elastoplastic_history(total_strain, thermal_strain, elastic_modulus_mpa, yield_strength_mpa, hardening_modulus_mpa=0.0):
    """一维小应变返回映射基准，用于校核本构语义，不代替三维整件求解器。"""
    strain = np.asarray(total_strain, float)
    thermal = np.asarray(thermal_strain, float)
    if strain.ndim != 1 or strain.shape != thermal.shape or not len(strain):
        raise ValueError("总应变与热应变必须为等长非空向量")
    if not np.isfinite(strain).all() or not np.isfinite(thermal).all():
        raise ValueError("应变历史必须有限")
    elastic_modulus_mpa = float(elastic_modulus_mpa)
    yield_strength_mpa = float(yield_strength_mpa)
    hardening_modulus_mpa = float(hardening_modulus_mpa)
    if elastic_modulus_mpa <= 0 or yield_strength_mpa <= 0 or hardening_modulus_mpa < 0:
        raise ValueError("材料参数必须满足 E>0、屈服强度>0、硬化模量>=0")

    stress = np.zeros_like(strain)
    plastic_strain = np.zeros_like(strain)
    equivalent_plastic_strain = np.zeros_like(strain)
    plastic_work_mj_mm3 = np.zeros_like(strain)
    for index in range(len(strain)):
        previous_plastic = plastic_strain[index - 1] if index else 0.0
        previous_equivalent = equivalent_plastic_strain[index - 1] if index else 0.0
        trial = elastic_modulus_mpa * (strain[index] - thermal[index] - previous_plastic)
        current_yield = yield_strength_mpa + hardening_modulus_mpa * previous_equivalent
        excess = abs(trial) - current_yield
        increment = max(0.0, excess / (elastic_modulus_mpa + hardening_modulus_mpa))
        direction = np.sign(trial) if trial else 0.0
        plastic_strain[index] = previous_plastic + increment * direction
        equivalent_plastic_strain[index] = previous_equivalent + increment
        stress[index] = trial - elastic_modulus_mpa * increment * direction
        previous_work = plastic_work_mj_mm3[index - 1] if index else 0.0
        # 1 MPa = 1 mJ/mm³；塑性功采用当前返回应力乘等效塑性增量。
        plastic_work_mj_mm3[index] = previous_work + abs(stress[index]) * increment
    return {
        "stress_mpa": stress,
        "plastic_strain": plastic_strain,
        "equivalent_plastic_strain": equivalent_plastic_strain,
        "plastic_work_mj_mm3": plastic_work_mj_mm3,
    }


def volume_weighted_p95(stress_mpa, volume_mm3):
    stress, volume = np.asarray(stress_mpa,float), np.asarray(volume_mm3,float)
    if stress.ndim != 1 or stress.shape != volume.shape or not len(stress):
        raise ValueError("应力与单元体积必须为等长非空向量")
    if not np.isfinite(stress).all() or not np.isfinite(volume).all() or np.any(volume<=0):
        raise ValueError("应力必须有限，体积必须为正")
    order = np.argsort(stress)
    index = np.searchsorted(np.cumsum(volume[order]),.95*volume.sum())
    return float(stress[order[index]])


def fixture_released(already_released, time_since_weld_end_s, interface_max_c, hold_s=120., release_c=200.):
    """释放为不可逆状态；保持时长从停弧计，温度条件与时长条件必须同时满足。"""
    if not np.isfinite(time_since_weld_end_s) or not np.isfinite(interface_max_c):
        raise ValueError("释放逻辑不得消费缺失温度或时间")
    if hold_s < 0:
        raise ValueError("保持时间不能为负")
    return bool(already_released or (time_since_weld_end_s>=hold_s and interface_max_c<release_c))


def _points(values, minimum):
    p = np.asarray(values,float)
    if p.ndim!=2 or p.shape[1]!=3 or len(p)<minimum or not np.isfinite(p).all():
        raise ValueError("拟合需要足量有限三维测点")
    return p


def fit_position_diameter(datum_a_points, datum_b_points, bore_points):
    """最小二乘测量情景：A 控制定向、B 以 A 法向约束轴线，孔轴独立拟合。

    输入必须为释放并冷却后的独立实体测点；此规则仍需与正式 CMM 基准协议确认。
    """
    a,b,bore = (_points(x,n) for x,n in ((datum_a_points,3),(datum_b_points,6),(bore_points,10)))
    origin = a.mean(axis=0)
    _,singular,basis = np.linalg.svd(a-origin,full_matrices=False)
    if singular[1]<1e-8:
        raise ValueError("基准 A 测点共线")
    x,y,normal = basis
    # 法向取向只影响坐标符号，不影响最终径向距离。
    frame = np.column_stack((x,y,normal))
    local_b = (b-origin)@frame
    design = np.column_stack((2*local_b[:,0],2*local_b[:,1],np.ones(len(b))))
    if np.linalg.matrix_rank(design)<3:
        raise ValueError("基准 B 周向覆盖不足")
    circle = np.linalg.lstsq(design,(local_b[:,:2]**2).sum(axis=1),rcond=None)[0]
    center = circle[:2]
    local_hole = (bore-origin)@frame
    local_hole[:,:2] -= center
    if np.ptp(local_hole[:,2])<1e-6:
        raise ValueError("孔测点缺少轴向跨度，不能拟合轴线倾斜")
    def residual(params):
        axis = np.array([params[2],params[3],1.])
        axis /= np.linalg.norm(axis)
        delta = local_hole-np.array([params[0],params[1],0.])
        radial = delta-np.outer(delta@axis,axis)
        return np.linalg.norm(radial,axis=1)-params[4]
    radius = np.median(np.linalg.norm(local_hole[:,:2],axis=1))
    fit = least_squares(residual,[0.,0.,0.,0.,radius],xtol=1e-12,ftol=1e-12,gtol=1e-12)
    if not fit.success or np.linalg.matrix_rank(fit.jac)<5:
        raise ValueError("孔圆柱拟合失败或欠约束")
    ends = np.array([local_hole[:,2].min(),local_hole[:,2].max()])
    offsets = fit.x[:2]+ends[:,None]*fit.x[2:4]
    return dict(position_diameter_mm=float(2*np.linalg.norm(offsets,axis=1).max()),
        bore_radius_mm=float(fit.x[4]),bore_axis_slopes=fit.x[2:4].tolist(),
        bore_fit_rms_mm=float(np.sqrt(np.mean(fit.fun**2))),
        datum_a_fit_rms_mm=float(np.sqrt(np.mean(((a-origin)@normal)**2))),
        evidence_level="solver_verified_measurement_scenario",official_cmm_equivalence_confirmed=False)


def service_loads(points, axis, force_n=0., moment_n_mm=0.):
    """对称测点集上的合力/纯力偶，幅值由 SERVICE 输入传入，禁止自造服役载荷。"""
    points = _points(points,3)
    direction = np.asarray(axis,float)
    if direction.shape!=(3,) or not np.isfinite(direction).all() or np.linalg.norm(direction)==0:
        raise ValueError("载荷方向非法")
    direction /= np.linalg.norm(direction)
    if not np.isfinite(force_n) or not np.isfinite(moment_n_mm):
        raise ValueError("载荷幅值必须有限")
    arm = points-points.mean(axis=0)
    # 解最小范数节点力，使任意测点分布均满足合力和三个方向的合矩。
    equilibrium = np.zeros((6,3*len(points)))
    for i,(rx,ry,rz) in enumerate(arm):
        equilibrium[:3,3*i:3*i+3] = np.eye(3)
        equilibrium[3:,3*i:3*i+3] = [[0,-rz,ry],[rz,0,-rx],[-ry,rx,0]]
    target = np.r_[direction*force_n,direction*moment_n_mm]
    forces = np.linalg.lstsq(equilibrium,target,rcond=None)[0]
    if not np.allclose(equilibrium@forces,target,atol=1e-8):
        raise ValueError("节点分布无法承受指定合力/力矩")
    return forces.reshape(-1,3)
