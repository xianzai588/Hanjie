"""基于修复后 STEP 实体的三维线弹性静刚度筛选。

该脚本消费 `models/*/*.step`，使用 Gmsh 生成实体四面体网格，再用
scikit-fem 装配小变形线弹性刚度矩阵。载荷施加在 Ø40 孔内表面，R74.98
圆柱接口用三向分布式弹簧连接到壳体；所有模型使用同一材料、载荷、网格策略和
边界定义。它用于 P1A 静刚度公平筛选，不替代真实热—弹塑性焊接 FE。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import gmsh
import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import splu
from skfem import Basis, ElementTetP1, ElementVector, MeshTet, asm
from skfem.models.elasticity import linear_elasticity


ROOT = Path(__file__).resolve().parent
MODEL_ROOT = ROOT / "models"
MESH_ROOT = ROOT / "meshes"
RESULT_ROOT = ROOT / "results" / "static-screening"
MODEL_IDS = (
    "Continuous",
    "4P-FAIR_A",
    "4P-FAIR_B",
    "6P-FAIR_A",
    "6P-FAIR_B",
    "8P-FAIR_A",
    "8P-FAIR_B",
)
RESOLUTIONS = {
    # Gmsh 特征尺寸；不是旧 FE3D 文档中的假想标签。
    "coarse": 4.2,
    "medium": 3.2,
    "fine": 2.5,
}
DIRECTIONS_DEG = (0, 15, 30, 45, 60, 75, 90)
SUPPORT_STIFFNESS = {"BC-1": 1.0e8, "BC-2": 1.0e6}
TOTAL_LOAD_N = 1000.0
YOUNG_MODULUS_MPA = 169000.0
POISSON_RATIO = 0.27
BORE_RADIUS_MM = 20.0
OUTER_RADIUS_MM = 74.98
SEAT_HEIGHT_MM = 12.0


@dataclass
class VolumeMesh:
    points: np.ndarray  # (N, 3)
    tetrahedra: np.ndarray  # (M, 4), zero-based
    boundary_triangles: np.ndarray  # (K, 3), zero-based


def _step_path(model_id: str) -> Path:
    folder = model_id.lower().replace("_", "-")
    return MODEL_ROOT / folder / f"{model_id}.step"


def _mesh_step(step_path: Path, mesh_path: Path, characteristic_length: float) -> VolumeMesh:
    """导入 STEP 并读取实体四面体和边界三角形。"""
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", characteristic_length)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", characteristic_length)
        gmsh.option.setNumber("Mesh.Algorithm3D", 10)
        gmsh.option.setNumber("Mesh.Optimize", 1)
        gmsh.model.add(step_path.stem)
        imported = gmsh.model.occ.importShapes(str(step_path))
        if not imported:
            raise RuntimeError(f"STEP import returned no shapes: {step_path}")
        gmsh.model.occ.synchronize()
        volumes = gmsh.model.getEntities(3)
        if len(volumes) != 1:
            raise RuntimeError(f"expected one volume, got {len(volumes)}: {step_path}")
        gmsh.model.mesh.generate(3)
        gmsh.write(str(mesh_path))

        node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
        if len(node_tags) == 0:
            raise RuntimeError(f"mesh has no nodes: {step_path}")
        tag_to_index = {int(tag): index for index, tag in enumerate(node_tags)}
        points = np.asarray(node_coords, dtype=float).reshape(-1, 3)

        tetra_tags, tetra_nodes = gmsh.model.mesh.getElementsByType(4)
        tri_tags, tri_nodes = gmsh.model.mesh.getElementsByType(2)
        if len(tetra_tags) == 0 or len(tri_tags) == 0:
            raise RuntimeError(f"mesh missing tetrahedra or boundary triangles: {step_path}")
        tetrahedra = np.asarray(
            [tag_to_index[int(tag)] for tag in tetra_nodes], dtype=int
        ).reshape(-1, 4)
        boundary_triangles = np.asarray(
            [tag_to_index[int(tag)] for tag in tri_nodes], dtype=int
        ).reshape(-1, 3)
        return VolumeMesh(points, tetrahedra, boundary_triangles)
    finally:
        gmsh.finalize()


def _surface_sets(mesh: VolumeMesh) -> tuple[np.ndarray, np.ndarray]:
    """按真实表面半径识别孔面和 R74.98 接口面。"""
    tri_points = mesh.points[mesh.boundary_triangles]
    centroid = tri_points.mean(axis=1)
    radii = np.linalg.norm(centroid[:, :2], axis=1)
    bore = np.flatnonzero(np.abs(radii - BORE_RADIUS_MM) < 0.8)
    outer = np.flatnonzero(radii > OUTER_RADIUS_MM - 0.35)
    if len(bore) == 0 or len(outer) == 0:
        raise RuntimeError(
            f"surface classification failed: bore_triangles={len(bore)}, outer_triangles={len(outer)}"
        )
    return bore, outer


def _triangle_areas(mesh: VolumeMesh, triangle_indices: np.ndarray) -> np.ndarray:
    triangles = mesh.points[mesh.boundary_triangles[triangle_indices]]
    return 0.5 * np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    )


def _assemble_system(mesh: VolumeMesh, support_k: float) -> tuple[Basis, Any, np.ndarray, dict[str, Any]]:
    """装配线弹性刚度和整圈接口弹簧。

    接口外部壳体在本地筛查中不显式划分实体，因此用三向分布式弹簧
    表示壳体对焊接接口的等效柔度。这样刚体模态由整圈支承消除，避免
    少数人为锚点随网格改变而污染收敛性。
    """
    sk_mesh = MeshTet(mesh.points.T, mesh.tetrahedra.T)
    basis = Basis(sk_mesh, ElementVector(ElementTetP1()))
    lam = YOUNG_MODULUS_MPA * POISSON_RATIO / (
        (1.0 + POISSON_RATIO) * (1.0 - 2.0 * POISSON_RATIO)
    )
    mu = YOUNG_MODULUS_MPA / (2.0 * (1.0 + POISSON_RATIO))
    stiffness = asm(linear_elasticity(lam, mu), basis).tolil()
    bore_triangles, outer_triangles = _surface_sets(mesh)
    outer_nodes = np.unique(mesh.boundary_triangles[outer_triangles].ravel())

    # 焊接接口对壳体的三向支承使用同一标量刚度，边界条件明确且可复现。
    for node in outer_nodes:
        dofs = np.array([basis.nodal_dofs[0, node], basis.nodal_dofs[1, node], basis.nodal_dofs[2, node]])
        stiffness[np.ix_(dofs, dofs)] += support_k * np.eye(3)

    # 三向分布式支承本身消除刚体模态，不再添加网格依赖的点锚固。
    fixed = np.array([], dtype=int)
    quality = {
        "tetrahedron_count": int(mesh.tetrahedra.shape[0]),
        "node_count": int(mesh.points.shape[0]),
        "bore_triangle_count": int(len(bore_triangles)),
        "outer_triangle_count": int(len(outer_triangles)),
        "minimum_bore_triangle_area_mm2": float(_triangle_areas(mesh, bore_triangles).min()),
        "minimum_outer_triangle_area_mm2": float(_triangle_areas(mesh, outer_triangles).min()),
        "fixed_node_ids": [],
        "support_model": "distributed_isotropic_interface_springs",
    }
    return basis, stiffness.tocsr(), fixed, quality


def _load_vector(
    basis: Basis, mesh: VolumeMesh, angle_deg: float, bore_triangles: np.ndarray
) -> tuple[np.ndarray, float]:
    force = np.zeros(basis.N, dtype=float)
    direction = np.array(
        [math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg)), 0.0]
    )
    areas = _triangle_areas(mesh, bore_triangles)
    total_area = float(areas.sum())
    traction = TOTAL_LOAD_N / total_area
    for local_index, triangle_index in enumerate(bore_triangles):
        nodal_force = direction * traction * areas[local_index] / 3.0
        for node in mesh.boundary_triangles[triangle_index]:
            force[basis.nodal_dofs[:, node]] += nodal_force
    return force, total_area


def _axis_metric(mesh: VolumeMesh, displacement: np.ndarray) -> dict[str, float]:
    bore_triangles, _ = _surface_sets(mesh)
    nodes = np.unique(mesh.boundary_triangles[bore_triangles].ravel())
    base_coords = mesh.points[nodes]
    coords = base_coords + displacement.reshape(-1, 3)[nodes]
    z = base_coords[:, 2] - SEAT_HEIGHT_MM / 2.0
    design = np.column_stack((np.ones(len(z)), z))
    base_x_coef, *_ = np.linalg.lstsq(design, base_coords[:, 0], rcond=None)
    base_y_coef, *_ = np.linalg.lstsq(design, base_coords[:, 1], rcond=None)
    x_coef, *_ = np.linalg.lstsq(design, coords[:, 0], rcond=None)
    y_coef, *_ = np.linalg.lstsq(design, coords[:, 1], rcond=None)
    # 位置度只计入载荷引起的轴线漂移，消除 CAD 原点或网格采样偏置。
    x_center = float(x_coef[0] - base_x_coef[0])
    y_center = float(y_coef[0] - base_y_coef[0])
    return {
        "position_radius_mm": math.hypot(x_center, y_center),
        "position_diameter_mm": 2.0 * math.hypot(x_center, y_center),
        "axis_slope_x_mm_per_mm": float(x_coef[1] - base_x_coef[1]),
        "axis_slope_y_mm_per_mm": float(y_coef[1] - base_y_coef[1]),
        "bore_node_count": int(len(nodes)),
    }


def _stress_metrics(mesh: VolumeMesh, displacement: np.ndarray) -> dict[str, float]:
    """用四面体 P1 形函数梯度回算单元应力。"""
    disp = displacement.reshape(-1, 3)
    lam = YOUNG_MODULUS_MPA * POISSON_RATIO / (
        (1.0 + POISSON_RATIO) * (1.0 - 2.0 * POISSON_RATIO)
    )
    mu = YOUNG_MODULUS_MPA / (2.0 * (1.0 + POISSON_RATIO))
    von_mises = []
    volumes = []
    for tetra in mesh.tetrahedra:
        xyz = mesh.points[tetra]
        jacobian = np.column_stack((xyz[1] - xyz[0], xyz[2] - xyz[0], xyz[3] - xyz[0]))
        volume = abs(float(np.linalg.det(jacobian))) / 6.0
        if volume <= 1e-12:
            continue
        gradients_ref = np.array(
            [[-1.0, -1.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        ).T
        gradients = np.linalg.inv(jacobian).T @ gradients_ref
        grad_u = disp[tetra].T @ gradients.T
        strain = 0.5 * (grad_u + grad_u.T)
        stress = lam * np.trace(strain) * np.eye(3) + 2.0 * mu * strain
        deviatoric = stress - np.trace(stress) / 3.0 * np.eye(3)
        von_mises.append(math.sqrt(1.5 * float(np.sum(deviatoric * deviatoric))))
        volumes.append(volume)
    if not von_mises:
        raise RuntimeError("no positive-volume tetrahedra for stress recovery")
    values = np.asarray(von_mises)
    return {
        "max_von_mises_mpa": float(values.max()),
        "p95_von_mises_mpa": float(np.percentile(values, 95)),
        "minimum_tetra_volume_mm3": float(min(volumes)),
    }


def _solve_case(
    mesh: VolumeMesh,
    basis: Basis,
    factor: Any,
    free: np.ndarray,
    support_k: float,
    angle_deg: float,
    bore_triangles: np.ndarray,
    quality: dict[str, Any],
) -> dict[str, Any]:
    load, bore_area = _load_vector(basis, mesh, angle_deg, bore_triangles)
    displacement = np.zeros(basis.N, dtype=float)
    displacement[free] = factor.solve(load[free])
    axis = _axis_metric(mesh, displacement)
    stress = _stress_metrics(mesh, displacement)
    displacement_norm = np.linalg.norm(displacement.reshape(-1, 3), axis=1)
    return {
        **quality,
        **axis,
        **stress,
        "support_stiffness_n_per_mm": support_k,
        "load_angle_deg": angle_deg,
        "load_total_n": TOTAL_LOAD_N,
        "bore_loaded_area_mm2": bore_area,
        "compliance_mm_per_n": float(np.dot(load, displacement) / TOTAL_LOAD_N**2),
        "strain_energy_n_mm": float(0.5 * np.dot(load, displacement)),
        "maximum_displacement_mm": float(displacement_norm.max()),
    }


def _write_results(rows: list[dict[str, Any]], mesh_rows: list[dict[str, Any]]) -> None:
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    raw_path = RESULT_ROOT / "static-screening-raw.json"
    raw_path.write_text(
        json.dumps({"evidence_level": "solver_result_unvalidated", "rows": rows, "meshes": mesh_rows}, indent=2),
        encoding="utf-8",
    )
    fieldnames = list(rows[0].keys())
    with (RESULT_ROOT / "static-screening.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    with (RESULT_ROOT / "mesh-summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(mesh_rows[0].keys()))
        writer.writeheader()
        writer.writerows(mesh_rows)

    lines = [
        "# P1A 三维线弹性静刚度筛选",
        "",
        "> 结果直接来自修复后 STEP 的 Gmsh 四面体网格和 scikit-fem 线弹性求解；证据等级为 `solver_result_unvalidated`。",
        "> 该结果不包含焊接热源、温度相关塑性、相变、焊缝金属本构或壳体实体柔度，不能写成完整热—结构 FE 结论。",
        "",
        "## 统一边界与载荷",
        "",
        "- Ø40 孔内表面施加合力 1 kN 的均匀径向分布载荷，扫描 0°–90°、每 15° 一点。",
        "- R74.98 圆柱焊接接口施加三向分布式等效弹簧；BC-1 = 1e8 N/mm，BC-2 = 1e6 N/mm。",
        "- 整圈分布式支承本身消除刚体模态，不使用随网格变化的点锚固。",
        "- 材料统一采用 QT450-10 室温线弹性参数 E=169 GPa、ν=0.27。",
        "",
        "## 各模型最不利方向结果",
        "",
        "| 模型 | 网格 | BC | 最不利角度 | 最大载荷诱导轴线偏移直径 (mm) | 最大 von Mises (MPa) | 质量 (kg) |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['model_id']} | {row['resolution']} | {row['boundary_condition']} | "
            f"{row['worst_angle_deg']:.0f} | {row['worst_position_diameter_mm']:.6f} | "
            f"{row['worst_stress_mpa']:.3f} | {row['mass_kg']:.6f} |"
        )
    lines.extend([
        "",
        "## 解释边界",
        "",
        "最不利方向按载荷诱导的孔轴线偏移直径选择，已扣除未变形 CAD 轴线基准；连续结构和离散结构的质量只用于比刚度辅助比较，不用于替代热—结构焊接结论。网格相邻变化和边界敏感性必须在新 BREP 上同时报告，不能沿用旧二维代理结果。",
    ])
    (RESULT_ROOT / "static-screening.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _model_manifest(model_id: str) -> dict[str, Any]:
    folder = model_id.lower().replace("_", "-")
    return json.loads((MODEL_ROOT / folder / "geometry-manifest.json").read_text(encoding="utf-8"))


def run(models: Iterable[str], resolutions: Iterable[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    mesh_rows: list[dict[str, Any]] = []
    for model_id in models:
        manifest = _model_manifest(model_id)
        for resolution in resolutions:
            if resolution not in RESOLUTIONS:
                raise ValueError(f"unknown resolution: {resolution}")
            mesh_path = MESH_ROOT / model_id.lower().replace("_", "-") / f"{resolution}.msh"
            mesh = _mesh_step(_step_path(model_id), mesh_path, RESOLUTIONS[resolution])
            quality = {
                "model_id": model_id,
                "resolution": resolution,
                "mesh_path": mesh_path.relative_to(ROOT).as_posix(),
                "node_count": int(mesh.points.shape[0]),
                "tetrahedron_count": int(mesh.tetrahedra.shape[0]),
                "boundary_triangle_count": int(mesh.boundary_triangles.shape[0]),
            }
            mesh_rows.append(quality)
            for boundary_condition, support_k in SUPPORT_STIFFNESS.items():
                basis, stiffness, fixed, solver_quality = _assemble_system(mesh, support_k)
                all_dofs = np.arange(basis.N)
                free = np.setdiff1d(all_dofs, fixed)
                factor = splu(stiffness[free][:, free].tocsc())
                bore_triangles, _ = _surface_sets(mesh)
                direction_rows = [
                    _solve_case(
                        mesh,
                        basis,
                        factor,
                        free,
                        support_k,
                        angle,
                        bore_triangles,
                        solver_quality,
                    )
                    | {
                        "model_id": model_id,
                        "resolution": resolution,
                        "boundary_condition": boundary_condition,
                    }
                    for angle in DIRECTIONS_DEG
                ]
                worst = max(direction_rows, key=lambda row: row["position_diameter_mm"])
                worst_p95 = max(direction_rows, key=lambda row: row["p95_von_mises_mpa"])
                rows.append(
                    {
                        "model_id": model_id,
                        "family": manifest["family"],
                        "resolution": resolution,
                        "boundary_condition": boundary_condition,
                        "mass_kg": float(manifest["geometry"]["calculated_mass_kg"]),
                        "worst_angle_deg": worst["load_angle_deg"],
                        "worst_position_diameter_mm": worst["position_diameter_mm"],
                        "worst_stress_mpa": worst["max_von_mises_mpa"],
                        "worst_p95_stress_mpa": worst_p95["p95_von_mises_mpa"],
                        "worst_compliance_mm_per_n": worst["compliance_mm_per_n"],
                        "direction_count": len(direction_rows),
                        "mesh_node_count": quality["node_count"],
                        "mesh_tetrahedron_count": quality["tetrahedron_count"],
                        "direction_results": direction_rows,
                    }
                )
    return rows, mesh_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default=",".join(MODEL_IDS))
    parser.add_argument("--resolutions", default=",".join(RESOLUTIONS))
    args = parser.parse_args()
    models = [item.strip() for item in args.models.split(",") if item.strip()]
    resolutions = [item.strip() for item in args.resolutions.split(",") if item.strip()]
    unknown = sorted(set(models) - set(MODEL_IDS))
    if unknown:
        parser.error(f"unknown models: {unknown}")
    rows, mesh_rows = run(models, resolutions)
    _write_results(rows, mesh_rows)
    print(f"完成 {len(mesh_rows)} 个三维实体网格和 {len(rows)} 个边界/网格筛选汇总")
    for row in rows:
        print(
            f"{row['model_id']} {row['resolution']} {row['boundary_condition']}: "
            f"P={row['worst_position_diameter_mm']:.6f} mm, "
            f"stress={row['worst_stress_mpa']:.3f} MPa"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
