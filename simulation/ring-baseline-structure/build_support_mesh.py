"""Generate a current full-ring P1 mesh for independent eigenstrain studies.

Keeps the legacy coarse diagnosis untouched.  This does not solve a load case
or assert that the thermal/precoat residual input is experimentally verified.
"""
import json
import run_ring_structure as base


def main():
    out = base.HERE / "results" / "p1-current-coarse-safe"
    mesh, summary = base.build_mesh("coarse", 3.5, outdir=out)
    identity = {
        "process_version": base.analysis_inputs("coarse", 3.5)["process_version"],
        "mesh_inputs": base.mesh_inputs("coarse", 3.5),
        "material_inputs": base.MATERIALS,
        "actual_faceted_gap_audit": summary["actual_faceted_gap_audit"],
        "scope": "Current independently built P1 support mesh only. No service-load solution or residual-stress qualification is implied.",
    }
    (out / "support-inputs.json").write_text(json.dumps(identity, indent=2))
    print(json.dumps({"output": str(out), "nodes":len(mesh["points"]), **identity},indent=2))


if __name__ == "__main__":
    main()
