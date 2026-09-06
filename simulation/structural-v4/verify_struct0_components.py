"""生成 STRUCT-0-PREP 独立本构算例；不读取未获准的焊接热场。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hanjie.simulation.structural_prep import uniaxial_elastoplastic_history


def build_results() -> dict[str, object]:
    materials = yaml.safe_load((ROOT / "project" / "materials.yaml").read_text(encoding="utf-8"))["materials"]
    cases = {}
    for name in ("q235b", "qt450_10"):
        props = materials[name]["nominal_properties_20c"]
        elastic = float(props["elastic_modulus_gpa"]) * 1000.0
        yield_strength = float(props["yield_strength_mpa"])
        yield_strain = yield_strength / elastic

        mechanical_strain = np.array([0.0, 0.5 * yield_strain, 1.5 * yield_strain, 2.0 * yield_strain, 0.0])
        unload = uniaxial_elastoplastic_history(mechanical_strain, np.zeros_like(mechanical_strain), elastic, yield_strength)

        delta_temperature = np.array([0.0, 40.0, 80.0, 160.0, 240.0])
        thermal_strain = float(props["alpha_per_k"]) * delta_temperature
        constrained = uniaxial_elastoplastic_history(np.zeros_like(thermal_strain), thermal_strain, elastic, yield_strength)
        cases[name] = {
            "inputs": {
                "elastic_modulus_mpa": elastic,
                "yield_strength_mpa": yield_strength,
                "alpha_per_k": float(props["alpha_per_k"]),
                "hardening_modulus_mpa": 0.0,
            },
            "yield_unload": {
                "total_strain": mechanical_strain.tolist(),
                "stress_mpa": unload["stress_mpa"].tolist(),
                "plastic_strain": unload["plastic_strain"].tolist(),
                "plastic_work_mj_mm3": unload["plastic_work_mj_mm3"].tolist(),
                "checks": {
                    "yield_bound_respected": bool(np.max(np.abs(unload["stress_mpa"])) <= yield_strength + 1e-9),
                    "permanent_strain_generated": bool(unload["equivalent_plastic_strain"][-1] > 0),
                    "plastic_work_nonnegative_monotonic": bool(np.all(np.diff(unload["plastic_work_mj_mm3"]) >= -1e-12)),
                },
            },
            "constrained_thermal_expansion": {
                "delta_temperature_c": delta_temperature.tolist(),
                "thermal_strain": thermal_strain.tolist(),
                "stress_mpa": constrained["stress_mpa"].tolist(),
                "plastic_strain": constrained["plastic_strain"].tolist(),
                "plastic_work_mj_mm3": constrained["plastic_work_mj_mm3"].tolist(),
                "checks": {
                    "compression_sign": bool(np.all(constrained["stress_mpa"][1:] < 0)),
                    "yield_bound_respected": bool(np.max(np.abs(constrained["stress_mpa"])) <= yield_strength + 1e-9),
                    "plastic_work_nonnegative_monotonic": bool(np.all(np.diff(constrained["plastic_work_mj_mm3"]) >= -1e-12)),
                },
            },
        }
    return {
        "stage": "STRUCT-0-PREP-CONSTITUTIVE-BASELINES",
        "evidence_level": "component_unit_verification",
        "model": "一维小应变、关联流动、理想弹塑性材料点",
        "temperature_field_source": "prescribed_independent_cases",
        "uses_thermal_0_4r1": False,
        "cases": cases,
        "all_checks_pass": all(all(section["checks"].values()) for case in cases.values() for section in (case["yield_unload"], case["constrained_thermal_expansion"])),
        "limitations": [
            "不是三维 J2 整件有限元求解器",
            "未包含温度相关插值、焊材本构、接触、焊道激活和应力自由出生状态",
            "不能作为实际焊接残余应力或位置度结果",
        ],
    }


def main() -> int:
    output = ROOT / "simulation" / "structural-v4" / "results" / "struct0-prep"
    output.mkdir(parents=True, exist_ok=True)
    result = build_results()
    target = output / "constitutive-baselines.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
