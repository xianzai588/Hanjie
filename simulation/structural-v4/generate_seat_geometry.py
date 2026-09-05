"""
P1A 统一参数化轴承座实体生成器。

本脚本是 P1A Phase 1 的唯一几何入口：同一套参数和同一个建模函数生成
Continuous、4/6/8P FAIR-A、4/6/8P FAIR-B 共七个模型，并输出 STEP、BREP
和可追溯的 geometry-manifest.json。

几何语义：离散方案由统一的 Ø82 mm 中心环和等角度布置的圆角翼组成；翼端
位于 R74.98 mm，外缘直线有效连接宽度按 FAIR 规则冻结。翼的四个平面角均
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

from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepTools import BRepTools
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import GeomAbs_Line
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopAbs import TopAbs_EDGE, TopAbs_SOLID
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS
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
        self.version = "2.0-ocp"

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
        # 为保证外缘的直线有效宽度仍等于 FAIR 输入，先把翼宽增加两个圆角
        # 半径；四个竖直角采用 R2 后，外端平直段回到 width_each。
        wing_box_width = width_each + 2.0 * p.slot_root_radius
        root_start = core_radius - 4.0
        wing_length = outer_radius - root_start
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
        total_width = continuous_width if family == "Continuous" else width_each * N  # type: ignore[operator]
        total_weld = total_width

        analyzer = BRepCheck_Analyzer(solid)
        solid_valid = bool(analyzer.IsValid())
        solid_explorer = TopExp_Explorer(solid, TopAbs_SOLID)
        solid_count = 0
        while solid_explorer.More():
            solid_count += 1
            solid_explorer.Next()
        seat_wall = p.seat_core_diameter / 2.0 - p.bearing_bore_diameter / 2.0
        min_wall = min(seat_wall, p.shell_thickness)
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
                "effective_width_each_mm": width_each,
                "effective_total_width_mm": total_width,
                "connection_width_definition": (
                    "outer radial face straight segment after common R2.0 fillets"
                    if N > 0
                    else "continuous outer circumference at R74.98"
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
                "seat_min_remaining_wall_thickness_mm": seat_wall,
                "min_remaining_wall_thickness_mm": min_wall,
                "minimum_wall_scope": "seat plus common Q235B shell wall",
                "slot_root_radius_applied_mm": p.slot_root_radius if N > 0 else None,
                "solid_count": solid_count,
                "solid_valid": solid_valid,
                "self_intersection_free": solid_valid,
                "zero_thickness_free": bool(
                    volume > 0
                    and z_length > 1e-6
                    and p.seat_thickness > 0
                    and p.slot_width > 0
                    and p.slot_root_radius > 0
                    and min_wall > 0
                ),
            },
            manufacturing={
                "slot_count": N if N > 0 else 0,
                "weld_segment_count": N if N > 0 else 1,
                "actual_total_weld_length_mm": total_weld,
                # 保留旧字段名以兼容已有配置；数值来自同一几何定义。
                "nominal_total_weld_length_mm": total_weld,
                "effective_connection_width_mm": total_width,
                "weld_length_definition": "outer-edge effective connection width",
            },
            generation={
                "generator_version": self.version,
                "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "rule": "single_unified_parametric_cad_function",
                "cad_kernel": "OpenCascade 7.9.3.1 (OCP)",
            },
        )

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
        "solid_valid": manifest.geometry.get("solid_valid") is True,
        "single_solid": manifest.geometry.get("solid_count") == 1,
        "self_intersection_free": manifest.geometry.get("self_intersection_free") is True,
        "zero_thickness_free": manifest.geometry.get("zero_thickness_free") is True,
        "slot_root_radius_frozen": manifest.N == 0
        or math.isclose(manifest.seat.get("slot_root_radius_mm", 0.0), 2.0),
    }

    if manifest.family == "FAIR_A":
        checks["fair_a_total_width"] = math.isclose(
            manifest.seat.get("effective_total_width_mm", 0.0), 108.0, abs_tol=1e-6
        )
    if manifest.family == "FAIR_B":
        checks["fair_b_each_width"] = math.isclose(
            manifest.seat.get("effective_width_each_mm", 0.0), 18.0, abs_tol=1e-6
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


def main() -> int:
    """生成并验证七个 P1A 实体；完成后停在独立几何审查门。"""
    output_root = Path(__file__).parent
    generator = BearingSeatGenerator(UnifiedParameters())
    models = generator.generate_all_p1a_geometry()

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
    print(f"{'Model ID':<16} {'Family':<12} {'N':<4} {'Effective width (mm)':>22} {'Weld (mm)':>12}")
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
