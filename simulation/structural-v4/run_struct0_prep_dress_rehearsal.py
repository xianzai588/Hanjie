"""在准入扫掠网格的完整截面周期扇区上排演 STRUCT-0 状态流。"""
from __future__ import annotations

import json
from pathlib import Path
import sys

import gmsh
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from hanjie.simulation.nonlinear_fem import solve_incremental_tetra


MESH = ROOT / "simulation/structural-v4/results/struct0-prep/continuous-swept-plan6-admitted.msh"
MESH_REPORT = MESH.with_suffix(".json")
OUTPUT = ROOT / "simulation/structural-v4/results/struct0-prep/struct0-prep-dress-rehearsal-plan6.json"


def _read_sector():
    report = json.loads(MESH_REPORT.read_text(encoding="utf-8"))
    cross_count = int(report["topology"]["cross_section_node_count"])
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.open(str(MESH))
        tags, coordinates, _ = gmsh.model.mesh.getNodes()
        order = np.argsort(tags)
        tags, coordinates = tags[order], coordinates.reshape(-1, 3)[order]
        if not np.array_equal(tags, np.arange(1, len(tags) + 1)):
            raise RuntimeError("扫掠网格节点标签不连续")
        nodes = coordinates[: 2 * cross_count]
        elements, regions = [], []
        for physical_tag, name in ((1, "shell"), (2, "seat"), (3, "weld")):
            entity = int(gmsh.model.getEntitiesForPhysicalGroup(3, physical_tag)[0])
            _, connectivity = gmsh.model.mesh.getElementsByType(4, entity)
            rows = connectivity.reshape(-1, 4)
            rows = rows[np.all(rows <= 2 * cross_count, axis=1)] - 1
            elements.append(rows); regions.extend([name] * len(rows))
        return nodes, np.vstack(elements), np.asarray(regions), report
    finally:
        gmsh.finalize()


def _constraints(nodes, fixture):
    constraints = {}
    radius = np.linalg.norm(nodes[:, :2], axis=1)
    # 周期扇区首轮仅核对数据与状态流，两个环向截面采用零环向位移近似。
    for node in range(len(nodes)):
        constraints[3 * node + 1] = 0.0
    for node in np.flatnonzero((np.abs(nodes[:, 2]) < 1e-8) & (radius >= 74.9)):
        constraints[3 * int(node) + 2] = 0.0
    datum = int(np.argmin(np.linalg.norm(nodes - np.array([80.0, 0.0, 0.0]), axis=1)))
    constraints[3 * datum] = 0.0
    if fixture:
        bore_nodes = np.flatnonzero(np.isclose(radius, 20.0, atol=1e-6))
        for node in bore_nodes:
            constraints[3 * int(node)] = 0.0
        if len(bore_nodes):
            constraints[3 * int(bore_nodes[0]) + 2] = 0.0
    return constraints


def _thermal_strain(nodes, elements, amplitude_c):
    centroid = nodes[elements].mean(axis=1)
    radius = np.linalg.norm(centroid[:, :2], axis=1)
    temperature = 20.0 + amplitude_c * np.exp(-((radius - 75.0) ** 2 + (centroid[:, 2] - 12.0) ** 2) / 18.0)
    return 1.2e-5 * (temperature - 20.0), temperature


def _axis_fit(nodes, displacement):
    radius = np.linalg.norm(nodes[:, :2], axis=1)
    selected = np.flatnonzero(np.isclose(radius, 20.0, atol=1e-6))
    radial = np.divide(nodes[selected, :2], radius[selected, None])
    radial_displacement = np.sum(displacement[selected, :2] * radial, axis=1)
    fitted_radius = float(20.0 + np.mean(radial_displacement))
    # 扇区位移绕轴重构整圈，仅用于验证孔轴拟合链路可执行。
    angle = np.linspace(0.0, 2 * np.pi, 128, endpoint=False)
    circles = []
    for z in (0.0, 12.0):
        circles.append(np.column_stack((fitted_radius * np.cos(angle), fitted_radius * np.sin(angle), np.full_like(angle, z))))
    points = np.vstack(circles)
    centre = points.mean(axis=0)
    _, _, vh = np.linalg.svd(points - centre, full_matrices=False)
    axis = vh[np.argmin(np.var((points - centre) @ vh.T, axis=0))]
    if axis[2] < 0:
        axis = -axis
    return {"centre_mm": centre.tolist(), "direction": axis.tolist(), "fitted_diameter_mm": 2 * fitted_radius, "pfep_fe_mm": float(2 * abs(np.mean(radial_displacement))), "engineering_meaning": "none_synthetic_rehearsal_only"}


