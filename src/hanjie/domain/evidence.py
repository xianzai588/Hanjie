"""证据登记防误晋升校验；登记完整不等同于科学验证。"""
from pathlib import Path
import yaml

LEVELS = {"official", "literature_supported", "design_assumption", "synthetic_demo",
          "surrogate_result", "solver_result_unvalidated", "solver_verified",
          "experiment_measured", "experiment_repeated", "calibrated", "rejected"}
VERIFIED = {"solver_verified", "experiment_measured", "experiment_repeated", "calibrated"}
PROMOTION_STATUSES = {"validated", "verified", "gate_b1_passed", "passed"}


def validate_evidence_graph(graph: dict, root: Path) -> list[str]:
    errors = []
    entries = {}
    for items in graph["taxonomy"].values():
        for key, item in items.items():
            if key in entries:
                errors.append(f"{key}: duplicate id")
            entries[key] = item
            level = item.get("evidence_level")
            if level not in LEVELS:
                errors.append(f"{key}: missing/unknown evidence level")
            status = item.get("status")
            if status in PROMOTION_STATUSES and level not in VERIFIED:
                errors.append(f"{key}: low-level evidence cannot pass verification")
            if level == "rejected" and status in PROMOTION_STATUSES:
                errors.append(f"{key}: rejected evidence cannot be promoted")
            if level in VERIFIED:
                paths = item.get("verification_artifacts", [])
                if not paths or any(not (root / p).is_file() for p in paths):
                    errors.append(f"{key}: verification artifacts required")
            if status != "planned" and item.get("path") and not (root / item["path"]).exists():
                errors.append(f"{key}: result path missing")
    for key, claim in graph["claims_graph"].items():
        support = claim.get("supporting_evidence", [])
        if not support or any(e not in entries for e in support):
            errors.append(f"{key}: missing evidence reference")
            continue
        if claim.get("confidence") == "high" or claim.get("status") == "verified":
            if any(entries[e].get("evidence_level") not in VERIFIED or entries[e].get("status") in {"planned", "unvalidated"} for e in support):
                errors.append(f"{key}: unresolved support cannot establish a verified claim")
        if claim.get("status") in PROMOTION_STATUSES and any(entries[e].get("evidence_level") not in VERIFIED for e in support):
            errors.append(f"{key}: low-level support cannot promote claim")
    return errors
