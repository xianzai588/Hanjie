"""Plan 5 热侧逐面通量、局部源分配与固定物理点账本测试。"""
import json

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from hanjie.simulation.thermal_ledgers import (
    DetailedThermalLedger,
    aggregate_interface_faces,
    aggregate_source_to_lower_cells,
    build_material_point_stencil,
)


def _line_geometry():
    return {
        "ids": np.array([2, 3, 1]),
        "index": np.array([[0, 0, 0], [0, 1, 0], [0, 2, 0]]),
        "dims": np.ones((3, 3)),
        "volumes": np.ones(3),
        "s_left": np.zeros(3),
        "s_edges": np.array([0.0, 1.0]),
        "n_edges": np.array([0.0, 1.0, 2.0, 3.0]),
        "z_edges": np.array([0.0, 1.0]),
        "edge_i": np.array([0, 1]),
        "edge_j": np.array([1, 2]),
        "edge_axis": np.array([1, 1]),
        "edge_area": np.ones(2),
    }


def test_detailed_ledger_preserves_signed_interface_energy_and_source_moments():
    geometry = _line_geometry()
    ledger = DetailedThermalLedger(geometry)
    # 矩阵已经包含 dt；两个公共面的 dt*G 分别为 2 和 3 J/K。
    matrix = csr_matrix([[2.0, -2.0, 0.0], [-2.0, 5.0, -3.0], [0.0, -3.0, 3.0]])
    ledger.prepare_step(np.ones(3), matrix, dt=0.5, face_area=np.ones(2))
    ledger.record_step(np.array([100.0, 50.0, 20.0]), np.array([0.0, 4.0, 0.0]))
    interface, source = ledger.finish()

    by_name = {row["name"]: row for row in interface["interfaces"]}
    assert by_name["qt450_10_to_ernife_ci"]["cumulative_signed_heat_j"] == pytest.approx(100.0)
    assert by_name["ernife_ci_to_q235b"]["cumulative_signed_heat_j"] == pytest.approx(90.0)
    assert by_name["qt450_10_to_ernife_ci"]["peak_abs_heat_flux_w_per_mm2"] == pytest.approx(200.0)
    assert source["total_source_energy_j"] == pytest.approx(2.0)
    assert source["energy_weighted_centroid_s_n_z_mm"] == pytest.approx([0.5, 1.5, 0.5])
    assert source["maximum_cell_source_density_w_per_mm3"] == pytest.approx(4.0)

    # 热源关闭后的步不应把 NaN 写进严格 JSON 证据。
    ledger.prepare_step(np.ones(3), matrix, dt=0.5, face_area=np.ones(2))
    ledger.record_step(np.array([90.0, 45.0, 25.0]), np.zeros(3))
    interface, source = ledger.finish()
    json.dumps({"interface":interface,"source":source},allow_nan=False)
    assert source["steps"][-1]["energy_weighted_centroid_s_n_z_mm"] is None


def test_point_stencil_never_crosses_material_or_silently_extrapolates():
    geometry = _line_geometry()
    with pytest.raises(ValueError, match="insufficient_stencil"):
        build_material_point_stencil(geometry, [0.5, 1.45, 0.5], material_id=3, neighbours=3)
    with pytest.raises(ValueError, match="计算域"):
        build_material_point_stencil(geometry, [0.5, 3.1, 0.5], material_id=1)
    with pytest.raises(ValueError, match="预期材料"):
        build_material_point_stencil(geometry, [0.5, 1.45, 0.5], material_id=2)


def _cloud_geometry(centres, material_ids):
    centres = np.asarray(centres, dtype=float)
    count = len(centres)
    # WLS 只依赖真实中心；规则边界用于点的域内与材料归属检查。
    return {
        "ids": np.asarray(material_ids, dtype=int),
        "index": np.column_stack((np.arange(count), np.zeros(count, int), np.zeros(count, int))),
        "dims": np.ones((count, 3)),
        "volumes": np.ones(count),
        "s_left": centres[:, 0] - 0.5,
        "s_edges": np.arange(count + 1, dtype=float),
        "n_edges": np.array([-2.0, 2.0]),
        "z_edges": np.array([-2.0, 2.0]),
        "cell_centres_override": centres,
        "lattice": np.arange(count, dtype=int)[:, None, None],
    }


