"""复核已运行的 0.3 证据与物理阻断，不触发新计算或校准。"""
import argparse
import json
from pathlib import Path

from run_physics03 import ROOT, OUT, digest, write_json


def audit(directory):
    gate = json.loads((directory/"G-PHYSICS.json").read_text(encoding="utf-8"))
    inputs = json.loads((directory/"run-inputs.json").read_text(encoding="utf-8"))
    for name, expected in inputs["hashes"].items():
        if digest(ROOT/name) != expected:
            raise ValueError(f"运行依赖已改变，不能审计为当前结果：{name}")
    results = gate["results"]
    for item in results:
        saved = json.loads((directory/item["case_id"]/item["activation"]/"summary.json").read_text(encoding="utf-8"))
        if saved != item:
            raise ValueError("聚合结果与逐工况记录不一致")
    numerical = json.loads((ROOT/"simulation/thermal-v5/results/g-thermal-audit/G-THERMAL-audit.json").read_text(encoding="utf-8"))
    baseline_manifest = json.loads((ROOT/"simulation/thermal-v5/results/thermal0-result-manifest.json").read_text(encoding="utf-8"))
    for name,expected in baseline_manifest["files"].items():
        if digest(ROOT/"simulation/thermal-v5/results"/name) != expected:
            raise ValueError(f"THERMAL0.2 封存文件已改变：{name}")
    by_key = {(r["case_id"],r["activation"]):r for r in results}
    dt_changes = {}
    for mode in ("pre_existing","progressive"):
        reference = by_key[("process-00-preheat-150",mode)]
        finer = by_key.get(("dt-half",mode))
        if finer:
            dt_changes[mode] = abs(finer["peak_temperature_c"]-reference["peak_temperature_c"])/reference["peak_temperature_c"]*100
    latent_off = by_key.get(("latent-off","pre_existing"))
    phase_bounds = {}
    for name,spec in inputs["specification"]["materials"].items():
        highest = max(r["material_statistics"][name]["peak_temperature_c"] for r in results)
        lowest_ts = spec["phase_change"]["uncertainty"]["solidus_c"][0]
        phase_bounds[name] = dict(maximum_sampled_temperature_c=highest,lowest_assumed_solidus_c=lowest_ts,
            phase_interval_unreached_for_all_samples=highest<lowest_ts)
    checks = dict(
        thermal02_numerical_verification=all(numerical["gate_checks"][k] for k in ("time_step_pass","mesh_pass","source_domain_capture_pass","source_resolution_pass")),
        thermal02_original_artifacts_preserved=True,
        material_specific_phase_change_present=True,
        energy_conservation=max(r["energy"]["residual_pct"] for r in results)<.02,
        source_domain_capture=all(r["energy"]["domain_capture_fraction"]>=.999 for r in results),
        source_deposition_on_active_material=all(r["energy"]["minimum_active_source_fraction"]>=.999 for r in results),
        timestep_sensitivity=len(dt_changes)==2 and max(dt_changes.values())<1.,
        progressive_mesh_convergence=False,
        activation_sensitivity=len(gate["activation_comparison"])==gate["sampled_process_count"],
        finite_process_sampling=gate["scan_status"]=="finite_predeclared_sampling_completed",
        evidence_supported_high_temperature_properties=False,
        weld_mass_consistency=gate["deposition_mass_audit"]["status"]=="PASS",
        plausible_two_sided_fusion=False,
        experimental_calibration=False,
        independent_validation=False)
    gate["checks"] = checks
    gate["time_step_peak_change_pct"] = dt_changes
    gate["phase_uncertainty_inactivity_check"] = phase_bounds
    gate["phase_uncertainty_note"] = "仅在这些已算热物性/几何情景下，若所有峰温低于假设固相线下限，则改变潜热和相变温区不影响温度；不代表联合不确定性全域上界。"
    gate["latent_on_minus_off_peak_c"] = by_key[("process-00-preheat-150","pre_existing")]["peak_temperature_c"]-latent_off["peak_temperature_c"] if latent_off else None
    gate["gate_status"] = "REVIEW"
    gate["thermal_1_allowed"] = False
    gate["formal_struct_0_allowed"] = False
    write_json(directory/"G-PHYSICS.json",gate)
    process_results = [r for r in results if r["case_id"].startswith("process-")]
    write_json(directory/"PROCESS-FEASIBILITY.json",dict(
        status="no_two_sided_fusion_in_sampled_surrogate_cases",
        evidence_level="solver_result_unvalidated",
        sampled_process_count=gate["sampled_process_count"],simulation_count=len(process_results),
        sampled_line_energy_range_j_mm=[min(r["process"]["net_line_energy_j_per_mm"] for r in process_results),max(r["process"]["net_line_energy_j_per_mm"] for r in process_results)],
        sampled_peak_temperature_range_c=[min(r["peak_temperature_c"] for r in process_results),max(r["peak_temperature_c"] for r in process_results)],
        property_sensitivity_peak_range_c=[min(r["peak_temperature_c"] for r in results if r["case_id"].startswith("nife-")),max(r["peak_temperature_c"] for r in results if r["case_id"].startswith("nife-"))] if latent_off else None,
        entire_process_domain_infeasible=False,real_TIG_route_rejected=False,
        next_action="先核实实际几何、送丝和宏观熔合；不对这个失配代理继续校准。",
        sampling_limitation="只扫描预登记的有限工况，未穷尽连续域、联合材料不确定性或热源尺寸；不能推导整个工艺域不可熔。"))
    paths = sorted(directory.rglob("*.json"))+sorted(directory.rglob("*.npz"))
    write_json(directory/"manifest.json",dict(evidence_level="solver_result_unvalidated",
        audit_script_sha256=digest(Path(__file__)),files={str(p.relative_to(directory)).replace("\\","/"):digest(p) for p in paths if p.name!="manifest.json"}))
    return {"checks":checks,"dt_peak_change_pct":dt_changes,"phase_bounds":phase_bounds,"case_count":len(results)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results",type=Path,default=OUT)
    args = parser.parse_args()
    print(json.dumps(audit(args.results),ensure_ascii=False))
