"""生成带基准、位置度框、焊缝符号和装配约束的 SVG 工程表达图包。

这些 SVG 是由参数入口生成的工程表达草图，便于评审和归档；在取得 CAD
软件后仍需按企业制图标准完成三维关联、GD&T 复核和制造发布签审。
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[2]
GEOMETRY = ROOT / "cad" / "parametric" / "geometry.json"
OUTPUT = ROOT / "cad" / "generated" / "engineering-drawings"


def text(x: float, y: float, value: str, cls: str = "note", anchor: str = "start") -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}">{escape(value)}</text>'


def line(x1: float, y1: float, x2: float, y2: float, cls: str = "edge", dash: str = "") -> str:
    extra = f' stroke-dasharray="{dash}"' if dash else ""
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="{cls}"{extra}/>'


def circle(cx: float, cy: float, radius: float, cls: str = "edge", fill: str = "none") -> str:
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" class="{cls}" fill="{fill}"/>'


def rect(x: float, y: float, width: float, height: float, cls: str = "edge", fill: str = "none", rx: float = 0) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" class="{cls}" fill="{fill}" rx="{rx:.1f}"/>'


def polygon(points: list[tuple[float, float]], cls: str = "edge", fill: str = "none") -> str:
    value = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polygon points="{value}" class="{cls}" fill="{fill}"/>'


def header(title: str, subtitle: str, drawing_number: str) -> list[str]:
    return [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">',
        '<rect width="1200" height="800" fill="#ffffff"/>',
        '<style>text{font-family:Arial,"Microsoft YaHei",sans-serif;fill:#111827}.title{font-size:25px;font-weight:700}.subtitle{font-size:14px;fill:#475569}.note{font-size:15px}.small{font-size:12px}.dim{font-size:16px;fill:#1d4ed8}.datum{font-size:15px;font-weight:700;fill:#b91c1c}.section{font-size:18px;font-weight:700;fill:#0f766e}.edge{stroke:#111827;stroke-width:2;fill:none}.center{stroke:#64748b;stroke-width:1;fill:none}.thin{stroke:#475569;stroke-width:1;fill:none}.weld{stroke:#dc2626;stroke-width:3;fill:none}.dimline{stroke:#1d4ed8;stroke-width:1.2;fill:none}.frame{stroke:#111827;stroke-width:1.5;fill:#fff}.datumbox{stroke:#b91c1c;stroke-width:1.5;fill:#fff}</style>',
        rect(25, 25, 1150, 750, "thin"),
        text(50, 65, title, "title"),
        text(50, 90, subtitle, "subtitle"),
        text(1140, 65, drawing_number, "section", "end"),
    ]


def footer(lines: list[str], material: str) -> list[str]:
    lines.extend([
        line(50, 710, 1150, 710, "thin"),
        text(55, 735, f"MATERIAL: {material}"),
        text(380, 735, "UNSPECIFIED TOLERANCES: ±0.10 mm (design assumption; verify before release)", "small"),
        text(1140, 735, "STATUS: DESIGN-REVIEW", "small", "end"),
        text(55, 758, "Functional assembly datums: A=seat/support plane; B=shell theoretical axis; C=independent clocking; design-review only.", "small"),
        '</svg>',
    ])
    return lines


def datum(lines: list[str], label: str, x: float, y: float, direction: str = "up") -> None:
    if direction == "up":
        points = [(x, y), (x - 10, y - 20), (x + 10, y - 20)]
        lines.append(polygon(points, "datumbox", "#fff"))
        lines.append(text(x, y - 6, label, "datum", "middle"))
        lines.append(line(x, y - 20, x, y - 45, "thin"))
    elif direction == "right":
        lines.append(polygon([(x, y), (x + 20, y - 10), (x + 20, y + 10)], "datumbox", "#fff"))
        lines.append(text(x + 8, y + 5, label, "datum", "middle"))
        lines.append(line(x + 20, y, x + 55, y, "thin"))


def position_frame(lines: list[str], x: float, y: float) -> None:
    # Ø40 孔轴线只引用独立的 A/B 基准；C 仅定义装配周向姿态。
    labels = ["POSITION", "Ø0.05", "A", "B"]
    cursor = x
    for index, label in enumerate(labels):
        width = 88 if index == 0 else 54
        lines.append(rect(cursor, y - 22, width, 28, "frame"))
        lines.append(text(cursor + width / 2, y - 3, label, "small", "middle"))
        cursor += width


def dim_h(lines: list[str], x1: float, x2: float, y: float, label: str, extension_y: float) -> None:
    lines.extend([line(x1, extension_y, x1, y, "dimline"), line(x2, extension_y, x2, y, "dimline"), line(x1, y, x2, y, "dimline"), text((x1 + x2) / 2, y - 7, label, "dim", "middle")])


def seat_drawing(geometry: dict) -> list[str]:
    design = geometry["design_assumptions"]
    official = geometry["official"]
    lines = header("轴承座零件图 · 六翼柔顺方案", "BEARING SEAT / PLAN VIEW / ALL DIMENSIONS IN mm", "HJ-DRW-001")
    cx, cy, scale = 330.0, 370.0, 3.0
    bore = official["bearing_bore_diameter"] / 2 * scale
    core = design["seat_core_outer_diameter"] / 2 * scale
    wing_r = design["wing_outer_radius"] * scale
    lines += [circle(cx, cy, wing_r, "edge", "#fef3c7"), circle(cx, cy, core, "edge", "#fde68a"), circle(cx, cy, bore, "edge", "#fff"), line(cx - wing_r - 20, cy, cx + wing_r + 20, cy, "center", "9 7"), line(cx, cy - wing_r - 20, cx, cy + wing_r + 20, "center", "9 7")]
    half_angle = math.asin((design["wing_width"] / 2) / design["wing_outer_radius"])
    for index in range(6):
        angle = index * math.pi / 3
        points = []
        for radius, offset in ((design["seat_core_outer_diameter"] / 2, -half_angle), (design["wing_outer_radius"], -half_angle), (design["wing_outer_radius"], half_angle), (design["seat_core_outer_diameter"] / 2, half_angle)):
            points.append((cx + radius * scale * math.cos(angle + offset), cy - radius * scale * math.sin(angle + offset)))
        lines.append(polygon(points, "edge", "#f59e0b"))
        inner = design["wing_outer_radius"] - 4
        p1 = (cx + inner * scale * math.cos(angle - 0.105), cy - inner * scale * math.sin(angle - 0.105))
        p2 = (cx + inner * scale * math.cos(angle + 0.105), cy - inner * scale * math.sin(angle + 0.105))
        lines.append(line(*p1, *p2, "weld"))
    dim_h(lines, cx - core, cx + core, 565, f"Ø{design['seat_core_outer_diameter']:.0f} CORE", cy + core)
    lines += [text(670, 225, f"BORE Ø{official['bearing_bore_diameter']:.0f}"), text(670, 255, f"WING OUTER R{design['wing_outer_radius']:.1f}"), text(670, 285, f"WING WIDTH {design['wing_width']:.0f}"), text(670, 315, f"RADIAL SLOT {design['slot_width']:.0f} WIDE"), text(670, 345, f"6 × {geometry['design_assumptions']['weld_segment_length']:.0f} WELD SEGMENTS", "section"), text(670, 390, "DATUM A: shell seating plane", "note"), text(670, 420, "DATUM B: shell theoretical axis", "note"), text(670, 450, "DATUM C: independent clocking feature", "note"), text(670, 480, "CONTROLLED: Ø40 bore axis", "note"), text(670, 520, "POSITION TOLERANCE", "section")]
    position_frame(lines, 670, 565)
    datum(lines, "A", cx, cy + wing_r, "up")
    datum(lines, "B", cx, cy, "up")
    datum(lines, "C", cx + wing_r, cy, "right")
    return footer(lines, "QT450-10 (actual grade to be verified by certificate)")


def shell_drawing(geometry: dict) -> list[str]:
    official = geometry["official"]
    lines = header("薄壁壳体零件图", "SHELL / ORTHOGRAPHIC DEFINITION / ALL DIMENSIONS IN mm", "HJ-DRW-002")
    # front elevation
    x, y, width, height = 180, 170, 210, 360
    lines += [rect(x, y, width, height, "edge", "#e2e8f0"), rect(x + 16, y, width - 32, height, "thin", "#fff"), line(x - 35, y + height / 2, x + width + 35, y + height / 2, "center", "9 7"), text(x + width / 2, y + height + 35, f"H {official['shell_height']:.0f}"), text(x + width + 45, y + 70, f"t {official['shell_thickness']:.0f}"), line(x, y - 35, x + width, y - 35, "dimline"), text(x + width / 2, y - 43, f"Ø{official['shell_outer_diameter']:.0f} OD", "dim", "middle")]
    # top view
    cx, cy = 575, 340
    lines += [circle(cx, cy, 140, "edge", "#e2e8f0"), circle(cx, cy, 122, "thin", "#fff"), line(cx - 165, cy, cx + 165, cy, "center", "9 7"), line(cx, cy - 165, cx, cy + 165, "center", "9 7"), text(cx, cy + 195, f"Ø{official['shell_outer_diameter']:.0f} / Ø{official['shell_outer_diameter'] - 2 * official['shell_thickness']:.0f} ID", "dim", "middle")]
    lines += [text(830, 215, "MATERIAL: Q235B", "section"), text(830, 250, "Ø160 × H200 × t5", "note"), text(830, 285, "Cylindrical shell; seam and edge prep", "note"), text(830, 330, "DATUM A: shell seating plane", "note"), text(830, 360, "DATUM B: shell theoretical axis", "note"), text(830, 390, "DATUM C: independent clocking feature", "note"), text(830, 445, "Weld access: internal shield / borescope", "note")]
    datum(lines, "A", x + width / 2, y + height, "up")
    datum(lines, "B", cx, cy - 140, "up")
    datum(lines, "C", cx + 140, cy, "right")
    return footer(lines, "Q235B (actual grade to be verified by certificate)")


def joint_drawing(geometry: dict) -> list[str]:
    design = geometry["design_assumptions"]
    lines = header("接头与焊缝细节图", "JOINT DETAIL / SECTION A-A / SCHEMATIC WELD SYMBOLS", "HJ-DRW-003")
    lines += [text(90, 155, "SECTION A-A", "section"), rect(120, 210, 430, 70, "edge", "#e2e8f0"), rect(120, 280, 430, 45, "edge", "#fbbf24"), line(120, 350, 550, 350, "center", "9 7")]
    # weld triangles and leader
    lines += [polygon([(310, 280), (345, 280), (310, 245)], "weld", "#fecaca"), line(330, 245, 330, 195, "weld"), line(330, 195, 490, 195, "weld"), text(495, 190, "TIG + Ni filler", "note"), text(495, 220, "FILLET WELD SYMBOL", "note"), text(145, 390, f"WELD SEGMENT LENGTH {design['weld_segment_length']:.0f}", "dim"), text(145, 425, "WELD BRIDGE TO SHELL ID: 1.2 (2D FE equivalent)", "dim"), text(145, 460, "SLOT WIDTH 4 (design assumption)", "dim"), text(700, 180, "PROCESS NOTE", "section"), text(700, 220, "Automatic TIG, short segments, S3 sequence", "note"), text(700, 255, "No slag route; internal shielding and borescope", "note"), text(700, 305, "Do not interpret this sheet as a qualified WPS", "note"), text(700, 360, "A: shell seating plane", "note"), text(700, 390, "B: shell theoretical axis", "note"), text(700, 420, "C: independent clocking feature", "note"), text(700, 450, "Controlled Ø40 bore axis: position Ø0.05 | A | B", "note")]
    datum(lines, "A", 180, 325, "up")
    datum(lines, "B", 540, 280, "right")
    datum(lines, "C", 410, 210, "up")
    return footer(lines, "QT450-10 + Q235B + Ni filler (weld metal grade to be verified)")


def weld_layout_drawing(geometry: dict) -> list[str]:
    design = geometry["design_assumptions"]
    lines = header("焊缝布置与顺序图", "WELD LAYOUT / PLAN VIEW / S3 PATH REPRESENTATION", "HJ-DRW-004")
    cx, cy, radius = 360, 365, 215
    lines += [circle(cx, cy, radius + 40, "edge", "#e2e8f0"), circle(cx, cy, radius, "thin", "#fff"), circle(cx, cy, 70, "edge", "#fef3c7"), line(cx - 260, cy, cx + 260, cy, "center", "9 7"), line(cx, cy - 260, cx, cy + 260, "center", "9 7")]
    for index in range(6):
        angle = index * math.pi / 3
        a = angle - 0.105
        b = angle + 0.105
        p1 = (cx + radius * math.cos(a), cy - radius * math.sin(a))
        p2 = (cx + radius * math.cos(b), cy - radius * math.sin(b))
        lines.append(line(*p1, *p2, "weld"))
        lx = cx + (radius + 35) * math.cos(angle)
        ly = cy - (radius + 35) * math.sin(angle)
        lines.append(text(lx, ly, f"W{index + 1}", "section", "middle"))
    sequence = [1, 4, 3, 6, 2, 5]
    for idx in range(6):
        angle = (sequence[idx] - 1) * math.pi / 3
        p1 = (cx + 120 * math.cos(angle), cy - 120 * math.sin(angle))
        p2 = (cx + 175 * math.cos(angle), cy - 175 * math.sin(angle))
        lines.append(line(*p1, *p2, "weld"))
    lines += [text(700, 200, "SEQUENCE S3", "section"), text(700, 240, "W1 → W4 → W3 → W6 → W2 → W5", "note"), text(700, 290, f"6 × {design['weld_segment_length']:.0f} mm short welds", "note"), text(700, 325, "Symmetric alternation; confirm start point", "note"), text(700, 380, "WELD SYMBOL: fillet / short segment", "note"), text(700, 430, "Thermal record: current, voltage, speed, interpass", "note"), text(700, 480, "A: shell seating plane", "note"), text(700, 510, "B: shell theoretical axis", "note"), text(700, 540, "C: independent clocking feature / W1", "note")]
    datum(lines, "A", cx, cy - radius, "up")
    datum(lines, "B", cx + radius, cy, "right")
    datum(lines, "C", cx, cy + radius, "up")
    return footer(lines, "Welded joint: QT450-10 / Q235B / Ni filler")


def fixture_assembly_drawing(geometry: dict) -> list[str]:
    design = geometry["design_assumptions"]
    lines = header("夹具总装图", "FIXTURE ASSEMBLY / SIX SUPPORTS / DOF AND DATUMS", "HJ-DRW-005")
    cx, cy, scale = 350, 350, 2.1
    base_r = design["fixture_base_diameter"] / 2 * scale
    lines += [circle(cx, cy, base_r, "edge", "#cbd5e1"), circle(cx, cy, design["fixture_pin_diameter"] / 2 * scale, "edge", "#94a3b8"), circle(cx, cy, 80, "thin", "#fff")]
    for index in range(6):
        angle = index * math.pi / 3
        px = cx + 86 * scale * math.cos(angle)
        py = cy - 86 * scale * math.sin(angle)
        lines.append(circle(px, py, 11, "edge", "#f59e0b"))
        lines.append(line(cx + 40 * math.cos(angle), cy - 40 * math.sin(angle), px, py, "thin"))
        lines.append(text(px, py + 30, f"S{index + 1}", "small", "middle"))
    lines += [text(700, 180, "FIXTURE DEFINITION", "section"), text(700, 220, f"BASE Ø{design['fixture_base_diameter']:.0f}", "note"), text(700, 250, f"CENTER PIN Ø{design['fixture_pin_diameter']:.2f}", "note"), text(700, 280, "6 radial compliant supports", "note"), text(700, 315, "Equivalent radial stiffness: 1200 N/mm", "note"), text(700, 355, "DOF CONTROL / ASSEMBLY MAPPING", "section"), text(700, 390, "A  base top plane → assembly A", "note"), text(700, 420, "B  center pin axis → assembly B", "note"), text(700, 450, "C  independent clocking hole → assembly C", "note"), text(700, 500, "Fixture is a design assumption until assembled and dial/CMM checked", "small")]
    datum(lines, "A", cx, cy + base_r, "up")
    datum(lines, "B", cx + base_r, cy, "right")
    datum(lines, "C", cx, cy - base_r, "up")
    return footer(lines, "Fixture steel / material and heat treatment TBD")


def fixture_part_drawing(geometry: dict) -> list[str]:
    design = geometry["design_assumptions"]
    lines = header("夹具定位销与底板零件图", "FIXTURE PART / PIN + BASE / DESIGN-REVIEW DEFINITION", "HJ-DRW-006")
    lines += [text(110, 150, "CENTER PIN - SECTION", "section"), rect(150, 220, 150, 230, "edge", "#cbd5e1"), rect(185, 170, 80, 50, "edge", "#94a3b8"), line(110, 335, 340, 335, "center", "9 7"), text(340, 250, f"Ø{design['fixture_pin_diameter']:.2f}", "dim"), text(340, 280, "pin height 28 (assumption)", "dim"), text(110, 520, "BASE PLATE - PLAN", "section"), circle(230, 630, design['fixture_base_diameter'] / 2 * 0.55, "edge", "#cbd5e1"), circle(230, 630, 28, "edge", "#fff"), text(230, 720, f"Ø{design['fixture_base_diameter']:.0f}", "dim", "middle"), text(600, 190, "PART NOTES", "section"), text(600, 230, "A: base top plane → assembly A", "note"), text(600, 260, "B: pin axis → assembly B", "note"), text(600, 290, "C: independent clocking hole → assembly C", "note"), text(600, 345, "Six support stations at 60° pitch", "note"), text(600, 375, "Radial support travel and preload TBD", "note"), text(600, 430, "No manufacturing release without tolerance stack-up", "note")]
    datum(lines, "A", 225, 450, "up")
    datum(lines, "B", 265, 170, "right")
    datum(lines, "C", 385, 630, "right")
    return footer(lines, "Fixture steel / material and heat treatment TBD")


def weld_assembly_drawing(geometry: dict) -> list[str]:
    official = geometry["official"]
    design = geometry["design_assumptions"]
    lines = header("焊接总装与定位基准图", "WELD ASSEMBLY / SHELL + SEAT + FIXTURE REFERENCE", "HJ-DRW-007")
    lines += [text(85, 155, "EXPLODED / AXONOMETRIC SCHEMATIC", "section"), polygon([(180, 330), (480, 330), (530, 375), (230, 375)], "edge", "#cbd5e1"), polygon([(230, 375), (530, 375), (530, 420), (230, 420)], "edge", "#94a3b8"), polygon([(250, 250), (430, 250), (480, 290), (300, 290)], "edge", "#f59e0b"), polygon([(300, 290), (480, 290), (480, 320), (300, 320)], "edge", "#d97706"), circle(340, 270, 24, "edge", "#fff"), line(340, 220, 340, 410, "center", "9 7"), text(200, 455, "fixture base + center pin", "note"), text(300, 215, "seat / bore / six wings", "note"), text(700, 170, "ASSEMBLY CONTROL", "section"), text(700, 210, f"SHELL: Ø{official['shell_outer_diameter']:.0f} × H{official['shell_height']:.0f} × t{official['shell_thickness']:.0f}", "note"), text(700, 245, f"SEAT: bore Ø{official['bearing_bore_diameter']:.0f}; core Ø{design['seat_core_outer_diameter']:.0f}", "note"), text(700, 280, f"WELDS: 6 × {design['weld_segment_length']:.0f}; sequence S3", "note"), text(700, 330, "A shell seating plane / B shell theoretical axis / C independent clocking", "note"), text(700, 380, "Controlled feature: Ø40 bore axis", "note"), text(700, 410, "Inspection hand-off: visual → bore gauge/CMM → records", "note"), text(700, 450, "WPS qualification, material certificates and actual weld data remain open", "note"), text(700, 500, "Position tolerance target: Ø0.05 | A | B", "section")]
    position_frame(lines, 700, 555)
    datum(lines, "A", 230, 420, "up")
    datum(lines, "B", 340, 220, "up")
    datum(lines, "C", 480, 290, "right")
    return footer(lines, "Q235B shell + QT450-10 seat + Ni filler + fixture steel TBD")


def main() -> None:
    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    drawings = {
        "bearing-seat.svg": seat_drawing(geometry),
        "shell.svg": shell_drawing(geometry),
        "joint-detail.svg": joint_drawing(geometry),
        "weld-layout.svg": weld_layout_drawing(geometry),
        "fixture-assembly.svg": fixture_assembly_drawing(geometry),
        "fixture-part.svg": fixture_part_drawing(geometry),
        "weld-assembly.svg": weld_assembly_drawing(geometry),
    }
    for filename, lines in drawings.items():
        (OUTPUT / filename).write_text("\n".join(lines), encoding="utf-8")
    manifest = {
        "generated_at": "2026-09-02",
        "source": "cad/parametric/geometry.json",
        "status": "design-review; not manufacturing release",
        "drawing_count": len(drawings),
        "drawings": sorted(drawings),
        "included_controls": ["A/B/C datums", "Ø40 bore axis position tolerance Ø0.05 | A | B", "weld symbols", "slot width", "fixture DOF mapping", "materials", "unspecified tolerances"],
    }
    (OUTPUT / "drawing-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {len(drawings)} 张工程表达图: {OUTPUT}")


if __name__ == "__main__":
    main()
