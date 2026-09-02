"""运行一次端到端数字样机 Demo：视觉定位、路径规划、信号检测、追溯。"""

from __future__ import annotations

import json
import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000, help="视觉数字样本数量")
    args = parser.parse_args()
    python = sys.executable
    run([python, "automation/vision/run_benchmark.py", "--count", str(args.count)])
    run([python, "automation/path-planning/generate_weld_path.py"])
    run([python, "automation/anomaly-detection/signal_simulator.py"])
    run([python, "automation/anomaly-detection/anomaly_detector.py"])
    run([python, "automation/traceability/database.py"])
    vision_summary = json.loads((ROOT / "automation/vision/results/summary.json").read_text(encoding="utf-8"))
    anomaly_summary = json.loads((ROOT / "automation/anomaly-detection/results/W2026-001-anomalies.json").read_text(encoding="utf-8"))
    demo = {
        "vision": vision_summary,
        "path": "automation/path-planning/results/weld-path.json",
        "anomaly_event_count": anomaly_summary["event_count"],
        "traceability_db": "automation/traceability/results/traceability.db",
        "statement": "端到端结果包含数字样本和仿真过程信号，不代表实物焊接采集。",
    }
    output = ROOT / "automation/app/results/demo-summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(demo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"数字样机 Demo 完成: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
