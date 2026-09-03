"""生成无需 CAD 软件即可查看的参数化俯视工程草图（SVG）。"""

from __future__ import annotations

import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GEOMETRY = ROOT / "cad" / "parametric" / "geometry.json"
OUTPUT = ROOT / "cad" / "generated" / "layout-v1.svg"


def point(cx: float, cy: float, radius: float, angle: float, scale: float) -> tuple[float, float]:
    return cx + radius * scale * math.cos(angle), cy - radius * scale * math.sin(angle)


def polygon(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def main() -> None:
    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    official = geometry["official"]
    design = geometry["design_assumptions"]
    width = height = 900
    cx = cy = 390
    scale = 4.35
    shell_r = official["shell_outer_diameter"] / 2
    seat_r = design["seat_core_outer_diameter"] / 2
    wing_r = design["wing_outer_radius"]
    bore_r = official["bearing_bore_diameter"] / 2
    wing_half_angle = math.asin((design["wing_width"] / 2) / wing_r)

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="900" viewBox="0 0 900 900">',
        '<rect width="900" height="900" fill="#f8fafc"/>',
        '<style>text{font-family:Arial,"Microsoft YaHei",sans-serif;fill:#0f172a}.dim{font-size:16px}.title{font-size:24px;font-weight:700}.note{font-size:14px}</style>',
        '<text x="40" y="45" class="title">Hanjie V1 · 六点柔顺连接单元俯视数字样机</text>',
        '<text x="40" y="70" class="note">Official: shell Ø160 × 200 × 5 mm; bore Ø40 mm · Design assumptions are marked below</text>',
        f'<circle cx="{cx}" cy="{cy}" r="{shell_r*scale:.1f}" fill="#e2e8f0" stroke="#334155" stroke-width="3"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{(shell_r-5)*scale:.1f}" fill="#f8fafc" stroke="#64748b" stroke-width="2"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{seat_r*scale:.1f}" fill="#d19a58" fill-opacity="0.35" stroke="#9a5b16" stroke-width="3"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{bore_r*scale:.1f}" fill="#f8fafc" stroke="#111827" stroke-width="3"/>',
        f'<line x1="{cx-350}" y1="{cy}" x2="{cx+350}" y2="{cy}" stroke="#94a3b8" stroke-dasharray="7 7"/>',
        f'<line x1="{cx}" y1="{cy-350}" x2="{cx}" y2="{cy+350}" stroke="#94a3b8" stroke-dasharray="7 7"/>',
    ]
    points = design["primary_layout_points"]
    for index in range(points):
        angle = index * 2 * math.pi / points
        # 翼部采用外端为焊接区域的梯形，仅用于布局表达。
        corners = [
            point(cx, cy, seat_r, angle - wing_half_angle, scale),
            point(cx, cy, wing_r, angle - wing_half_angle, scale),
            point(cx, cy, wing_r, angle + wing_half_angle, scale),
            point(cx, cy, seat_r, angle + wing_half_angle, scale),
        ]
        lines.append(f'<polygon points="{polygon(corners)}" fill="#d19a58" fill-opacity="0.55" stroke="#9a5b16" stroke-width="2"/>')
        w1 = point(cx, cy, wing_r - 4, angle - 0.105, scale)
        w2 = point(cx, cy, wing_r - 4, angle + 0.105, scale)
        lines.append(f'<line x1="{w1[0]:.1f}" y1="{w1[1]:.1f}" x2="{w2[0]:.1f}" y2="{w2[1]:.1f}" stroke="#dc2626" stroke-width="7" stroke-linecap="round"/>')
        label = point(cx, cy, wing_r + 7, angle, scale)
        lines.append(f'<text x="{label[0]-6:.1f}" y="{label[1]+5:.1f}" class="dim">{index+1}</text>')

    # 右侧图例与设计假设。
    x = 690
    lines.extend([
        f'<rect x="{x}" y="140" width="175" height="285" rx="10" fill="#ffffff" stroke="#cbd5e1"/>',
        f'<text x="{x+15}" y="170" class="dim" font-weight="700">图例 / Legend</text>',
        f'<line x1="{x+15}" y1="195" x2="{x+50}" y2="195" stroke="#dc2626" stroke-width="7"/><text x="{x+60}" y="200" class="note">短焊段</text>',
        f'<rect x="{x+15}" y="218" width="35" height="16" fill="#d19a58" fill-opacity="0.55" stroke="#9a5b16"/><text x="{x+60}" y="232" class="note">柔顺翼</text>',
        f'<circle cx="{x+32}" cy="266" r="12" fill="#f8fafc" stroke="#111827" stroke-width="2"/><text x="{x+60}" y="271" class="note">Ø40 孔</text>',
        f'<text x="{x+15}" y="310" class="note">中心刚性区 Ø82</text>',
        f'<text x="{x+15}" y="335" class="note">翼端 R74.98 (H7/h6配合)</text>',
        f'<text x="{x+15}" y="360" class="note">槽宽 4</text>',
        f'<text x="{x+15}" y="385" class="note">6 × 18 焊段</text>',
        f'<text x="{x+15}" y="410" class="note">红线仅为布局符号</text>',
        '<text x="40" y="835" class="note">注：轴承座厚度、翼宽、装配间隙和焊缝尺寸均为设计假设；不得当作题面官方尺寸。</text>',
        '</svg>',
    ])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成: {OUTPUT}")


if __name__ == "__main__":
    main()

