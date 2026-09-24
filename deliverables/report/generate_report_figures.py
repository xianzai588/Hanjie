"""生成说明书总览图，数据只读取已登记的数字设计结果。"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "deliverables/report/figures"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads((ROOT / "studies/COMPETITION-DESIGN/results/robust-selection.json").read_text(encoding="utf-8"))
    rows = data["ranking"]
    font_path = Path(r"C:\Windows\Fonts\msyh.ttc")
    font = FontProperties(fname=str(font_path)) if font_path.exists() else FontProperties()
    plt.rcParams.update({
        "font.family": font.get_name() if font_path.exists() else "DejaVu Sans",
        "axes.unicode_minus": False,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
    })

    fig = plt.figure(figsize=(11.2, 4.15), dpi=240, facecolor="white")
    gs = fig.add_gridspec(1, 2, width_ratios=(1.02, 1.35), wspace=0.16,
                          left=0.035, right=0.985, top=0.86, bottom=0.16)
    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[0, 1])
    teal = "#0F6F78"
    navy = "#183B56"
    orange = "#D97742"
    pale = "#EEF4F5"
    grey = "#5D6B78"

    ax0.set_xlim(0, 1)
    ax0.set_ylim(0, 1)
    ax0.axis("off")
    ax0.text(0.0, 1.05, "设计骨架与放行边界", fontsize=12, fontproperties=font,
             fontweight="bold", color=navy, va="bottom")
    cards = [
        (0.02, 0.61, 0.29, 0.25, "工艺", "6段 × 4道自动 TIG\nNiFe 55 实心棒\n1→4→3→6→2→5"),
        (0.355, 0.61, 0.29, 0.25, "定位", "内锥驱动胀套\n独立压环与 A/B 基准\n焊后同基准终镗"),
        (0.69, 0.61, 0.29, 0.25, "洁净", "连续薄裙屏障\n盘面朝上、贴壁回收\n任一条件失效即拒绝"),
    ]
    for x, y, w, h, title, body in cards:
        ax0.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                                     facecolor=pale, edgecolor="#B8CDD0", linewidth=0.8))
        ax0.text(x + 0.025, y + h - 0.06, title, fontsize=10, fontproperties=font,
                 fontweight="bold", color=teal, va="top")
        ax0.text(x + 0.025, y + h - 0.12, body, fontsize=7.4, fontproperties=font,
                 color=grey, va="top", linespacing=1.45)
    ax0.annotate("", xy=(0.79, 0.49), xytext=(0.21, 0.49),
                 arrowprops={"arrowstyle": "-|>", "lw": 1.4, "color": orange})
    ax0.text(0.50, 0.53, "制造前：数字筛查", fontsize=8.2, fontproperties=font,
             color=orange, ha="center", va="center")
    ax0.text(0.02, 0.36, "当前已知", fontsize=9.3, fontproperties=font, fontweight="bold", color=navy)
    ax0.text(0.02, 0.29, "几何、守恒、候选排序和控制逻辑已可复算", fontsize=8.0,
             fontproperties=font, color=grey)
    ax0.text(0.02, 0.18, "仍需放行", fontsize=9.3, fontproperties=font, fontweight="bold", color="#9A4D2D")
    ax0.text(0.02, 0.11, "批次金相、宏观截面、接头强韧性、焊后 CMM", fontsize=8.0,
             fontproperties=font, color=grey)

    names = ["6P-FAIR_B", "8P-FAIR_B", "Continuous"]
    heat = [r["net_heat_input_kj"] for r in rows]
    req = [r["required_allowable_mpa"] for r in rows]
    y = list(range(3))
    ax1.set_title("同一筛查口径下的候选取舍", loc="left", fontsize=12,
                  fontproperties=font, fontweight="bold", color=navy, pad=12)
    ax1.barh(y, heat, color=[teal, "#6E8DA3", "#C5CDD3"], height=0.46, alpha=0.95)
    ax1.set_yticks(y, names, fontproperties=font, fontsize=8.6)
    ax1.invert_yaxis()
    ax1.set_xlabel("名义净热输入 / kJ", fontproperties=font, fontsize=8.5)
    ax1.grid(axis="x", color="#DDE4E8", linewidth=0.7)
    ax1.set_axisbelow(True)
    ax1.spines[["top", "right", "left"]].set_visible(False)
    ax1.tick_params(axis="x", labelsize=8, colors=grey)
    for yi, h, r in zip(y, heat, req):
        ax1.text(h + 9, yi, f"{h:.2f} kJ | {r:.2f} MPa", va="center", fontsize=8,
                 fontproperties=font, color=grey)
    ax1.text(0.0, -0.24, "6P 为当前首选，8P 保留为承载筛查切换方案；Continuous 仅作高热输入参照。",
             transform=ax1.transAxes, fontsize=7.4, fontproperties=font, color=grey)
    fig.suptitle("QT450-10 / Q235B 异种接头：设计选择与证据边界", fontsize=14,
                 fontproperties=font, fontweight="bold", color=navy, y=0.985)
    fig.savefig(OUT / "design-evidence-overview.png", dpi=300, bbox_inches="tight")
    fig.savefig(OUT / "design-evidence-overview.svg", bbox_inches="tight")
    fig.savefig(OUT / "design-evidence-overview.pdf", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
