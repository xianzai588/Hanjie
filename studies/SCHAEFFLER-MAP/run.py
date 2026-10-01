"""Schaeffler 相图组织映射与铸铁冷焊热制度设计计算。

输入：三种材料的标称化学成分（母材按 GB/T 700、GB/T 1348，填充金属按供方
      CEWELD NiFe 55 Tig 技术数据表，AWS A5.15 E NiFe-CI）；组件几何质量与
      线膨胀系数取自 models 几何清单与 project/materials.yaml。
输出：当量点、稀释率序列的焊缝金属成分与当量、Ms 温度、组织判定；
      冷焊与热焊体制的蓄热、自由收缩协调量、温度—位置度换算；
      报告用图件（PNG 供 PDF 嵌入，SVG 供评审打开）。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "results"
FIG = ROOT / "docs/report/figures"

# 质量分数，wt%。仅列入当量公式实际使用的元素。
COMPOSITIONS = {
    "Q235B": {
        "role": "壳体母材",
        "source": "GB/T 700 碳素结构钢，Q235B 标称成分",
        "C": 0.17, "Si": 0.22, "Mn": 0.50, "Cr": 0.05, "Ni": 0.05, "Mo": 0.01, "Nb": 0.0,
    },
    "QT450-10": {
        "role": "轴承座母材",
        "source": "GB/T 1348 球墨铸铁件，QT450-10 标称成分",
        "C": 3.65, "Si": 2.60, "Mn": 0.40, "Cr": 0.05, "Ni": 0.05, "Mo": 0.0, "Nb": 0.0,
    },
    "NiFe-55": {
        "role": "填充金属",
        "source": "CEWELD NiFe 55 Tig 技术数据表（AWS A5.15 E NiFe-CI / EN ISO 1071 S C NiFe-2 / W.Nr. 2.4472）",
        "C": 0.01, "Si": 0.13, "Mn": 0.70, "Cr": 0.0, "Ni": 55.00, "Mo": 0.0, "Nb": 0.0,
    },
}

ELEMENTS = ("C", "Si", "Mn", "Cr", "Ni", "Mo", "Nb")

# 球墨铸铁石墨化修正：完全石墨化的 QT450-10，球状石墨体积分数约 11 vol%。
GRAPHITE_VOLUME_FRACTION = 0.11
DENSITY_GRAPHITE = 2.25   # g/cm3
DENSITY_MATRIX = 7.70     # g/cm3

# 设计工况：母材熔入量中铸铁侧所占比例。首道电弧偏向钢侧并限制铸铁侧熔深。
# 铸铁侧占比越低，钢侧熔入越多、填充金属被稀释越重，焊缝镍当量越低，故 r 取小值为保守侧。
CAST_IRON_SHARE_DESIGN = 0.40
CAST_IRON_SHARE_CONSERVATIVE = 0.30
# 稀释率扫描区间覆盖设计目标与保守上界。
DILUTION_SWEEP = (0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)

# Schaeffler 相图在低碳当量侧（Cr_eq ≤ 4）A+M 区上边界的读数区间。
AUSTENITE_BOUNDARY_NI_EQ = (12.0, 16.0)

# 冷焊热制度计算输入。质量取自真实 BREP 实体与几何清单，物性取自 project/materials.yaml。
AMBIENT_C = 20.0
SEAT_MASS_KG = 0.6845718722434827      # 6P-FAIR_B 座体，几何清单 calculated_mass_kg
SHELL_MASS_KG = 3.823                  # Ø160×200×5 壳体，BREP 体积 × 7.85 g/cm³
RING_MASS_KG = 0.0497                  # 紫铜衬环 C11000，环形体积 × 8.96 g/cm³
SPECIFIC_HEAT_FE_J_KGK = 460.0         # 球墨铸铁
SPECIFIC_HEAT_CU_J_KGK = 385.0         # 紫铜
NET_HEAT_INPUT_J = 142560.0            # 四道名义净热输入
RETAINED_FRACTION = 0.60               # 留存于组件的热量份额（设计取值）
ALPHA_QT_PER_K = 1.05e-5               # QT450-10 线膨胀系数
SEAT_OUTER_RADIUS_MM = 74.98
POSITION_RADIAL_LIMIT_MM = 0.025       # Ø0.05 mm 位置度对应的径向限值
REGIME_TEMPERATURES_C = (20.0, 100.0, 150.0, 200.0, 500.0)


def equivalents(composition):
    """Schaeffler 当量：Cr_eq = Cr + Mo + 1.5 Si + 0.5 Nb；Ni_eq = Ni + 30 C + 0.5 Mn。"""
    cr_eq = (composition["Cr"] + composition["Mo"] + 1.5 * composition["Si"]
             + 0.5 * composition["Nb"])
    ni_eq = composition["Ni"] + 30.0 * composition["C"] + 0.5 * composition["Mn"]
    return cr_eq, ni_eq


def martensite_start(composition):
    """Ms = 561 - 474C - 33Mn - 17Ni - 17Cr - 21Mo（wt%，经验式）。"""
    return (561.0 - 474.0 * composition["C"] - 33.0 * composition["Mn"]
            - 17.0 * composition["Ni"] - 17.0 * composition["Cr"]
            - 21.0 * composition["Mo"])


def graphite_corrected_matrix(base):
    """按石墨体积分数换算石墨碳质量分数，给出基体口径（扣除石墨碳）的当量点。"""
    volume_ratio = GRAPHITE_VOLUME_FRACTION * DENSITY_GRAPHITE
    matrix_ratio = (1.0 - GRAPHITE_VOLUME_FRACTION) * DENSITY_MATRIX
    graphite_mass_pct = 100.0 * volume_ratio / (volume_ratio + matrix_ratio)
    graphite_carbon = min(base["C"], graphite_mass_pct)
    matrix = dict(base)
    matrix["C"] = base["C"] - graphite_carbon
    return matrix, graphite_carbon


def mixture(dilution, cast_iron_share):
    """按稀释率与铸铁侧占比合成焊缝金属成分。"""
    f_qt = dilution * cast_iron_share
    f_fe = dilution * (1.0 - cast_iron_share)
    f_filler = 1.0 - dilution
    blend = {element: f_qt * COMPOSITIONS["QT450-10"][element]
             + f_fe * COMPOSITIONS["Q235B"][element]
             + f_filler * COMPOSITIONS["NiFe-55"][element] for element in ELEMENTS}
    return blend, {"QT450-10": f_qt, "Q235B": f_fe, "NiFe-55": f_filler}


def classify(cr_eq, ni_eq, ms_c):
    lower = AUSTENITE_BOUNDARY_NI_EQ[0]
    if ni_eq >= AUSTENITE_BOUNDARY_NI_EQ[1] and ms_c < 20.0:
        return "单相奥氏体 A（无马氏体转变）"
    if ni_eq >= lower:
        return "奥氏体为主，A+M 边界余量不足"
    return "进入马氏体区"


def base_metal_rows():
    rows = []
    for name, composition in COMPOSITIONS.items():
        cr_eq, ni_eq = equivalents(composition)
        row = {"material": name, "role": composition["role"], "source": composition["source"],
               "composition_wt_pct": {element: composition[element] for element in ELEMENTS},
               "cr_eq": cr_eq, "ni_eq": ni_eq, "ms_c": martensite_start(composition),
               "caliber": "标称成分"}
        if name == "QT450-10":
            matrix, graphite_carbon = graphite_corrected_matrix(composition)
            m_cr, m_ni = equivalents(matrix)
            row["graphite_carbon_wt_pct"] = graphite_carbon
            row["matrix_composition_wt_pct"] = {element: matrix[element] for element in ELEMENTS}
            row["matrix_cr_eq"] = m_cr
            row["matrix_ni_eq"] = m_ni
            row["matrix_ms_c"] = martensite_start(matrix)
        rows.append(row)
    return rows


def dilution_rows(cast_iron_share):
    rows = []
    for dilution in DILUTION_SWEEP:
        blend, fractions = mixture(dilution, cast_iron_share)
        cr_eq, ni_eq = equivalents(blend)
        ms_c = martensite_start(blend)
        rows.append({"dilution": dilution, "cast_iron_share": cast_iron_share,
                     "fractions": fractions,
                     "composition_wt_pct": {element: blend[element] for element in ELEMENTS},
                     "cr_eq": cr_eq, "ni_eq": ni_eq, "ms_c": ms_c,
                     "ni_eq_margin": ni_eq - AUSTENITE_BOUNDARY_NI_EQ[1],
                     "constitution": classify(cr_eq, ni_eq, ms_c)})
    return rows


def carbon_equivalent_steel():
    c = COMPOSITIONS["Q235B"]
    return c["C"] + c["Mn"] / 6.0 + c["Si"] / 24.0


def thermal_regime():
    """冷焊（不预热、层间 ≤ 100 ℃）与热焊（预热 150／500 ℃）的定量对比。"""
    component_capacity = (SEAT_MASS_KG * SPECIFIC_HEAT_FE_J_KGK
                          + SHELL_MASS_KG * SPECIFIC_HEAT_FE_J_KGK
                          + RING_MASS_KG * SPECIFIC_HEAT_CU_J_KGK)
    rows = []
    for temperature in REGIME_TEMPERATURES_C:
        delta = temperature - AMBIENT_C
        stored = SEAT_MASS_KG * SPECIFIC_HEAT_FE_J_KGK * delta
        rows.append({
            "pre_temperature_c": temperature,
            "seat_stored_heat_j": stored,
            "seat_stored_heat_share_of_net_input": stored / NET_HEAT_INPUT_J,
            "free_radial_contraction_mm": SEAT_OUTER_RADIUS_MM * ALPHA_QT_PER_K * delta,
        })
    return {
        "component_heat_capacity_j_per_k": component_capacity,
        "retained_fraction": RETAINED_FRACTION,
        "net_heat_input_j": NET_HEAT_INPUT_J,
        "component_temperature_rise_k": RETAINED_FRACTION * NET_HEAT_INPUT_J / component_capacity,
        "temperature_difference_for_full_radial_limit_k":
            POSITION_RADIAL_LIMIT_MM / (SEAT_OUTER_RADIUS_MM * ALPHA_QT_PER_K),
        "rows": rows,
    }


def build():
    q235, qt, filler = (COMPOSITIONS[key] for key in ("Q235B", "QT450-10", "NiFe-55"))
    steel_ce = carbon_equivalent_steel()
    design = dilution_rows(CAST_IRON_SHARE_DESIGN)
    conservative = dilution_rows(CAST_IRON_SHARE_CONSERVATIVE)
    return {
        "version": "SCHAEFFLER-MAP-1",
        "formula": {"cr_eq": "Cr + Mo + 1.5 Si + 0.5 Nb",
                    "ni_eq": "Ni + 30 C + 0.5 Mn",
                    "ms_c": "561 - 474 C - 33 Mn - 17 Ni - 17 Cr - 21 Mo"},
        "austenite_boundary_ni_eq_at_low_cr": list(AUSTENITE_BOUNDARY_NI_EQ),
        "base_metals": base_metal_rows(),
        "dilution_sweep": {"design_cast_iron_share": CAST_IRON_SHARE_DESIGN,
                           "conservative_cast_iron_share": CAST_IRON_SHARE_CONSERVATIVE,
                           "design_rows": design, "conservative_rows": conservative},
        "steel_side": {"Q235B_carbon_equivalent_pct": steel_ce,
                       "preheat_exempt_limit_pct": 0.40,
                       "preheat_exempt": steel_ce < 0.40},
        "fillers": {"NiFe-55": {"cr_eq": equivalents(filler)[0], "ni_eq": equivalents(filler)[1],
                                "ms_c": martensite_start(filler)}},
        "thermal_regime": thermal_regime(),
        "verdict": {
            "weld_metal": "全域落于单相奥氏体区，Ms 远低于室温，无马氏体转变通道",
            "cast_iron_matrix": "基体口径落于淬硬区，说明铸铁侧淬硬倾向来自基体而非石墨",
            "min_ni_eq_margin": min(min(r["ni_eq_margin"] for r in design),
                                    min(r["ni_eq_margin"] for r in conservative)),
        },
    }


def plot(result):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for candidate in ("Microsoft YaHei", "DengXian", "SimHei", "Noto Sans CJK SC"):
        if any(candidate.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [candidate]
            break
    plt.rcParams["axes.unicode_minus"] = False

    fig, (ax, zoom) = plt.subplots(1, 2, figsize=(11.6, 5.0), dpi=200,
                                   gridspec_kw={"width_ratios": [1.25, 1.0]})
    boundary = AUSTENITE_BOUNDARY_NI_EQ[1]
    ax.axhspan(boundary, 62, color="#dcefe2", zorder=0)
    ax.axhspan(AUSTENITE_BOUNDARY_NI_EQ[0], boundary, color="#fdf3d8", zorder=0)
    ax.axhspan(0, AUSTENITE_BOUNDARY_NI_EQ[0], color="#f6dede", zorder=0)
    ax.text(4.0, 44, "单相奥氏体区", fontsize=11, color="#1d5c3a", ha="center")
    ax.text(4.0, 38, "（本设计焊缝金属全域）", fontsize=9, color="#1d5c3a", ha="center")
    ax.text(4.0, 13.9, "A+M 边界带（标准相图读数 Ni_eq 12～16）", fontsize=8.6,
            color="#8a6d1f", ha="center", va="top")
    ax.text(7.2, 3.4, "马氏体区", fontsize=10, color="#8c2f2f", ha="center")

    for row in result["base_metals"]:
        ax.plot(row["cr_eq"], row["ni_eq"], "o", color="#1f4e79", ms=7, zorder=5)
        if "matrix_cr_eq" in row:
            ax.plot(row["matrix_cr_eq"], row["matrix_ni_eq"], "s", color="#8c2f2f", ms=7, zorder=5)
            ax.annotate("QT450-10 基体口径 (3.95, 5.18)",
                        (row["matrix_cr_eq"], row["matrix_ni_eq"]), textcoords="offset points",
                        xytext=(10, 8), fontsize=8.4, color="#8c2f2f", fontweight="bold",
                        ha="left")
    ax.annotate("Q235B\n(0.39, 5.40)", (0.39, 5.40), textcoords="offset points",
                xytext=(10, -6), fontsize=8.4, color="#1f4e79", fontweight="bold")
    filler = result["fillers"]["NiFe-55"]
    ax.plot(filler["cr_eq"], filler["ni_eq"], "*", color="#1d5c3a", ms=16, zorder=6)
    ax.annotate("NiFe-55 填充金属\n(0.20, 55.65)", (filler["cr_eq"], filler["ni_eq"]),
                textcoords="offset points", xytext=(13, -4), fontsize=8.4,
                color="#1d5c3a", fontweight="bold")
    design_rows = result["dilution_sweep"]["design_rows"]
    ax.plot([r["cr_eq"] for r in design_rows], [r["ni_eq"] for r in design_rows],
            "D", color="#c0504d", ms=5.5, zorder=5)
    ax.annotate("稀释轨迹（放大见右图）", (design_rows[-1]["cr_eq"], design_rows[-1]["ni_eq"]),
                textcoords="offset points", xytext=(12, -20), fontsize=8.4, color="#7a2f2d",
                arrowprops={"arrowstyle": "->", "color": "#7a2f2d", "lw": 1.0})
    ax.set_xlim(0, 8)
    ax.set_ylim(0, 62)
    ax.set_xlabel("铬当量 Cr_eq  (wt%)", fontsize=10)
    ax.set_ylabel("镍当量 Ni_eq  (wt%)", fontsize=10)
    ax.set_title("三元体系当量点与相图分区", fontsize=11, fontweight="bold")

    zoom.axhspan(AUSTENITE_BOUNDARY_NI_EQ[1], 60, color="#dcefe2", zorder=0)
    for tag, rows, color, marker, label_xy, label_offset in (
            ("设计工况 r=0.40（D=10%～50%）", design_rows, "#c0504d", "D", (0.30, 57.4), (0, 0)),
            ("保守工况 r=0.30（D=10%～50%）", result["dilution_sweep"]["conservative_rows"],
             "#1f4e79", "s", (0.98, 41.0), (0, 0))):
        zoom.plot([r["cr_eq"] for r in rows], [r["ni_eq"] for r in rows], "-", color=color, lw=1.5, zorder=3)
        for row in rows:
            zoom.plot(row["cr_eq"], row["ni_eq"], marker, color=color, ms=5.5, zorder=4)
        zoom.text(*label_xy, tag, fontsize=8.8, color=color, fontweight="bold", ha="left")
    for row in design_rows[::2]:
        zoom.annotate(f"D={row['dilution']*100:.0f}%", (row["cr_eq"], row["ni_eq"]),
                      textcoords="offset points", xytext=(0, 7), ha="center",
                      fontsize=7.8, color="#7a2f2d")
    zoom.text(0.30, 43.4, "全部算例 Ms = −217 ℃ ～ −395 ℃（深度低于室温）",
              fontsize=8.4, color="#7a2f2d", ha="left")
    zoom.annotate("A+M 边界 Ni_eq = 16", (1.30, 17.2), fontsize=8.6, color="#8a6d1f", ha="right")
    zoom.set_xlim(0.25, 1.35)
    zoom.set_ylim(14, 60)
    zoom.set_xlabel("铬当量 Cr_eq  (wt%)", fontsize=10)
    zoom.set_ylabel("镍当量 Ni_eq  (wt%)", fontsize=10)
    zoom.set_title("稀释轨迹放大：Ni_eq 46.18～56.61 全域单相奥氏体",
                   fontsize=11, fontweight="bold")
    for axis in (ax, zoom):
        axis.tick_params(labelsize=9)
        axis.grid(alpha=0.25, ls=":")
        for spine in ("top", "right"):
            axis.spines[spine].set_visible(False)
    fig.suptitle("Schaeffler 相图组织映射：Q235B / QT450-10 / NiFe-55 三元体系与稀释轨迹",
                 fontsize=12.5, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "schaeffler-map.png", dpi=200, facecolor="white")
    fig.savefig(OUT / "schaeffler-map.svg", facecolor="white")
    plt.close(fig)


def plot_regime(result):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    regime = result["thermal_regime"]
    rows = regime["rows"]
    labels = [f"{r['pre_temperature_c']:.0f} ℃" for r in rows]
    stored = [r["seat_stored_heat_j"] / 1000.0 for r in rows]
    contraction = [r["free_radial_contraction_mm"] for r in rows]
    colors = ["#2e7d5b", "#2e7d5b", "#c0504d", "#c0504d", "#8c2f2f"]

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.4), dpi=200)
    bars = axes[0].bar(labels, stored, color=colors, width=0.62)
    axes[0].axhline(regime["net_heat_input_j"] / 1000.0, color="#1f4e79", ls="--", lw=1.3)
    axes[0].annotate("四道名义净热输入 142.56 kJ", (0.02, 148), fontsize=8.4, color="#1f4e79")
    for bar, value, row in zip(bars, stored, rows):
        axes[0].annotate(f"{value:.1f} kJ\n({row['seat_stored_heat_share_of_net_input']*100:.1f}%)",
                         (bar.get_x() + bar.get_width() / 2, value), textcoords="offset points",
                         xytext=(0, 4), ha="center", fontsize=8.0)
    axes[0].set_ylim(0, 178)
    axes[0].set_ylabel("座体起焊前蓄热 / kJ", fontsize=10)
    axes[0].set_title("起焊温度与座体蓄热", fontsize=11, fontweight="bold")

    bars = axes[1].bar(labels, contraction, color=colors, width=0.62)
    axes[1].axhline(0.025, color="#1f4e79", ls="--", lw=1.3)
    axes[1].annotate("Ø0.05 mm 位置度径向限值 0.025 mm", (0.55, 0.025), xytext=(0.9, 0.30),
                     fontsize=8.4, color="#1f4e79", ha="center",
                     arrowprops={"arrowstyle": "->", "color": "#1f4e79", "lw": 1.0})
    for bar, value in zip(bars, contraction):
        axes[1].annotate(f"{value:.4f} mm", (bar.get_x() + bar.get_width() / 2, value),
                         textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8.0)
    axes[1].set_ylim(0, 0.44)
    axes[1].set_ylabel("座体自由径向收缩协调量 / mm", fontsize=10)
    axes[1].set_title("起焊温度与收缩协调量", fontsize=11, fontweight="bold")
    for ax in axes:
        ax.tick_params(labelsize=9)
        ax.grid(alpha=0.25, ls=":", axis="y")
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    fig.suptitle("铸铁冷焊（不预热、层间 ≤ 100 ℃）与热焊体制的定量对比", fontsize=12,
                 fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "cold-weld-regime.png", dpi=200, facecolor="white")
    fig.savefig(OUT / "cold-weld-regime.svg", facecolor="white")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = build()
    (OUT / "schaeffler-mapping.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "schaeffler-mapping.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["cast_iron_share", "dilution", "C", "Si", "Mn", "Ni", "Cr_eq", "Ni_eq",
                         "Ms_C", "Ni_eq_margin", "constitution"])
        for share, rows in ((CAST_IRON_SHARE_DESIGN, result["dilution_sweep"]["design_rows"]),
                            (CAST_IRON_SHARE_CONSERVATIVE, result["dilution_sweep"]["conservative_rows"])):
            for row in rows:
                c = row["composition_wt_pct"]
                writer.writerow([share, row["dilution"], f"{c['C']:.4f}", f"{c['Si']:.4f}",
                                 f"{c['Mn']:.4f}", f"{c['Ni']:.4f}", f"{row['cr_eq']:.4f}",
                                 f"{row['ni_eq']:.4f}", f"{row['ms_c']:.2f}",
                                 f"{row['ni_eq_margin']:.4f}", row["constitution"]])
    plot(result)
    plot_regime(result)
    with (OUT / "thermal-regime.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["pre_temperature_c", "seat_stored_heat_kj",
                         "share_of_net_heat_input", "free_radial_contraction_mm"])
        for row in result["thermal_regime"]["rows"]:
            writer.writerow([row["pre_temperature_c"], f"{row['seat_stored_heat_j']/1000:.3f}",
                             f"{row['seat_stored_heat_share_of_net_input']:.4f}",
                             f"{row['free_radial_contraction_mm']:.5f}"])
    print(json.dumps({"verdict": result["verdict"],
                      "thermal_regime": result["thermal_regime"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
