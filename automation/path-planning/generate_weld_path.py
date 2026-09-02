"""为六点柔顺连接结构生成可复核的焊接路径与顺序文件。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "automation" / "path-planning" / "results" / "weld-path.json"


def sequence_for(name: str, count: int) -> list[int]:
    half = count // 2
    if name == "S1":
        return list(range(count))
    if name == "S2":
        return [item for i in range(half) for item in (i, i + half)]
    if name == "S3":
        return ([0, half] + [item for i in range(1, half) for item in ((half - i) % count, (count - i) % count)])[:count]
    raise ValueError(f"未知顺序: {name}")


def generate_path(points: int = 6, sequence: str = "S3", radius_mm: float = 73.8,
                  segment_length_mm: float = 18.0) -> dict[str, object]:
    if points % 2:
        raise ValueError("S2/S3 需要偶数焊接单元")
    delta = segment_length_mm / radius_mm

    def polar(radius: float, angle: float) -> list[float]:
        return [radius * math.cos(angle), radius * math.sin(angle), 0]

    segments = []
    for index in range(points):
        angle = 2 * math.pi * index / points
        start_angle, end_angle = angle - delta / 2, angle + delta / 2
        segments.append({
            "segment_id": index + 1,
            "angle_deg": index * 360 / points,
            "approach_mm": polar(radius_mm - 6, angle),
            "start_mm": polar(radius_mm, start_angle),
            "end_mm": polar(radius_mm, end_angle),
            "retract_mm": polar(radius_mm - 6, angle),
        })
    order = sequence_for(sequence, points)
    return {
        "units": "mm",
        "sequence": sequence,
        "sequence_segment_ids": [item + 1 for item in order],
        "coordinate_system": "轴承孔中心为原点，+X 向右，+Y 逆时针，+Z 沿轴线",
        "segments": segments,
        "statement": "路径为数字样机输出，机器人安全点位与实际 TCP 标定需现场复核。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--points", type=int, default=6)
    parser.add_argument("--sequence", choices=("S1", "S2", "S3"), default="S3")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = generate_path(args.points, args.sequence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {args.points} 点 {args.sequence} 路径: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
