"""
P1A 统一参数化轴承座实体生成器。

本脚本是 P1A Phase 1 的唯一几何入口：同一套参数和同一个建模函数生成
Continuous、4/6/8P FAIR-A、4/6/8P FAIR-B 共七个模型，并输出 STEP、BREP
和可追溯的 geometry-manifest.json。

几何语义：离散方案由统一的 Ø82 mm 中心环和等角度布置的圆角翼组成；所有
座体点先与 R74.98 mm 圆柱求交，R74.98 因而是真实最大径向包络，而不是某个
平面端点坐标。FAIR 宽度冻结为该圆柱面上的焊接接口弧长。翼的四个平面角均
采用 R2.0 mm 圆角，避免用数学尖角代替槽根/连接过渡。Continuous 是同一
中心环向外延伸至 R74.98 mm 的连续环形基线。

本阶段只负责可复算实体和几何质量检查，不运行结构求解、热 FE 或候选排序。
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Dict, Optional

from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Check, BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepGProp import BRepGProp
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepTools import BRepTools
from OCP.Bnd import Bnd_Box
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Line
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool
from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec


@dataclass
class UnifiedParameters:
    """所有 P1A 实体共享的几何、材料和题面参数。"""

    # 壳体（题面固定）
    shell_outer_diameter: float = 160.0  # mm
    shell_height: float = 200.0  # mm
    shell_thickness: float = 5.0  # mm

    # 轴承座（V4 冻结）
    bearing_bore_diameter: float = 40.000  # mm，名义尺寸（FE 用）
    seat_thickness: float = 12.0  # mm
    seat_outer_radius: float = 74.98  # mm
    seat_core_diameter: float = 82.0  # mm

    # 离散翼/槽（P1A Phase 1 冻结）
    slot_width: float = 4.0  # mm，记录制造槽宽；翼之间的自由间隔由拓扑决定
    slot_root_radius: float = 2.0  # mm，统一公共圆角；不得按拓扑分别调参

    # 材料（V4 冻结）
    material_qr450_density: float = 7200.0  # kg/m³
    material_q235_density: float = 7850.0  # kg/m³


@dataclass
class GeometryManifest:
    """单个实体模型的参数、派生量、验证结果和文件索引。"""

    model_id: str
    family: str  # 'FAIR_A' / 'FAIR_B' / 'Continuous'
    layout: str  # '4P' / '6P' / '8P' / 'Continuous'
    N: int  # 连接点数量，0=Continuous
    shell: Dict[str, float]
    seat: Dict[str, Any]
    geometry: Dict[str, Any]
    manufacturing: Dict[str, Any]
    generation: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self, filepath: Path) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with filepath.open("w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, indent=2, ensure_ascii=False)
            handle.write("\n")


@dataclass
class GeneratedModel:
    """实体和其 manifest 的内部组合，避免用文件名替代几何对象。"""

    manifest: GeometryManifest
    shape: Any


class BearingSeatGenerator:
    """用同一个参数化函数生成 Continuous 与六个离散公平模型。"""

    def __init__(self, params: UnifiedParameters):
        self.params = params
        self.version = "2.1-ocp-cylindrical-interface"

    @staticmethod
    def _model_spec(N: int, family: str) -> tuple[str, str, Optional[float]]:
        """校验拓扑并返回布局、模型 ID 与外缘有效宽度。"""
        if family == "Continuous":
            if N != 0:
                raise ValueError("Continuous must have N=0")
            return "Continuous", "Continuous", None

        if family not in {"FAIR_A", "FAIR_B"}:
            raise ValueError(f"Unknown family: {family}")
        if N not in {4, 6, 8}:
            raise ValueError("Discrete P1A layouts require N in {4, 6, 8}")

        width_each = 108.0 / N if family == "FAIR_A" else 18.0
        return f"{N}P", f"{N}P-{family}", width_each

    def _build_shape(self, N: int, family: str, width_each: Optional[float]) -> Any:
        """构造真实 OCC 实体；Continuous 与离散方案共用中心环参数。"""
        p = self.params
        outer_radius = p.seat_outer_radius
        core_radius = p.seat_core_diameter / 2.0
        bore_radius = p.bearing_bore_diameter / 2.0

        if not outer_radius > core_radius > bore_radius > 0:
            raise ValueError("outer/core/bore radius ordering is invalid")
        if p.seat_thickness <= 0 or p.slot_root_radius <= 0:
            raise ValueError("seat thickness and slot root radius must be positive")

        if family == "Continuous":
            # 同一个中心环规则向外延伸，作为连续环形基线，而不是实心圆盘。
            return self._annular_solid(outer_radius, bore_radius, p.seat_thickness)

        assert width_each is not None
        root_start = core_radius - 4.0
        wing_length = outer_radius - root_start
        # width_each 是圆柱焊接接口的目标弧长。平面母体宽度通过同一套 OCC
        # 圆柱裁切几何反求，避免把弦长或平面端面宽度误当成焊缝长度。
        wing_box_width = self._solve_raw_wing_width(width_each, wing_length, root_start)
        if wing_box_width <= 2.0 * p.slot_root_radius or wing_length <= 2.0 * p.slot_root_radius:
            raise ValueError("discrete wing dimensions cannot accommodate R2.0 fillets")

        core = self._annular_solid(core_radius, bore_radius, p.seat_thickness)
        seat = core
        for index in range(N):
            # 从中心环内部起翼，保证融合是有面积的实体连接，而非相切拼接。
            wing = self._rounded_wing(
                wing_length,
                wing_box_width,
                p.seat_thickness,
                p.slot_root_radius,
                root_start,
                index * 360.0 / N,
            )
            fuse = BRepAlgoAPI_Fuse(seat, wing)
            fuse.Build()
            if not fuse.IsDone():
                raise RuntimeError(f"OCC fuse failed for discrete wing {index + 1}")
            seat = fuse.Shape()

        # 这是接口几何的关键约束：布尔交集后，翼端变成 R74.98 圆柱面，
        # 而不是保留沿 x 方向终止的平面端面。
        seat = self._clip_to_radial_envelope(seat, outer_radius, p.seat_thickness)

        # 在每个翼间隙的中线上切出真实 4 mm 径向槽。槽底由半径 2 mm
        # 的圆柱端帽形成，端帽中心落在中心环外缘，因而槽根最深到 R39 mm。
        # 这一步让 manifest 中的 R2.0 是实体几何，而不是仅有参数记录。
        for index in range(N):
            slot = self._rounded_slot_cutter(
                p.slot_width,
                p.slot_root_radius,
                outer_radius - core_radius + 4.0,
                p.seat_thickness + 0.4,
                core_radius,
                -0.2,
                (index + 0.5) * 360.0 / N,
            )
            cut = BRepAlgoAPI_Cut(seat, slot)
            cut.Build()
            if not cut.IsDone():
                raise RuntimeError(f"OCC rounded slot cut failed for slot {index + 1}")
            seat = cut.Shape()

        return seat

    def _clip_to_radial_envelope(self, shape: Any, radius: float, height: float) -> Any:
        """将实体裁切到真实圆柱包络内，保留圆柱共形焊接接口。"""
        envelope = BRepPrimAPI_MakeCylinder(radius, height + 0.4).Shape()
        envelope = self._transform(envelope, (0.0, 0.0, -0.2), 0.0)
        common = BRepAlgoAPI_Common(shape, envelope)
        common.Build()
        if not common.IsDone():
            raise RuntimeError("cylindrical radial envelope intersection failed")
        return common.Shape()

    def _solve_raw_wing_width(self, target_arc: float, length: float, root_start: float) -> float:
        """反求圆柱裁切前的平面母体宽度，使实测接口弧长等于 FAIR 目标。"""
        low = max(2.0 * self.params.slot_root_radius + 1e-6, target_arc * 0.5)
        high = target_arc + 2.0 * self.params.slot_root_radius + 2.0
        for _ in range(48):
            mid = 0.5 * (low + high)
            wing = self._rounded_wing(
                length,
                mid,
                self.params.seat_thickness,
                self.params.slot_root_radius,
                root_start,
                0.0,
            )
            clipped = self._clip_to_radial_envelope(
                wing, self.params.seat_outer_radius, self.params.seat_thickness
            )
            measured = self._outer_interface_length(clipped)
            if measured < target_arc:
                low = mid
            else:
                high = mid
        return 0.5 * (low + high)

    def _outer_interface_length(self, shape: Any) -> float:
        """从 R74.98 圆柱面的 OCC 面积读取接口弧长。"""
        total = 0.0
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            surface = BRepAdaptor_Surface(face, True)
            if (
                surface.GetType() == GeomAbs_Cylinder
                and math.isclose(
                    surface.Cylinder().Radius(), self.params.seat_outer_radius, abs_tol=1e-6
                )
            ):
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                total += float(props.Mass()) / self.params.seat_thickness
            explorer.Next()
        return total

    @staticmethod
    def _annular_solid(outer_radius: float, bore_radius: float, height: float) -> Any:
        """用 OCC 圆柱布尔差生成有孔环体。"""
        outer = BRepPrimAPI_MakeCylinder(outer_radius, height).Shape()
        inner = BRepPrimAPI_MakeCylinder(bore_radius, height).Shape()
        cut = BRepAlgoAPI_Cut(outer, inner)
        cut.Build()
        if not cut.IsDone():
            raise RuntimeError("OCC annulus cut failed")
        return cut.Shape()

    @staticmethod
    def _transform(shape: Any, translation: tuple[float, float, float], angle_deg: float) -> Any:
        """按先平移、后绕 Z 轴旋转的统一规则放置翼。"""
        translate = gp_Trsf()
        translate.SetTranslation(gp_Vec(*translation))
        moved = BRepBuilderAPI_Transform(shape, translate, True).Shape()

        rotate = gp_Trsf()
        rotate.SetRotation(
            gp_Ax1(gp_Pnt(0.0, 0.0, 0.0), gp_Dir(0.0, 0.0, 1.0)),
            math.radians(angle_deg),
        )
        return BRepBuilderAPI_Transform(moved, rotate, True).Shape()

    @classmethod
    def _rounded_wing(
        cls,
        length: float,
        width: float,
        height: float,
        radius: float,
        root_start: float,
        angle_deg: float,
    ) -> Any:
        """对翼的四条竖直棱做真实 OCC R2.0 圆角，再统一放置。"""
        box = BRepPrimAPI_MakeBox(length, width, height).Shape()
        fillet = BRepFilletAPI_MakeFillet(box)
        edge_map = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(box, TopAbs_EDGE, edge_map)
        vertical_edges = 0
        for edge_index in range(1, edge_map.Extent() + 1):
            edge = TopoDS.Edge_s(edge_map.FindKey(edge_index))
            curve = BRepAdaptor_Curve(edge)
            if curve.GetType() == GeomAbs_Line and abs(curve.Line().Direction().Z()) > 0.99:
                fillet.Add(radius, edge)
                vertical_edges += 1
        if vertical_edges != 4:
            raise RuntimeError(f"expected four vertical wing edges, got {vertical_edges}")
        fillet.Build()
        if not fillet.IsDone():
            raise RuntimeError("OCC R2.0 wing fillet failed")
        return cls._transform(fillet.Shape(), (root_start, -width / 2.0, 0.0), angle_deg)

    @classmethod
    def _rounded_slot_cutter(
        cls,
        width: float,
        radius: float,
        length: float,
        height: float,
        root_center: float,
        z_start: float,
        angle_deg: float,
    ) -> Any:
        """生成宽 4 mm、槽根 R2.0 mm 的径向圆头切刀。"""
        if not math.isclose(width, 2.0 * radius, abs_tol=1e-9):
            raise ValueError("the frozen slot geometry requires slot_width = 2 * root_radius")
        box = BRepPrimAPI_MakeBox(length, width, height).Shape()
        box = cls._transform(box, (0.0, -width / 2.0, 0.0), 0.0)
        cap = BRepPrimAPI_MakeCylinder(radius, height).Shape()
        fuse = BRepAlgoAPI_Fuse(box, cap)
        fuse.Build()
        if not fuse.IsDone():
            raise RuntimeError("OCC rounded slot cutter construction failed")
        return cls._transform(fuse.Shape(), (root_center, 0.0, z_start), angle_deg)

    def _manifest(
        self,
        N: int,
        family: str,
        layout: str,
        model_id: str,
        width_each: Optional[float],
        shape: Any,
    ) -> GeometryManifest:
        """从 OCC 实体读取派生量，不把手算值当作求解结果。"""
        p = self.params
        solid = shape
        volume_properties = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, volume_properties)
        volume = float(volume_properties.Mass())
        area = volume / p.seat_thickness
        outer_radius = p.seat_outer_radius
        continuous_width = 2.0 * math.pi * outer_radius
        fair_target_each = None if family == "Continuous" else width_each
        fair_target_total = continuous_width if family == "Continuous" else width_each * N  # type: ignore[operator]
        weld_segments = self._measure_weld_segments(solid, N, family)
        measured_weld = sum(segment["arc_length_mm"] for segment in weld_segments)
        measured_area = sum(segment["interface_area_mm2"] for segment in weld_segments)

        analyzer = BRepCheck_Analyzer(solid)
        brep_valid = bool(analyzer.IsValid())
        algo_check = BRepAlgoAPI_Check(solid)
        algo_check.Perform()
        algorithmic_self_interference_free = bool(algo_check.IsValid())
        solid_explorer = TopExp_Explorer(solid, TopAbs_SOLID)
        solid_count = 0
        while solid_explorer.More():
            solid_count += 1
            solid_explorer.Next()
        bore_radius = p.bearing_bore_diameter / 2.0
        core_radius = p.seat_core_diameter / 2.0
        seat_wall = core_radius - bore_radius
        slot_root_min_radius = core_radius - p.slot_root_radius if N > 0 else seat_wall + bore_radius
        min_seat_ligament = min(seat_wall, slot_root_min_radius - bore_radius)
        min_wall = min(min_seat_ligament, p.shell_thickness)
        min_face_area, min_edge_length = self._minimum_topological_scales(solid)
        max_radial = self._maximum_radial_envelope(solid, outer_radius)
        shell_shape = self._shell_shape()
        shell_common = BRepAlgoAPI_Common(solid, shell_shape)
        shell_common.Build()
        common_props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shell_common.Shape(), common_props)
        shell_intersection_volume = float(common_props.Mass())
        shell_distance = self._shape_distance(solid, shell_shape)
        shell_inner_radius = p.shell_outer_diameter / 2.0 - p.shell_thickness
        inner_void = BRepPrimAPI_MakeCylinder(
            shell_inner_radius, p.shell_height + 0.4
        ).Shape()
        inner_void = self._transform(inner_void, (0.0, 0.0, -0.2), 0.0)
        outside_inner = BRepAlgoAPI_Cut(solid, inner_void)
        outside_inner.Build()
        outside_props = GProp_GProps()
        BRepGProp.VolumeProperties_s(outside_inner.Shape(), outside_props)
        outside_inner_volume = float(outside_props.Mass())
        max_penetration = (
            0.0
            if outside_inner_volume <= 1e-8
            else max(0.0, max_radial - shell_inner_radius)
        )
        bbox = Bnd_Box()
        BRepBndLib.Add_s(solid, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        z_length = zmax - zmin

        return GeometryManifest(
            model_id=model_id,
            family=family,
            layout=layout,
            N=N,
            shell={
                "outer_diameter_mm": p.shell_outer_diameter,
                "height_mm": p.shell_height,
                "thickness_mm": p.shell_thickness,
            },
            seat={
                "bore_nominal_diameter_mm": p.bearing_bore_diameter,
                "thickness_mm": p.seat_thickness,
                "outer_radius_mm": p.seat_outer_radius,
                "core_diameter_mm": p.seat_core_diameter,
                "slot_width_mm": p.slot_width if N > 0 else None,
                "slot_root_radius_mm": p.slot_root_radius if N > 0 else None,
                "slot_root_profile": (
                    "R2.0 circular end cap at R41 centerline, deepest point R39"
                    if N > 0
                    else None
                ),
                "fair_target_width_each_mm": fair_target_each,
                "fair_target_total_width_mm": fair_target_total,
                # 兼容旧配置名；新语义明确为 CAD 实测接口弧长。
                "effective_width_each_mm": (
                    measured_weld / len(weld_segments) if weld_segments else 0.0
                ),
                "effective_total_width_mm": measured_weld,
                "connection_width_definition": (
                    "R74.98 cylindrical weld-interface arc length after R2.0 fillets"
                    if N > 0
                    else "continuous R74.98 cylindrical outer circumference"
                ),
            },
            geometry={
                "planform_area_mm2": area,
                "solid_volume_mm3": volume,
                "calculated_mass_kg": volume * 1e-9 * p.material_qr450_density,
                "bounding_box_mm": {
                    "x": float(xmax - xmin),
                    "y": float(ymax - ymin),
                    "z": float(zmax - zmin),
                },
                "seat_min_remaining_wall_thickness_mm": min_seat_ligament,
                "min_remaining_wall_thickness_mm": min_wall,
                "minimum_wall_scope": "seat slot-root ligament, bore ligament, and common Q235B shell wall",
                "bore_ligament_mm": seat_wall,
                "slot_root_min_radius_mm": slot_root_min_radius if N > 0 else None,
                "slot_root_radius_applied_mm": p.slot_root_radius if N > 0 else None,
                "solid_count": solid_count,
                "brep_valid": brep_valid,
                "solid_valid": brep_valid,
                "single_solid": solid_count == 1,
                "algorithmic_self_interference_free": algorithmic_self_interference_free,
                "self_intersection_free": algorithmic_self_interference_free,
                "minimum_face_area_mm2": min_face_area,
                "minimum_edge_length_mm": min_edge_length,
                "zero_thickness_free": bool(
                    volume > 0
                    and z_length > 1e-6
                    and p.seat_thickness > 0
                    and p.slot_width > 0
                    and p.slot_root_radius > 0
                    and min_seat_ligament > 0
                    and min_face_area > 1e-8
                    and min_edge_length > 1e-8
                ),
                "max_radial_envelope_mm": max_radial,
                "shell_inner_radius_mm": shell_inner_radius,
                "seat_shell_min_gap_mm": shell_distance,
                "seat_shell_max_penetration_mm": max_penetration,
                "seat_shell_intersection_volume_mm3": shell_intersection_volume,
                "seat_outside_shell_inner_volume_mm3": outside_inner_volume,
                "shell_interference_free": bool(
                    shell_intersection_volume <= 1e-8 and max_penetration <= 1e-8
                ),
            },
            manufacturing={
                "slot_count": N if N > 0 else 0,
                "weld_segment_count": len(weld_segments),
                "weld_segments": weld_segments,
                "cad_measured_total_weld_length_mm": measured_weld,
                "cad_measured_weld_interface_area_mm2": measured_area,
                # 保留旧字段名以兼容已有配置，但现在确实来自 CAD 接口测量。
                "actual_total_weld_length_mm": measured_weld,
                "nominal_total_weld_length_mm": fair_target_total,
                "effective_connection_width_mm": measured_weld,
                "weld_length_definition": "sum of R74.98 cylindrical interface arc lengths measured from OCC face area / seat thickness",
            },
            generation={
                "generator_version": self.version,
                "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "rule": "single_unified_parametric_cad_function",
                "cad_kernel": "OpenCascade 7.9.3.1 (OCP)",
            },
        )

    def _measure_weld_segments(self, shape: Any, N: int, family: str) -> list[Dict[str, Any]]:
        """从最终实体外圆柱面提取每个焊接段的弧长、面积和角度。"""
        faces: list[tuple[float, float, float]] = []
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        while explorer.More():
            face = TopoDS.Face_s(explorer.Current())
            surface = BRepAdaptor_Surface(face, True)
            if (
                surface.GetType() == GeomAbs_Cylinder
                and math.isclose(
                    surface.Cylinder().Radius(), self.params.seat_outer_radius, abs_tol=1e-6
                )
            ):
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                arc_length = float(props.Mass()) / self.params.seat_thickness
                angles: list[float] = []
                vertices = TopExp_Explorer(face, TopAbs_VERTEX)
                while vertices.More():
                    point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertices.Current()))
                    if math.hypot(point.X(), point.Y()) > 1e-6:
                        angles.append(math.atan2(point.Y(), point.X()))
                    vertices.Next()
                if angles:
                    sx = sum(math.cos(value) for value in angles)
                    sy = sum(math.sin(value) for value in angles)
                    center_angle = math.atan2(sy, sx)
                else:
                    center_angle = 0.0
                faces.append((center_angle, arc_length, float(props.Mass())))
            explorer.Next()

        if family == "Continuous":
            return [
                {
                    "segment_id": 1,
                    "start_angle_deg": -180.0,
                    "end_angle_deg": 180.0,
                    "arc_angle_deg": 360.0,
                    "arc_length_mm": sum(item[1] for item in faces),
                    "interface_area_mm2": sum(item[2] for item in faces),
                    "face_count": len(faces),
                }
            ]

        groups: list[list[tuple[float, float, float]]] = [[] for _ in range(N)]
        for item in faces:
            angle = item[0] % (2.0 * math.pi)
            index = min(
                range(N),
                key=lambda candidate: abs(
                    math.atan2(
                        math.sin(angle - candidate * 2.0 * math.pi / N),
                        math.cos(angle - candidate * 2.0 * math.pi / N),
                    )
                ),
            )
            groups[index].append(item)

        segments: list[Dict[str, Any]] = []
        for index, group in enumerate(groups, start=1):
            if not group:
                raise RuntimeError(f"no cylindrical weld interface found for segment {index}")
            center = (index - 1) * 360.0 / N
            arc_length = sum(item[1] for item in group)
            arc_angle = math.degrees(arc_length / self.params.seat_outer_radius)
            segments.append(
                {
                    "segment_id": index,
                    "start_angle_deg": center - arc_angle / 2.0,
                    "end_angle_deg": center + arc_angle / 2.0,
                    "arc_angle_deg": arc_angle,
                    "arc_length_mm": arc_length,
                    "interface_area_mm2": sum(item[2] for item in group),
                    "face_count": len(group),
                }
            )
        return segments

    @staticmethod
    def _minimum_topological_scales(shape: Any) -> tuple[float, float]:
        """用面面积和边曲线长度检查局部退化，而非只看总体积。"""
        min_face_area = float("inf")
        faces = TopExp_Explorer(shape, TopAbs_FACE)
        while faces.More():
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(TopoDS.Face_s(faces.Current()), props)
            min_face_area = min(min_face_area, float(props.Mass()))
            faces.Next()

        min_edge_length = float("inf")
        edges = TopExp_Explorer(shape, TopAbs_EDGE)
        while edges.More():
            curve = BRepAdaptor_Curve(TopoDS.Edge_s(edges.Current()))
            length = GCPnts_AbscissaPoint.Length_s(
                curve, curve.FirstParameter(), curve.LastParameter()
            )
            min_edge_length = min(min_edge_length, float(length))
            edges.Next()
        return min_face_area, min_edge_length

    @staticmethod
    def _maximum_radial_envelope(shape: Any, expected_outer_radius: float) -> float:
        """从面解析几何和顶点独立估计实体最大径向坐标。"""
        maximum = 0.0
        outer_face_radius = 0.0
        vertices = TopExp_Explorer(shape, TopAbs_VERTEX)
        while vertices.More():
            point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vertices.Current()))
            maximum = max(maximum, math.hypot(point.X(), point.Y()))
            vertices.Next()
        faces = TopExp_Explorer(shape, TopAbs_FACE)
        while faces.More():
            surface = BRepAdaptor_Surface(TopoDS.Face_s(faces.Current()), True)
            if surface.GetType() == GeomAbs_Cylinder:
                cylinder = surface.Cylinder()
                if math.isclose(cylinder.Radius(), expected_outer_radius, abs_tol=1e-6):
                    # 共形接口面本身给出精确包络；不能把被裁切的 R2
                    # 圆角母面完整圆柱半径误加到轴心距离上。
                    outer_face_radius = max(outer_face_radius, cylinder.Radius())
                else:
                    maximum = max(
                        maximum,
                        math.hypot(cylinder.Axis().Location().X(), cylinder.Axis().Location().Y())
                        + cylinder.Radius(),
                    )
            faces.Next()
        if outer_face_radius > 0.0:
            return outer_face_radius
        # 退化到网格节点包络，供没有显式圆柱接口的输入形状诊断。
        BRepMesh_IncrementalMesh(shape, 1e-4, True, 0.1, True)
        mesh_faces = TopExp_Explorer(shape, TopAbs_FACE)
        from OCP.TopLoc import TopLoc_Location

        while mesh_faces.More():
            triangulation = BRep_Tool.Triangulation_s(
                TopoDS.Face_s(mesh_faces.Current()), TopLoc_Location()
            )
            if triangulation is not None:
                for index in range(1, triangulation.NbNodes() + 1):
                    point = triangulation.Node(index)
                    maximum = max(maximum, math.hypot(point.X(), point.Y()))
            mesh_faces.Next()
        return maximum

    def _shell_shape(self) -> Any:
        """构造独立的 Q235B Ø160×t5 壳体实体。"""
        outer = BRepPrimAPI_MakeCylinder(
            self.params.shell_outer_diameter / 2.0, self.params.shell_height
        ).Shape()
        inner = BRepPrimAPI_MakeCylinder(
            self.params.shell_outer_diameter / 2.0 - self.params.shell_thickness,
            self.params.shell_height,
        ).Shape()
        cut = BRepAlgoAPI_Cut(outer, inner)
        cut.Build()
        if not cut.IsDone():
            raise RuntimeError("shell annulus construction failed")
        return cut.Shape()

    def _shape_distance(self, first: Any, second: Any) -> float:
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape

        distance = BRepExtrema_DistShapeShape(first, second)
        distance.Perform()
        if not distance.IsDone():
            raise RuntimeError("seat-shell distance calculation failed")
        return float(distance.Value())

    def generate_model(
        self,
        N: int,
        family: str,
        wing_width_each: Optional[float] = None,
    ) -> GeneratedModel:
        """生成一个真实实体及其 manifest；所有拓扑均走此函数。"""
        layout, model_id, computed_width = self._model_spec(N, family)
        # FAIR 宽度是规则的一部分，禁止调用者为单个拓扑注入不同数值。
        if family != "Continuous":
            if wing_width_each is not None and not math.isclose(
                wing_width_each, computed_width, rel_tol=0.0, abs_tol=1e-9
            ):
                raise ValueError("wing_width_each must match the frozen FAIR rule")
            wing_width_each = computed_width
        else:
            wing_width_each = None

        shape = self._build_shape(N, family, wing_width_each)
        manifest = self._manifest(N, family, layout, model_id, wing_width_each, shape)
        return GeneratedModel(manifest=manifest, shape=shape)

    def generate(
        self,
        N: int,
        family: str,
        wing_width_each: Optional[float] = None,
    ) -> GeometryManifest:
        """兼容旧调用接口：返回 manifest；实体生成仍由同一入口完成。"""
        return self.generate_model(N, family, wing_width_each).manifest

    def generate_all_p1a_models(self) -> Dict[str, GeometryManifest]:
        """生成 P1A 七个模型的 manifest，不启动任何结构求解。"""
        return {
            model_id: self.generate(N, family)
            for model_id, N, family in [
                ("Continuous", 0, "Continuous"),
                ("4P-FAIR_A", 4, "FAIR_A"),
                ("4P-FAIR_B", 4, "FAIR_B"),
                ("6P-FAIR_A", 6, "FAIR_A"),
                ("6P-FAIR_B", 6, "FAIR_B"),
                ("8P-FAIR_A", 8, "FAIR_A"),
                ("8P-FAIR_B", 8, "FAIR_B"),
            ]
        }

    def generate_all_p1a_geometry(self) -> Dict[str, GeneratedModel]:
        """生成 P1A 七个真实实体；这是 Phase 1 的批量唯一入口。"""
        return {
            model_id: self.generate_model(N, family)
            for model_id, N, family in [
                ("Continuous", 0, "Continuous"),
                ("4P-FAIR_A", 4, "FAIR_A"),
                ("4P-FAIR_B", 4, "FAIR_B"),
                ("6P-FAIR_A", 6, "FAIR_A"),
                ("6P-FAIR_B", 6, "FAIR_B"),
                ("8P-FAIR_A", 8, "FAIR_A"),
                ("8P-FAIR_B", 8, "FAIR_B"),
            ]
        }


def validate_geometry_manifest(manifest: GeometryManifest) -> Dict[str, bool]:
    """验证参数、派生量和实体质量检查；返回可审计的逐项结果。"""
    checks: Dict[str, bool] = {
        "has_model_id": bool(manifest.model_id),
        "has_family": manifest.family in {"FAIR_A", "FAIR_B", "Continuous"},
        "has_layout": bool(manifest.layout),
        "N_valid": manifest.N == 0
        if manifest.family == "Continuous"
        else manifest.N in {4, 6, 8},
        "shell_od_valid": manifest.shell.get("outer_diameter_mm") == 160.0,
        "shell_height_valid": manifest.shell.get("height_mm") == 200.0,
        "shell_thickness_valid": manifest.shell.get("thickness_mm") == 5.0,
        "bore_valid": manifest.seat.get("bore_nominal_diameter_mm") == 40.0,
        "thickness_valid": manifest.seat.get("thickness_mm") == 12.0,
        "outer_radius_valid": manifest.seat.get("outer_radius_mm") == 74.98,
        "volume_computed": float(manifest.geometry.get("solid_volume_mm3", 0.0)) > 0.0,
        "mass_computed": float(manifest.geometry.get("calculated_mass_kg", 0.0)) > 0.0,
        "weld_length_computed": float(
            manifest.manufacturing.get("actual_total_weld_length_mm", 0.0)
        )
        > 0.0,
        "brep_valid": manifest.geometry.get("brep_valid") is True,
        "solid_valid": manifest.geometry.get("solid_valid") is True,
        "single_solid": manifest.geometry.get("single_solid") is True
        and manifest.geometry.get("solid_count") == 1,
        "algorithmic_self_interference_free": manifest.geometry.get(
            "algorithmic_self_interference_free"
        )
        is True,
        "self_intersection_free": manifest.geometry.get("self_intersection_free") is True,
        "zero_thickness_free": manifest.geometry.get("zero_thickness_free") is True,
        "shell_interference_free": manifest.geometry.get("shell_interference_free") is True,
        "radial_envelope_clear": float(
            manifest.geometry.get("seat_shell_max_penetration_mm", 1.0)
        )
        <= 1e-8,
        "minimum_ligament_positive": float(
            manifest.geometry.get("seat_min_remaining_wall_thickness_mm", 0.0)
        )
        > 0.0,
        "slot_root_radius_frozen": manifest.N == 0
        or math.isclose(manifest.seat.get("slot_root_radius_mm", 0.0), 2.0),
    }

    target_total = float(manifest.seat.get("fair_target_total_width_mm", 0.0))
    measured_total = float(manifest.manufacturing.get("cad_measured_total_weld_length_mm", 0.0))
    checks["fair_target_matches_cad_interface"] = math.isclose(
        measured_total, target_total, abs_tol=1e-5
    )
    if manifest.family == "FAIR_A":
        checks["fair_a_total_target"] = math.isclose(target_total, 108.0, abs_tol=1e-6)
    if manifest.family == "FAIR_B":
        checks["fair_b_each_target"] = math.isclose(
            float(manifest.seat.get("fair_target_width_each_mm", 0.0)), 18.0, abs_tol=1e-6
        )
    return checks


def _model_directory_name(model_id: str) -> str:
    """使用已有目录命名约定，避免 Windows 大小写冲突。"""
    return model_id.lower().replace("_", "-")


def export_model(model: GeneratedModel, output_root: Path) -> GeometryManifest:
    """导出一个实体的 STEP、BREP 和 geometry-manifest.json。"""
    manifest = model.manifest
    model_dir = output_root / "models" / _model_directory_name(manifest.model_id)
    model_dir.mkdir(parents=True, exist_ok=True)

    step_path = model_dir / f"{manifest.model_id}.step"
    brep_path = model_dir / f"{manifest.model_id}.brep"
    manifest_path = model_dir / "geometry-manifest.json"

    step_writer = STEPControl_Writer()
    step_writer.Transfer(model.shape, STEPControl_AsIs)
    if step_writer.Write(str(step_path)) != IFSelect_RetDone:
        raise RuntimeError(f"STEP export failed: {step_path}")
    if not BRepTools.Write_s(model.shape, str(brep_path)):
        raise RuntimeError(f"BREP export failed: {brep_path}")

    manifest.generation.update(
        {
            "step_file": step_path.relative_to(output_root).as_posix(),
            "brep_file": brep_path.relative_to(output_root).as_posix(),
            "manifest_file": manifest_path.relative_to(output_root).as_posix(),
        }
    )
    manifest.to_json(manifest_path)
    return manifest


def export_shell(generator: BearingSeatGenerator, output_root: Path) -> Dict[str, Any]:
    """导出独立壳体实体，供后续接口和干涉审查复用。"""
    common_dir = output_root / "common"
    common_dir.mkdir(parents=True, exist_ok=True)
    shell = generator._shell_shape()
    step_path = common_dir / "shell.step"
    brep_path = common_dir / "shell.brep"
    manifest_path = common_dir / "shell-manifest.json"
    writer = STEPControl_Writer()
    writer.Transfer(shell, STEPControl_AsIs)
    if writer.Write(str(step_path)) != IFSelect_RetDone:
        raise RuntimeError(f"shell STEP export failed: {step_path}")
    if not BRepTools.Write_s(shell, str(brep_path)):
        raise RuntimeError(f"shell BREP export failed: {brep_path}")
    analyzer = BRepCheck_Analyzer(shell)
    payload = {
        "outer_diameter_mm": generator.params.shell_outer_diameter,
        "inner_diameter_mm": generator.params.shell_outer_diameter
        - 2.0 * generator.params.shell_thickness,
        "height_mm": generator.params.shell_height,
        "thickness_mm": generator.params.shell_thickness,
        "brep_valid": bool(analyzer.IsValid()),
        "step_file": step_path.relative_to(output_root).as_posix(),
        "brep_file": brep_path.relative_to(output_root).as_posix(),
    }
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    """生成并验证七个 P1A 实体；完成后停在独立几何审查门。"""
    output_root = Path(__file__).parent
    generator = BearingSeatGenerator(UnifiedParameters())
    models = generator.generate_all_p1a_geometry()
    shell_manifest = export_shell(generator, output_root)
    print(
        "Shell exported: "
        f"OD={shell_manifest['outer_diameter_mm']:.2f} mm, "
        f"ID={shell_manifest['inner_diameter_mm']:.2f} mm"
    )

    all_valid = True
    print("Generating seven P1A CAD solids...")
    for model_id, model in models.items():
        manifest = export_model(model, output_root)
        config_path = output_root / "configs" / f"{model_id.replace('_', '-')}.json"
        manifest.to_json(config_path)
        checks = validate_geometry_manifest(manifest)
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            all_valid = False
            print(f"  [FAIL] {model_id}: {', '.join(failed)}")
        else:
            print(
                f"  [PASS] {model_id}: V={manifest.geometry['solid_volume_mm3']:.3f} mm3, "
                f"m={manifest.geometry['calculated_mass_kg']:.6f} kg, "
                f"weld={manifest.manufacturing['actual_total_weld_length_mm']:.3f} mm"
            )

    print("\nP1A geometry summary")
    print(f"{'Model ID':<16} {'Family':<12} {'N':<4} {'CAD interface (mm)':>22} {'Weld (mm)':>12}")
    print("-" * 72)
    for model_id, model in models.items():
        manifest = model.manifest
        width = manifest.seat["effective_total_width_mm"]
        print(
            f"{model_id:<16} {manifest.family:<12} {manifest.N:<4} "
            f"{width:>22.3f} {manifest.manufacturing['actual_total_weld_length_mm']:>12.3f}"
        )

    if not all_valid:
        print("\n[ERROR] Geometry validation failed; do not enter P1A structural screening.")
        return 1

    print("\n[SUCCESS] Seven CAD solids exported and self-checked.")
    print("[HOLD] Stop here for independent geometry audit before any structural solve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
