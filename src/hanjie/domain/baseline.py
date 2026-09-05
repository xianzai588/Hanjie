"""Single Source of Truth (SSOT) 基线配置加载与校验模块。

本模块确保全工程所有子系统（CAD、有限元仿真、路径规划、视觉检测、测试套件、报告生成）
仅从 project/ 下的权威配置文件中读取参数，坚决杜绝魔法数字与参数分叉。
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Dict
import yaml


def find_project_root() -> Path:
    """自动向上寻访工程根目录。"""
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / "project" / "baseline.yaml").exists():
            return parent
        if (parent / "pyproject.toml").exists() and (parent / "project").exists():
            return parent
    # 默认回退
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = find_project_root()
PROJECT_CONFIG_DIR = PROJECT_ROOT / "project"


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"配置必须是字典结构: {path}")
    return data


@functools.lru_cache(maxsize=1)
def get_baseline() -> Dict[str, Any]:
    return load_yaml(PROJECT_CONFIG_DIR / "baseline.yaml")


@functools.lru_cache(maxsize=1)
def get_materials() -> Dict[str, Any]:
    return load_yaml(PROJECT_CONFIG_DIR / "materials.yaml")


@functools.lru_cache(maxsize=1)
def get_process() -> Dict[str, Any]:
    return load_yaml(PROJECT_CONFIG_DIR / "process.yaml")


@functools.lru_cache(maxsize=1)
def get_tolerance() -> Dict[str, Any]:
    return load_yaml(PROJECT_CONFIG_DIR / "tolerance.yaml")


def get_geometry() -> Dict[str, Any]:
    return get_baseline()["geometry"]


def get_fixture() -> Dict[str, Any]:
    return get_baseline()["fixture"]


def load_all_configs() -> Dict[str, Any]:
    return {
        "baseline": get_baseline(),
        "materials": get_materials(),
        "process": get_process(),
        "tolerance": get_tolerance(),
    }


def validate_parameter_consistency() -> Dict[str, Any]:
    """检查跨配置与领域参数一致性，若有冲突立即抛出异常。"""
    base = get_baseline()
    geom = base["geometry"]
    fixt = base["fixture"]
    tol = base["tolerance"]

    # 关键基线校验
    errors = []
    if abs(geom["wing_outer_radius_mm"] - 74.98) > 1e-4:
        errors.append(f"wing_outer_radius_mm 必须为 74.98，当前为 {geom['wing_outer_radius_mm']}")

    if abs(geom["shell_outer_diameter_mm"] - 160.0) > 1e-4:
        errors.append(f"shell_outer_diameter_mm 必须为 160.0，当前为 {geom['shell_outer_diameter_mm']}")

    if abs(geom["bearing_bore_diameter_mm"] - 40.0) > 1e-4:
        errors.append(f"bearing_bore_diameter_mm 必须为 40.0，当前为 {geom['bearing_bore_diameter_mm']}")

    if fixt["type"] != "tapered_mandrel":
        errors.append(f"fixture.type 必须为 tapered_mandrel，当前为 {fixt['type']}")

    if abs(tol["position_limit_mm"] - 0.05) > 1e-4:
        errors.append(f"position_limit_mm 必须为 0.05，当前为 {tol['position_limit_mm']}")

    if errors:
        raise ValueError("SSOT 基线校验未通过:\n" + "\n".join(errors))

    return {"status": "PASSED", "version": base.get("version", "V4.1")}
