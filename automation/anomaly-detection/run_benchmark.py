"""运行 100 个正常与 100 个异常注入试验的事件级检测基准。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "automation" / "anomaly-detection" / "results" / "benchmark"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_detector import detect, score_events  # noqa: E402
from signal_simulator import simulate_trial  # noqa: E402


def _robustness_curves(seed: int, trials: int) -> dict[str, object]:
    """运行时压力曲线：短事件召回、噪声误报和电流静态偏置误报。"""
    duration_curve = []
    for index, duration in enumerate((0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.20)):
        detected = 0
        for trial in range(trials):
            data = simulate_trial(f"D-{index}-{trial}", True, seed + index * 1000 + trial, duration_s=8.0, sample_rate_hz=200.0, anomaly_duration_s=duration, anomaly_names=("current_drop",))
            score = score_events(data, detect(data))
            detected += int(score["tp"] > 0)
        duration_curve.append({"duration_s": duration, "detection_rate": detected / trials})

    noise_curve = []
    for index, noise_scale in enumerate((1.0, 1.5, 2.0, 2.5, 3.0)):
        false_trials = 0
        false_events = 0
        for trial in range(trials):
            data = simulate_trial(f"N-{index}-{trial}", False, seed + 10000 + index * 1000 + trial, noise_scale=noise_scale)
            score = score_events(data, detect(data))
            false_trials += int(score["fp"] > 0)
            false_events += int(score["fp"])
        noise_curve.append({"noise_scale": noise_scale, "false_positive_trial_rate": false_trials / trials, "false_positive_events_per_trial": false_events / trials})

    bias_curve = []
    for index, bias in enumerate((0.0, 1.0, 2.0, 3.0, 4.0)):
        false_trials = 0
        for trial in range(trials):
            data = simulate_trial(f"B-{index}-{trial}", False, seed + 20000 + index * 1000 + trial, current_bias=bias)
            score = score_events(data, detect(data))
            false_trials += int(score["fp"] > 0)
        bias_curve.append({"current_bias_a": bias, "false_positive_trial_rate": false_trials / trials})
    return {"short_event_duration": duration_curve, "normal_noise": noise_curve, "current_bias": bias_curve}


def run_benchmark(normal_count: int, injected_count: int, seed: int, robustness_trials: int = 20) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows: list[dict[str, object]] = []
    for index in range(normal_count):
        data = simulate_trial(f"N-{index + 1:03d}", False, seed + index)
        detection = detect(data)
        score = score_events(data, detection)
        rows.append({"trial_id": data["sample_id"], "class": "normal", "injected": False, **{key: value for key, value in score.items() if key != "delays_s"}, "mean_delay_s": ""})
    for index in range(injected_count):
        data = simulate_trial(f"A-{index + 1:03d}", True, seed + normal_count + index)
        detection = detect(data)
        score = score_events(data, detection)
        delays = [float(item) for item in score["delays_s"]]
        rows.append({"trial_id": data["sample_id"], "class": "injected", "injected": True, **{key: value for key, value in score.items() if key != "delays_s"}, "mean_delay_s": float(np.mean(delays)) if delays else ""})

    tp = int(sum(int(row["tp"]) for row in rows))
    fp = int(sum(int(row["fp"]) for row in rows))
    fn = int(sum(int(row["fn"]) for row in rows))
    normal_rows = [row for row in rows if row["class"] == "normal"]
    injected_rows = [row for row in rows if row["class"] == "injected"]
    delays = [float(row["mean_delay_s"]) for row in injected_rows if row["mean_delay_s"] != ""]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    summary = {
        "normal_trials": normal_count,
        "injected_trials": injected_count,
        "seed": seed,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "false_positive_rate_trial": float(np.mean([int(row["fp"]) > 0 for row in normal_rows])) if normal_rows else 0.0,
        "false_positive_rate_event_per_normal_trial": fp / normal_count if normal_count else 0.0,
        "mean_detection_delay_s": float(np.mean(delays)) if delays else None,
        "median_detection_delay_s": float(np.median(delays)) if delays else None,
        "robustness_curves": _robustness_curves(seed + normal_count + injected_count, robustness_trials) if robustness_trials > 0 else {},
        "robustness_trials_per_point": robustness_trials,
        "statement": "事件级规则检测基准，信号和异常均为仿真注入；短事件、噪声和传感器偏置曲线用于暴露在线边界，阈值仍需用真实设备数据重新标定。",
    }
    return rows, summary


def write_outputs(rows: list[dict[str, object]], summary: dict[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with (output_dir / "trial-metrics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 异常检测基准结果",
        "",
        "> 100 个正常试验 + 100 个异常注入试验；全部信号为 simulated，不是焊机采集。",
        "",
        "| 指标 | 数值 |",
        "| --- | ---: |",
        f"| TP | {summary['tp']} |",
        f"| FP | {summary['fp']} |",
        f"| FN | {summary['fn']} |",
        f"| precision | {summary['precision']:.3%} |",
        f"| recall | {summary['recall']:.3%} |",
        f"| F1 | {summary['f1']:.3%} |",
        f"| FPR（正常试验有误报） | {summary['false_positive_rate_trial']:.3%} |",
        f"| FPR（每正常试验误报事件数） | {summary['false_positive_rate_event_per_normal_trial']:.6f} |",
        f"| 平均检测延迟 (s) | {summary['mean_detection_delay_s'] if summary['mean_detection_delay_s'] is not None else 'N/A'} |",
        f"| 中位检测延迟 (s) | {summary['median_detection_delay_s'] if summary['median_detection_delay_s'] is not None else 'N/A'} |",
        "",
        "匹配规则：同一信号、时间区间重叠或相差不超过 0.2 s 计为命中；FP/FN 为事件级统计，FPR 同时给出正常试验级和事件率口径。",
        "",
        "## 鲁棒性曲线",
        "",
        "短于最小持续时间的脉冲按设计会被去抖；曲线用于决定采样率、阈值和后续硬件触发策略。",
        "",
        "| 电流异常持续时间 (s) | 检出率 |",
        "| ---: | ---: |",
        *[f"| {item['duration_s']:.3f} | {item['detection_rate']:.3%} |" for item in summary["robustness_curves"].get("short_event_duration", [])],
        "",
        "| 正常噪声倍数 | 试验级误报率 | 每试验误报事件数 |",
        "| ---: | ---: | ---: |",
        *[f"| {item['noise_scale']:.1f} | {item['false_positive_trial_rate']:.3%} | {item['false_positive_events_per_trial']:.3f} |" for item in summary["robustness_curves"].get("normal_noise", [])],
        "",
        "| 电流静态偏置 (A) | 试验级误报率 |",
        "| ---: | ---: |",
        *[f"| {item['current_bias_a']:.1f} | {item['false_positive_trial_rate']:.3%} |" for item in summary["robustness_curves"].get("current_bias", [])],
    ]
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--normal-count", type=int, default=100)
    parser.add_argument("--injected-count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--robustness-trials", type=int, default=20)
    args = parser.parse_args()
    rows, summary = run_benchmark(args.normal_count, args.injected_count, args.seed, args.robustness_trials)
    write_outputs(rows, summary, args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
