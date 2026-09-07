"""修复早期 Plan 6 运行中冷却步复用末次面元快照，并封存源码哈希。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from credibility_source import boundary_face_source_power, projected_boundary_faces
from mass_closed_geometry import build_geometry
from run_physics03 import load


SPEC = ROOT / "project/thermal-boundary-neumann-v5.7.yaml"
RESULTS = ROOT / "simulation/thermal-v5/results/boundary-neumann-plan6"


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finalize(case):
    plan = load(SPEC); baseline = load(ROOT / plan["baseline"])
    selected = next(row for row in plan["cases"] if row["name"] == case)
    baseline["mesh"].update(selected["mesh_overrides"])
    config = load(ROOT / baseline["inputs"])
    geometry = build_geometry(config, load(ROOT / baseline["process_input"]), baseline)
    source_model = plan["sources"][selected["source"]]
    bare, bead = [projected_boundary_faces(geometry, state, config["heat_source"]["b_radial_mm"], **source_model) for state in (False, True)]
    speed = config["process"]["travel_speed_mm_s"]
    start, end = (config["heat_source_path"][key] for key in ("source_start_s_mm", "source_end_s_mm"))
    duration = (end - start) / speed; dt = float(selected["dt"])
    centre = start + speed * (duration - dt / 2)
    _, last = boundary_face_source_power(geometry, bare, bead, start, end, centre, config["heat_source"], config["process"]["net_power_w"], return_face_data=True)

    directory = RESULTS / case
    boundary_path = directory / "boundary-neumann-ledger.json"
    boundary = json.loads(boundary_path.read_text(encoding="utf-8"))
    source = json.loads((directory / "source-density-ledger.json").read_text(encoding="utf-8"))
    active_steps = sum(float(row["source_energy_j"]) > 0 for row in source["steps"])
    stale_steps = len(boundary["steps"]) - active_steps
    if stale_steps > 0:
        last_power = {(str(last["state"][i]), int(last["path_cell"][i]), int(last["cross_face"][i])): float(last["power_w"][i]) for i in range(len(last["power_w"]))}
        for row in boundary["faces"]:
            key = (row["state"], int(row["path_cell"]), int(row["cross_face"]))
            row["cumulative_energy_j"] -= last_power.get(key, 0.0) * stale_steps * dt
            if row["cumulative_energy_j"] < -1e-8:
                raise RuntimeError("面元累计能量修复后为负")
        boundary["faces"] = [row for row in boundary["faces"] if row["cumulative_energy_j"] > 1e-12]
        boundary["steps"] = boundary["steps"][:active_steps]
        energy = np.asarray([row["cumulative_energy_j"] for row in boundary["faces"]])
        centres = np.asarray([row["centre_s_n_z_mm"] for row in boundary["faces"]])
        total = float(energy.sum()); centroid = np.average(centres, axis=0, weights=energy)
        delta = centres - centroid
        boundary["total_face_energy_j"] = total
        boundary["energy_weighted_centroid_s_n_z_mm"] = centroid.tolist()
        boundary["energy_weighted_covariance_mm2"] = (np.einsum("ni,nj,n->ij", delta, delta, energy) / total).tolist()
        boundary["evidence_correction"] = {"reason": "早期观测器在热源关闭后复用了末次面元快照；仅面账本受影响，求解器RHS始终为零", "removed_cooling_snapshots": stale_steps, "numerical_field_changed": False}
        boundary_path.write_text(json.dumps(boundary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    inputs_path = directory / "run-inputs.json"
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    source_path = ROOT / "src/hanjie/simulation/neumann_source.py"
    inputs["hashes"][source_path.relative_to(ROOT).as_posix()] = _digest(source_path)
    inputs.setdefault("executed_hashes", dict(inputs["hashes"]))
    inputs["reproduction_hashes"] = {
        name: _digest(ROOT / name) for name in inputs["hashes"] if (ROOT / name).is_file()
    }
    inputs["post_run_observer_note"] = (
        "温度场由启动时源码生成；随后只修复冷却步面快照清空和补充源码哈希。"
        "这两项不进入求解器RHS；executed_hashes保留启动快照，reproduction_hashes记录当前可复跑版本。"
    )
    inputs_path.write_text(json.dumps(inputs, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = {path.name: _digest(path) for path in directory.iterdir() if path.is_file() and path.name != "manifest.json"}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return {"case": case, "active_steps": active_steps, "removed_stale_steps": max(stale_steps, 0), "total_face_energy_j": boundary["total_face_energy_j"]}


def main():
    print(json.dumps([finalize(case) for case in ("NEST-F", "NEST-VF")], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
