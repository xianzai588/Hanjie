"""材料质量守恒与 Goldak 矩阵准入预检；不调用热场求解器。"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np

from run_physics03 import ROOT, digest, load, write_json
from run_thermal0 import _goldak_domain_capture_fraction

SPEC = ROOT / "project/thermal1-admission.yaml"
OUTPUT = ROOT / "simulation/thermal-v5/results/thermal1-preflight.json"


def density_state(material, phase, temperature_c, alpha_scale=1.):
    """固态无应力各向同性膨胀情景；明确绑定 rho、J 与参考质量。"""
    temperature = float(temperature_c)
    if not np.isfinite(temperature) or not np.isfinite(alpha_scale) or alpha_scale<=0:
        raise ValueError("温度与膨胀系数倍率必须有效")
    nominal = material["nominal_properties_20c"]
    rho0 = float(nominal["density_kg_m3"])
    table = material.get("temperature_dependent")
    maximum = float(phase["uncertainty"]["solidus_c"][0])
    if not np.isfinite(rho0) or rho0<=0 or not np.isfinite(maximum) or maximum<=20:
        raise ValueError("参考密度必须有限且为正，固相线下限必须高于参考温度")
    if table and "alpha_per_k" in table:
        knots = np.asarray(table["temperatures_c"],float)
        alpha = np.asarray(table["alpha_per_k"],float)
        if (knots.ndim!=1 or alpha.shape!=knots.shape or len(knots)<2
                or not np.isfinite(knots).all() or not np.isfinite(alpha).all()
                or np.any(np.diff(knots)<=0) or knots[0]>20 or knots[-1]<20):
            raise ValueError("alpha表必须有限、等长、温度严格递增并覆盖20°C")
        maximum = min(maximum,float(knots[-1]))
        basis = "existing_alpha_table_interpreted_as_tangent_assumption"
    else:
        knots = np.array([20.,maximum])
        alpha = np.full(2,float(nominal["alpha_per_k"]))
        if not np.isfinite(alpha).all():
            raise ValueError("常温alpha必须有限")
        basis = "constant_room_temperature_alpha_assumption"
    if temperature<20 or temperature>maximum:
        return dict(temperature_c=temperature,density_kg_m3=None,volume_ratio=None,
                    status="missing_evidence",maximum_solid_scenario_temperature_c=maximum,
                    reason="超出已登记alpha范围或保守固相线界限，禁止液相外推")
    sample = np.unique(np.r_[20.,knots[(knots>20)&(knots<temperature)],temperature])
    values = np.interp(sample,knots,alpha)*alpha_scale
    integral = float(np.sum(np.diff(sample)*(values[1:]+values[:-1])*.5))
    with np.errstate(over="ignore",under="ignore",invalid="ignore"):
        jacobian = float(np.exp(3*integral))
    if not np.isfinite(jacobian) or jacobian<=0 or not np.isfinite(rho0/jacobian) or rho0/jacobian<=0:
        raise ValueError("膨胀积分导致无效体积或密度，请检查alpha单位和范围")
    return dict(temperature_c=temperature,density_kg_m3=rho0/jacobian,volume_ratio=jacobian,
                reference_density_kg_m3=rho0,reference_mass_relative_error=(rho0/jacobian*jacobian-rho0)/rho0,
                fixed_volume_naive_mass_error_pct=(1/jacobian-1)*100,
                status="design_assumption_solid_scenario",source=basis,
                maximum_solid_scenario_temperature_c=maximum)


def matrix_case(config, process_window, values):
    keys = ("efficiency","a_front_mm","a_rear_mm","b_radial_mm","c_axial_mm")
    parameters = dict(zip(keys,map(float,values),strict=True))
    if not all(np.isfinite(list(parameters.values()))) or not 0<parameters["efficiency"]<=1 or min(parameters[k] for k in keys[1:])<=0:
        raise ValueError("Goldak参数必须有限，轴长为正，效率在(0,1]内")
    p,g,h,path = (config[k] for k in ("process","thermal_grid","heat_source","heat_source_path"))
    for key in ("current_a","voltage_v","travel_speed_mm_s"):
        if not np.isfinite(p[key]) or p[key]<=0:
            raise ValueError(f"工艺参数{key}必须有限且为正")
    if not np.isfinite(p["preheat_temperature_c"]):
        raise ValueError("预热温度必须有限")
    power = parameters["efficiency"]*p["current_a"]*p["voltage_v"]
    line = power/p["travel_speed_mm_s"]
    bounds = ((g["arc_min_offset_mm"],g["arc_max_offset_mm"]),(g["radial_min_offset_mm"],g["radial_max_offset_mm"]),(g["axial_min_offset_mm"],g["axial_max_offset_mm"]))
    if any(not np.isfinite([lo,hi]).all() or hi<=lo for lo,hi in bounds):
        raise ValueError("计算域边界必须有限且严格递增")
    for key in ("arc_points","radial_points","axial_points"):
        count = g[key]
        if isinstance(count,bool) or not isinstance(count,(int,float)) or not np.isfinite(count) or count<2 or int(count)!=count:
            raise ValueError("网格单元数必须为不小于2的整数")
    fractions = [h["front_fraction"],h["rear_fraction"]]
    if not np.isfinite(fractions).all() or min(fractions)<=0 or not np.isclose(sum(fractions),2.,rtol=0,atol=1e-9):
        raise ValueError("Goldak前后权重必须有限、为正且和为2")
    capture_limit = g["minimum_source_domain_capture_fraction"]
    margin_limit = g["minimum_source_s_boundary_margin_multiple"]
    if not np.isfinite([capture_limit,margin_limit]).all() or not .999<=capture_limit<=1 or margin_limit<3:
        raise ValueError("源捕获率和边界余量不得低于冻结数值门槛")
    af,ar,b,c = [parameters[k] for k in keys[1:]]
    start,end = path["source_start_s_mm"],path["source_end_s_mm"]
    if not np.isfinite([start,end]).all() or start>=end:
        raise ValueError("热源路径必须有限且起点小于终点")
    capture = min(_goldak_domain_capture_fraction(pos,bounds,af,ar,b,c,h["front_fraction"],h["rear_fraction"],False) for pos in (start,end))
    ds,dn,dz = [(hi-lo)/g[key] for (lo,hi),key in zip(bounds,("arc_points","radial_points","axial_points"),strict=True)]
    ratios = dict(s_front=ds/af,s_rear=ds/ar,n=dn/b,z=dz/c)
    energy_window = process_window["heat_input_j_per_mm"]
    checks = dict(line_energy=energy_window["min"]<=line<=energy_window["max"],
                  process_bounds=all(process_window[k]["min"]<=p[k]<=process_window[k]["max"] for k in ("current_a","voltage_v","travel_speed_mm_s")),
                  preheat_bounds=process_window["preheat_c"]["min"]<=p["preheat_temperature_c"]<=process_window["preheat_c"]["max"],
                  source_domain_capture=capture>=g["minimum_source_domain_capture_fraction"],
                  source_path_inside_domain=bounds[0][0]<start<end<bounds[0][1],
                  source_boundary_margin=min(start-bounds[0][0],bounds[0][1]-end)>=g["minimum_source_s_boundary_margin_multiple"]*max(af,ar),
                  source_resolution=max(ratios.values())<=1/3)
    return dict(parameters=parameters,net_power_w=power,net_line_energy_j_mm=line,
                minimum_source_capture=capture,grid_source_ratios=ratios,checks=checks,
                numerical_preflight_pass=all(checks.values()),thermal_simulation_executed=False)


def physics_blockers(gate):
    gate = gate if isinstance(gate,dict) else {}
    checks = gate.get("checks",{})
    checks = checks if isinstance(checks,dict) else {}
    required = ("energy_conservation","source_domain_capture","timestep_sensitivity",
                "progressive_mesh_convergence","material_specific_phase_change_present",
                "activation_sensitivity","finite_process_sampling","weld_mass_consistency",
                "source_deposition_on_active_material","evidence_supported_high_temperature_properties",
                "plausible_two_sided_fusion")
    # 缺项或字符串PASS不能视为布尔通过，避免旧版Gate结构被静默放行。
    blocked = [key for key in required if checks.get(key) is not True]
    if gate.get("gate_status")!="PASS":
        blocked.insert(0,"gate_status")
    return blocked


def preflight(spec_path=SPEC,output=OUTPUT):
    spec = load(spec_path)
    inputs = load(ROOT/spec["inputs"])
    materials = load(ROOT/spec["materials"])["materials"]
    physics = load(ROOT/spec["physics_specification"])
    gate_path = ROOT/spec["physics_gate"]
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    # 消费0.3结果时检查来源，不把过期Gate当成当前物理状态。
    manifest_path = gate_path.parent/"manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["files"].get(gate_path.name) != digest(gate_path):
        raise ValueError("G-PHYSICS与其产物清单不一致")
    snapshot_path = gate_path.parent/"run-inputs.json"
    if manifest["files"].get(snapshot_path.name) != digest(snapshot_path):
        raise ValueError("0.3运行输入快照与产物清单不一致")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    for name,expected in snapshot["hashes"].items():
        if digest(ROOT/name) != expected:
            raise ValueError(f"0.3来源已变化：{name}")
    if spec["density"]["reference_temperature_c"] != 20.:
        raise ValueError("当前材料表的密度参考温度固定为20°C")
    process_path = ROOT/physics["scan"]["source"]
    process_window = load(process_path)["process"]["acceptable_window"]
    blocked = physics_blockers(gate)
    density = {}
    for name,material in materials.items():
        phase = physics["materials"][name]["phase_change"]
        samples = []
        for temperature in spec["density"]["sample_temperatures_c"]:
            central = density_state(material,phase,temperature)
            extremes = [density_state(material,phase,temperature,scale)["density_kg_m3"] for scale in spec["density"]["alpha_scale_range"]]
            central["assumed_density_range_kg_m3"] = sorted(extremes) if all(v is not None for v in extremes) else None
            samples.append(central)
        density[name] = dict(evidence_level="design_assumption",samples=samples,
            independent_rho_temperature_measurement_available=False,liquid_density_available=False,
            solver_uses_reference_density=True,temperature_dependent_density_coupled=False)
    matrix = spec["goldak_matrix"]
    cases = [matrix_case(inputs,process_window,values) for values in itertools.product(*[matrix[k] for k in ("efficiency","a_front_mm","a_rear_mm","b_radial_mm","c_axial_mm")])]
    for i,case in enumerate(cases):
        case["case_id"] = f"GOLDAK-{i:03d}"
        case["physics_blockers"] = blocked
        # 此入口只有解析预检，没有执行热场的权限或优化目标。
        case["execution_status"] = "blocked_by_physics" if blocked else "not_executed_preflight_only"
    dependencies = [spec_path,ROOT/spec["inputs"],ROOT/spec["materials"],ROOT/spec["physics_specification"],gate_path,manifest_path,snapshot_path,process_path,Path(__file__),Path(__file__).with_name("run_thermal0.py"),Path(__file__).with_name("run_physics03.py")]
    result = dict(stage="THERMAL1-ADMISSION-PREFLIGHT",evidence_level="design_assumption",
        current_baseline="THERMAL-0.3-PHYS",specification=spec,
        input_sha256={str(p.relative_to(ROOT)).replace("\\","/"):digest(p) for p in dependencies},
        density=density,matrix_case_count=len(cases),numerical_preflight_pass_count=sum(c["numerical_preflight_pass"] for c in cases),
        physics_blockers=blocked,thermal_simulation_count=0,calibration_executed=False,thermal_1_allowed=False,formal_struct_0_allowed=False,
        cases=cases,limitations=["密度只是未测固态膨胀情景，尚未补齐三种材料20–1500°C实测rho(T)。",
          "当前热求解器固定参考质量；空间密度变化须同时处理体积变化或质量输运，不能直接替换数组。",
          "数值预检通过不代表物理准入，不新增失配焊缝上的热场计算。"])
    write_json(output,result)
    return {k:result[k] for k in ("matrix_case_count","numerical_preflight_pass_count","physics_blockers","thermal_simulation_count","thermal_1_allowed")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(preflight(output=args.output),ensure_ascii=False))
