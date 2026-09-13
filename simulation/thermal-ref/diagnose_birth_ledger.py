"""最小元素级出生焓账诊断，不调用 Elmer。

用与 Fortran 回调相同的集中质量定义，检查部分激活时出生源、质量增量
和离散焓变化是否守恒；结果用于决定后续修改位置。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def heat(t: float, cp: float = 700.0, latent: float = 0.0) -> float:
    return cp * (t - 20.0) + latent * float(100.0 <= t < 200.0)


def element_energy(temp: np.ndarray, frac: float, rho: float = 1.0) -> float:
    return rho * frac * float(np.mean([heat(float(t)) for t in temp]))


def birth_source(old: np.ndarray, frac_delta: float, rho: float = 1.0, birth=20.0) -> float:
    # 当前 Fortran signed inverse mapping 的元素总和：每个节点对八个角点权重总和为 1。
    # 因此元素总出生源应等于 rho*dfrac*(Hbirth - 平均 Hold)。
    return rho * frac_delta * (heat(birth) - float(np.mean([heat(float(t)) for t in old])))


def case(name: str, old: np.ndarray, new: np.ndarray, prior: float, current: float) -> dict:
    de = current - prior
    before = element_energy(old, prior)
    after = element_energy(new, current)
    # 去除显式外部热源/散热后的理论焓变化：新增质量在 birth 温度出生。
    expected = de * heat(20.0) + current * float(np.mean([heat(float(t)) for t in new])) - prior * float(np.mean([heat(float(t)) for t in old]))
    source = birth_source(old, de)
    return {
        "case": name,
        "energy_before_j": before,
        "energy_after_j": after,
        "birth_source_j": source,
        "expected_net_change_j": expected,
        "actual_net_change_j": after - before,
        # 出生源是冷焓修正项，进入方程后应抵消新增质量被旧温度初始化的能量。
        "closure_error_j": (after - before) + source,
    }


def main() -> None:
    old = np.full(8, 1500.0)
    new = np.full(8, 1500.0)
    rows = [
        case("same_material_partial_birth", old, new, 0.25, 0.50),
        case("shared_node_material_transition", old, np.array([1500, 1500, 1500, 1500, 20, 20, 20, 20], float), 0.25, 0.50),
        case("full_activation", old, new, 0.0, 1.0),
    ]
    result = {
        "version": "BIRTH-LEDGER-PROBE-1",
        "cases": rows,
        "element_formula_closes": bool(max(abs(r["closure_error_j"]) for r in rows) < 1e-10),
        "interpretation": "若元素账闭合而 Elmer 仍有缺陷，根因位于共享节点质量/容量装配或回调调用时序。",
    }
    out = Path(__file__).parent / "results" / "birth-ledger-probe.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
