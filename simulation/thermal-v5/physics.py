"""THERMAL0.3 焓更新与空单元激活；0.2 冻结求解器保持独立。"""
from __future__ import annotations

import numpy as np
from numba import njit


def material_tables(materials, specification, scales=None, latent=True):
    """把分段线性 cp 的积分及相变焓编成可精确反解的区间表。"""
    scales = scales or {}
    tables = []
    for name in ("q235b", "qt450_10", "ernife_ci"):
        mat, spec = materials[name], specification[name]
        thermal = spec["high_temperature"] if name == "ernife_ci" else mat["temperature_dependent"]
        phase = spec["phase_change"]
        ts, tl, heat = (float(phase[k]) for k in ("solidus_c", "liquidus_c", "latent_heat_j_kg"))
        if not 20 < ts < tl or heat <= 0:
            raise ValueError("固相线、液相线或潜热非法")
        knots = np.unique([20.0, *thermal["temperatures_c"], ts, tl, 3000.0])
        cp_scale, k_scale = scales.get(name, (1.0, 1.0))
        cp = np.interp(knots, thermal["temperatures_c"], thermal["specific_heat_j_kgk"]) * cp_scale
        k = np.interp(knots, thermal["temperatures_c"], thermal["thermal_conductivity_w_mk"]) * k_scale / 1000
        gradient = np.diff(cp) / np.diff(knots)
        start_cp = cp[:-1].copy()
        if latent:
            start_cp[(knots[:-1] >= ts) & (knots[1:] <= tl)] += heat / (tl - ts)
        h = np.r_[0., np.cumsum(start_cp * np.diff(knots) + .5 * gradient * np.diff(knots)**2)]
        if np.any(cp <= 0) or np.any(k <= 0) or np.any(np.diff(h) <= 0):
            raise ValueError("非正热物性或非单调焓表")
        tables.append((knots, start_cp, gradient, h, k, mat["nominal_properties_20c"]["density_kg_m3"] / 1e9))
    size = max(len(t[0]) for t in tables)
    packed = np.zeros((3, 5, size))
    lengths = np.zeros(3, dtype=np.int64)
    density = np.zeros(3)
    for m, (t, cp, grad, h, k, rho) in enumerate(tables):
        lengths[m] = len(t)
        density[m] = rho
        for row, values in enumerate((t, cp, grad, h, k)):
            packed[m, row, :len(values)] = values
    return packed, lengths, density


@njit(cache=True)
def enthalpy(t, m, tables, lengths):
    count = lengths[m]
    knots = tables[m, 0]
    if t < knots[0] or t > knots[count-1]:
        raise ValueError("温度超出声明物性域 [20,3000] C")
    i = min(np.searchsorted(knots[:count], t, side="right") - 1, count-2)
    d = t - knots[i]
    return tables[m, 3, i] + tables[m, 1, i]*d + .5*tables[m, 2, i]*d*d


@njit(cache=True, inline="always")
def temperature_from_enthalpy(h, m, tables, lengths):
    count = lengths[m]
    hs = tables[m, 3]
    if h < -1e-7 or h > hs[count-1]:
        raise ValueError("比焓超出声明物性域；禁止静默截断温度")
    h = max(0., h)
    i = 0
    while i < count-2 and h >= hs[i+1]:
        i += 1
    dh = h - hs[i]
    cp, slope = tables[m, 1, i], tables[m, 2, i]
    # 二次方程有理化，避免小焓增量时两大数相减损失精度。
    d = 2*dh / (cp + np.sqrt(cp*cp + 2*slope*dh))
    return tables[m, 0, i] + d


