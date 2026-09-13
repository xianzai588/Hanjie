"""运行当前 R1 截面在既有三维FV求解器中的单段热诊断。

这是实际求解器执行，不是四道整件热历史：源路径仍为历史60 mm局部窗，
用于先检查新棒径和3.5 mm截面是否破坏质量、温度与非线性收敛。
"""
from pathlib import Path
import copy, json, sys
sys.path[:0] = [str(Path(__file__).resolve().parents[2]/"simulation/thermal-ref"),
                str(Path(__file__).resolve().parents[2]/"simulation/thermal-v5")]
import run_plan7_fvm as fvm
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/"simulation/thermal-ref/results/competition-r2/r1-singlepass"

old_load = fvm.core.load


def load(path):
    value = old_load(path)
    name = str(path).replace("\\", "/")
    if name.endswith("thermal-mass-closed-v5.4r1.yaml"):
        value = copy.deepcopy(value)
        value["deposition"]["efficiency"] = .85
    if name.endswith("project/process.yaml"):
        value = copy.deepcopy(value)
        nominal = value["process"]["nominal"]
        nominal["filler_diameter_mm"] = 1.6
        # 单段诊断按效率下界反算3.5 mm等面积截面；R1四道固定送丝仍以配置文件为准。
        nominal["filler_feed_rate_mm_s"] = 5.375867793
    return value


def main():
    fvm.core.load = load
    if OUT.exists():
        raise FileExistsError(OUT)
    fvm.run(OUT, False)
    import numpy as np
    history = np.genfromtxt(OUT/"history.csv", delimiter=",", names=True)
    result = {"stage":"THERMAL-R1-SINGLEPASS-DIAGNOSTIC", "evidence_level":"solver_result_unvalidated",
              "solver_executed":True, "geometry":"R1 wire diameter and lower-efficiency equivalent leg; historical 60 mm source window",
              "compatible_with_four_pass_full_part":False, "returncode":0,
              "time_step_s":.1, "duration_s":60., "maximum_temperature_c":float(np.max(history["max_c"])),
              "minimum_temperature_c":float(np.min(history["min_c"])),
              "deposited_volume_mm3":float(history["deposit_volume_mm3"][-1]),
              "maximum_absolute_energy_residual_j":float(np.max(np.abs(history["residual_j"]))),
              "maximum_relative_energy_residual":float(np.max(np.abs(history["residual_j"])/np.maximum(history["source_j"],1e-12))),
              "nonlinear_solver_residual_j":json.loads((OUT/"execution.json").read_text())["maximum_nonlinear_residual_j"],
              "formal_thermal_structural_allowed":False,
              "reason":"仅验证R1截面接入既有FV求解链；四道时序、108 mm路径和热结构映射尚未运行"}
    (OUT/"assessment.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
