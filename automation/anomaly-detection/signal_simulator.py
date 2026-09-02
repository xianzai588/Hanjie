"""生成过程监测仿真信号；明确标记为 simulated，不冒充焊机采集。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data" / "samples" / "W2026-001-simulated.json"


def simulate(duration_s: float = 20.0, sample_rate_hz: float = 20.0, seed: int = 20260902) -> dict[str, object]:
    rng = np.random.default_rng(seed)
    timestamp = np.arange(0.0, duration_s, 1.0 / sample_rate_hz)
    current = 75.0 + rng.normal(0.0, 0.8, timestamp.size)
    voltage = 12.0 + rng.normal(0.0, 0.08, timestamp.size)
    speed = 1.5 + rng.normal(0.0, 0.025, timestamp.size)
    temperature = 150.0 + 25.0 * (1.0 - np.exp(-timestamp / 4.0)) + rng.normal(0.0, 0.5, timestamp.size)
    anomalies = []

    def inject(name: str, start: float, end: float, values: tuple[float, float, float] | None = None) -> None:
        mask = (timestamp >= start) & (timestamp < end)
        if values:
            current[mask], voltage[mask], speed[mask] = values
        anomalies.append({"name": name, "start_s": start, "end_s": end})

    inject("current_drop", 6.0, 6.8, (35.0, 11.5, 1.5))
    inject("voltage_spike", 10.0, 10.6, (75.0, 16.2, 1.5))
    inject("speed_deviation", 14.0, 15.2, (75.0, 12.0, 2.5))
    inject("arc_interruption", 17.0, 17.5, (0.0, 0.0, 0.0))
    temperature[(timestamp >= 14.0) & (timestamp < 15.2)] += 55.0
    return {
        "sample_id": "W2026-001",
        "timestamp": [round(float(item), 4) for item in timestamp],
        "current": [round(float(item), 4) for item in current],
        "voltage": [round(float(item), 4) for item in voltage],
        "speed": [round(float(item), 4) for item in speed],
        "temperature": [round(float(item), 4) for item in temperature],
        "meta": {
            "process": "tig-simulated",
            "sequence": "S3",
            "preheat_c": 150.0,
            "operator": "simulation",
            "source_type": "simulated",
            "notes": "仅用于数据链路和异常识别逻辑验证；不是实际焊接采集。",
            "injected_anomalies": anomalies,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data = simulate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成仿真过程信号: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
