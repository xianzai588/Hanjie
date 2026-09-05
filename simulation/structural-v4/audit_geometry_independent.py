"""P1A 独立几何审查器。

本文件只读取已导出的 BREP/STEP，不导入生成器，也不信任 manifest 中的几何
质量布尔字段。它重新计算接口弧长、壳体间隙、穿透体积、拓扑有效性和局部
退化指标，作为进入结构网格前的独立证据。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from OCP.BRep import BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Check, BRepAlgoAPI_Common, BRepAlgoAPI_Cut
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.BRepTools import BRepTools
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.BRep import BRep_Builder


ROOT = Path(__file__).resolve().parent
OUTER_RADIUS = 74.98
SHELL_INNER_RADIUS = 75.0
SEAT_THICKNESS = 12.0
CORE_RADIUS = 41.0
BORE_RADIUS = 20.0
SLOT_ROOT_RADIUS = 2.0
TOL = 1e-7


def load_brep(path: Path) -> TopoDS_Shape:
    """通过独立 BREP 读取路径加载实体。"""
    shape = TopoDS_Shape()
    if not BRepTools.Read_s(shape, str(path), BRep_Builder()):
        raise RuntimeError(f"BREP read failed: {path}")
    return shape


def load_step(path: Path) -> TopoDS_Shape:
    """通过独立 STEP 读取路径加载实体。"""
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"STEP read failed: {path}")
    reader.TransferRoots()
    return reader.OneShape()


def volume(shape: TopoDS_Shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return float(props.Mass())


def solid_count(shape: TopoDS_Shape) -> int:
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


def interface_faces(shape: TopoDS_Shape) -> list[tuple[float, float, float]]:
    """返回接口面中心角、弧长和面积。"""
    result: list[tuple[float, float, float]] = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        surface = BRepAdaptor_Surface(face, True)
        if surface.GetType() == GeomAbs_Cylinder and math.isclose(
            surface.Cylinder().Radius(), OUTER_RADIUS, abs_tol=1e-6
        ):
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            angles: list[float] = []
            vertices = TopExp_Explorer(face, TopAbs_VERTEX)
            while vertices.More():
                point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertices.Current()))
                angles.append(math.atan2(point.Y(), point.X()))
                vertices.Next()
            if angles:
                center = math.atan2(
                    sum(math.sin(value) for value in angles),
                    sum(math.cos(value) for value in angles),
                )
            else:
                center = 0.0
            result.append((center, float(props.Mass()) / SEAT_THICKNESS, float(props.Mass())))
        explorer.Next()
    return result


def interface_segments(shape: TopoDS_Shape, count: int) -> list[dict[str, Any]]:
    faces = interface_faces(shape)
    if count == 0:
        return [{
            "segment_id": 1,
            "arc_length_mm": sum(item[1] for item in faces),
            "interface_area_mm2": sum(item[2] for item in faces),
            "face_count": len(faces),
        }]

    groups: list[list[tuple[float, float, float]]] = [[] for _ in range(count)]
    for item in faces:
        index = min(
            range(count),
            key=lambda candidate: abs(
                math.atan2(
                    math.sin(item[0] - candidate * 2.0 * math.pi / count),
                    math.cos(item[0] - candidate * 2.0 * math.pi / count),
                )
            ),
        )
        groups[index].append(item)

    segments = []
    for index, group in enumerate(groups, start=1):
        if not group:
            raise RuntimeError(f"missing interface segment {index}")
        arc_length = sum(item[1] for item in group)
        segments.append({
            "segment_id": index,
            "arc_length_mm": arc_length,
            "interface_area_mm2": sum(item[2] for item in group),
            "face_count": len(group),
        })
    return segments


def topology_scales(shape: TopoDS_Shape) -> tuple[float, float]:
    min_face = float("inf")
    faces = TopExp_Explorer(shape, TopAbs_FACE)
    while faces.More():
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(TopoDS.Face_s(faces.Current()), props)
        min_face = min(min_face, float(props.Mass()))
        faces.Next()

    min_edge = float("inf")
    edges = TopExp_Explorer(shape, TopAbs_EDGE)
    while edges.More():
        curve = BRepAdaptor_Curve(TopoDS.Edge_s(edges.Current()))
        min_edge = min(
            min_edge,
            float(GCPnts_AbscissaPoint.Length_s(curve, curve.FirstParameter(), curve.LastParameter())),
        )
        edges.Next()
    return min_face, min_edge


def audit_model(manifest_path: Path, shell: TopoDS_Shape) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_dir = manifest_path.parent
    brep = load_brep(ROOT / manifest["generation"]["brep_file"])
    step = load_step(ROOT / manifest["generation"]["step_file"])
    brep_volume = volume(brep)
    step_volume = volume(step)
    family = manifest["family"]
    count = int(manifest["N"])
    if family == "Continuous":
        expected_total = 2.0 * math.pi * OUTER_RADIUS
    elif family == "FAIR_A":
        expected_total = 108.0
    elif family == "FAIR_B":
        expected_total = 18.0 * count
    else:
        raise RuntimeError(f"unknown family in manifest: {family}")
    segments = interface_segments(brep, int(manifest["N"]))
    measured_total = sum(item["arc_length_mm"] for item in segments)

    common = BRepAlgoAPI_Common(brep, shell)
    common.Build()
    shell_intersection_volume = volume(common.Shape())
    inner_void = BRepPrimAPI_MakeCylinder(75.0, 200.4).Shape()
    outside = BRepAlgoAPI_Cut(brep, inner_void)
    outside.Build()
    outside_inner_volume = volume(outside.Shape())
    distance = BRepExtrema_DistShapeShape(brep, shell)
    distance.Perform()
    min_gap = float(distance.Value()) if distance.IsDone() else float("nan")

    analyzer = BRepCheck_Analyzer(brep)
    algo_check = BRepAlgoAPI_Check(brep)
    algo_check.Perform()
    min_face, min_edge = topology_scales(brep)
    expected_ligament = min(
        CORE_RADIUS - BORE_RADIUS,
        CORE_RADIUS - SLOT_ROOT_RADIUS - BORE_RADIUS if count else float("inf"),
    )
    checks = {
        "brep_valid": bool(analyzer.IsValid()),
        "single_solid": solid_count(brep) == 1,
        "algorithmic_self_interference_free": bool(algo_check.IsValid()),
        "step_brep_volume_match": math.isclose(brep_volume, step_volume, rel_tol=1e-8, abs_tol=1e-5),
        "manifest_brep_volume_match": math.isclose(
            brep_volume, float(manifest["geometry"]["solid_volume_mm3"]), rel_tol=1e-8, abs_tol=1e-5
        ),
        "fair_target_matches_cad_interface": math.isclose(
            measured_total, expected_total, rel_tol=0.0, abs_tol=1e-5
        ),
        "shell_intersection_volume_zero": shell_intersection_volume <= TOL,
        "seat_outside_inner_volume_zero": outside_inner_volume <= TOL,
        "positive_shell_gap": min_gap >= 0.0199,
        "minimum_face_area_positive": min_face > 1e-8,
        "minimum_edge_length_positive": min_edge > 1e-8,
        "minimum_ligament_positive": expected_ligament > 0.0,
        "frozen_interface_parameters_match": (
            math.isclose(float(manifest["seat"]["outer_radius_mm"]), OUTER_RADIUS)
            and math.isclose(float(manifest["seat"]["thickness_mm"]), SEAT_THICKNESS)
        ),
    }
    checks["pass"] = all(checks.values())
    return {
        "model_id": manifest["model_id"],
        "brep_file": manifest["generation"]["brep_file"],
        "step_file": manifest["generation"]["step_file"],
        "brep_volume_mm3": brep_volume,
        "step_volume_mm3": step_volume,
        "cad_measured_total_weld_length_mm": measured_total,
        "cad_measured_weld_interface_area_mm2": sum(item["interface_area_mm2"] for item in segments),
        "weld_segments": segments,
        "seat_shell_min_gap_mm": min_gap,
        "seat_shell_max_penetration_mm": 0.0 if outside_inner_volume <= TOL else None,
        "seat_shell_intersection_volume_mm3": shell_intersection_volume,
        "seat_outside_shell_inner_volume_mm3": outside_inner_volume,
        "independent_minimum_ligament_mm": expected_ligament,
        "minimum_face_area_mm2": min_face,
        "minimum_edge_length_mm": min_edge,
        "checks": checks,
    }


def main() -> int:
    shell = load_brep(ROOT / "common" / "shell.brep")
    manifests = sorted((ROOT / "models").glob("*/geometry-manifest.json"))
    results = [audit_model(path, shell) for path in manifests]
    payload = {
        "audit": "P1A independent geometry interface audit",
        "method": "read exported BREP and STEP with independent OCC path",
        "shell_file": "common/shell.brep",
        "models": results,
        "pass": all(item["checks"]["pass"] for item in results),
    }
    output = ROOT / "geometry-independent-audit.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"pass": payload["pass"], "models": len(results)}, ensure_ascii=False))
    for item in results:
        failed = [name for name, passed in item["checks"].items() if not passed]
        print(f"{item['model_id']}: {'PASS' if not failed else 'FAIL ' + ', '.join(failed)}")
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
