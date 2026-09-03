"""V3 误差预算：区分装配/制造尺寸链与自动化路径控制预算

装配链影响最终零件几何，自动化链影响焊枪轨迹，两者关联但不等价。
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def assembly_chain() -> dict[str, float]:
    """装配/制造尺寸链（影响最终轴承孔轴线位置度）

    壳体基准 → 夹具基准 → 自定心定位 → 轴承座初始偏心
    → 焊接收缩 → 松夹回弹 → 最终孔轴线

    Returns:
        各环节径向误差预算 (mm)，单边值
    """
    return {
        'shell_datum_A_flatness': 0.005,      # 壳体基准 A 平面度
        'shell_datum_B_axis': 0.003,          # 壳体轴线建立（从外圆）
        'fixture_mandrel_repeat': 0.008,      # 锥形心轴定位重复性
        'seat_initial_eccentric': 0.005,      # 座初始偏心（装配间隙）
        'weld_shrinkage': 0.012,              # 焊接收缩变形（主控项）
        'unclamping_springback': 0.002,       # 松夹回弹
    }


def automation_chain() -> dict[str, float]:
    """自动化路径控制预算（影响焊枪轨迹精度）

    视觉 → 标定 → TCP → 机器人重复定位 → 焊枪轨迹

    焊枪轨迹误差到最终零件几何误差之间还隔着焊缝成形和热收缩。

    Returns:
        各环节径向误差预算 (mm)
    """
    return {
        'vision_detection': 0.018,            # 视觉定位（P95）
        'camera_calibration': 0.012,          # 相机标定
        'robot_TCP': 0.003,                   # TCP 标定
        'robot_repeatability': 0.005,         # 机器人重复定位
    }


def generate_report() -> None:
    """生成误差预算报告"""
    assembly = assembly_chain()
    automation = automation_chain()

    lines = [
        "# V3 误差预算分配表",
        "",
        "**版本**：V3 · 2026-09-03",
        "",
        "## 1. 装配/制造尺寸链",
        "",
        "影响最终轴承孔轴线位置度的全链路误差源：",
        "",
        "| 环节 | 径向预算 (mm) | 说明 |",
        "| --- | ---: | --- |",
    ]

    for key, value in assembly.items():
        name_map = {
            'shell_datum_A_flatness': '壳体基准 A 平面度',
            'shell_datum_B_axis': '壳体轴线 B 建立',
            'fixture_mandrel_repeat': '锥形心轴定位重复性',
            'seat_initial_eccentric': '轴承座初始偏心',
            'weld_shrinkage': '焊接收缩变形',
            'unclamping_springback': '松夹回弹',
        }
        lines.append(f"| {name_map[key]} | {value:.3f} | |")

    assembly_sum = sum(assembly.values())
    lines.extend([
        f"| **线性最坏情况合计** | **{assembly_sum:.3f}** | 对应位置度 Ø{assembly_sum * 2:.3f} |",
        "",
        "**目标**：Ø0.05 mm 位置度 = 0.025 mm 径向总预算",
        "**当前合计**：{:.3f} mm ≈ Ø{:.3f} mm".format(assembly_sum, assembly_sum * 2),
        "",
        "**主控项**：焊接收缩变形占 {:.1f}%".format(assembly['weld_shrinkage'] / assembly_sum * 100),
        "",
        "---",
        "",
        "## 2. 自动化路径控制预算",
        "",
        "影响焊枪轨迹精度的误差源（不直接等于零件位置度）：",
        "",
        "| 环节 | 径向预算 (mm) | 说明 |",
        "| --- | ---: | --- |",
    ])

    for key, value in automation.items():
        name_map = {
            'vision_detection': '视觉定位',
            'camera_calibration': '相机标定',
            'robot_TCP': 'TCP 标定',
            'robot_repeatability': '机器人重复定位',
        }
        lines.append(f"| {name_map[key]} | {value:.3f} | |")

    automation_sum = sum(automation.values())
    lines.extend([
        f"| **线性最坏情况合计** | **{automation_sum:.3f}** | 焊枪轨迹控制目标 |",
        "",
        "---",
        "",
        "## 3. 两者关联",
        "",
        "**装配链**决定最终零件几何，是位置度验收依据。",
        "",
        "**自动化链**决定焊枪轨迹，通过焊缝成形影响装配链中的焊接收缩项。",
        "",
        "机器人 TCP 偏了 0.003 mm，并不意味着最终轴承孔轴线一定偏 0.003 mm；",
        "焊枪轨迹误差到最终零件几何误差之间还隔着焊缝成形和热收缩。",
        "",
        "---",
        "",
        "## 4. V3 修复说明",
        "",
        "**V2 问题**：把视觉、TCP、机器人、夹具、热变形线性相加到 0.025 mm，",
        "但这些来源混合了轨迹控制和零件几何两个不同层次。",
        "",
        "**V3 改进**：",
        "1. **装配链**：壳体基准 → 夹具 → 座偏心 → 焊接 → 回弹 → 最终孔轴线",
        "2. **自动化链**：视觉 → 标定 → TCP → 机器人 → 焊枪轨迹",
        "3. 夹具定位从 0.003 mm（Ø39.96 销不可信）改为 0.008 mm（锥形心轴）",
        "",
        "**边界**：",
        "- 本预算为设计分配，不是实测不确定度",
        "- 焊接收缩 0.012 mm 来自降阶模型估计，需实物 CMM 验证",
        "- 锥形心轴 0.008 mm 为设计假设，需夹具标定",
        "",
    ])

    output = ROOT / "docs" / "validation" / "position-error-budget-v3.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"已生成 V3 误差预算报告: {output}")


if __name__ == "__main__":
    generate_report()