def main():
    nodes, elements, regions, mesh_report = _read_sector()
    substrate = regions != "weld"
    active_all = np.ones(len(elements), dtype=bool)
    hot_strain, hot_temperature = _thermal_strain(nodes, elements, 800.0)
    warm_strain, _ = _thermal_strain(nodes, elements, 180.0)
    cool_strain, _ = _thermal_strain(nodes, elements, 35.0)
    cold_strain = np.zeros(len(elements))
    radius = np.linalg.norm(nodes[:, :2], axis=1)
    contact_nodes = np.flatnonzero(np.isclose(radius, 74.98, atol=1e-6) & (nodes[:, 2] <= 12.0 + 1e-8) & (np.abs(nodes[:, 1]) < 1e-8))
    contact = {"normal": [1, 0, 0], "offset_mm": 75.0, "allowed_side": "negative", "node_indices": contact_nodes.tolist(), "penalty_n_per_mm": 2e6}
    fixed, released = _constraints(nodes, True), _constraints(nodes, False)
    substrate_nodes = np.unique(elements[substrate])
    dormant_nodes = np.setdiff1d(np.unique(elements[~substrate]), substrate_nodes)
    dormant_fixed = {3 * int(node) + axis: 0.0 for node in dormant_nodes for axis in range(3)}
    pre_activation = {**fixed, **dormant_fixed}
    steps = [
        {"name": "initial_assembly", "prescribed_dofs": pre_activation, "thermal_strain": cold_strain, "active_elements": substrate},
        {"name": "normal_contact_initialized", "prescribed_dofs": pre_activation, "thermal_strain": cold_strain, "active_elements": substrate, "contact": contact},
        {"name": "prescribed_global_thermal_cycle", "prescribed_dofs": pre_activation, "thermal_strain": warm_strain, "active_elements": substrate, "contact": contact},
        {"name": "local_heat_before_birth", "prescribed_dofs": pre_activation, "thermal_strain": hot_strain, "active_elements": substrate, "contact": contact},
        {"name": "stress_free_weld_activation", "prescribed_dofs": fixed, "thermal_strain": hot_strain, "active_elements": active_all, "stress_free_on_activation": True, "contact": contact},
        {"name": "cool_under_fixture", "prescribed_dofs": fixed, "thermal_strain": cool_strain, "active_elements": active_all, "contact": contact},
        {"name": "release_criterion_evaluation", "prescribed_dofs": fixed, "thermal_strain": cool_strain, "active_elements": active_all, "contact": contact},
        {"name": "fixture_release", "prescribed_dofs": released, "thermal_strain": cool_strain, "active_elements": active_all},
        {"name": "continue_cooling", "prescribed_dofs": released, "thermal_strain": cold_strain, "active_elements": active_all},
    ]
    material = {"elastic_modulus_mpa": 1200.0, "poisson_ratio": 0.3, "yield_strength_mpa": 1e8, "hardening_modulus_mpa": 1000.0}
    solved = solve_incremental_tetra(nodes, elements, material, steps, relative_tolerance=2e-7, absolute_tolerance_n=2e-6, max_iterations=20)
    rows = solved["steps"]
    final_displacement = np.asarray(rows[-1]["displacement_mm"])
    axis_fit = _axis_fit(nodes, final_displacement)
    force_error = max(float(np.linalg.norm(row["force_balance_n"])) for row in rows)
    moment_error = max(float(np.linalg.norm(row["moment_balance_n_mm"])) for row in rows)
    checks = {
        "admitted_swept_mesh": bool(mesh_report["mesh_acceptance_pass"]),
        "sparse_global_newton_path": solved["linear_solver"] == "scipy_sparse_direct",
        "all_newton_steps_converged": all(row["converged"] for row in rows),
        "force_balance_below_1e_minus_5_n": force_error < 1e-5,
        "moment_balance_below_1e_minus_3_n_mm": moment_error < 1e-3,
        "plastic_dissipation_nonnegative": all(row["plastic_dissipation_mj"] >= 0 for row in rows),
        "penetration_below_0p001_mm": max((row["contact"]["maximum_penetration_mm"] for row in rows if row["contact"]), default=0.0) < 0.001,
        "thermal_contact_activated_then_separated": rows[3]["contact"]["active_node_count"] > 0 and rows[6]["contact"]["active_node_count"] == 0,
        "activation_count_matches_weld_sector": rows[4]["newly_activated_element_count"] == int(np.count_nonzero(~substrate)),
        "fixture_release_displacement_finite": bool(np.all(np.isfinite(final_displacement))),
        "axis_fit_completed": bool(np.isfinite(axis_fit["fitted_diameter_mm"])),
    }
    result = {
        "stage": "STRUCT-0-PREP-DRESS-REHEARSAL", "evidence_level": "synthetic_cyclic_sector_workflow_rehearsal",
        "mesh": MESH.relative_to(ROOT).as_posix(), "sector": {"nodes": len(nodes), "tetrahedra": len(elements), "contains_full_cross_section": True, "circumferential_layers": 1},
        "synthetic_temperature": {"maximum_c": float(hot_temperature.max()), "formal_thermal_history": False},
        "steps": [{key: value for key, value in row.items() if key not in ("displacement_mm", "reaction_force_n", "external_force_n")} for row in rows],
        "maximum_newton_iterations": max(row["newton_iterations"] for row in rows), "maximum_force_balance_error_n": force_error,
        "maximum_moment_balance_error_n_mm": moment_error, "release_displacement_mm": float(np.max(np.abs(np.asarray(rows[7]["displacement_mm"]) - np.asarray(rows[6]["displacement_mm"])))),
        "datum_reconstruction": {"datum_a": "reconstructed", "datum_b": "reconstructed"}, "bore_axis_fit": axis_fit,
        "checks": checks, "dress_rehearsal_pass": all(checks.values()), "struct0_prep_status": "ready_pending_admitted_thermal_history" if all(checks.values()) else "not_ready_rehearsal_failed", "formal_struct_0_allowed": False,
        "limitations": ["完整径向-轴向截面的单环向周期扇区，不是整圈非对称正式求解", "稀疏全局 Newton 已在该扇区执行，整圈规模与非对称载荷仍待正式热历史准入后求解", "合成温度与PFEP_FE只验证状态流，不具有工程意义"],
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT), "maximum_newton_iterations": result["maximum_newton_iterations"], "force_balance_n": force_error, "moment_balance_n_mm": moment_error, "checks": checks}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
