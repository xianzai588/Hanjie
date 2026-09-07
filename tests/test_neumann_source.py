"""Plan 6 显式边界 Neumann 离散的解析准入测试。"""

import numpy as np
import pytest

from hanjie.simulation.neumann_source import (
    gaussian_interval_moments,
    solve_series_slab,
    uniform_face_power,
)


def test_uniform_planar_flux_on_arbitrary_nonuniform_faces():
    edges = np.array([-2.0, -1.71, -0.4, 0.13, 1.9, 3.0])
    areas = np.diff(edges) * 2.75
    q0 = 37.2
    powers = uniform_face_power(areas, q0)
    assert powers.sum() == pytest.approx(q0 * 5.0 * 2.75, rel=2e-16)


@pytest.mark.parametrize("subdivisions", [5, 11, 37])
def test_gaussian_face_integrals_match_truncated_analytic_moments(subdivisions):
    edges = np.linspace(-3.1, 2.4, subdivisions + 1) ** 3 / 9.61
    edges.sort()
    moments = np.array([gaussian_interval_moments(a, b, width=2.5) for a, b in zip(edges[:-1], edges[1:])])
    exact = gaussian_interval_moments(edges[0], edges[-1], width=2.5)
    np.testing.assert_allclose(moments.sum(axis=0), exact, rtol=2e-13, atol=2e-14)
    assert exact[0] < 1.0  # 有限面不允许偷偷补回无限域尾部功率。


def test_one_material_neumann_dirichlet_slab_is_exactly_linear():
    edges = np.array([0.0, 0.17, 0.8, 1.5, 3.0])
    result = solve_series_slab(edges, np.full(4, 12.0), left_flux_w_mm2=2.4, right_temperature_c=30.0)
    expected = 30.0 + 2.4 * (3.0 - result["cell_centres_mm"]) / 12.0
    np.testing.assert_allclose(result["temperature_c"], expected, atol=2e-13)
    np.testing.assert_allclose(result["face_flux_w_mm2"], 2.4, atol=2e-13)


def test_two_material_series_slab_has_piecewise_linear_temperature_and_equal_flux():
    edges = np.array([0.0, 0.2, 0.7, 1.0, 1.4, 2.0])
    conductivity = np.array([10.0, 10.0, 10.0, 25.0, 25.0])
    result = solve_series_slab(edges, conductivity, left_flux_w_mm2=5.0, right_temperature_c=20.0)
    x = result["cell_centres_mm"]
    expected = np.where(x < 1.0, 20.0 + 5.0 * ((1.0 - x) / 10.0 + 1.0 / 25.0), 20.0 + 5.0 * (2.0 - x) / 25.0)
    np.testing.assert_allclose(result["temperature_c"], expected, atol=3e-13)
    np.testing.assert_allclose(result["face_flux_w_mm2"], 5.0, atol=3e-13)
