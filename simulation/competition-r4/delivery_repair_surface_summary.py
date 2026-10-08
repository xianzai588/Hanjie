"""Compare the preserved quarter-second source checks and publish their budget.

Temperature iterates are diagnostic numerical outputs. They have not passed
space/time independence or source qualification and are not actual predictions.
The source energy partition is algebraically checkable without those claims.
"""
import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "delivery_repair_surface_heat_20261008"


def read_rows(path):
    with path.open(encoding="utf8") as stream:
        return [{k: float(v) for k, v in row.items()} for row in csv.DictReader(stream)]


def summarize(folder, last, name, width, liquid_factor):
    history = [r for r in read_rows(folder / "thermal-history.csv") if r["t_s"] <= last+1e-10]
    partition = [r for r in read_rows(folder / "source-partition-history.csv") if r["t_s"] <= last+1e-10]
    witnesses = [r for r in read_rows(folder / "precoat-interface-observer/melting-depth-witness.csv")
                 if r["t_s"] <= last+1e-10 and r["material"] == 1]
    energy = {key: sum(r[key] for r in partition) for key in
              ["command_J", "wire_J", "arc_intercept_J", "uncaptured_J", "arc_to_QT_J", "arc_to_Ni_J"]}
    closure = energy["command_J"]-energy["wire_J"]-energy["arc_intercept_J"]-energy["uncaptured_J"]
    if abs(closure) > 1e-6:
        raise RuntimeError("Source budget did not close")
    return dict(name=name, actual_time_s=history[-1]["t_s"],
                Gaussian_one_over_e_half_width_mm=width,
                Gaussian_95pct_projected_diameter_mm=2*np.sqrt(np.log(20))*width,
                liquid_transport_factor=liquid_factor,
                growth_rise_length_mm=3.2,
                commanded_deposit_mass_g=.17*history[-1]["t_s"],
                energy=energy, source_energy_balance_error_J=closure,
                maximum_enthalpy_residual_balance_J=max(abs(r["balance_J"]) for r in history),
                numerical_iterate_peak_C=max(r["max_C"] for r in history),
                numerical_iterate_QT_peak_C=max(r["QT_max_C"] for r in history),
                numerical_P1_QT_melt_depth_below_z115_mm=max(115-r["minimum_melt_z_mm"] for r in witnesses),
                space_time_convergence_verified=False,
                actual_temperature_prediction_qualified=False,
                mechanical_input_qualified=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--reference-root", type=Path, default=Path("E:/AI/bisai/Hanjie"))
    a = p.parse_args()
    old = a.reference_root / "simulation/competition-r4/results/mma-first-end80-r12-phase-front-dt0125-20261007"
    cases = [
        summarize(old, .125, "既有体热源", 3.2, 3),
        summarize(OUT / "surface-k1-first1s", .125, "可见表面／原宽度", 3.2, 1),
        summarize(OUT / "surface-k1-groove95-fixed-growth-first1s", .125,
                  "可见表面／6 mm投影", 6/(2*np.sqrt(np.log(20))), 1),
    ]
    quarter = [summarize(old, .25, "既有体热源", 3.2, 3),
               summarize(OUT / "surface-k1-first1s", .25, "可见表面／原宽度", 3.2, 1)]
    report = dict(
        decision="不把既有体热源的全界面液化与未完成机械态作为制造达标证据；先将热通量宽度与沉积前沿长度解耦，再以实际几何进行热源/部分出生单元资格验证。仅上述输入取得资格后继续存留状态机械计算。",
        corrected_source_front_coupling=True,
        common_inputs=dict(current_A=110, voltage_V=23, efficiency=.8,
                           commanded_net_budget_W=2024, speed_mm_min=100,
                           deposited_mass_rate_g_s=.17, initial_QT_C=300,
                           mesh_nodes=18450, mesh_tetrahedra=77499,
                           CAD_deposit_volume_one_wing_mm3=215.54042990141917,
                           original_growth_rise_length_mm=3.2),
        matched_first_increment_cases=cases, quarter_second_cases=quarter,
        surface_source_scope="替换为第一可见上表面通量；未截获能量单列损失，不重新归一化。基础Ni导热仍为Ni200参考值×0.75，移除液相factor3不等同获得实际CI-A1导热。",
        geometry_width_scope="6 mm为槽覆盖要求，用95%圆Gaussian投影直径定义唯一几何候选；不把覆盖要求视为实际熔池宽度或源标定。",
        numerical_stop="原宽表面在0.25 s、唯一6 mm投影候选在0.125 s跨越2800℃无蒸发适用上限。保存数值诊断响应，停止机械传递；该结果不等同实物工艺失败。",
        withheld_trial="surface-k1-groove95-first1s复用了热源宽度作为沉积上升长度；作为输入耦合诊断保留原始数据，排除于受控对比，修订候选保持上升长度3.2 mm。",
        applicability="空间/时间独立性未完成，源尺度与部分出生单元可见面未取得资格；数值峰与P1熔深仅定位表示问题，非实际温度/熔深预测。能量预算闭合是代数校核，不替代制造资格。",
        actual_first_layer_joint_passed=False, cold_geometry_qualified=False,
        full_manufacturing_chain_passed=False,
        sources=[dict(url="https://doi.org/10.1590/0104-9224/SI2201.10",
                      scope="表面Gaussian热源和熔池表面宽度确定尺度的方法；原文GTAW钢板验证，不能直接赋予本CI-A1源尺寸或效率。"),
                 dict(url="https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/add_ded/add_ded_method_abstract.html",
                      scope="工程顺序热/力学沉积抽象；参数资格与熔池流动边界需独立处理。")])
    (OUT / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    font = ROOT / "assets/fonts/NotoSansSC-Regular.ttf"
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({"font.family": font_manager.FontProperties(fname=str(font)).get_name(),
                         "axes.unicode_minus": False, "pdf.fonttype": 42,
                         "svg.fonttype": "path", "font.size": 8})
    colors = ["#3F6B68", "#A48352", "#CBD2D4"]
    fig, ax = plt.subplots(figsize=(170/25.4, 92/25.4))
    fig.subplots_adjust(left=.25, right=.96, top=.82, bottom=.26)
    y = np.arange(3)
    offset = np.zeros(3)
    for key, label, color in zip(["wire_J", "arc_intercept_J", "uncaptured_J"],
                                 ["进入金属携带焓", "表面／体内截获", "未截获损失"], colors):
        values = np.array([r["energy"][key] for r in cases])
        ax.barh(y, values, left=offset, color=color, height=.5, label=label)
        for yi, left, value in zip(y, offset, values):
            if value > 20:
                ax.text(left+value/2, yi, f"{value:.1f}", ha="center", va="center", fontsize=7)
        offset += values
    ax.set_yticks(y, [r["name"] for r in cases])
    ax.invert_yaxis()
    ax.set(xlim=(0, 265), xlabel="首个0.125 s净预算分项 / J")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.2), frameon=False, ncol=3, fontsize=7)
    fig.suptitle("同一253 J预算：热源形状改变截获与空间分配", fontsize=11, color="#24364B")
    fig.text(.03, .035, "保持CAD、0.17 g/s供料及3.2 mm沉积上升长度；各分项闭合。\n表面算例尚未取得热源和网格时间资格，未转为残余应力或工艺达标结论。", fontsize=7, color="#59666F")
    for ext in ["png", "pdf", "svg"]:
        fig.savefig(OUT / f"source-budget-comparison.{ext}", dpi=300)
    plt.close(fig)
    print(json.dumps({"first_increment_source_budgets_J": [r["energy"] for r in cases],
                      "full_manufacturing_chain_passed": False}, indent=2), flush=True)


if __name__ == "__main__":
    main()