def test_wls_reconstruction_is_affine_exact_on_random_nonuniform_cloud():
    rng = np.random.default_rng(7456)
    centres = rng.uniform(-1.0, 1.0, size=(24, 3))
    # 让目标点明确落入第一个控制体，中心云本身保持非规则。
    centres[:, 0] = np.linspace(0.2, 23.8, len(centres))
    geometry = _cloud_geometry(centres, np.ones(len(centres), int))
    point = np.array([0.4, 0.1, -0.2])
    stencil = build_material_point_stencil(geometry, point, 1, neighbours=12)
    values = 7.0 + centres @ np.array([1.5, -2.0, 0.75])
    assert stencil["method"] == "same_material_weighted_least_squares_affine_exact"
    assert np.dot(values[stencil["cell_indices"]], stencil["weights"]) == pytest.approx(
        7.0 + point @ np.array([1.5, -2.0, 0.75]), abs=2e-12
    )


def test_wls_piecewise_affine_trace_uses_only_requested_material():
    rng = np.random.default_rng(12)
    left = rng.uniform([-0.9, -1.0, -1.0], [-0.05, 1.0, 1.0], size=(16, 3))
    right = rng.uniform([0.05, -1.0, -1.0], [0.9, 1.0, 1.0], size=(16, 3))
    centres = np.vstack((left, right))
    geometry = _cloud_geometry(centres, np.r_[np.full(16, 2), np.full(16, 3)])
    geometry["s_edges"] = np.linspace(-1.0, 1.0, 33)
    geometry["s_left"] = centres[:, 0] - 0.01
    geometry["index"] = np.column_stack((np.arange(32), np.zeros(32, int), np.zeros(32, int)))
    geometry["lattice"] = np.arange(32, dtype=int)[:, None, None]
    # 两侧温度连续，法向梯度按 k_left*g_left=k_right*g_right 构造。
    target = np.array([-0.02, 0.15, -0.1])
    stencil = build_material_point_stencil(geometry, target, 2, neighbours=12, containing_cell=0)
    assert set(np.asarray(geometry["ids"])[stencil["cell_indices"]]) == {2}
    left_values = 100.0 + centres @ np.array([2.0, 0.5, -0.25])
    assert np.dot(left_values[stencil["cell_indices"]], stencil["weights"]) == pytest.approx(
        100.0 + target @ np.array([2.0, 0.5, -0.25]), abs=2e-11
    )


def test_nested_ledgers_aggregate_on_common_physical_controls():
    lower_field = {
        "s_edges": np.array([0.0, 1.0]),
        "n_edges": np.array([0.0, 1.0, 2.0]),
        "z_edges": np.array([0.0, 1.0]),
        "material_cross_section": np.array([[2], [3]]),
        "material_id": np.array([2, 3]),
    }
    source_rows = [
        {"centre_s_n_z_mm": [0.25, 0.25, 0.5], "material": "qt450_10", "cumulative_source_energy_j": 2.0},
        {"centre_s_n_z_mm": [0.75, 0.75, 0.5], "material": "qt450_10", "cumulative_source_energy_j": 3.0},
        {"centre_s_n_z_mm": [0.5, 1.5, 0.5], "material": "ernife_ci", "cumulative_source_energy_j": 4.0},
    ]
    np.testing.assert_allclose(aggregate_source_to_lower_cells(lower_field, source_rows), [5.0, 4.0])

    lower_faces = [{
        "name": "qt450_10_to_ernife_ci", "axis": 1,
        "centre_s_n_z_mm": [0.5, 1.0, 0.5],
        "bounds_s_n_z_mm": [[0.0, 1.0], [1.0, 1.0], [0.0, 1.0]],
        "cumulative_signed_heat_j": 10.0,
    }]
    upper_faces = [
        {**lower_faces[0], "centre_s_n_z_mm": [0.25, 1.0, 0.5], "cumulative_signed_heat_j": 4.0},
        {**lower_faces[0], "centre_s_n_z_mm": [0.75, 1.0, 0.5], "cumulative_signed_heat_j": 6.0},
    ]
    np.testing.assert_allclose(aggregate_interface_faces(lower_field, lower_faces, upper_faces), [10.0])
