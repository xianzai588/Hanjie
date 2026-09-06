"""汇总实跑的0.4R1结果，并量化相对历史0.4R的离散修正影响。"""
import argparse
import json
from pathlib import Path

from run_credibility04r import ROOT, SPEC, OUTPUT, NAMES, cases, load, digest, write_json


def compare(a,b,rules):
    records = {}
    for name in NAMES:
        x,y = a["material_statistics"][name],b["material_statistics"][name]
        metrics = {}
        for key in ("peak_temperature_c","ever_solidus_exceeded_volume_mm3","ever_liquidus_exceeded_volume_mm3",
                    "maximum_cross_section_solidus_area_mm2","maximum_section_solidus_width_mm","maximum_section_solidus_depth_mm",
                    "t8_5_valid_volume_mm3","t8_5_volume_weighted_mean_s","exposure_above_400c_volume_mm3"):
            u,v = x[key],y[key]
            if u is None or v is None:
                metrics[key] = dict(status="not_available",passed=None)
                continue
            if u==v==0:
                metrics[key] = dict(status="both_zero_no_geometry_claim",passed=None,absolute_change=0.)
                continue
            delta = abs(v-u)
            relative = delta/max(abs(v),abs(u),1e-30)
            passed = relative<=rules["relative_limit"]
            if key=="peak_temperature_c":
                passed = passed and delta<=rules["peak_absolute_limit_c"]
            if key.endswith("_mm"):
                passed = passed and delta<=rules["fusion_dimension_absolute_limit_mm"]
            metrics[key] = dict(absolute_change=delta,relative_change=relative,passed=passed)
        records[name] = metrics
    return dict(materials=records,nonzero_metrics_pass=all(v["passed"] is not False for m in records.values() for v in m.values()),
        fusion_geometry_demonstrated=all(b["material_statistics"][n]["ever_solidus_exceeded_volume_mm3"]>0 for n in NAMES[:2]))


def audit(directory):
    plan = load(SPEC)
    results = {}
    for case in cases(plan):
        folder = directory/case["name"]
        manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
        for name,expected in manifest["files"].items():
            if digest(folder/name)!=expected:
                raise ValueError(f"结果证据发生变化：{folder/name}")
        inputs = json.loads((folder/"run-inputs.json").read_text(encoding="utf-8"))
        for name,expected in inputs["hashes"].items():
            if digest(ROOT/name)!=expected:
                raise ValueError(f"源码或输入发生变化：{name}")
        summary = json.loads((folder/"summary.json").read_text(encoding="utf-8"))
        e = summary["energy"]
        history = json.loads((folder/"material-energy-history.json").read_text(encoding="utf-8"))["steps"]
        if any(min(row["source_step_j"]) < -1e-12 or abs(sum(row["net_conductive_step_j"]))>1e-6 for row in history):
            raise ValueError("逐步材料能量账本存在负源或不守恒导热")
        for index,name in enumerate(NAMES):
            if abs(history[-1]["cumulative_source_j"][index]-e["direct_source_by_material_j"][name])>1e-6:
                raise ValueError("材料累计源与最终摘要不一致")
        if abs(e["material_source_partition_residual_j"])>1e-6 or abs(sum(e["net_conductive_by_material_j"].values()))>1e-6:
            raise ValueError("材料间源或导热账本不闭合")
        if not all(summary["checks"][k] for k in ("weld_mass_consistency","parents_always_present","source_deposition_on_active_material","energy_conservation")):
            raise ValueError("基础质量/源/能量检查失败")
        results[case["name"]] = summary
    frozen = json.loads((ROOT/"simulation/thermal-v5/results/mass-closed04/summary.json").read_text(encoding="utf-8"))
    baseline_difference = {n:results["baseline"]["material_statistics"][n]["peak_temperature_c"]-frozen["material_statistics"][n]["peak_temperature_c"] for n in NAMES}
    pairs = [("coarse","medium"),("medium","fine"),("medium","dt-0.05"),("dt-0.05","dt-0.025")]
    comparisons = {a+"_to_"+b:compare(results[a],results[b],plan["convergence"]) for a,b in pairs}
    phy = load(ROOT/"project/thermal-physics-v5.3.yaml")
    evidence = {}
    for name in NAMES:
        s = phy["materials"][name]
        evidence[name] = dict(phase_evidence=s["phase_change"]["evidence_level"],phase_nominal={k:s["phase_change"][k] for k in ("solidus_c","liquidus_c","latent_heat_j_kg")},
            phase_engineering_bounds=s["phase_change"]["uncertainty"],k_cp_evidence=s["high_temperature"]["evidence_level"],
            k_scale_bounds=s["high_temperature"]["k_scale_range"],cp_scale_bounds=s["high_temperature"]["cp_scale_range"],
            density_evidence="design_assumption_reference_density_from_materials_yaml_not_high_temperature_measurement",
            alpha_evidence="design_assumption_not_used_in_reference_domain_thermal_equation",
            uncertainty_scope="工程敏感性范围，不是实测范围或置信区间")
    report = dict(stage="THERMAL-0.4R1",evidence_level="solver_result_unvalidated",audit_source_sha256=digest(Path(__file__)),sources=phy["sources"],material_evidence=evidence,
        source_method_reference=dict(url="https://journals.sagepub.com/doi/10.1243/09544054JEM1886",scope="AA1050 GTAW比较表面/体积热源，只支持比较方法，不支持本项目10%/0.5mm/30°参数"),
        source_review=dict(date="2026-09-06",supplier="复查生产商网页只有成分/用途/机械性能，没有高温k/cp/相变数据。",mdpi="本轮原页面429；保留既有来源及证据分级，没有新增逐值核验声明。"),
        discretization_change=dict(reference="历史 mass-closed04 名义工况（旧无权调和平均）",new="0.4R1 两侧串联热阻",baseline_peak_difference_c=baseline_difference,
            interpretation="仅量化离散修正影响；不是相对实测真值误差，旧结果保留且不得与新结果混用"),
        comparisons=comparisons,cases={k:dict(material_statistics=v["material_statistics"],energy=v["energy"],mesh=v["geometry"],case=v["case"]) for k,v in results.items()},
        conditional_numerical_convergence=all(v["nonzero_metrics_pass"] for v in comparisons.values()),
        experimentally_validated=False,high_temperature_evidence_complete=False,
        process_scan_status="not_run_prerequisites_unmet",thermal_1_allowed=False,formal_struct_0_allowed=False,
        design_leg_review=dict(value_mm=3.5,origin="project/baseline.yaml geometry字段；official字段未列焊脚。docs/plan-1-execution-v5.2.md列为设计假设。尚未找到独立承载/疲劳证明，不自行改变冻结设计。",
            external_area_mm2=6.125,wire_deposit_area_mm2=results["baseline"]["geometry"]["bead_area_mm2"],
            caveat="母材熔化区域与外部新增截面积不同；没有母材迁移/自由表面模型，不能把熔化体积加到外部焊脚。"))
    write_json(directory/"assessment.json",report)
    print(json.dumps({"convergence":report["conditional_numerical_convergence"],"cases":len(results)},ensure_ascii=False))
    return report


if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",type=Path,default=OUTPUT)
    audit(parser.parse_args().output_dir)
