"""用工艺窗口与连续采样规则识别仿真过程异常。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "samples" / "W2026-001-simulated.json"
DEFAULT_OUTPUT = ROOT / "automation" / "anomaly-detection" / "results" / "W2026-001-anomalies.json"


WINDOWS = {
    "current": (70.0, 80.0, "A"),
    "voltage": (11.0, 13.0, "V"),
    "speed": (1.2, 1.8, "mm/s"),
    "temperature": (0.0, 200.0, "°C"),
}


def detect(data: dict[str, object]) -> dict[str, object]:
    timestamp = np.asarray(data["timestamp"], dtype=float)
    events = []
    for signal, (low, high, unit) in WINDOWS.items():
        values = np.asarray(data[signal], dtype=float)
        mask = (values < low) | (values > high)
        starts = np.flatnonzero(mask & ~np.r_[False, mask[:-1]])
        ends = np.flatnonzero(mask & ~np.r_[mask[1:], False])
        for start, end in zip(starts, ends):
            events.append({
                "signal": signal,
                "type": "out_of_window",
                "start_s": float(timestamp[start]),
                "end_s": float(timestamp[end]),
                "duration_s": float(timestamp[end] - timestamp[start]),
                "min": float(values[start:end + 1].min()),
                "max": float(values[start:end + 1].max()),
                "window": [low, high],
                "unit": unit,
            })
    return {
        "sample_id": data["sample_id"],
        "event_count": len(events),
        "events": events,
        "statement": "基于仿真信号的规则检测结果；阈值需由真实设备与工艺评定标定。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    result = detect(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

