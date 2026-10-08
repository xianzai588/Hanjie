"""One bounded repair of the CI-A1 source representation, not joint certification.

The same geometry, electrical settings, feed, initial temperature and phase
enthalpy are retained. A first-visible-surface Gaussian replaces a volume
source whose depth had been set from the as-deposited CAD envelope. Molecular
conductivity replaces the uncalibrated SS316L liquid enhancement. No thermal
state, plastic state, or liquid stiffness is manufactured by this calculation.
"""
import argparse
import json
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--source-repository", type=Path, default=Path(__file__).resolve().parents[2])
parser.add_argument("--width-mm", type=float, default=3.2)
parser.add_argument("--case-name", default="surface-k1-first1s")
options = parser.parse_args()
SOURCE_REPOSITORY = options.source_repository.resolve()
DESTINATION = Path(__file__).resolve().parent / "delivery_repair_surface_heat_20261008"
sys.path.insert(0, str(SOURCE_REPOSITORY / "simulation/competition-r4"))
from run_mma_startup_check import arguments
from run_ni99_precoat_first import run
from threadpoolctl import threadpool_limits
import visible_surface_flux

# The legacy solver reuses ``a.width`` in the deposited-envelope front law.
# Separate flux width from that retained3.2 mm rise length. No capacity, birth
# mass, front speed or geometric reference is changed with the heat-flux width.
original_surface_load = visible_surface_flux.load
def independent_surface_load(x, face, xyz, owner, projection, wet, source,
                             width, power, grid_step):
    return original_surface_load(x, face, xyz, owner, projection, wet, source,
                                 options.width_mm, power, grid_step)
visible_surface_flux.load = independent_surface_load


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    configuration = arguments(None, DESTINATION / options.case_name, .125,
                              False, 1.0, 1.0, "bottom_up")
    configuration.source_model = "visible_surface"
    configuration.width = 3.2
    configuration.record_nodal_history = True
    started = time.monotonic()
    try:
        with threadpool_limits(limits=1):
            run(configuration)
        completed = True
        error = None
    except Exception as exc:
        completed = False
        error = repr(exc)
    input_path = configuration.output / "input.json"
    if input_path.exists():
        metadata = json.loads(input_path.read_text(encoding="utf8"))
        # The legacy MMA metadata assumes a volumetric source. Correct its
        # description to the boundary representation actually executed above.
        metadata.update(
            source_depth_mm_effective=None,
            source_width_mm=options.width_mm,
            growth_rise_length_mm=3.2,
            inactive_source_parameters=["source_drop", "depth"],
            source_parameter_scope=f"1/e Gaussian half-width{options.width_mm:.12g} mm is an uncalibrated heat-flux scale; it is not a qualified electrode diameter, standoff or penetration",
            surface_normalization="analytic pi*width^2; each vertical ray loads its first visible upward surface; missed power is retained as a loss, never redistributed",
            power_policy="2024 W net incident-plus-incoming-metal design budget: incoming enthalpy is subtracted once, remaining boundary power is geometrically intercepted; un-intercepted boundary power is a separately recorded loss",
            source_validation="surface heat deposition follows an arc-conduction idealisation; no actual bead/source spatial qualification is assigned",
            liquid_transport_scope="factor1: no imported liquid conductivity enhancement; material conductivity itself remains the original engineering hypothesis",
            comparison_scope="only0..1s startup on the actual complete QT seat; not the completed first bead or cooled mechanical state",
            source_front_decoupled=True,
            actual_first_layer_joint_passed=False,
            cold_geometry_qualified=False,
            full_manufacturing_chain_passed=False,
        )
        input_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf8")
    execution = dict(runtime_s=time.monotonic()-started,
                     thermal_startup_completed=completed, error=error,
                     cold_geometry_qualified=False,
                     full_manufacturing_chain_passed=False)
    (configuration.output / "execution.json").write_text(json.dumps(execution, indent=2), encoding="utf8")
    print(json.dumps(execution, indent=2), flush=True)
    if not completed:
        raise RuntimeError(error)


if __name__ == "__main__":
    main()
