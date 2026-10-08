"""Build the five editable figures used in the competition design manuscript.

Run from any directory with ``python docs/report/build_publication_figures.py``.
All figures are 170 mm wide; PNGs are 300 dpi, and SVG/PDF remain vector.
The graphics distinguish design allocations, process planning and calculated
objects. They do not generate experimental data or simulation field maps.
"""

from __future__ import annotations

import io
import json
import math
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from matplotlib import font_manager
from matplotlib.patches import Circle, Polygon, Rectangle, Wedge

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/report/figures/publication"
MM = 1 / 25.4
NAVY = "#24364B"
TEAL = "#3F6B68"
OCHRE = "#A48352"
INK = "#25323D"
GRAY = "#71808A"
PALE = "#F4F6F5"
LINE = "#C6CFD1"
SEAT = "#D9DFDF"
SHELL = "#E8ECEF"
FONT_PATHS: dict[str, str] = {}


def choose_font(kind: str) -> font_manager.FontProperties:
    family = "NotoSansSC" if kind == "sans" else "NotoSerifSC"
    override = os.environ.get("HANJIE_FIGURE_FONT_" + kind.upper())
    candidates = [Path(override)] if override else []
    candidates += [
        ROOT / f"assets/fonts/{family}-Regular.ttf",
        ROOT / f"assets/fonts/{family}-variable.ttf",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for path in candidates:
        if path.is_file():
            font_manager.fontManager.addfont(str(path))
            FONT_PATHS[kind] = str(path)
            return font_manager.FontProperties(fname=str(path))
    raise FileNotFoundError(f"Chinese {kind} font unavailable; set HANJIE_FIGURE_FONT_{kind.upper()}")


SANS = choose_font("sans")
SERIF = choose_font("serif")
plt.rcParams.update(
    {
        "font.family": SANS.get_name(),
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "path",
        "hatch.linewidth": 0.45,
    }
)

METADATA: dict[str, dict] = {}
BASELINE = yaml.safe_load((ROOT / "project/submission-baseline.yaml").read_text(encoding="utf-8"))
RING_CARD = json.loads((ROOT / "deliverables/process/ring-final-welding-card.json").read_text(encoding="utf-8"))


def canvas(height: float = 95):
    fig = plt.figure(figsize=(170 * MM, height * MM), facecolor="white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set(xlim=(0, 170), ylim=(0, height), aspect="equal")
    ax.axis("off")
    return fig, ax


def text(ax, x, y, value, *, size=8.6, color=INK, ha="left", va="center", serif=False, **kw):
    return ax.text(
        x, y, value, fontsize=size, color=color, ha=ha, va=va,
        fontproperties=SERIF if serif else SANS, linespacing=1.4, **kw,
    )


def line(ax, points, *, color=LINE, lw=0.65, **kw):
    x, y = zip(*points)
    ax.plot(x, y, color=color, lw=lw, **kw)


def arrow(ax, start, end, *, color=GRAY):
    ax.annotate("", xy=end, xytext=start,
                arrowprops={"arrowstyle": "-|>", "lw": 0.7, "color": color, "mutation_scale": 6})


def save(fig, name: str, *, description: str, sources: list, semantics: dict):
    fig.canvas.draw()
    # A small but useful layout gate: every text rectangle must stay on canvas.
    renderer = fig.canvas.get_renderer()
    canvas_box = fig.bbox
    escaped = []
    for ax in fig.axes:
        for obj in ax.texts:
            box = obj.get_window_extent(renderer=renderer)
            if (box.x0 < -1 or box.y0 < -1 or box.x1 > canvas_box.x1 + 1 or box.y1 > canvas_box.y1 + 1):
                escaped.append(obj.get_text())
    if escaped:
        raise ValueError(f"Text outside {name} canvas: {escaped}")
    OUT.mkdir(parents=True, exist_ok=True)
    # Complete each export in memory before publishing it. The manuscript
    # builder may consume figures while a graphics rebuild is in progress.
    export_options = {
        "png": {"dpi": 300},
        "svg": {"metadata": {"Title": description, "Creator": ""}},
        "pdf": {"metadata": {"Title": description, "Author": "", "Creator": "", "Subject": "工程设计图"}},
    }
    for ext, options in export_options.items():
        buffer = io.BytesIO()
        fig.savefig(buffer, format=ext, facecolor="white", **options)
        contents = buffer.getvalue()
        if ext == "pdf" and not contents.rstrip().endswith(b"%%EOF"):
            raise ValueError(f"Incomplete vector PDF export: {name}")
        target = OUT / f"{name}.{ext}"
        temporary = target.with_name(target.name + ".building")
        temporary.write_bytes(contents)
        temporary.replace(target)
    METADATA[name] = {
        "description": description,
        "files": [f"{name}.{ext}" for ext in ("png", "svg", "pdf")],
        "width_mm": 170,
        "height_mm": round(fig.get_figheight() / MM, 2),
        "png_dpi": 300,
        "sources": sources,
        **semantics,
    }
    plt.close(fig)


def draw_seat(ax, cx, cy, *, open_wings: bool):
    # Topology diagram, rather than a manufacturing drawing. The two structures
    # share the same bore and eight separated final weld segments.
    r = 22.0
    scale = r / 80
    ax.add_patch(Wedge((cx, cy), r, 0, 360, width=5 * scale, facecolor=SHELL, edgecolor=GRAY, lw=0.65))
    seat_r = 74.98 * scale
    if open_wings:
        hub_r = 41 * scale
        half = math.asin(9 / 74.98)
        for i in range(8):
            angle = i * math.pi / 4
            p = []
            for radius, offset in ((41, -half), (74.98, -half), (74.98, half), (41, half)):
                p.append((cx + radius * scale * math.cos(angle + offset), cy + radius * scale * math.sin(angle + offset)))
            ax.add_patch(Polygon(p, facecolor=SEAT, edgecolor=GRAY, lw=0.6))
        ax.add_patch(Circle((cx, cy), hub_r, facecolor=SEAT, edgecolor=GRAY, lw=0.6))
    else:
        ax.add_patch(Circle((cx, cy), seat_r, facecolor=SEAT, edgecolor=GRAY, lw=0.65))
    ax.add_patch(Circle((cx, cy), 20 * scale, facecolor="white", edgecolor=GRAY, lw=0.65))
    text(ax, cx, cy, "Ø40", size=7.1, color=GRAY, ha="center")
    # Ring paths include the 1 mm start/end transitions around the stable
    # 18 mm segment; the historical eight-wing diagram retains its own path.
    path_mm = 18 if open_wings else BASELINE["weld_layout"]["segment_length_mm"]
    weld_half_deg = math.degrees(path_mm / (2 * 74.98))
    for i in range(8):
        ax.add_patch(Wedge((cx, cy), seat_r + 0.26, i * 45 - weld_half_deg, i * 45 + weld_half_deg,
                           width=0.85, facecolor=OCHRE, edgecolor=OCHRE, lw=0.35))
    for delta in ((-25, 0), (25, 0), (0, -25), (0, 25)):
        line(ax, [(cx + delta[0] * 0.82, cy + delta[1] * 0.82), (cx + delta[0], cy + delta[1])], lw=0.45, ls="--")


def design_route():
    fig, ax = canvas(100)
    text(ax, 42.5, 94, "完整圆环座体 · 基准结构", size=9.2, color=NAVY, ha="center")
    text(ax, 127.5, 94, "八翼开口座体 · 创新候选", size=9.2, color=TEAL, ha="center")
    draw_seat(ax, 42.5, 64.5, open_wings=False)
    draw_seat(ax, 127.5, 64.5, open_wings=True)
    text(ax, 42.5, 38.5, "8×20 mm路径；有效18 mm/段", size=8.1, ha="center")
    text(ax, 127.5, 38.5, "开口减重；柔顺与承载共同校核", size=8.1, ha="center")
    for x, c, label in ((23, SEAT, "座体"), (53, SHELL, "钢壳"), (83, OCHRE, "8段短焊缝")):
        ax.add_patch(Rectangle((x, 31), 4, 2.2, facecolor=c, edgecolor=GRAY, lw=0.5))
        text(ax, x + 6, 32.1, label, size=7.6, color=GRAY)
    text(ax, 159, 32.1, "俯视形态示意", size=7.6, color=GRAY, ha="right")
    line(ax, [(7, 27), (163, 27)])
    stages = [
        (7, "壳外独立预制", "首层→修整/PT→低碳第二层"),
        (62, "终加工与清洗", "缓冷/延迟PT→孔和连接面加工"),
        (117, "入壳组焊与检验", "对向短焊→冷却卸夹→检测"),
    ]
    for x, title, sub in stages:
        text(ax, x + 23, 22, title, size=8.8, color=NAVY, ha="center")
        text(ax, x + 23, 15.5, sub, size=7.25, ha="center")
    arrow(ax, (54, 22), (59, 22))
    arrow(ax, (109, 22), (114, 22))
    text(ax, 85, 5.7, "结构与焊缝分段分别设计；预制、控形和资源核算采用对应座体实体。", size=7.7, color=GRAY, ha="center", serif=True)
    save(fig, "design-route", description="基准圆环、八翼候选及分工序制造路线",
         sources=["project/submission-baseline.yaml", "deliverables/process/ring-final-welding-card.json", "project/competition-design.yaml"],
         semantics={"kind": "design_schematic", "scale": "俯视形态示意，非加工尺寸图", "comparison": "连续圆环为基准，八翼开口为创新候选；八段焊缝是焊缝布局", "primary_calculation_object": "完整圆环座体", "ring_actual_path_per_segment_mm": 20, "ring_effective_segment_length_mm": 18, "ring_total_actual_path_mm": 320, "ring_net_heat_kJ": 96, "ring_arc_on_s": RING_CARD["arc_on_time_s"]})


def process_comparison():
    fig, ax = canvas(95)
    text(ax, 7, 90, "工艺条件比较", size=9.2, color=NAVY)
    text(ax, 163, 90, "按熔合、控形、洁净与实施条件选择", size=7.7, color=GRAY, ha="right")
    edges = [7, 34, 73, 119, 163]
    centers = [(a + b) / 2 for a, b in zip(edges, edges[1:])]
    header = ["方法", "热量与节拍", "冶金与内腔洁净", "设备与实施条件"]
    line(ax, [(7, 83.5), (163, 83.5)], color=NAVY, lw=0.95)
    for x, value in zip(centers, header):
        text(ax, x, 79, value, size=8.2, color=NAVY, ha="center")
    line(ax, [(7, 74.5), (163, 74.5)], color=NAVY, lw=0.65)
    rows = [
        ["外周GMAW\n塞焊", "连续送丝，利于沉积\n本接头节拍按孔数核算", "外侧施焊便于隔离\n控制贯穿、飞溅与QT稀释", "需壳体开孔与背衬\n重做塞焊受力细节"],
        ["激光\n深熔焊", "热源集中，可快速施焊\n熔深受间隙和焦点影响", "需控制快冷、孔隙和裂纹\n阻隔贯穿飞溅", "焦点跟踪与装配精度\n配置激光安全系统"],
        ["微束\n等离子", "低流稳定，适用于薄件\n本接头须另定熔合窗口", "镍过渡与气体保护\n保留实体落物屏障", "喷嘴、气路与可达性\n按本接头另定参数"],
        ["脉冲GTAW\n设计主工艺", "热源与加丝分别调控\n短段焊序、层间温控", "气体保护，无药皮熔渣\n镍过渡＋铜环/接料盘", "已配置单头工作站\n适合分工序小批试制"],
    ]
    for i, row in enumerate(rows):
        y = 67.5 - 13.3 * i
        if i == 3:
            ax.add_patch(Rectangle((7, y - 6.1), 156, 12.8, facecolor="#EDF3F1", edgecolor="none"))
        for j, (x, value) in enumerate(zip(centers, row)):
            text(ax, x, y, value, size=7.45 if j else 8.0, color=TEAL if i == 3 and j == 0 else INK, ha="center")
        if i < 3:
            line(ax, [(7, y - 6.6), (163, y - 6.6)], lw=0.45)
    line(ax, [(7, 21), (163, 21)], color=NAVY, lw=0.85)
    text(ax, 7, 14, "选择依据：铸铁预制与最终控形分工序，气体保护和实体屏障共同管理内腔洁净。", size=7.9, serif=True)
    text(ax, 7, 6, "依据：TWI GTAW / PAW / 激光焊接缺陷及脉冲GMAW工艺资料；本件参数见工艺规程卡。", size=7.0, color=GRAY, serif=True)
    save(fig, "process-comparison", description="四种主流工艺的定性条件比较",
         sources=[
             "deliverables/report/technical-report-v4-unified.md §1.1",
             "deliverables/process/ring-final-welding-card.json",
             "https://www.twi-global.com/technical-knowledge/job-knowledge/tungsten-inert-gas-tig-or-gta-welding-006",
             "https://www.twi-global.com/technical-knowledge/job-knowledge/plasma-arc-welding-007",
             "https://www.twi-global.com/technical-knowledge/faqs/faq-what-are-the-common-defects-in-laser-welding-of-structural-steels-and-how-do-i-avoid-them",
             "https://www.twi-global.com/technical-knowledge/faqs/faq-what-is-pulsed-mig-mag-welding-and-what-are-its-advantages-over-conventional-mig-mag-processes",
         ], semantics={"kind": "qualitative_evidence_comparison", "primary_object": "完整圆环座体", "score": None, "scope": "通用工艺机理结合本接头设计条件；不作同实体已验证性能排名"})


def precision_budget():
    config = BASELINE["precision"]
    allocations = config["diameter_allocations_um"]
    total = 1000 * config["official_position_tolerance_diameter_mm"]
    uncertainty = allocations["measurement_expanded_uncertainty"]
    honing = allocations["limited_honing_axis_change"]
    nonthermal = allocations["manufacturing_assembly_and_positioning"]
    thermal = total - nonthermal - uncertainty - honing
    fig, ax = canvas(85)
    text(ax, 7, 79, "Ø0.05 mm 位置度设计分配", size=9.2, color=NAVY)
    text(ax, 163, 79, "直径量统一口径 · 合计50 μm", size=7.9, color=GRAY, ha="right")
    text(ax, 7, 70, "20±1℃冷态，孔内及壳底工装完全解除后，以独立A/B基准评价。", size=7.9, serif=True)
    x0, scale = 9, 3.04
    cursor = x0
    values = [nonthermal, uncertainty, honing, thermal]
    colors = [NAVY, "#A9BEBA", OCHRE, TEAL]
    labels = ["非热分配\n28.0", "", "有限微珩\n6.5", "热残余上限\n13.5"]
    for value, color, label in zip(values, colors, labels):
        ax.add_patch(Rectangle((cursor, 44), value * scale, 13, facecolor=color, edgecolor="white", lw=0.65))
        if label:
            text(ax, cursor + value * scale / 2, 50.5, label, size=8.2 if value > 10 else 7.5, color="white", ha="center")
        cursor += value * scale
    middle_u = x0 + (nonthermal + uncertainty / 2) * scale
    line(ax, [(middle_u, 57.2), (middle_u, 62.5)], color=GRAY)
    text(ax, middle_u, 65, "测量扩展不确定度2.0", size=7.3, color=GRAY, ha="center")
    line(ax, [(x0, 40), (cursor, 40)], color=GRAY, lw=0.5)
    for tick in range(0, 51, 10):
        x = x0 + tick * scale
        line(ax, [(x, 40), (x, 38.5)], color=GRAY, lw=0.45)
        text(ax, x, 35.8, str(tick), size=7.1, color=GRAY, ha="center")
    text(ax, 85, 29.7, "位置度直径方向分配 / μm", size=7.5, color=GRAY, ha="center")
    text(ax, 9, 21.5, "非热：径向14 μm折算为直径28 μm", size=7.8, serif=True)
    text(ax, 90, 21.5, "有限微珩：局部径向去除≤3 μm", size=7.8, serif=True)
    text(ax, 9, 14.3, "测量：不确定度目标按方法评估", size=7.8, serif=True)
    text(ax, 90, 14.3, "热残余：按完整焊后卸夹状态计算", size=7.8, serif=True)
    text(ax, 85, 5.3, "该图为设计预算；数值计算结果与首件检测结果分别评价。", size=7.7, color=GRAY, ha="center", serif=True)
    save(fig, "precision-budget", description="50微米直径位置度预算",
         sources=["project/submission-baseline.yaml precision", "deliverables/process/ring-final-welding-card.json precision_budget", "deliverables/report/technical-report-v4-unified.md §4.1"],
         semantics={"kind": "design_allocation", "primary_object": "完整圆环座体", "unit": "μm, diameter", "values": {"nonthermal": nonthermal, "measurement_U_target": uncertainty, "limited_honing_axis_allocation": honing, "thermal_residual_limit": thermal, "sum": sum(values)}, "measured_pass_claim": False})


def station_resources():
    r = RING_CARD["resource_planning"]
    fig, ax = canvas(95)
    text(ax, 7, 90, "圆环小批试制资源设计", size=9.2, color=NAVY)
    text(ax, 163, 90, "目标8件/8 h · 供料间隔3600 s", size=7.8, color=GRAY, ha="right")
    text(ax, 7, 80.5, "完整圆环保守规划：1件/h供料，各件独立控温、独立计时。", size=7.8, serif=True)
    text(ax, 7, 71.5, "工序与单件时间依据", size=7.5, color=GRAY)
    text(ax, 113, 71.5, "独立工艺 / 等待位置数", size=7.5, color=GRAY, ha="center")
    rows = [
        ("首层升温、SMAW、缓冷", r["first_thermal_slot_reserved_s"] / 3600, r["first_independent_thermal_positions"], NAVY, "资源预留"),
        ("第二层升温、GTAW、缓冷", r["second_thermal_slot_reserved_s"] / 3600, r["second_independent_thermal_positions"], TEAL, "资源预留"),
        ("第二层冷却后延迟PT", r["delayed_PT_wait_s"] / 3600, r["delayed_PT_positions"], OCHRE, "工艺等待"),
    ]
    bx, unit = 76, 2.9
    for i, (label, hours, count, color, state) in enumerate(rows):
        y = 62 - i * 12
        text(ax, 7, y + 1.8, label, size=8.0)
        text(ax, 7, y - 3.5, f"{hours:g} h/件 · {state}", size=7.1, color=GRAY)
        ax.add_patch(Rectangle((bx, y - 2.5), count * unit, 5.5, facecolor=color, edgecolor="none"))
        text(ax, bx + count * unit + 2, y + 0.25, str(count), size=8.4, color=color)
    line(ax, [(bx, 29.5), (bx + 24 * unit, 29.5)], color=GRAY, lw=0.45)
    for tick in (0, 8, 16, 24):
        x = bx + tick * unit
        line(ax, [(x, 29.5), (x, 28)], color=GRAY, lw=0.45)
        text(ax, x, 25.4, str(tick), size=7.0, color=GRAY, ha="center")
    line(ax, [(7, 21.5), (163, 21.5)], color=NAVY, lw=0.65)
    text(ax, 7, 16, "机加工、清洗、单头组焊、PT、UT、CMM：各1站；每阶段PT另设2停留位。", size=7.7, serif=True)
    text(ax, 7, 9.3, "每层10 h：300→20℃按50℃/h缓冷5.6 h，保温2 h，升温/转运预留2.4 h。", size=7.3, serif=True)
    text(ax, 7, 3.4, "依据：HJ-W-S01；共44个热过程/等待位；热时隙为规划输入，首批跨日组织。", size=7.0, color=GRAY, serif=True)
    save(fig, "station-resources", description="完整圆环小批试制的预制缓冷和检测资源规划",
         sources=["deliverables/process/ring-final-welding-card.json resource_planning", "deliverables/process/ring-final-welding-card.md §5", "deliverables/process/ring-production-resource-card.md"],
         semantics={"kind": "capacity_planning", "calculated_object": "完整圆环座体", "target_parts_per_shift": r["parts_per_8h_shift"], "shift_h": 8, "feed_interval_s": r["feed_interval_s"], "thermal_slot_reserved_h_each_layer": 10, "thermal_slot_basis_h": {"cooling_300_to_20_at_50C_per_h": 5.6, "hold": 2, "heating_and_transfer_reserve": 2.4}, "positions": {"first_cycle_reserved": r["first_independent_thermal_positions"], "second_cycle_reserved": r["second_independent_thermal_positions"], "delayed_PT_wait": r["delayed_PT_positions"], "total": r["thermal_and_delay_positions_subtotal"]}, "heat_slots_are_planning_not_thermal_history_results": True, "actual_capacity_verified": RING_CARD["capacity_verified"]})


def precoat_section():
    fig, ax = canvas(95)
    text(ax, 7, 90, "圆环分层连接局部剖面", size=9.2, color=NAVY)
    text(ax, 163, 90, "层次示意 · 不按厚度比例", size=7.8, color=GRAY, ha="right")
    # A machined shallow recess in QT supports the two nickel layers. The
    # final NiFe55 fillet joins the second layer to the steel shell wall.
    seat = [(17, 42), (113, 42), (113, 64), (80, 64), (80, 73), (17, 73)]
    ax.add_patch(Polygon(seat, facecolor=SEAT, edgecolor=NAVY, lw=0.8, hatch="///"))
    ax.add_patch(Rectangle((80, 64), 33, 4.3, facecolor=OCHRE, edgecolor=NAVY, lw=0.65))
    ax.add_patch(Rectangle((80, 68.3), 33, 4.7, facecolor="#86A8A2", edgecolor=NAVY, lw=0.65))
    ax.add_patch(Rectangle((113.7, 35), 12, 49, facecolor=SHELL, edgecolor=NAVY, lw=0.8, hatch="\\\\"))
    # Schematic fillet envelope, not a claimed macrosection or dilution field.
    weld = [(104.5, 73), (113.7, 73), (113.7, 82), (111.9, 80), (109.8, 77.8), (107.5, 75.9)]
    ax.add_patch(Polygon(weld, facecolor=NAVY, edgecolor=NAVY, lw=0.8))
    line(ax, [(73, 73), (80, 73)], color=GRAY, ls="--", lw=0.5)
    text(ax, 45.5, 56.5, "QT450-10座体", size=8.4, color=NAVY, ha="center")
    text(ax, 120, 60, "Q235B\n壳体", size=8.1, color=NAVY, ha="center")
    text(ax, 17, 81.5, "CI-A1高镍首层", size=8.1, color=OCHRE)
    line(ax, [(58, 81.5), (65, 81.5), (89, 66.1)], color=OCHRE)
    text(ax, 17, 77, "低碳Ni99第二层", size=8.1, color=TEAL)
    line(ax, [(61, 77), (70, 77), (96, 70.6)], color=TEAL)
    text(ax, 132, 81.5, "NiFe55\n最终焊缝", size=8.0, color=NAVY)
    line(ax, [(130, 78), (123.7, 78), (111, 77)], color=NAVY)
    text(ax, 137, 49, "壳体\n外侧", size=7.6, color=GRAY, ha="center")
    text(ax, 17, 34.5, "截面对应：QT→CI-A1→低碳Ni99→NiFe55→Q235B", size=7.9, serif=True)
    line(ax, [(7, 28.5), (163, 28.5)], color=NAVY, lw=0.65)
    stages = [
        (7, "① 壳外首次连接", "首层预热/缓冷\n清渣、修整与中间PT"),
        (63, "② 壳外第二层与终加工", "低碳层→缓冷/延迟PT\n连接面/孔终加工→清洗"),
        (120, "③ 入壳最终组焊", "脉冲GTAW＋NiFe55\n温控、铜屏障与卸夹检测"),
    ]
    for x, title, sub in stages:
        text(ax, x, 23.3, title, size=8.0, color=NAVY)
        text(ax, x, 13.7, sub, size=7.1)
    text(ax, 85, 4.3, "两层预制完成后再终加工精密孔；高温预制与入壳低热组焊分别制定温度制度。", size=7.35, color=GRAY, ha="center", serif=True)
    save(fig, "precoat-section", description="铸铁到钢壳的分层材料链及加工顺序",
         sources=["project/submission-baseline.yaml material_route", "cad/generated/ring-baseline/ring-precoat-design.json", "deliverables/process/ring-final-welding-card.json"],
         semantics={"kind": "section_schematic", "primary_object": "完整圆环座体8个局部预制窗口", "not_to_scale": True, "material_chain": ["QT450-10", "CI-A1首层", "低碳Ni99第二层", "NiFe55最终焊缝", "Q235B"], "precoat_window": BASELINE["material_route"]["precoat_windows"], "first_layer_travel_speed_mm_min": BASELINE["material_route"]["first_layer"]["travel_speed_mm_min"], "second_layer_paths": 3, "actual_macrosection_claim": False, "machining_sequence": "两层壳外预制及检查后，最终孔和连接面加工，清洗干燥后入壳组焊"})


def main():
    design_route()
    process_comparison()
    precision_budget()
    station_resources()
    precoat_section()
    relative_fonts = {}
    for key, value in FONT_PATHS.items():
        path = Path(value)
        relative_fonts[key] = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else value
    document = {
        "purpose": "比赛说明书插图；可编辑脚本与矢量输出",
        "palette": {"navy": NAVY, "teal": TEAL, "ochre": OCHRE, "background": "white"},
        "fonts": relative_fonts,
        "figure_text_size_pt": "7.0–9.2，正文图注在排版文件内另设",
        "figures": METADATA,
    }
    (OUT / "figure-sources.json").write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(METADATA)} figures (PNG, SVG and PDF) in {OUT}")


if __name__ == "__main__":
    main()
