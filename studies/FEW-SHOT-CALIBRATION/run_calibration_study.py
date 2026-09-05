"""只生成合成校准演示，禁止写入实测目录。"""
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from hanjie.measurement.few_shot_calibration import FewShotCalibrator


def main() -> int:
    calibrator = FewShotCalibrator()
    trials = calibrator.generate_synthetic_physical_trials()
    report = calibrator.calibrate_from_trials(trials)
    out_dir = ROOT / "data" / "synthetic" / "few-shot-calibration"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = [dict(asdict(t), synthetic_values=t.synthetic_values.tolist()) for t in trials]
    (out_dir / "trials.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "calibration_summary.json").write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
    print("synthetic_demo: fit and leave-one-out only; no physical validation or uncertainty-reduction claim")
    print(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
