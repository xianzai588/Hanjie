"""生成 COMPETITION-R1 的确定性鲁棒边界，不进行随机抽样或实物性能推断。"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import yaml
from matplotlib import font_manager, rcParams

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "studies/ROBUST-BOUNDARY/results"

_FALLBACK_CJK_FONTS = (
    "C:/Windows/Fonts/Deng.ttf",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
)

# 两张边界图随技术包交付并登记进 SHA256 冻结记录，必须逐字节可复现：
# 固定元素 ID 的盐值，并关闭 SVG 内嵌日期，否则每次重建都会产生纯噪声差异。
SVG_HASHSALT = "hanjie-competition-r1"
SVG_METADATA = {"Date": None}


def configure_cjk_font() -> str | None:
    """matplotlib 默认字体缺少中文字形；优先复用报告字体候选，避免图内中文变成空框。"""
    candidates = []
    try:
        report = yaml.safe_load((ROOT / "project/report.yaml").read_text(encoding="utf-8"))
        candidates.extend(item["regular"] for item in report["pdf"]["font_candidates"])
    except (OSError, KeyError, TypeError):
        pass
    candidates.extend(_FALLBACK_CJK_FONTS)
    for path in candidates:
        if not Path(path).is_file():
            continue
        try:
            font_manager.fontManager.addfont(path)
            name = font_manager.FontProperties(fname=path).get_name()
        except (OSError, ValueError, RuntimeError):
            continue
        rcParams["font.family"] = "sans-serif"
        rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
        rcParams["axes.unicode_minus"] = False
        return name
    return None


def load_inputs():
    authority = yaml.safe_load((ROOT / "project/competition-authority.yaml").read_text(encoding="utf-8"))
    assessment = json.loads((ROOT / "studies/COMPETITION-DESIGN/results/assessment.json").read_text(encoding="utf-8"))
    return authority, assessment


def strength_boundary(authority, assessment):
    rows = {r["layout"]: r for r in assessment["four_pass_comparison"]}
    six = rows["6P-FAIR_B"]["required_allowable_mpa"]
    eight = rows["8P-FAIR_B"]["required_allowable_mpa"]
    load_multipliers = [round(0.50 + i * 0.05, 2) for i in range(31)]
    allowables = list(range(20, 121, 5))
    grid = []
    for load in load_multipliers:
        for allowable in allowables:
            six_ok = allowable >= load * six
            eight_ok = allowable >= load * eight
            region = "6P_and_8P" if six_ok else "8P_only" if eight_ok else "neither"
            grid.append({"load_multiplier": load, "allowable_mpa": allowable,
                         "six_p_ok": six_ok, "eight_p_ok": eight_ok, "region": region})
    # 给图使用连续阈值：许用应力低于曲线即不满足条件筛查。
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "strength-boundary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(grid[0]))
        writer.writeheader(); writer.writerows(grid)
    fig, ax = plt.subplots(figsize=(8.4, 5.2), dpi=160)
    ax.fill_between(load_multipliers, [m * eight for m in load_multipliers],
                    [m * six for m in load_multipliers], color="#f2c94c", alpha=.45,
                    label="6P失败、8P通过")
    ax.fill_between(load_multipliers, 0, [m * eight for m in load_multipliers],
                    color="#e76f51", alpha=.28, label="两者均不通过")
    ax.plot(load_multipliers, [m * six for m in load_multipliers], color="#1b4965", lw=2.2, label="6P阈值")
    ax.plot(load_multipliers, [m * eight for m in load_multipliers], color="#2a9d8f", lw=2.2, label="8P阈值")
    ax.axvline(authority["assumptions"]["load_scale"], color="#555", ls="--", lw=1)
    ax.axhline(authority["assumptions"]["assumed_allowable_mpa"], color="#555", ls=":", lw=1)
    ax.set(xlabel="载荷倍率（相对参考包络）", ylabel="假设许用应力 / MPa",
           title="COMPETITION-R1 确定性 6P → 8P 切换边界")
    ax.set_xlim(.5, 2.0); ax.set_ylim(0, 125); ax.grid(alpha=.2); ax.legend(loc="upper left", frameon=True)
    fig.tight_layout(); fig.savefig(OUT / "strength-boundary.svg", format="svg", metadata=SVG_METADATA); plt.close(fig)
    return {"basis": "required_allowable_mpa scales linearly with load multiplier",
            "thresholds": {"6P-FAIR_B": six, "8P-FAIR_B": eight},
            "reference_point": {"load_multiplier": authority["assumptions"]["load_scale"],
                                "allowable_mpa": authority["assumptions"]["assumed_allowable_mpa"],
                                "region": "6P_and_8P" if authority["assumptions"]["assumed_allowable_mpa"] >= six else "8P_only"},
            "grid_csv": "studies/ROBUST-BOUNDARY/results/strength-boundary.csv",
            "plot_svg": "studies/ROBUST-BOUNDARY/results/strength-boundary.svg"}


def position_boundary():
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from hanjie.domain.competition_design import read_spec
    spec = read_spec(ROOT)
    p, f = spec["precision"], spec["fixture"]
    tilt = 2 * p["support_height_spread_limit_mm"] / (3 * f["support_radius_mm"])
    tilt_radial = p["bore_length_mm"] * tilt
    allocations = p["radial_allocations_mm"]
    other = sum(v for k, v in allocations.items() if k != "thermal_residual_target") + tilt_radial
    limit_radial = p["limit_diameter_mm"] / 2
    scenarios = [
        ("当前目标", allocations["thermal_residual_target"], p["measurement_expanded_uncertainty_diameter_target_mm"], 0.0),
        ("工装差0.002", allocations["thermal_residual_target"], p["measurement_expanded_uncertainty_diameter_target_mm"], 0.002),
        ("测量不确定度恶化", allocations["thermal_residual_target"], 0.004, 0.0),
        ("工装差+测量恶化", allocations["thermal_residual_target"], 0.004, 0.002),
        ("热残余失效边界", limit_radial - other - p["measurement_expanded_uncertainty_diameter_target_mm"] / 2, p["measurement_expanded_uncertainty_diameter_target_mm"], 0.0),
    ]
    rows = []
    for name, thermal, uncertainty_dia, fixture_extra in scenarios:
        allowed = limit_radial - (other + fixture_extra) - uncertainty_dia / 2
        total_dia = 2 * (other + fixture_extra + thermal) + uncertainty_dia
        rows.append({"scenario": name, "other_radial_error_mm": round(other + fixture_extra, 6),
                     "measurement_uncertainty_diameter_mm": uncertainty_dia,
                     "thermal_residual_radial_mm": round(thermal, 6),
                     "thermal_max_allowed_radial_mm": round(allowed, 6),
                     "total_diameter_with_uncertainty_mm": round(total_dia, 6),
                     "closes": total_dia <= p["limit_diameter_mm"] + 1e-12})
    # 连续浅波纹薄裙的梁近似：把半波长视为简支弯曲长度，给出数量级应变检查。
    t, wave_pitch, compression = 0.15, 24.0, 0.35
    half_span = wave_pitch / 2
    bending_strain = 6 * compression * t / half_span**2
    skirt = {"configuration": "连续浅波纹金属薄裙＋刚性接料盘", "thickness_mm": t,
             "wave_pitch_mm": wave_pitch, "radial_compliance_required_mm": compression,
             "beam_approx_bending_strain": round(bending_strain, 7),
             "interpretation": "数量级筛查；候选弹簧不锈钢需以材料证书屈服应变和热态循环试验复核"}
    payload = {"limit_diameter_mm": p["limit_diameter_mm"], "limit_radial_mm": limit_radial,
               "tilt_radial_allowance_mm": tilt_radial, "other_radial_error_baseline_mm": other,
               "formula": "thermal_max = 0.025 - other_radial_error - measurement_uncertainty_diameter/2",
               "rows": rows, "continuous_skirt_check": skirt,
               "plot": "studies/ROBUST-BOUNDARY/results/position-boundary.svg"}
    (OUT / "position-boundary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (OUT / "position-boundary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    fig, ax = plt.subplots(figsize=(8.4, 4.8), dpi=160)
    names = [r["scenario"] for r in rows]; vals = [r["thermal_max_allowed_radial_mm"] for r in rows]
    bars = ax.bar(names, vals, color=["#2a9d8f", "#f2c94c", "#f4a261", "#e76f51", "#1b4965"])
    ax.axhline(allocations["thermal_residual_target"], color="#333", ls="--", label="当前热残余目标 0.008 mm")
    ax.set_ylabel("热残余最大允许径向量 / mm"); ax.set_title("Ø0.05 位置度预算：热残余确定性边界")
    ax.grid(axis="y", alpha=.2); ax.legend(loc="upper right")
    for bar, val in zip(bars, vals): ax.text(bar.get_x()+bar.get_width()/2, val+.0001, f"{val:.4f}", ha="center", fontsize=8)
    fig.tight_layout(); fig.savefig(OUT / "position-boundary.svg", format="svg", metadata=SVG_METADATA); plt.close(fig)
    return payload


def main():
    # 图件随包交付，必须在中文字形可用的前提下渲染；文字转路径以保证任何查看器一致。
    font_name = configure_cjk_font()
    rcParams["svg.fonttype"] = "path"
    rcParams["svg.hashsalt"] = SVG_HASHSALT
    if font_name is None:
        print("警告：未找到中文字体，边界图内的中文可能缺字形")
    authority, assessment = load_inputs()
    payload = {"version": "COMPETITION-R1-DETERMINISTIC-BOUNDARY-1",
               "cjk_font": font_name,
               "strength": strength_boundary(authority, assessment), "position": position_boundary()}
    (OUT / "boundary-summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
