"""读取当前圆环pWPS，生成八段两道的局部与产品坐标路径。"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "automation" / "path-planning" / "results" / "weld-path.json"
sys.path.insert(0, str(ROOT / "src"))
from hanjie.domain.submission import read_submission


def get_default_radius() -> float:
    return float(read_submission()["geometry"]["seat"]["outside_radius_mm"])


def sequence_for(name: str, count: int) -> list[int]:
    half = count // 2
    if name == "S1":
        return list(range(count))
    if name == "S2":
        return [item for i in range(half) for item in (i, i + half)]
    if name == "S3":
        if count == 8:
            return [0, 4, 2, 6, 1, 5, 3, 7]
        return ([0, half] + [item for i in range(1, half) for item in ((half - i) % count, (count - i) % count)])[:count]
    raise ValueError(f"未知顺序: {name}")


def generate_path(points: int | None = None, sequence: str | None = None, radius_mm: float | None = None,
                  segment_length_mm: float | None = None) -> dict[str, object]:
    spec = read_submission()
    layout = spec["weld_layout"]
    points = layout["segment_count"] if points is None else points
    sequence = "S3" if sequence is None else sequence
    if radius_mm is None:
        radius_mm = get_default_radius()
    if segment_length_mm is None:
        segment_length_mm = layout["segment_length_mm"]
    if points < 2 or points % 2:
        raise ValueError("S2/S3 需要偶数焊接单元")
    if not math.isfinite(radius_mm) or radius_mm <= 6 or not 0 < segment_length_mm < 2 * math.pi * radius_mm / points:
        raise ValueError("焊接半径/段长不合法或相邻路径重叠")
    delta = segment_length_mm / radius_mm
    seat = spec["geometry"]["seat"]
    origin_z = seat["bottom_z_mm"] + seat["thickness_mm"]

    def polar(radius: float, angle: float) -> list[float]:
        return [radius * math.cos(angle), radius * math.sin(angle), 0]

    segments = []
    for index in range(points):
        angle = 2 * math.pi * index / points
        start_angle, end_angle = angle - delta / 2, angle + delta / 2
        segment = {
            "segment_id": index + 1,
            "angle_deg": index * 360 / points,
            "actual_arc_length_mm": segment_length_mm,
            "effective_connection_length_mm": layout["effective_segment_length_mm"],
            "geometry": "circular_arc",
            "center_local_mm": [0.0, 0.0, 0.0],
            "radius_mm": radius_mm,
            "sweep_angle_rad": delta,
        }
        for name, radius, theta in (("approach", radius_mm - 6, angle), ("start", radius_mm, start_angle),
                                    ("end", radius_mm, end_angle), ("retract", radius_mm - 6, angle)):
            local = polar(radius, theta)
            segment[f"{name}_local_mm"] = local
            segment[f"{name}_product_mm"] = [local[0], local[1], origin_z]
            segment[f"{name}_mm"] = local  # 历史调用别名，coordinate_system 明确其为局部坐标。
        segments.append(segment)
    order = sequence_for(sequence, points)
    is_current = (points == layout["segment_count"] and [i + 1 for i in order] == layout["sequence"]
                  and math.isclose(radius_mm, seat["outside_radius_mm"])
                  and math.isclose(segment_length_mm, layout["segment_length_mm"]))
    commands = [{"pass_id": p, "segment_id": i + 1, "actual_arc_length_mm": segment_length_mm,
                 "nominal_arc_time_s": segment_length_mm / spec["final_GTAW"]["travel_speed_mm_s"]}
                for p in range(1, layout["pass_count"] + 1) for i in order]
    return {
        "units": "mm",
        "path_role": "joint_reference_centerline",
        "tcp_waypoints_complete": False,
        "pass_height_policy": "根道与盖面复用接头参考线；实际TCP按枪姿态/弧长标定，盖面按实测根道轮廓及弧长控制修正，不照抄根道TCP高度",
        "source_type": "design",
        "process_version": spec["version"] if is_current else "historical-layout-override",
        "operation": "final_GTAW" if is_current else "layout_study",
        "sequence": sequence,
        "sequence_segment_ids": [item + 1 for item in order],
        "pass_count": layout["pass_count"],
        "total_arc_length_mm": sum(item["actual_arc_length_mm"] for item in commands),
        "coordinate_system": "*_mm历史别名及*_local_mm均为座体上表面孔中心局部坐标；机器人接入使用明确的*_product_mm或经标定变换后的工作站坐标",
        "coordinate_frames": {"local": {"origin_product_mm": [0.0, 0.0, origin_z], "rotation_degrees": [0, 0, 0]},
                              "product": {"origin": "壳体下端A面中心", "z_axis": "壳体理论轴线"},
                              "robot": {"transform_calibrated": False, "tcp_calibrated": False}},
        "segments": segments,
        "arc_commands": commands,
        "statement": "路径为数字样机输出，机器人安全点位与实际 TCP 标定需现场复核。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=int, default=None, help="默认读取当前圆环基准；覆盖值只作布局研究")
    parser.add_argument("--sequence", choices=("S1", "S2", "S3"), default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = generate_path(args.points, args.sequence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {len(result['segments'])} 段 {result['pass_count']} 道路径: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