@njit(cache=True)
def solve(s, n, z, ids, tables, lengths, rho, process, source, mode, lead, deposition_t, cooling_s, max_dt):
    """固定窗口显式 FV；内通量成对守恒，账本包含出生焓及空域未吸收能量。"""
    ns, nn, nz = len(s), len(n), len(z)
    ds, dn, dz = s[1]-s[0], n[1]-n[0], z[1]-z[0]
    vol = ds*dn*dz
    power, speed, preheat, ambient, conv, emiss = process
    start, end, af, ar, b, c, ff, fr = source
    duration = (end-start)/speed
    total = duration+cooling_s
    t = np.full(ids.shape, preheat)
    h = np.zeros(ids.shape)
    k = np.zeros(ids.shape)
    active = np.ones(ids.shape, dtype=np.bool_)
    peak = t.copy()
    t800 = np.full(ids.shape, np.nan)
    t500 = np.full(ids.shape, np.nan)
    maxcool = np.zeros(ids.shape)
    deposit_h = enthalpy(deposition_t, 2, tables, lengths)
    initial = 0.
    for i in range(ns):
        for j in range(nn):
            for l in range(nz):
                m = ids[i,j,l]-1
                active[i,j,l] = mode == 0 or m != 2
                if active[i,j,l]:
                    h[i,j,l] = enthalpy(preheat, m, tables, lengths)
                    initial += h[i,j,l]*rho[m]*vol
                else:
                    t[i,j,l] = deposition_t
                    peak[i,j,l] = deposition_t
    weights_yz = np.exp(-3*(n[:,None]/b)**2-3*(z[None,:]/c)**2)
    weights_x = np.empty(ns)
    yz_sum = np.sum(weights_yz)
    source_j, absorbed_j, birth_j, conv_j, rad_j, born_mass = 0.,0.,0.,0.,0.,0.
    time = 0.
    steps = 0
    minimum_dt = max_dt
    minimum_absorbed_fraction = 1.
    # 物性全域上界构造显式步长限制；相变只增加热容，不放宽稳定步长。
    max_alpha = 0.
    for m in range(3):
        mincp = np.min(tables[m,1,:lengths[m]-1])
        maxk = np.max(tables[m,4,:lengths[m]])
        max_alpha = max(max_alpha, maxk/(rho[m]*mincp))
    stable_dt = .4/(max_alpha*(1/ds**2+1/dn**2+1/dz**2))
    while time < total-1e-10:
        dt = min(max_dt, stable_dt, total-time)
        if time < duration:
            dt = min(dt, duration-time)
        minimum_dt = min(minimum_dt, dt)
        center = start+speed*(min(time, duration)+dt/2)
        for i in range(ns):
            d = s[i]-center
            a, f = (af,ff) if d >= 0 else (ar,fr)
            weights_x[i] = f*np.exp(-3*(d/a)**2)
            for j in range(nn):
                for l in range(nz):
                    m = ids[i,j,l]-1
                    if not active[i,j,l] and time < duration and s[i] <= center+lead and s[i] >= start:
                        active[i,j,l] = True
                        h[i,j,l] = deposit_h
                        birth_j += deposit_h*rho[m]*vol
                        born_mass += rho[m]*vol
                    if active[i,j,l]:
                        segment = 0
                        while segment < lengths[m]-2 and t[i,j,l] >= tables[m,0,segment+1]:
                            segment += 1
                        fraction = (t[i,j,l]-tables[m,0,segment])/(tables[m,0,segment+1]-tables[m,0,segment])
                        k[i,j,l] = tables[m,4,segment]+fraction*(tables[m,4,segment+1]-tables[m,4,segment])
        norm = np.sum(weights_x)*yz_sum
        absorbed_w = 0.
        # 所有面通量读取同一步旧温度；新焓先存储，最后统一反解温度。
        for i in range(ns):
            for j in range(nn):
                for l in range(nz):
                    if not active[i,j,l]:
                        continue
                    m = ids[i,j,l]-1
                    old = t[i,j,l]
                    flux, area = 0.,0.
                    for axis in range(3):
                        spacing = ds if axis == 0 else dn if axis == 1 else dz
                        for direction in (-1,1):
                            ii = i+direction if axis == 0 else i
                            jj = j+direction if axis == 1 else j
                            ll = l+direction if axis == 2 else l
                            inside = 0<=ii<ns and 0<=jj<nn and 0<=ll<nz
                            if inside and active[ii,jj,ll]:
                                kh = 2*k[i,j,l]*k[ii,jj,ll]/(k[i,j,l]+k[ii,jj,ll])
                                flux += kh*(t[ii,jj,ll]-old)/spacing**2
                            elif inside or axis != 0:
                                area += vol/spacing
                    qc = conv*(old-ambient)/1e6*area
                    qr = emiss*5.670374419e-14*((old+273.15)**4-(ambient+273.15)**4)*area
                    qsource = power*weights_x[i]*weights_yz[j,l]/norm if time < duration else 0.
                    absorbed_w += qsource
                    h[i,j,l] += dt*(flux+(qsource-qc-qr)/vol)/rho[m]
                    conv_j += qc*dt
                    rad_j += qr*dt
        if time < duration:
            source_j += power*dt
            absorbed_j += absorbed_w*dt
            minimum_absorbed_fraction = min(minimum_absorbed_fraction, absorbed_w/power)
        for i in range(ns):
            for j in range(nn):
                for l in range(nz):
                    if active[i,j,l]:
                        old = t[i,j,l]
                        new = temperature_from_enthalpy(h[i,j,l], ids[i,j,l]-1, tables, lengths)
                        t[i,j,l] = new
                        peak[i,j,l] = max(peak[i,j,l], new)
                        maxcool[i,j,l] = max(maxcool[i,j,l], (old-new)/dt)
                        if old >= 800 and new < 800 and np.isnan(t800[i,j,l]):
                            t800[i,j,l] = time+dt*(old-800)/(old-new)
                        if old >= 500 and new < 500 and not np.isnan(t800[i,j,l]) and np.isnan(t500[i,j,l]):
                            t500[i,j,l] = time+dt*(old-500)/(old-new)
        time += dt
        steps += 1
    final = 0.
    for i in range(ns):
        for j in range(nn):
            for l in range(nz):
                if active[i,j,l]:
                    final += h[i,j,l]*rho[ids[i,j,l]-1]*vol
    ledger = np.array([source_j, absorbed_j, birth_j, conv_j, rad_j, final-initial, born_mass, minimum_absorbed_fraction, minimum_dt, steps])
    return t, peak, active, t800, t500, maxcool, ledger
