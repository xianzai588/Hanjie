"""由共形二维轴对称截面环向扫掠，生成固定棱柱拆分拓扑的 Continuous 网格。"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import gmsh
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "simulation/structural-v4/results/struct0-prep"
LEG_MM = 1.73664301094
REGIONS = ("Q235B_SHELL", "QT450_10_SEAT", "ERNIFE_CI_WELD")


def _cross_section(size):
    gmsh.model.add("continuous_cross_section")
    point_tags = {}

    def point(r, z, local_size=5.0):
        key = (float(r), float(z))
        if key not in point_tags:
            point_tags[key] = gmsh.model.geo.addPoint(r, z, 0.0, local_size)
        return point_tags[key]

    line_tags = {}

    def line(a, b):
        key = (a, b)
        reverse = (b, a)
        if reverse in line_tags:
            return -line_tags[reverse]
        if key not in line_tags:
            line_tags[key] = gmsh.model.geo.addLine(a, b)
        return line_tags[key]

    a = point(75.0 - LEG_MM, 12.0, size)
    d = point(74.98, 12.0, size)
    b = point(75.0, 12.0, size)
    c = point(75.0, 12.0 + LEG_MM, size)
    p20_0, p20_12 = point(20.0, 0.0), point(20.0, 12.0)
    p7498_0 = point(74.98, 0.0)
    p75_0, p75_200 = point(75.0, 0.0), point(75.0, 200.0)
    p80_0, p80_200 = point(80.0, 0.0), point(80.0, 200.0)

    weld_seat = line(a, d)
    gap_bridge = line(d, b)
    weld_shell = line(b, c)
    seat_outer = line(p7498_0, d)
    shell_gap = line(p75_0, b)
    shell_inner_upper = line(c, p75_200)
    fixture_bore = line(p20_0, p20_12)
    datum_b = line(p80_0, p80_200)
    datum_a = line(p75_0, p80_0)

    loops = [
        [datum_a, datum_b, line(p80_200, p75_200), -shell_inner_upper, -weld_shell, -shell_gap],
        [line(p20_0, p7498_0), seat_outer, -weld_seat, line(a, p20_12), line(p20_12, p20_0)],
        [weld_seat, gap_bridge, weld_shell, line(c, a)],
    ]
    surfaces = []
    for loop in loops:
        surfaces.append(gmsh.model.geo.addPlaneSurface([gmsh.model.geo.addCurveLoop(loop)]))
    gmsh.model.geo.synchronize()
    gmsh.option.setNumber("Mesh.MeshSizeMin", min(0.02, size))
    gmsh.option.setNumber("Mesh.MeshSizeMax", 5.0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.model.mesh.generate(2)
    boundaries = {
        "WELD_SHELL_INTERFACE": [abs(weld_shell)], "WELD_SEAT_INTERFACE": [abs(weld_seat)],
        "SEAT_GAP_FACE": [abs(seat_outer)], "SHELL_GAP_FACE": [abs(shell_gap)],
        "FIXTURE_BORE": [abs(fixture_bore)], "DATUM_B_SHELL_OUTER": [abs(datum_b)],
        "DATUM_A_SHELL_Z0": [abs(datum_a)],
    }
    return surfaces, boundaries


def _signed_six_volume(nodes, tetrahedra):
    p = nodes[tetrahedra]
    return np.einsum("ij,ij->i", np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), p[:, 3] - p[:, 0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cross-size", type=float, default=0.8)
    parser.add_argument("--arc-size", type=float, default=0.8)
    parser.add_argument("--output-stem", default="continuous-swept-plan6")
    args = parser.parse_args()
    if args.cross_size <= 0 or args.arc_size <= 0:
        parser.error("截面和环向尺寸必须为正")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1)
        surfaces, boundary_curves = _cross_section(args.cross_size)
        node_tags, coordinates, _ = gmsh.model.mesh.getNodes()
        order = np.argsort(node_tags)
        node_tags, cross_nodes = node_tags[order], coordinates.reshape(-1, 3)[order][:, :2]
        tag_to_index = {int(tag): index for index, tag in enumerate(node_tags)}
        region_triangles = []
        for surface in surfaces:
            _, connectivity = gmsh.model.mesh.getElementsByType(2, surface)
            region_triangles.append(np.vectorize(tag_to_index.__getitem__)(connectivity.reshape(-1, 3)))
        boundary_edges = {}
        for name, curves in boundary_curves.items():
            rows = []
            for curve in curves:
                _, connectivity = gmsh.model.mesh.getElementsByType(1, curve)
                rows.append(np.vectorize(tag_to_index.__getitem__)(connectivity.reshape(-1, 2)))
            boundary_edges[name] = np.vstack(rows)

        # 装配间隙只存在于未焊区；焊根处把座体上角点并到壳体根点，消除0.02 mm瘦棱柱。
        d_index = int(np.argmin(np.linalg.norm(cross_nodes - np.array([74.98, 12.0]), axis=1)))
        b_index = int(np.argmin(np.linalg.norm(cross_nodes - np.array([75.0, 12.0]), axis=1)))
        if np.linalg.norm(cross_nodes[d_index] - [74.98, 12.0]) > 1e-8 or np.linalg.norm(cross_nodes[b_index] - [75.0, 12.0]) > 1e-8:
            raise RuntimeError("未找到冻结焊根间隙端点")
        cross_nodes[d_index] = cross_nodes[b_index]
        for index, triangles in enumerate(region_triangles):
            triangles[triangles == d_index] = b_index
            region_triangles[index] = triangles[np.apply_along_axis(lambda row: len(set(row)) == 3, 1, triangles)]
        for name, edges in boundary_edges.items():
            edges[edges == d_index] = b_index
            boundary_edges[name] = edges[edges[:, 0] != edges[:, 1]]
        used = np.unique(np.concatenate([triangles.ravel() for triangles in region_triangles]))
        remap = np.full(len(cross_nodes), -1, dtype=int)
        remap[used] = np.arange(len(used))
        cross_nodes = cross_nodes[used]
        region_triangles = [remap[triangles] for triangles in region_triangles]
        boundary_edges = {name: remap[edges] for name, edges in boundary_edges.items()}

        layer_count = int(math.ceil(2 * math.pi * 75.0 / args.arc_size))
        theta = 2 * math.pi * np.arange(layer_count) / layer_count
        radius, axial = cross_nodes[:, 0], cross_nodes[:, 1]
        nodes = np.column_stack((
            (np.cos(theta)[:, None] * radius).ravel(),
            (np.sin(theta)[:, None] * radius).ravel(),
            np.broadcast_to(axial, (layer_count, len(axial))).ravel(),
        ))
        cross_count = len(cross_nodes)
        region_tetrahedra = []
        for triangles in region_triangles:
            blocks = []
            sorted_triangles = np.sort(triangles, axis=1)
            for layer in range(layer_count):
                lower = sorted_triangles + layer * cross_count
                upper = sorted_triangles + ((layer + 1) % layer_count) * cross_count
                a, b0, c0 = lower.T
                aa, bb, cc = upper.T
                blocks.extend((np.column_stack((a, b0, c0, cc)), np.column_stack((a, b0, bb, cc)), np.column_stack((a, aa, bb, cc))))
            tetrahedra = np.vstack(blocks)
            signed = _signed_six_volume(nodes, tetrahedra)
            negative = signed < 0
            tetrahedra[negative, :2] = tetrahedra[negative, 1::-1]
            region_tetrahedra.append(tetrahedra)

        # 复用同一节点建立离散体和边界面，保证接口两侧节点拓扑完全一致。
        gmsh.clear()
        gmsh.model.add(args.output_stem)
        all_node_tags = np.arange(1, len(nodes) + 1, dtype=np.int64)
        element_cursor = 1
        region_entities = []
        for entity, (name, tetrahedra) in enumerate(zip(REGIONS, region_tetrahedra), 1):
            gmsh.model.addDiscreteEntity(3, entity)
            if entity == 1:
                gmsh.model.mesh.addNodes(3, entity, all_node_tags, nodes.ravel())
            element_tags = np.arange(element_cursor, element_cursor + len(tetrahedra), dtype=np.int64)
            element_cursor += len(tetrahedra)
            gmsh.model.mesh.addElementsByType(entity, 4, element_tags, (tetrahedra + 1).ravel())
            gmsh.model.addPhysicalGroup(3, [entity], entity)
            gmsh.model.setPhysicalName(3, entity, name)
            region_entities.append(entity)
        surface_counts = {}
        for offset, (name, edges) in enumerate(boundary_edges.items(), 101):
            triangles = []
            low_edge = np.sort(edges, axis=1)
            for layer in range(layer_count):
                low = low_edge + layer * cross_count
                high = low_edge + ((layer + 1) % layer_count) * cross_count
                u, v = low.T; uu, vv = high.T
                triangles.extend((np.column_stack((u, v, vv)), np.column_stack((u, uu, vv))))
            triangles = np.vstack(triangles)
            gmsh.model.addDiscreteEntity(2, offset)
            tags = np.arange(element_cursor, element_cursor + len(triangles), dtype=np.int64)
            element_cursor += len(triangles)
            gmsh.model.mesh.addElementsByType(offset, 2, tags, (triangles + 1).ravel())
            gmsh.model.addPhysicalGroup(2, [offset], offset)
            gmsh.model.setPhysicalName(2, offset, name)
            surface_counts[name] = int(len(triangles))

        mesh_path = OUTPUT / f"{args.output_stem}.msh"
        gmsh.option.setNumber("Mesh.Binary", 1)
        gmsh.write(str(mesh_path))
        quality_by_region = {}
        all_quality = []
        region_counts = {}
        for name, entity in zip(REGIONS, region_entities):
            tags, _ = gmsh.model.mesh.getElementsByType(4, entity)
            quality = np.asarray(gmsh.model.mesh.getElementQualities(tags, "minSICN"), dtype=float)
            all_quality.append(quality); region_counts[name] = int(len(tags))
            quality_by_region[name] = {"minimum": float(quality.min()), "p01": float(np.percentile(quality, 1)), "below_0p1_count": int(np.count_nonzero(quality < 0.1))}
        quality = np.concatenate(all_quality)
        analytic_volume = {
            "Q235B_SHELL": math.pi * (80**2 - 75**2) * 200,
            "QT450_10_SEAT": math.pi * (74.98**2 - 20**2) * 12,
            "ERNIFE_CI_WELD": 2 * math.pi * 75 * (LEG_MM**2 / 2) - 2 * math.pi * (LEG_MM**3 / 6),
        }
        discrete_volume = {name: float(np.abs(_signed_six_volume(nodes, tets)).sum() / 6) for name, tets in zip(REGIONS, region_tetrahedra)}
        result = {
            "stage": "STRUCT-0-PREP-CONTINUOUS-SWEPT-MESH", "evidence_level": "geometry_and_mesh_preparation",
            "mesh_file": mesh_path.relative_to(ROOT).as_posix(),
            "topology": {"method": "axisymmetric_cross_section_circumferential_sweep", "prism_to_tet_rule": "global_cross_section_node_order_fixed_three_tet_split", "cross_section_node_count": cross_count, "circumferential_layers": layer_count, "arc_size_at_r75_mm": 2 * math.pi * 75 / layer_count},
            "regions": {"tetrahedron_counts": region_counts, "quality_by_region": quality_by_region},
            "interfaces": {"surface_triangle_counts": surface_counts, "conforming_by_construction": True},
            "geometry": {"analytic_volume_mm3": analytic_volume, "discrete_volume_mm3": discrete_volume, "relative_volume_error": {name: abs(discrete_volume[name] - analytic_volume[name]) / analytic_volume[name] for name in REGIONS}, "weld_root_gap_closure_mm": 0.02, "rule": "0.02 mm装配间隙保留在未焊接触面，在焊根共享节点处闭合；焊缝三角面积与路径不变"},
            "counts": {"nodes": int(len(nodes)), "tetrahedra": int(sum(region_counts.values()))},
            "quality": {"metric": "Gmsh minSICN", "minimum": float(quality.min()), "p01": float(np.percentile(quality, 1)), "nonpositive_count": int(np.count_nonzero(quality <= 0)), "below_0p1_count": int(np.count_nonzero(quality < 0.1))},
        }
        weld_bad = quality_by_region["ERNIFE_CI_WELD"]["below_0p1_count"]
        result["checks"] = {
            "three_material_regions": all(value > 0 for value in region_counts.values()), "interfaces_conforming": True,
            "no_inverted_tetrahedra": result["quality"]["nonpositive_count"] == 0,
            "weld_minSICN_below_0p1_zero": weld_bad == 0, "sets_intact": all(value > 0 for value in surface_counts.values()),
            "volume_unchanged_within_0p1_percent": max(result["geometry"]["relative_volume_error"].values()) < 1e-3,
        }
        result["mesh_acceptance_pass"] = all(result["checks"].values())
        report = OUTPUT / f"{args.output_stem}.json"
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(report), "counts": result["counts"], "quality": result["quality"], "checks": result["checks"]}, ensure_ascii=False))
    finally:
        gmsh.finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
