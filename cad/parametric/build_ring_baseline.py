"""Build the complete-ring nominal baseline and its engineering drawing.

This model contains only the QT450-10 seat and Q235B shell.  Welds and the
two-layer precoat are separate process designs, rather than bonded solids
silently inserted into this nominal assembly.  STEP solids are re-read and
checked after export.  Run from any directory with Python + OCP installed.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from xml.sax.saxutils import escape
from PIL import Image

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire, BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeRevol
from OCP.GC import GC_MakeArcOfCircle
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cad/generated/ring-baseline"
NOMINAL = {
    "seat_inner_radius_mm": 20.0,
    "seat_outer_radius_mm": 74.98,
    "seat_bottom_z_mm": 100.0,
    "seat_thickness_mm": 15.0,
    "shell_inner_radius_mm": 75.0,
    "shell_outer_radius_mm": 80.0,
    "shell_bottom_z_mm": 0.0,
    "shell_height_mm": 200.0,
    "bore_axis_position_tolerance_diameter_mm": 0.05,
}
DENSITIES = {"QT450-10": 7200.0, "Q235B": 7850.0}


def volume(shape):
    prop = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, prop)
    return float(prop.Mass())


def annulus(inner, outer, bottom, height):
    axis = gp_Ax2(gp_Pnt(0.0, 0.0, bottom), gp_Dir(0.0, 0.0, 1.0))
    operation = BRepAlgoAPI_Cut(
        BRepPrimAPI_MakeCylinder(axis, outer, height).Shape(),
        BRepPrimAPI_MakeCylinder(axis, inner, height).Shape(),
    )
    operation.Build()
    if not operation.IsDone() or not BRepCheck_Analyzer(operation.Shape()).IsValid():
        raise RuntimeError("Invalid annular solid")
    return operation.Shape()


def export_step(path, shapes):
    writer = STEPControl_Writer()
    # Transfer individual solids so the two assembly components stay distinct.
    for shape in shapes:
        if writer.Transfer(shape, STEPControl_AsIs) != IFSelect_RetDone:
            raise RuntimeError(f"STEP transfer failed: {path.name}")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"STEP export failed: {path.name}")


def recheck_step(path, expected):
    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f"Cannot reopen {path.name}")
    if not reader.TransferRoots():
        raise RuntimeError(f"Cannot transfer {path.name}")
    shape = reader.OneShape()
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    solids = []
    while explorer.More():
        current = explorer.Current()
        solids.append({"valid": bool(BRepCheck_Analyzer(current).IsValid()),
                       "volume_mm3": volume(current)})
        explorer.Next()
    if len(solids) != expected or not all(row["valid"] for row in solids):
        raise RuntimeError(f"{path.name}: expected {expected} valid solids, got {solids}")
    return {"file": path.name, "solid_count": len(solids),
            "all_solids_valid": True, "solids": solids}


def pocket_sector(offset, angular_span, angle):
    """R1.5 concave inner-bottom pocket; offset preserves normal first layer."""
    inner, outer, top, radius, depth = 68.98, 74.98, 115.0, 1.5, 1.5
    cr, cz = inner + radius, top - depth + radius
    r = radius - offset
    pts = [gp_Pnt(cr-r, 0, top), gp_Pnt(outer, 0, top),
           gp_Pnt(outer, 0, cz-r), gp_Pnt(cr, 0, cz-r)]
    wire = BRepBuilderAPI_MakeWire()
    for i in range(3):
        wire.Add(BRepBuilderAPI_MakeEdge(pts[i], pts[i+1]).Edge())
    middle = gp_Pnt(cr-r/math.sqrt(2), 0, cz-r/math.sqrt(2))
    wire.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(pts[3], middle, pts[0]).Value()).Edge())
    face = BRepBuilderAPI_MakeFace(wire.Wire()).Face()
    solid = BRepPrimAPI_MakeRevol(face, gp_Ax1(gp_Pnt(0,0,0), gp_Dir(0,0,1)), angular_span).Shape()
    transform = gp_Trsf()
    transform.SetRotation(gp_Ax1(gp_Pnt(0,0,0), gp_Dir(0,0,1)), angle-angular_span/2)
    result = BRepBuilderAPI_Transform(solid, transform, True).Shape()
    if not BRepCheck_Analyzer(result).IsValid():
        raise RuntimeError("Invalid precoat sector")
    return result


def trajectory_control():
    """Measured-window guidance keeps fixed protection dimensions effective."""
    return {
        "basis": "Measure each machined pocket before precoat; use its own inner/outer radius and angular end faces",
        "measured_fields": ["inner_radius_mm", "outer_radius_mm", "window_start_angle_rad", "window_stop_angle_rad"],
        "inner_track_radius_formula": "measured_inner_radius_mm + 1.0",
        "center_track_radius_formula": "(measured_inner_radius_mm + measured_outer_radius_mm) / 2",
        "outer_track_radius_formula": "measured_outer_radius_mm - 1.0",
        "track_start_stop_angle": "Use measured window_start_angle_rad/window_stop_angle_rad for all three tracks, rather than the fixed nominal 24/71.98 angle",
        "protection_geometry": "Inner-land protection 0.5mm normal to actual inner edge; terminal protection 1.5mm normal to each measured terminal face. Protection is not enlarged.",
        "actual_pitch_range_mm": [1.95, 2.05],
        "minimum_effective_bead_width_formula_mm": "max(2.8, maximum_measured_adjacent_track_pitch_mm + 0.8)",
        "maximum_effective_bead_width_mm": 3.0,
        "wide_6_1mm_window_required_width_min_mm": 2.85,
        "nominal_track_radii_mm": [69.98, 71.98, 73.98],
        "nominal_three_track_length_one_window_mm": 72.0,
        "nominal_three_track_length_eight_windows_mm": 576.0,
        "nominal_accounting_scope": "72/576mm and their mass/arc-time/net-heat quantities refer to nominal 24mm windows; actual track lengths, supply and arc times are recorded and evaluated with the same formulas for each measured window",
        "qualification": "First-piece macrosections confirm inner corner, terminal coverage, full radial coverage and overlap >=0.8mm on the measured-window path; verify contour and retained layers for each window",
        "STEP_scope": "The 17-solid STEP is the nominal flush-machined retained-material partition, not a simulation of the melt-pool process at every tolerance corner",
    }


def ring_precoat(output, seat):
    """Freeze eight local windows and calculate their own precoat inputs."""
    theta = 24.0 / 71.98
    # Unlike an open wing, a complete ring has two QT terminal walls.
    # Keep >=0.70mm first-layer normal coverage on both walls so the second
    # material cannot create a finite-face bypass directly onto QT.
    second_theta = theta - 2 * 0.70 / 68.98
    qt = seat
    first, second, pockets = [], [], []
    for i in range(8):
        full = pocket_sector(0, theta, i*math.pi/4)
        upper = pocket_sector(.70, second_theta, i*math.pi/4)
        cut = BRepAlgoAPI_Cut(full, upper)
        cut.Build()
        if not cut.IsDone() or not BRepCheck_Analyzer(cut.Shape()).IsValid():
            raise RuntimeError("Invalid retained first-layer geometry")
        first.append(cut.Shape()); second.append(upper); pockets.append(full)
        cut_qt = BRepAlgoAPI_Cut(qt, full)
        cut_qt.Build()
        if not cut_qt.IsDone():
            raise RuntimeError("Cannot cut precoat window into complete ring")
        qt = cut_qt.Shape()
    export_step(output / "ring-precoat-eight-windows-17solids.step", [qt, *first, *second])
    check = recheck_step(output / "ring-precoat-eight-windows-17solids.step", 17)
    totals = {"QT450-10": volume(qt), "first_CI_A1_retained": sum(map(volume, first)),
              "second_Ni_retained": sum(map(volume, second))}
    closure = sum(totals.values())-volume(seat)
    if abs(closure)/volume(seat) > 1e-7:
        raise RuntimeError("Precoat partition does not close on nominal ring")
    # Distance is zero on shared edges; finite-face bypass is checked by
    # geometric common area, rather than interpreting zero distance as fusion.
    bypass_area = 0.0
    for upper in second:
        common = BRepAlgoAPI_Common(qt, upper)
        common.Build()
        if not common.IsDone():
            raise RuntimeError("Cannot check second-layer/QT bypass")
        prop = GProp_GProps()
        BRepGProp.SurfaceProperties_s(common.Shape(), prop)
        bypass_area += prop.Mass()
    if bypass_area > 1e-5:
        raise RuntimeError(f"Second layer directly touches QT over {bypass_area}mm2")
    rho = 8.89e-3  # g/mm3, engineering Ni density for supply screening
    maximum_envelope = 24.5*6.1*(1.60+.20)
    required_mass = maximum_envelope*rho
    # Temporary first-Ni protection outside the inner land and both ends.
    # It remains during second-layer welding, then is removed at final flush machining.
    protection_volume = ((24.5*.5+2*6.1*1.5)+math.pi*.5*1.5/2)*.75
    total_first_target = required_mass+protection_volume*rho
    choices = []
    for speed in (75.,80.,90.,100.):
        time = 24./(speed*1.02/60.)
        equivalent = time-1.2*(1-(110+80)/(2*110))
        mass = .15*equivalent
        choices.append({"speed_mm_min": speed, "speed_plus_2_percent_arc_time_s": time,
                        "ramp_current_equivalent_time_s": equivalent,
                        "low_supply_mass_g": mass,
                        "max_envelope_with_0_2mm_overfill_mass_g": required_mass,
                        "mass_margin_g": mass-required_mass,
                        "covers_maximum_envelope": mass>=required_mass})
    independent_corners = []
    protective_equivalent_time = .5+.5*80/110
    for speed in (75.,80.,90.,100.):
        tmin = 23.5/(speed*1.02/60.)
        main_mass = .15*(tmin-1.2*(1-(110+80)/(2*110)))
        massmin = main_mass+.15*protective_equivalent_time
        independent_corners.append({"speed_mm_min":speed,"shortest_window_arc_mm":23.5,
                                    "speed_plus_2_percent_arc_time_s":tmin,
                                    "main_arc_low_supply_mass_g":main_mass,
                                    "protective_start_stop_arc_time_s":1.,
                                    "low_supply_mass_g":massmin,
                                    "maximum_long_window_envelope_and_protection_target_g":total_first_target,
                                    "margin_g":massmin-total_first_target,
                                    "relative_margin":massmin/total_first_target-1,
                                    "covers_independent_envelope":massmin>=total_first_target})
    first_main_time = 24./(75./60.)
    first_time = first_main_time+1.
    equivalent = first_main_time-1.2*(1-(110+80)/(2*110))+protective_equivalent_time
    first_mass = {"low": .15*equivalent,"nominal": .16*equivalent,"high": .17*equivalent}
    first_heat = .8*23*110*equivalent
    radii = [69.98,71.98,73.98]
    lengths = [r*theta for r in radii]
    second_time = sum(lengths)/2.
    second_volume = {
        "low": math.pi*1.18**2/4*7.0*.90*second_time,
        "nominal": math.pi*1.20**2/4*7.2*.94*second_time,
        "high": math.pi*1.22**2/4*7.4*.98*second_time,
    }
    second_heat = .60*75*11*second_time
    maximum_area = 24.5*6.1
    minimum_average = second_volume["low"]/maximum_area
    extended_area = (24.5+2*1.5)*(6.1+2*.5)
    resources = []
    for interval in (3600.,240.):
        per_stage = math.ceil(36000/interval)
        delay = math.ceil(86400/interval)
        resources.append({"target_supply_interval_s": interval,
                          "planned_residence_each_precoat_stage_s":36000,
                          "in_process_positions_each_stage":per_stage,
                          "planned_delay_PT_residence_s":86400,
                          "delay_positions":delay,
                          "total_precoat_and_delay_positions":2*per_stage+delay})
    plan = {
        "card": "HJ-S01", "model_id": "ring-eight-local-precoat-windows",
        "geometry": {"window_count":8,"window_center_radius_mm":71.98,
                     "window_arc_length_at_center_mm":24.,"arc_length_tolerance_mm":.5,
                     "window_angle_rad":theta,"radial_width_mm":6.,"width_tolerance_mm":.1,
                     "pocket_depth_mm":1.5,"depth_tolerance_mm":.1,"inner_bottom_radius_mm":1.5,
                     "outer_edge_radius_mm":74.98,"window_opens_through_outer_edge":True,
                     "seat_thickness_mm":15.,"minimum_QT_bottom_ligament_mm":13.4,
                     "effective_connection_length_mm":18.,"actual_final_path_length_mm":20.,
                     "first_retained_normal_mm":.7,"first_retained_tolerance_mm":.05,
                     "first_terminal_wall_normal_min_nominal_mm":.7,
                     "second_terminal_inset_angle_rad":.7/68.98,
                     "nominal_second_inner_corner_radius_mm":.8,
                     "second_QT_finite_face_contact_area_mm2":bypass_area,
                     "retained_material_volumes_mm3":totals,
                     "nominal_pocket_volume_per_window_mm3":volume(pockets[0]),
                     "partition_closure_error_mm3":closure,"STEP_reopen_check":check},
        "first_layer": {"material":"CI-A1 / ENi-CI coated electrode","electrode_core_diameter_mm":3.2,
                        "current_A":110,"voltage_V":23,"net_efficiency_design_assumption":.8,
                        "speed_mm_min":75,"speed_tolerance_relative":.02,
                        "diagnostic_supply_g_s":[.15,.17],
                        "last_1_2s_current_A":[110,80],"supply_scales_with_current":True,
                        "main_arc_time_one_window_s":first_main_time,
                        "protective_start_arc_time_s":.5,"protective_start_current_A":110,
                        "protective_stop_arc_time_s":.5,"protective_stop_current_A":80,
                        "protective_start_stop_equivalent_time_s":protective_equivalent_time,
                        "protective_arc_scope":"Controlled start/end coverage before final pore machining; actual travel and supply are recorded. Extra arc time does not replace continuous fused-interface acceptance.",
                        "arc_time_one_window_s":first_time,"arc_time_eight_windows_s":8*first_time,
                        "current_equivalent_time_one_window_s":equivalent,
                        "mass_one_window_g":first_mass,
                        "mass_eight_windows_g":{k:8*v for k,v in first_mass.items()},
                        "net_heat_one_window_J":first_heat,"net_heat_eight_windows_J":8*first_heat,
                        "density_basis_g_mm3":rho,"maximum_rectangular_envelope_mm3":maximum_envelope,
                        "maximum_envelope_target_mass_g":required_mass,
                        "temporary_inner_land_protection_width_mm":.5,
                        "temporary_terminal_protection_length_mm":1.5,
                        "temporary_protection_maximum_volume_mm3":protection_volume,
                        "temporary_protection_maximum_mass_g":protection_volume*rho,
                        "total_envelope_and_protection_target_mass_g":total_first_target,
                        "shortest_path_plus_2_percent_main_arc_low_supply_mass_g":independent_corners[0]["main_arc_low_supply_mass_g"],
                        "shortest_path_plus_2_percent_low_supply_mass_g":independent_corners[0]["low_supply_mass_g"],
                        "shortest_path_independent_envelope_margin_g":independent_corners[0]["margin_g"],
                        "independent_corner_speed_choice":independent_corners,
                        "corner_scope":"Shortest arc controls minimum supply; longest/widest/deepest pocket controls required envelope. Combining their independent extremes is a conservative design screen, not a claim that one actual window simultaneously has both lengths.",
                        "speed_choice_screen":choices,
                        "motion":"Controlled small weaving covers the full 6mm pocket bottom and inner-land protection; arc start/end coverage is checked locally",
                        "acceptance":"First-piece and each-batch cold weighing qualifies deposited supply; inspect >=0.20mm overfill and all temporary inner/end protection on each window. Retain first-Ni protection until second welding, then remove at final flush machining. Actual material chemistry and dilution govern retained-layer properties"},
        "second_layer": {"material":"Low-carbon bare Ni alloy rod","current_A":75,"voltage_V":11,
                         "net_efficiency_design_assumption":.60,"speed_mm_s":2.,
                         "track_radii_mm":radii,"common_track_angle_rad":theta,
                         "trajectory_control":trajectory_control(),
                         "track_lengths_mm":lengths,"total_track_length_one_window_mm":sum(lengths),
                         "arc_time_one_window_s":second_time,"arc_time_eight_windows_s":8*second_time,
                         "wire_diameter_mm":1.2,"wire_diameter_tolerance_mm":.02,
                         "feed_mm_s":7.2,"feed_tolerance_mm_s":.2,"deposit_efficiency_range":[.90,.98],
                         "deposit_volume_one_window_mm3":second_volume,
                         "deposit_mass_one_window_g":{k:v*rho for k,v in second_volume.items()},
                         "deposit_mass_eight_windows_g":{k:8*v*rho for k,v in second_volume.items()},
                         "net_heat_one_window_J":second_heat,"net_heat_eight_windows_J":8*second_heat,
                         "target_effective_bead_width_min_mm":2.8,
                         "controlled_effective_bead_width_range_mm":[2.8,3.0],
                         "center_track_spacing_mm":2.,"minimum_overlap_mm":.8,
                         "radial_coverage_check":"Nominal radii describe the nominal window. Actual inner/outer tracks are 1.0mm from measured edges, center track is at measured mid-radius, and the angles follow measured terminal faces; width is max(2.8mm, measured pitch+0.8mm) and <=3.0mm",
                         "minimum_average_added_height_on_maximum_area_mm":minimum_average,
                         "minimum_total_after_first_retained_0_65_average_mm":.65+minimum_average,
                         "conservative_extended_deposit_area_mm2":extended_area,
                         "minimum_average_added_height_including_edge_overhang_mm":second_volume["low"]/extended_area,
                         "required_added_volume_for_1_75mm_total_on_extended_area_mm3":(1.75-.65)*extended_area,
                         "minimum_total_before_final_machining_mm":1.75,
                         "finished_total_layer_range_mm":[1.4,1.6],"finished_second_layer_min_mm":.65,
                         "acceptance":"Actual local contour >=1.75mm above measured pocket bottom, overlap >=0.8mm, no uncovered QT in final path; supply volume is not a local minimum-thickness measurement"},
        "combined_nominal": {"arc_time_s":8*(first_time+second_time),
                            "net_heat_J":8*(first_heat+second_heat),
                            "deposited_mass_g":8*(first_mass["nominal"]+second_volume["nominal"]*rho)},
        "resource_planning": {"planning_basis":"10h thermal occupation per independent layer and 24h delayed PT are conservative scheduling reservations, not a solved ring cooling history",
                             "scenarios":resources,
                             "meaning":"Two 10-position stages plus 24 delay positions support an hourly supply target. A 240s supply target requires 150+150+360 positions or equivalent parallel capacity, before inspection queues."},
        "geometry_and_input_scope":"Ring-specific nominal curved pockets, retained material partitions and supply/energy integrals. Actual fused area, cooling phase path and unloaded bore displacement are evaluated separately in the design route.",
    }
    (output/"ring-precoat-design.json").write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding="utf-8")
    return plan


def drawing(output):
    p = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1000" viewBox="0 0 1400 1000">',
        '<defs><marker id="arr" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto-start-reverse"><path d="M0 0 L7 3.5 L0 7 Z" fill="#24364B"/></marker>',
        '<pattern id="qt" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="10" height="10" fill="#E8EFED"/><line x1="0" y1="0" x2="0" y2="10" stroke="#3F6B68" stroke-width="1"/></pattern>',
        '<pattern id="steel" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)"><rect width="9" height="9" fill="#F2F3F4"/><line x1="0" y1="0" x2="0" y2="9" stroke="#6D7984" stroke-width="1"/></pattern></defs>',
        '<style>text{font-family:"NotoSansSC","Noto Sans SC","Noto Sans CJK SC","DejaVu Sans",sans-serif;fill:#24364B;font-size:20px}.small{font-size:17px}.tiny{font-size:15px}.title{font-size:31px;font-weight:700}.subtitle{font-size:20px;fill:#3F6B68}.edge{fill:none;stroke:#24364B;stroke-width:1.6}.center{fill:none;stroke:#8A939B;stroke-width:.8;stroke-dasharray:16 5 3 5}.dim{fill:none;stroke:#24364B;stroke-width:1}.candidate{fill:none;stroke:#A48352;stroke-width:5;stroke-linecap:round}</style>',
        '<rect width="1400" height="1000" fill="#fff"/><rect x="25" y="25" width="1350" height="950" class="edge"/>',
    ]

    def text(x, y, value, cls="", anchor="start"):
        p.append(f'<text x="{x:g}" y="{y:g}" class="{cls}" text-anchor="{anchor}">{escape(value)}</text>')

    def line(x1, y1, x2, y2, cls="edge", arrows=False):
        extra = ' marker-start="url(#arr)" marker-end="url(#arr)"' if arrows else ""
        p.append(f'<line x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}" class="{cls}"{extra}/>')

    def rect(x, y, w, h, fill="none"):
        p.append(f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" stroke="#24364B" stroke-width="1.6" fill="{fill}"/>')

    def circle(x, y, r, fill="none", cls="edge"):
        p.append(f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{fill}" class="{cls}"/>')

    def h_dim(x1, x2, y, feature_y, label):
        line(x1, feature_y, x1, y + 7, "dim")
        line(x2, feature_y, x2, y + 7, "dim")
        line(x1, y, x2, y, "dim", True)
        text((x1 + x2) / 2, y - 9, label, "small", "middle")

    def v_dim(y1, y2, x, feature_x, label):
        line(feature_x, y1, x + 7, y1, "dim")
        line(feature_x, y2, x + 7, y2, "dim")
        line(x, y1, x, y2, "dim", True)
        p.append(f'<text x="{x-10}" y="{(y1+y2)/2}" class="small" text-anchor="middle" transform="rotate(-90 {x-10} {(y1+y2)/2})">{escape(label)}</text>')

    text(55, 70, "完整圆环座体 · 名义装配与检验基准", "title")
    text(55, 106, "完整 QT450-10 圆环 + Q235B 机壳；分段连接候选与预制接口另见 HJ-S01 设计卡", "subtitle")
    text(1315, 72, "HJ-S01", "subtitle", "end")
    text(55, 164, "俯视图", "subtitle")
    cx, cy, s = 345.0, 434.0, 2.9
    circle(cx, cy, 80 * s, "#F2F3F4")
    circle(cx, cy, 75 * s, "#fff")
    circle(cx, cy, 74.98 * s, "#E8EFED")
    circle(cx, cy, 20 * s, "#fff")
    line(cx - 260, cy, cx + 260, cy, "center")
    line(cx, cy - 260, cx, cy + 260, "center")
    # Optional 8 x 18mm weld locations are marked without removing seat material.
    angle = 18.0 / 74.98
    for i in range(8):
        a0, a1 = i * math.pi / 4 - angle / 2, i * math.pi / 4 + angle / 2
        r = 74.98 * s
        x0, y0 = cx + r * math.cos(a0), cy - r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy - r * math.sin(a1)
        p.append(f'<path d="M{x0:g},{y0:g} A{r:g},{r:g} 0 0 0 {x1:g},{y1:g}" class="candidate"/>')
        text(cx + 195 * math.cos(i * math.pi / 4) - 5,
             cy - 195 * math.sin(i * math.pi / 4) + 7, str(i + 1), "small")
    h_dim(cx - 80 * s, cx + 80 * s, 190, cy, "壳体 Ø160")
    h_dim(cx - 74.98 * s, cx + 74.98 * s, 703, cy, "座体 Ø149.96（名义）")
    line(cx - 20 * s, cy - 8, 238, 350, "dim")
    line(238, 350, 138, 350, "dim")
    text(137, 338, "Ø40（名义）", "small")
    text(87, 742, "赭色：8×18 mm 有效区；实际每段20 mm、两道", "small")
    text(87, 773, "按 1→5→3→7→2→6→4→8 对称次序设计", "small")

    text(760, 164, "轴向剖视图", "subtitle")
    xc, floor, k = 1000.0, 690.0, 2.0
    top = floor - 200 * k
    seat_low, seat_high = floor - 100 * k, floor - 115 * k
    rect(xc - 80 * k, top, 5 * k, 200 * k, "url(#steel)")
    rect(xc + 75 * k, top, 5 * k, 200 * k, "url(#steel)")
    rect(xc - 74.98 * k, seat_high, (74.98 - 20) * k, 15 * k, "url(#qt)")
    rect(xc + 20 * k, seat_high, (74.98 - 20) * k, 15 * k, "url(#qt)")
    line(xc, top - 40, xc, floor + 38, "center")
    h_dim(xc - 75 * k, xc + 75 * k, 247, top, "壳内 Ø150")
    h_dim(xc - 20 * k, xc + 20 * k, 418, seat_high, "Ø40")
    v_dim(top, floor, 1303, xc + 80 * k, "200")
    v_dim(seat_low, floor, 780, xc - 80 * k, "100")
    v_dim(seat_high, seat_low, 1214, xc + 74.98 * k, "15")
    # Primary datum A: shell lower installation face, not the bearing seat.
    line(xc - 80 * k, floor, 827, floor, "dim")
    p.append('<path d="M827 690 L817 707 L837 707 Z" fill="#24364B"/>')
    line(827, 707, 827, 715, "dim")
    rect(812, 715, 30, 30, "#fff")
    text(827, 738, "A", "", "middle")
    # Datum B is attached to the shell inner cylindrical feature.
    line(xc + 75 * k, 580, 1202, 580, "dim")
    p.append('<path d="M1150 580 L1165 572 L1165 588 Z" fill="#24364B"/>')
    rect(1202, 565, 30, 30, "#fff")
    text(1217, 588, "B", "", "middle")
    text(912, 537, "QT450-10", "small")
    text(1120, 331, "Q235B", "small", "end")
    line(1149.96, 459, 1190, 369, "dim")
    line(1190, 369, 1340, 369, "dim")
    text(1340, 350, "名义径向间隙 0.02", "small", "end")
    text(1340, 395, "直径间隙 0.04", "small", "end")
    # Position frame attaches to bore wall: tolerance is a requirement.
    line(xc - 20 * k, 472, 938, 767, "dim")
    line(938, 767, 904, 767, "dim")
    gx, gy = 710, 751
    for x, w in ((gx, 34), (gx + 34, 82), (gx + 116, 34), (gx + 150, 34)):
        rect(x, gy, w, 32, "#fff")
    circle(gx + 17, gy + 16, 8)
    line(gx + 5, gy + 16, gx + 29, gy + 16)
    line(gx + 17, gy + 4, gx + 17, gy + 28)
    text(gx + 44, gy + 23, "Ø0.05", "small")
    text(gx + 127, gy + 23, "A", "small")
    text(gx + 161, gy + 23, "B", "small")
    text(710, 816, "A：机壳下端安装面；B：机壳内壁建立的轴线", "small")
    text(710, 847, "位置度为孔轴要求；完全卸夹、冷态、独立基准测量", "small")
    text(87, 817, "名义 STEP：机壳与圆环共轴，两个独立有效实体", "small")
    text(87, 849, "层次：QT → 首镍层 → 第二镍层 → NiFe 连接 → Q235B", "small")
    line(55, 883, 1345, 883)
    line(705, 883, 705, 975)
    line(1040, 883, 1040, 975)
    text(70, 916, "工艺设计图｜完整圆环基准｜单位：mm", "small")
    text(70, 947, "8局部预制窗与层次见 HJ-S02；完整座体不开八翼槽", "tiny")
    text(720, 916, "比例：NTS（不按比例）", "small")
    text(720, 947, "名义设计 · 位置度目标 Ø0.05", "tiny")
    text(1055, 916, "材料：QT450-10 / Q235B", "small")
    text(1055, 947, "HJ-S01 · 圆环基准", "small")
    p.append('</svg>')
    svg = output / "HJ-S01-ring-baseline.svg"
    svg.write_text("\n".join(p), encoding="utf-8")
    render_png(svg, output / "HJ-S01-ring-baseline.png")


def render_png(svg, png):
    # Fontconfig loads the bundled static CJK fonts without changing system fonts.
    with tempfile.TemporaryDirectory(prefix="hanjie-ring-fonts-") as temporary:
        config = Path(temporary) / "fonts.conf"
        config.write_text(
            '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>'
            '<include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
            f'<dir>{escape(str(ROOT / "assets/fonts"))}</dir>'
            f'<cachedir>{escape(temporary)}</cachedir></fontconfig>', encoding="utf-8")
        staged = Path(temporary) / "drawing.png"
        subprocess.run(["inkscape", str(svg), "--export-type=png",
                        "--export-width=2800", f"--export-filename={staged}"],
                       env={**os.environ, "FONTCONFIG_FILE": str(config)}, check=True)
        with Image.open(staged) as rendered:
            rendered.load()
        # Copy only a fully decoded image into the publication path.
        png.write_bytes(staged.read_bytes())


def precoat_drawing(output):
    """Radial nominal retained-section and an unwrapped local process window."""
    svg = output / "HJ-S02-ring-precoat-section.svg"
    svg.write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="1000" viewBox="0 0 1400 1000">
<defs><marker id="ar" markerWidth="7" markerHeight="7" refX="3.5" refY="3.5" orient="auto-start-reverse"><path d="M0 0 L7 3.5 L0 7 Z" fill="#24364B"/></marker><pattern id="qt" width="12" height="12" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="12" height="12" fill="#EEF1F3"/><line x1="0" y1="0" x2="0" y2="12" stroke="#82909B" stroke-width="1"/></pattern></defs>
<style>text{font-family:"NotoSansSC","Noto Sans SC",sans-serif;fill:#24364B;font-size:20px}.title{font-size:31px;font-weight:700}.sub{font-size:20px;fill:#3F6B68}.small{font-size:17px}.line{fill:none;stroke:#24364B;stroke-width:1.5}.dim{fill:none;stroke:#24364B;stroke-width:1}.center{fill:none;stroke:#84929B;stroke-width:1;stroke-dasharray:9 5}.first{fill:#C0AA7C;stroke:#24364B;stroke-width:1.5}.second{fill:#9CB7B2;stroke:#24364B;stroke-width:1.5}</style>
<rect width="1400" height="1000" fill="#fff"/><rect x="25" y="25" width="1350" height="950" class="line"/>
<text x="55" y="70" class="title">圆环局部预制窗口 · 两层留层与覆盖设计</text><text x="1280" y="70" class="sub">HJ-S02</text>
<text x="55" y="109" class="sub">8窗重复；名义成品断面与独立预制工序；单位mm；母件完整环，余底厚≥13.4</text>
<text x="70" y="163" class="sub">径向名义成品截面（窗口中部）</text>
<path d="M70 280 H120 A120 120 0 0 0 240 400 H600 V570 H70 Z" fill="url(#qt)" stroke="#24364B" stroke-width="1.5"/>
<path d="M120 280 A120 120 0 0 0 240 400 H600 V344 H240 A64 64 0 0 1 176 280 Z" class="first"/>
<path d="M176 280 H600 V344 H240 A64 64 0 0 1 176 280 Z" class="second"/>
<path d="M70 552 l15 -10 l15 20 l15 -10 M570 552 l15 -10 l15 20" class="line"/>
<line x1="120" y1="280" x2="120" y2="212" class="dim"/><line x1="600" y1="400" x2="600" y2="212" class="dim"/>
<line x1="120" y1="226" x2="600" y2="226" class="dim" marker-start="url(#ar)" marker-end="url(#ar)"/><text x="360" y="210" text-anchor="middle">径宽6.0±0.1</text>
<line x1="600" y1="280" x2="674" y2="280" class="dim"/><line x1="600" y1="400" x2="674" y2="400" class="dim"/><line x1="659" y1="280" x2="659" y2="400" class="dim" marker-start="url(#ar)" marker-end="url(#ar)"/>
<text x="644" y="340" class="small" text-anchor="middle" transform="rotate(-90 644 340)">深1.50±0.10</text>
<text x="85" y="491">QT450-10；下部省略</text><text x="85" y="529" class="small">R68.98内缘 → R74.98外缘贯通</text>
<line x1="395" y1="374" x2="448" y2="457" class="dim"/><line x1="448" y1="457" x2="620" y2="457" class="dim"/>
<text x="446" y="484" class="small">首层：法向0.70±0.05</text>
<line x1="188" y1="387" x2="164" y2="435" class="dim"/><text x="75" y="452" class="small">QT底角R1.5</text>
<line x1="197" y1="324" x2="250" y2="306" class="dim"/><text x="254" y="302" class="small">第二层：名义R0.80</text>
<text x="380" y="330" class="small">Ni第二层</text>
<text x="740" y="163" class="sub">局部窗口展开（中心R71.98处）</text>
<rect x="770" y="278" width="384" height="96" class="first"/>
<rect x="782" y="278" width="360" height="85" class="second"/>
<line x1="770" y1="278" x2="770" y2="218" class="dim"/><line x1="1154" y1="278" x2="1154" y2="218" class="dim"/><line x1="770" y1="232" x2="1154" y2="232" class="dim" marker-start="url(#ar)" marker-end="url(#ar)"/><text x="962" y="215" text-anchor="middle">中心弧长24±0.5</text>
<line x1="787" y1="294" x2="1137" y2="294" class="center"/><line x1="787" y1="326" x2="1137" y2="326" class="center"/><line x1="787" y1="358" x2="1137" y2="358" class="center"/>
<text x="1180" y="298" class="small">名义R69.98</text><text x="1180" y="330" class="small">名义R71.98</text><text x="1180" y="362" class="small">名义R73.98</text>
<line x1="818" y1="422" x2="1106" y2="422" class="dim" marker-start="url(#ar)" marker-end="url(#ar)"/><text x="962" y="410" text-anchor="middle" class="small">有效18（最终实际路径20）</text>
<text x="744" y="479" class="small">两端首层法向包覆≥0.70，第二层端部内缩</text>
<text x="744" y="512" class="small">名义STEP二层无QT面接触；公差实件按实测引导</text>
<text x="744" y="545" class="small">三轨按实测槽缘/中径/起止角；搭接≥0.8</text>
<text x="744" y="578" class="small">最宽槽熔宽≥2.85且≤3.0；角部首件宏观确认</text>
<line x1="55" y1="611" x2="1345" y2="611" class="line"/>
<text x="70" y="650">首层：CI-A1 Ø3.2；110A/23V；75mm/min；两端各0.5s保护；20.2s/窗</text>
<text x="70" y="688" class="small">最短弧与+2%速度保守供料2.869706g；最大槽＋余高＋保护带2.603046g；余量10.24%</text>
<text x="70" y="729">第二层：75A/11V；2mm/s；名义三轨72mm/窗（576mm/件）；名义36s/窗</text>
<text x="70" y="767" class="small">首镍临时保护：内缘外延0.5、两端各1.5；外缘超出部分由可拆铜背衬承托，完成二层后修去</text>
<text x="70" y="805" class="small">首件/每批冷态称量核验供料；每窗检查余高与保护覆盖；第二层总料高≥1.75再加工齐平</text>
<text x="70" y="843" class="small">17实体STEP为齐平后名义留层；公差轨迹按实测槽修正，名义实体不代替全公差熔池过程</text>
<line x1="55" y1="883" x2="1345" y2="883" class="line"/><line x1="705" y1="883" x2="705" y2="975" class="line"/><line x1="1040" y1="883" x2="1040" y2="975" class="line"/>
<text x="70" y="916" class="small">工艺设计图｜圆环8局部预制窗｜单位mm</text><text x="70" y="947" class="small">供料与能量见ring-precoat-design.json</text><text x="720" y="916" class="small">比例：NTS（不按比例）</text><text x="720" y="947" class="small">实际局部留层按法向测量</text><text x="1055" y="916" class="small">QT / CI-A1 / Ni覆盖层</text><text x="1055" y="947" class="small">HJ-S02 · 独立入壳前预制</text></svg>''', encoding="utf-8")
    render_png(svg, output / "HJ-S02-ring-precoat-section.png")


def build(output=OUT):
    output.mkdir(parents=True, exist_ok=True)
    n = NOMINAL
    seat = annulus(n["seat_inner_radius_mm"], n["seat_outer_radius_mm"],
                   n["seat_bottom_z_mm"], n["seat_thickness_mm"])
    shell = annulus(n["shell_inner_radius_mm"], n["shell_outer_radius_mm"],
                    n["shell_bottom_z_mm"], n["shell_height_mm"])
    export_step(output / "ring-seat-QT450-10.step", [seat])
    export_step(output / "ring-assembly-QT450-10-Q235B.step", [seat, shell])
    checks = [recheck_step(output / "ring-seat-QT450-10.step", 1),
              recheck_step(output / "ring-assembly-QT450-10-Q235B.step", 2)]
    distance = BRepExtrema_DistShapeShape(seat, shell)
    distance.Perform()
    if not distance.IsDone():
        raise RuntimeError("Cannot determine nominal assembly clearance")
    common = BRepAlgoAPI_Common(seat, shell)
    common.Build()
    if not common.IsDone():
        raise RuntimeError("Assembly intersection calculation failed")
    seat_v, shell_v = volume(seat), volume(shell)
    analytic_seat = math.pi * (74.98 ** 2 - 20.0 ** 2) * 15.0
    analytic_shell = math.pi * (80.0 ** 2 - 75.0 ** 2) * 200.0
    if abs(seat_v / analytic_seat - 1) > 1e-8 or abs(shell_v / analytic_shell - 1) > 1e-8:
        raise RuntimeError("Analytic annulus and solid volume disagree")
    if abs(distance.Value() - 0.02) > 1e-7 or abs(volume(common.Shape())) > 1e-7:
        raise RuntimeError("Nominal assembly clearance/interference mismatch")
    prior_path = ROOT / "simulation/competition-r4/geometry/8P-R2-t15-manifest.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    prior_v = prior["geometry"]["solid_volume_mm3"]
    full_length = 2 * math.pi * 74.98
    audit = {
        "model_id": "HJ-S01-complete-ring-nominal",
        "units": "mm",
        "geometry_state": "Nominal uncoated QT450-10 complete ring and Q235B shell; separate solids before welding",
        "nominal_dimensions": n,
        "materials": {
            "QT450-10": {"volume_mm3": seat_v, "density_kg_m3": DENSITIES["QT450-10"],
                         "mass_kg": seat_v * DENSITIES["QT450-10"] * 1e-9},
            "Q235B": {"volume_mm3": shell_v, "density_kg_m3": DENSITIES["Q235B"],
                      "mass_kg": shell_v * DENSITIES["Q235B"] * 1e-9},
        },
        "density_basis": "Existing repository engineering design densities; mass is nominal CAD volume times density, not measured mass",
        "total_nominal_mass_kg": seat_v * 7200e-9 + shell_v * 7850e-9,
        "analytic_volume_mm3": {"seat": analytic_seat, "shell": analytic_shell},
        "nominal_radial_clearance_mm": float(distance.Value()),
        "nominal_diametral_clearance_mm": 0.04,
        "seat_shell_intersection_volume_mm3": volume(common.Shape()),
        "exported_STEP_reopen_check": checks,
        "datum_scheme": {"A": "Independent shell lower installation face z=0",
                         "B": "Axis established from shell inner cylindrical wall, oriented with respect to A",
                         "position_requirement": "Bearing bore axis within a diameter 0.05 cylindrical zone relative to A|B over the 15 mm bore length"},
        "candidate_connection_geometry": {
            "segment_count": 8, "segment_length_mm": 18.0,
            "total_segment_length_mm": 144.0,
            "actual_path_length_one_segment_mm": 20.0,
            "pass_count": 2, "actual_total_path_length_mm": 320.0,
            "full_circumference_at_seat_outer_radius_mm": full_length,
            "full_circumference_to_segment_length_ratio": full_length / 144.0,
            "segment_length_scope": "Nominal connection-arc design; no weld solid, fused area, heat history, or qualified pWPS assigned",
        },
        "comparison_with_existing_eight_wing": {
            "source_manifest": str(prior_path.relative_to(ROOT)),
            "eight_wing_volume_mm3": prior_v,
            "eight_wing_mass_kg": prior_v * 7200e-9,
            "ring_to_eight_wing_volume_ratio": seat_v / prior_v,
            "ring_extra_mass_kg": (seat_v - prior_v) * 7200e-9,
            "scope": "Geometric material comparison only; prior eight-wing thermomechanical/fatigue results keep their original geometry identity",
        },
        "precoat_design_scope": "Eight 24mm local curved pockets on this ring; see ring-precoat-design.json and the separate 17-solid retained-layer STEP",
        "fused_interface_assigned": False,
        "residual_stress_assigned": False,
        "position_tolerance_verified_by_geometry": False,
        "drawing": "HJ-S01-ring-baseline.svg",
    }
    (output / "geometry-quality-and-mass.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    ring_precoat(output, seat)
    drawing(output)
    precoat_drawing(output)
    print(json.dumps({"seat_volume_mm3": seat_v, "seat_mass_kg": seat_v * 7200e-9,
                      "shell_volume_mm3": shell_v, "shell_mass_kg": shell_v * 7850e-9,
                      "assembly_solids": 2, "all_valid_after_STEP_read": True,
                      "radial_clearance_mm": distance.Value()}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    build(parser.parse_args().output)
