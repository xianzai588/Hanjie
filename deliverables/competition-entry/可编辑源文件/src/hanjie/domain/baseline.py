"""Hanjie 权威配置加载与跨文件一致性校验。

几何/夹具、工艺、公差三链分别由 baseline.yaml、process.yaml、tolerance.yaml
负责；本模块验证它们的交叉引用，不再让旧混合预算冒充当前产品预算。
"""

from __future__ import annotations

import functools
import json
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
    process = get_process()
    tolerance = get_tolerance()
    geom = base["geometry"]
    fixt = base["fixture"]

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

    if "tolerance" in base:
        errors.append("baseline.yaml 不得再包含旧混合 tolerance 链")
    if "process" in base:
        errors.append("baseline.yaml 不得再复制 process.yaml 工艺参数")

    official_limit = float(base["official"]["position_tolerance_limit_mm"])
    target_limit = float(tolerance["target"]["cylindrical_tolerance_zone_diameter_mm"])
    cmm_limit = float(tolerance["quality_gates"]["position_tolerance_cmm"]["acceptance_threshold_mm"])
    if max(abs(official_limit-target_limit),abs(official_limit-cmm_limit))>1e-12:
        errors.append("官方位置度、产品目标和 CMM 接收阈值不一致")

    radial_limit = float(tolerance["target"]["radial_deviation_limit_mm"])
    if abs(2*radial_limit-target_limit)>1e-12:
        errors.append("径向偏差限值必须等于直径位置度限值的一半")
    contributions = tolerance["product_geometry_chain"]["contributions_mm"]
    stated_sum = float(tolerance["product_geometry_chain"]["worst_case_design_sum_mm"])
    if abs(sum(map(float,contributions.values()))-stated_sum)>1e-12:
        errors.append("产品几何链分项之和与声明最坏情况不一致")
    expected_status = "not_closed" if stated_sum>radial_limit else "closed_by_design_allocation_only"
    if tolerance["budget_status"]!=expected_status:
        errors.append(f"公差预算状态应为 {expected_status}")
    if abs(float(contributions["fixture_repeatability"])-float(fixt["positioning_repeatability_mm"]))>1e-12:
        errors.append("产品链夹具重复性与夹具基线不一致")

    nominal = process["process"]["nominal"]
    expected_heat = nominal["current_a"]*nominal["voltage_v"]*nominal["arc_efficiency"]/nominal["travel_speed_mm_s"]
    if abs(expected_heat-nominal["heat_input_j_per_mm"])>1e-9:
        errors.append("process.yaml 名义线能量与 I/U/效率/焊速不一致")

    g_inputs = load_yaml(PROJECT_CONFIG_DIR/"g-inputs-v5.2.yaml")
    cad = json.loads((PROJECT_ROOT/"cad/parametric/geometry.json").read_text(encoding="utf-8"))
    cad_design = cad["design_assumptions"]
    if abs(float(cad["design_assumptions"]["fillet_leg_length"])-float(geom["fillet_leg_length_mm"]))>1e-12:
        errors.append("CAD 焊脚设计目标与几何基线不一致")
    shell_inner_radius = float(geom["shell_inner_diameter_mm"])/2
    nominal_radial_clearance = shell_inner_radius-float(geom["wing_outer_radius_mm"])
    if not float(geom["radial_clearance_min_mm"]) <= nominal_radial_clearance <= float(geom["radial_clearance_max_mm"]):
        errors.append("翼端半径与壳体内径形成的名义径向间隙超出声明范围")
    if abs(float(cad_design["wing_outer_radius"])-float(geom["wing_outer_radius_mm"]))>1e-12:
        errors.append("CAD 翼端受控半径与几何基线不一致")
    if max(
        abs(float(cad_design["radial_clearance_min"])-float(geom["radial_clearance_min_mm"])),
        abs(float(cad_design["radial_clearance_max"])-float(geom["radial_clearance_max_mm"])),
    )>1e-12:
        errors.append("CAD 径向间隙范围与几何基线不一致")
    shell_limits = list(map(float, geom["shell_inner_diameter_limits_mm"]))
    wing_limits = list(map(float, geom["wing_outer_diameter_limits_mm"]))
    limit_clearances = ((shell_limits[0]-wing_limits[1])/2, (shell_limits[1]-wing_limits[0])/2)
    declared_clearances = (float(geom["radial_clearance_min_mm"]), float(geom["radial_clearance_max_mm"]))
    if any(abs(actual-declared)>1e-12 for actual,declared in zip(limit_clearances,declared_clearances)):
        errors.append("壳体内径/翼端外径极限尺寸不能形成声明的径向间隙范围")
    if list(map(float,cad_design["shell_inner_diameter_limits"]))!=shell_limits or list(map(float,cad_design["wing_outer_diameter_limits"]))!=wing_limits:
        errors.append("CAD 配合极限尺寸与几何基线不一致")
    expected_taper = (float(fixt["large_diameter_mm"])-float(fixt["small_diameter_mm"]))/float(fixt["effective_length_mm"])
    if abs(expected_taper-float(fixt["taper_ratio"]))>1e-12:
        errors.append("夹具直径锥度 (D-d)/L 与端部直径和有效长度不一致")
    if max(
        abs(float(cad_design["mandrel_taper_ratio"])-float(fixt["taper_ratio"])),
        abs(float(cad_design["mandrel_small_diameter"])-float(fixt["small_diameter_mm"])),
        abs(float(cad_design["mandrel_large_diameter"])-float(fixt["large_diameter_mm"])),
        abs(float(cad_design["mandrel_effective_length"])-float(fixt["effective_length_mm"])),
    )>1e-12:
        errors.append("CAD 锥形心轴几何与夹具基线不一致")
    if abs(float(g_inputs["geometry"]["fillet_leg_length_mm"])-float(geom["fillet_leg_length_mm"]))>1e-12:
        errors.append("热模型输入的焊脚设计目标与几何基线不一致")
    mappings = {
        "current_a":"current_a","voltage_v":"voltage_v","travel_speed_mm_s":"travel_speed_mm_s",
        "efficiency":"arc_efficiency","preheat_temperature_c":"preheat_c","interpass_limit_c":"interpass_limit_c",
    }
    for target,source in mappings.items():
        if abs(float(g_inputs["process"][target])-float(nominal[source]))>1e-12:
            errors.append(f"g-inputs 工艺字段 {target} 与 process.yaml 不一致")
    if abs(float(g_inputs["fixture"]["release_temperature_c"])-float(fixt["release_temperature_c"]))>1e-12:
        errors.append("热模型输入的松夹温度与夹具基线不一致")
    thermal = load_yaml(PROJECT_CONFIG_DIR/"thermal-mass-closed-v5.4r1.yaml")
    joint = process["process"]["joint_consistency"]
    if abs(float(thermal["geometry"]["nominal_design_leg_mm"])-float(joint["design_fillet_leg_mm"]))>1e-12:
        errors.append("热模型声明的设计焊脚与 process.yaml 不一致")
    if abs(float(thermal["deposition"]["efficiency"])-float(joint["deposition_efficiency_nominal"]))>1e-12:
        errors.append("热模型沉积效率与 process.yaml 名义值不一致")
    if list(map(float,thermal["deposition"]["efficiency_range"]))!=list(map(float,joint["deposition_efficiency_range"])):
        errors.append("热模型沉积效率范围与 process.yaml 不一致")

    if errors:
        raise ValueError("SSOT 基线校验未通过:\n" + "\n".join(errors))

    return {"status": "PASSED", "versions": {
        "baseline": base.get("version"),"process": process.get("version"),"tolerance": tolerance.get("version")
    },"budget_status": tolerance["budget_status"]}
