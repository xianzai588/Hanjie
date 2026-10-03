"""服务载荷下开槽座体的孔轴偏移与孔椭圆化核算（8P-FAIR_B vs Continuous 细网格基线）。

复用 P1A 静刚度筛查（run_static_screening.py）的网格、装配、载荷与轴线指标，
新增两个服务侧输出：
1. 载荷诱导的孔面径向位移不圆度（椭圆化幅值）：(max u_r − min u_r)/2，已在
   指标内扣除未变形 CAD 形位（与轴线偏移同一口径）。
2. 服务工况线性缩放：启停 Fr 幅 1500 N、连续 Fr 幅 500 N（§5 设计谱），
   线弹性下位移与载荷成正比，缩放比在结果中显式记录。

边界：座体单件线弹性（QT450-10 室温 E=169 GPa、ν=0.27），焊接接口以三向
分布弹簧等效壳体（BC-1=1e8 N/mm 主口径），不含焊接残余应力态、不含壳体
真实柔度、不含孔与胀套的接触——结果是服务刚度的方向性量级，不是整机刚度。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
from scipy.sparse.linalg import splu

import run_static_screening as rss

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "service-stiffness-8p.json"
DIRECTIONS_DEG = (0, 15, 30, 45, 60, 75, 90)
SERVICE_RADIAL_N = {"start_stop_amp": 1500.0, "continuous_amp": 500.0}
REFERENCE_LOAD_N = float(rss.TOTAL_LOAD_N)


def _bore_radial_metrics(mesh: rss.VolumeMesh, displacement: np.ndarray) -> dict[str, float]:
    bore_triangles, _ = rss._surface_sets(mesh)
    nodes = np.unique(mesh.boundary_triangles[bore_triangles].ravel())
    base = mesh.points[nodes]
    u = displacement.reshape(-1, 3)[nodes]
    radial_dir = base[:, :2] / np.linalg.norm(base[:, :2], axis=1)[:, None]
    u_radial = np.einsum("ij,ij->i", u[:, :2], radial_dir)
    return {
        # 椭圆化幅值：载荷诱导径向位移的周向峰谷差之半。
        "bore_ovalization_amplitude_mm": float((u_radial.max() - u_radial.min()) / 2.0),
        # 平均径向位移：孔整体胀缩分量（正=胀大）。
        "bore_mean_radial_displacement_mm": float(u_radial.mean()),
        "bore_probe_nodes": int(len(nodes)),
    }


def _solve_model(model_id: str) -> dict:
    mesh = rss._mesh_step(
        rss._step_path(model_id),
        rss.MESH_ROOT / model_id.lower().replace("_", "-") / "fine.msh",
        rss.RESOLUTIONS["fine"],
    )
    basis, stiffness, fixed, quality = rss._assemble_system(mesh, rss.SUPPORT_STIFFNESS["BC-1"])
    factor = splu(stiffness.tocsr())
    free = np.arange(basis.N)
    bore_triangles, _ = rss._surface_sets(mesh)
    directions = []
    for angle in DIRECTIONS_DEG:
        row = rss._solve_case(mesh, basis, factor, free, rss.SUPPORT_STIFFNESS["BC-1"], angle, bore_triangles, quality)
        # _solve_case 只回指标不回位移场，按同一装配/载荷路径重解一次以取孔面位移。
        load, bore_area = rss._load_vector(basis, mesh, angle, bore_triangles)
        displacement = np.zeros(basis.N, dtype=float)
        displacement[free] = factor.solve(load[free])
        oval = _bore_radial_metrics(mesh, displacement)
        directions.append(
            dict(
                load_angle_deg=angle,
                load_total_n=REFERENCE_LOAD_N,
                position_diameter_mm=row["position_diameter_mm"],
                p95_von_mises_mpa=row["p95_von_mises_mpa"],
                **{k: round(v, 9) if isinstance(v, float) else v for k, v in oval.items()},
            )
        )
    worst = max(directions, key=lambda item: item["position_diameter_mm"])
    scaled = {
        name: dict(
            radial_force_n=force,
            axis_offset_diameter_mm=round(worst["position_diameter_mm"] * force / REFERENCE_LOAD_N, 7),
            bore_ovalization_amplitude_mm=round(worst["bore_ovalization_amplitude_mm"] * force / REFERENCE_LOAD_N, 7),
            fraction_of_position_limit_mm=round(
                worst["position_diameter_mm"] * force / REFERENCE_LOAD_N / 0.05, 6
            ),
        )
        for name, force in SERVICE_RADIAL_N.items()
    }
    return dict(
        model_id=model_id,
        resolution="fine",
        boundary_condition="BC-1",
        mesh=dict(tetrahedron_count=quality["tetrahedron_count"], node_count=quality["node_count"]),
        reference_load_n=REFERENCE_LOAD_N,
        worst_direction_deg=worst["load_angle_deg"],
        worst_axis_offset_diameter_mm=worst["position_diameter_mm"],
        worst_bore_ovalization_amplitude_mm=worst["bore_ovalization_amplitude_mm"],
        worst_bore_mean_radial_displacement_mm=worst["bore_mean_radial_displacement_mm"],
        worst_p95_von_mises_mpa=worst["p95_von_mises_mpa"],
        directions=directions,
        service_scaling_linear=scaled,
    )


def main() -> int:
    results = [_solve_model("8P-FAIR_B"), _solve_model("Continuous")]
    continuous = next(item for item in results if item["model_id"] == "Continuous")
    slotted = next(item for item in results if item["model_id"] == "8P-FAIR_B")
    payload = dict(
        version="WAVE2-SERVICE-STIFFNESS-1",
        method="linear elastic seat-only FEM on cached fine meshes via run_static_screening functions; "
        "bore ovalization = half range of load-induced radial displacement on the finished Ø40 surface",
        boundaries=[
            "seat-only linear elastic at room temperature (E=169 GPa, nu=0.27)",
            "weld interface as distributed isotropic springs BC-1=1e8 N/mm; shell flexibility not modelled",
            "no weld residual stress state, no mandrel contact, no thermal field — service stiffness magnitude only",
            "linear scaling to service loads is exact within linear elasticity",
        ],
        service_spectra_source="report §5 design conditions (start_stop Fr amp 1500 N, continuous Fr amp 500 N)",
        models=results,
        comparison=dict(
            axis_offset_ratio_8p_vs_continuous=round(
                slotted["worst_axis_offset_diameter_mm"] / continuous["worst_axis_offset_diameter_mm"], 2
            ),
            ovalization_ratio_8p_vs_continuous=round(
                slotted["worst_bore_ovalization_amplitude_mm"] / continuous["worst_bore_ovalization_amplitude_mm"], 2
            ),
        ),
    )
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for item in results:
        print(
            f"{item['model_id']}: axis {item['worst_axis_offset_diameter_mm']:.7f} mm @1000 N, "
            f"ovalization {item['worst_bore_ovalization_amplitude_mm']:.7f} mm, worst dir {item['worst_direction_deg']}°"
        )
    print(f"written: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
