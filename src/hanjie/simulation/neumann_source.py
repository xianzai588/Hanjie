"""显式边界面 Neumann 热流的积分与解析准入工具。"""
from __future__ import annotations

import numpy as np
from scipy.special import erf


def uniform_face_power(face_area_mm2, flux_w_mm2):
    """把均匀面热流严格转换为每个边界面的功率。"""
    area = np.asarray(face_area_mm2, dtype=float)
    if np.any(area < 0):
        raise ValueError("边界面面积不能为负")
    return area * float(flux_w_mm2)


def gaussian_interval_moments(lo, hi, width):
    """返回归一化高斯在有限区间内的零至二阶原点矩。"""
    if width <= 0 or hi < lo:
        raise ValueError("高斯宽度或积分区间无效")
    a = 3.0 / float(width) ** 2
    root_a = np.sqrt(a)
    lo, hi = float(lo), float(hi)
    elo, ehi = np.exp(-a * lo**2), np.exp(-a * hi**2)
    m0 = 0.5 * (erf(root_a * hi) - erf(root_a * lo))
    m1 = (elo - ehi) / (2.0 * np.sqrt(np.pi * a))

    def primitive2(value, exponential):
        return erf(root_a * value) / (4.0 * a) - value * exponential / (2.0 * np.sqrt(np.pi * a))

    return np.array([m0, m1, primitive2(hi, ehi) - primitive2(lo, elo)])


def solve_series_slab(edges_mm, conductivity_w_mm_k, left_flux_w_mm2, right_temperature_c):
    """用单元中心有限体积离散求解单位面积串联平板。"""
    edges = np.asarray(edges_mm, dtype=float)
    conductivity = np.asarray(conductivity_w_mm_k, dtype=float)
    widths = np.diff(edges)
    if len(conductivity) != len(widths) or np.any(widths <= 0) or np.any(conductivity <= 0):
        raise ValueError("平板网格或导热系数无效")
    count = len(widths)
    matrix = np.zeros((count, count))
    rhs = np.zeros(count)
    conductance = 1.0 / (widths[:-1] / (2 * conductivity[:-1]) + widths[1:] / (2 * conductivity[1:]))
    for cell, value in enumerate(conductance):
        matrix[cell, cell] += value
        matrix[cell + 1, cell + 1] += value
        matrix[cell, cell + 1] -= value
        matrix[cell + 1, cell] -= value
    # 左面为流入域内的正 Neumann 功率；右面以半单元热阻连接定温边界。
    rhs[0] += float(left_flux_w_mm2)
    right_conductance = 2.0 * conductivity[-1] / widths[-1]
    matrix[-1, -1] += right_conductance
    rhs[-1] += right_conductance * float(right_temperature_c)
    temperature = np.linalg.solve(matrix, rhs)
    face_flux = np.r_[
        left_flux_w_mm2,
        conductance * (temperature[:-1] - temperature[1:]),
        right_conductance * (temperature[-1] - right_temperature_c),
    ]
    return {
        "cell_centres_mm": (edges[:-1] + edges[1:]) / 2,
        "temperature_c": temperature,
        "face_flux_w_mm2": face_flux,
    }
