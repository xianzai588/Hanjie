"""One existing-stock design point; no CAD, FE, material or process search.

The supplier's local TDS supplies the operating range. Saved CAD roof areas
supply the volume demand. Nominal mass/length is preserved; the existing
relative feed allowance is rounded outward, not tightened to create a pass.
"""
from pathlib import Path
import itertools
import json
import math

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "studies/COMPETITION-DESIGN/results/focused-second-layer-alignment-20261008.json"


def account(spec, current, voltage, speed, feed, feed_tolerance, demand):
    length = spec["track_length_per_wing_mm"]
    diameter = spec["diameter_mm"]
    diameter_tolerance = spec["diameter_tolerance_mm"]
    speed_tolerance = spec["travel_relative_tolerance"]
    corners = []
    for d, f, v, eta in itertools.product(
        [diameter-diameter_tolerance, diameter+diameter_tolerance],
        [feed-feed_tolerance, feed+feed_tolerance],
        [speed*(1-speed_tolerance), speed*(1+speed_tolerance)],
        spec["deposition_efficiency_range"],
    ):
        consumed = f*length/v
        volume = math.pi*d*d/4*consumed*eta
        corners.append({"diameter_mm": d, "feed_mm_s": f, "travel_mm_s": v,
                        "deposition_utilization": eta,
                        "consumed_length_per_wing_mm": consumed,
                        "deposited_volume_per_wing_mm3": volume})
    power = current*voltage*spec["efficiency_for_design_accounting"]
    time = 8*length/speed
    rod = spec["rod_feed_interface"]
    maximum_consumed = max(c["consumed_length_per_wing_mm"] for c in corners)
    available = rod["cut_blank_length_per_wing_mm"]-rod["cut_blank_length_tolerance_mm"]
    tail = rod["inactive_clamping_tail_min_mm"]+rod["front_trim_allowance_mm"]
    minimum_volume = min(c["deposited_volume_per_wing_mm3"] for c in corners)
    return {
        "setpoint": {"current_A": current, "reference_voltage_V": voltage,
                     "travel_mm_s": speed, "travel_relative_tolerance": speed_tolerance,
                     "feed_mm_s": feed, "feed_tolerance_mm_s": feed_tolerance},
        "net_power_W": power, "nominal_net_energy_J_mm": power/speed,
        "pure_arc_time_s": time, "nominal_net_heat_kJ": power*time/1000,
        "nominal_consumed_length_mm": 8*length*feed/speed,
        "feed_per_travel_ratio": feed/speed,
        "minimum_volume_per_wing_mm3": minimum_volume,
        "maximum_volume_per_wing_mm3": max(c["deposited_volume_per_wing_mm3"] for c in corners),
        "minimum_volume_margin_mm3": minimum_volume-demand,
        "minimum_volume_margin_percent": 100*(minimum_volume/demand-1),
        "maximum_consumed_length_per_wing_mm": maximum_consumed,
        "shortest_blank_tail_margin_mm": available-tail-maximum_consumed,
        "existing_feed_stroke_requirement_mm": rod["minimum_available_feed_stroke_mm"],
        "feed_stroke_margin_mm": rod["minimum_available_feed_stroke_mm"]-maximum_consumed,
        "fixed_tolerance_corners": corners,
    }


def calculate():
    design = yaml.safe_load((ROOT/"project/precoat-process-design.yaml").read_text(encoding="utf-8"))
    spec = design["second"]
    saved = json.loads((ROOT/"studies/COMPETITION-DESIGN/results/second-layer-supply-decision-20261008.json").read_text())
    area = max(r["planar_pocket_roof_area_one_wing_mm2"] for r in saved["geometry"]["existing_roof_reads"])
    demand = area*(design["machining"]["second_deposited_top_min_mm"]-min(design["machining"]["first_retained_mm"]))
    old = account(spec, spec["current_A"], spec["voltage_V_reference"],
                  spec["travel_mm_s"], spec["feed_mm_s"], spec["feed_tolerance_mm_s"], demand)
    # An interior point allows +/-5 A and a 13--15 V observed range to remain
    # inside the documented 80--110 A / 13--16 V general recommendation.
    # Those signal ranges do NOT imply constant heat input at fixed travel.
    current, voltage = 85., 14.
    ideal_speed = current*voltage*spec["efficiency_for_design_accounting"]/old["nominal_net_energy_J_mm"]
    speed = round(ideal_speed, 2)
    feed = round(speed*old["feed_per_travel_ratio"], 2)
    relative_feed_allowance = spec["feed_tolerance_mm_s"]/spec["feed_mm_s"]
    feed_tolerance = math.ceil(feed*relative_feed_allowance*100-1e-10)/100
    proposal = account(spec, current, voltage, speed, feed, feed_tolerance, demand)
    baseline_min = min(c["deposited_volume_per_wing_mm3"] for c in saved["supply"]["corners"])
    if not math.isclose(old["minimum_volume_per_wing_mm3"], baseline_min, rel_tol=1e-12):
        raise ValueError("Existing saved geometry/feed accounting no longer matches current inputs")
    if not math.isclose(old["feed_per_travel_ratio"], proposal["feed_per_travel_ratio"], rel_tol=1e-12):
        raise ValueError("Nominal volume per length was not preserved")
    if proposal["minimum_volume_margin_mm3"] <= 0 or proposal["shortest_blank_tail_margin_mm"] <= 0 or proposal["feed_stroke_margin_mm"] <= 0:
        raise ValueError("The single proposed point does not satisfy existing supply/rod interfaces")
    if proposal["setpoint"]["feed_tolerance_mm_s"]/feed < relative_feed_allowance:
        raise ValueError("Relative feeder tolerance was tightened")
    return {
        "baseline_commit": "b69e26a1e69479b02db252fa2f0256fc0c0d1c08",
        "kind": "one proposed design revision, not an adopted production WPS",
        "sources": ["docs/sources/Weldwire-Duramax-DMNA099-ERNi-CI-TDS.pdf p1",
                    "project/precoat-process-design.yaml",
                    "studies/COMPETITION-DESIGN/results/second-layer-supply-decision-20261008.json"],
        "supplier_recommendation": {"wire_inches": .045, "current_A": [80,110], "voltage_V": [13,16]},
        "stock_and_geometry": {"diameter_mm": spec["diameter_mm"], "diameter_tolerance_mm": spec["diameter_tolerance_mm"],
                               "maximum_saved_roof_area_mm2": area, "minimum_cover_volume_demand_mm3": demand,
                               "track_length_per_wing_mm": spec["track_length_per_wing_mm"]},
        "current_baseline": old, "selected_proposal": proposal,
        "nominal_heat_change_percent": 100*(proposal["nominal_net_heat_kJ"]/old["nominal_net_heat_kJ"]-1),
        "pure_arc_time_change_s": proposal["pure_arc_time_s"]-old["pure_arc_time_s"],
        "physical_questions_to_resolve": ["local two-track coverage and continuous fusion", "first-layer remelt and surviving composition",
                                           "actual arc-voltage/current energy integral", "changed instantaneous power and travel thermal history"],
        "accounting_scope": "Supplier range, conserved nominal feed/travel ratio and fixed existing tolerances. Equal line energy does not equate source shape, penetration or residual stress; pure arc time is not station cycle time.",
        "source_parameters_modified": False,
        "manufacturing_performance_solver_runs": 0,
        "second_layer_fusion_verified": False,
        "postweld_position_verified": False,
    }


if __name__ == "__main__":
    result = calculate()
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    p = result["selected_proposal"]
    print(json.dumps({"output": str(OUT.relative_to(ROOT)), "setpoint": p["setpoint"],
                      "energy_J_mm": p["nominal_net_energy_J_mm"],
                      "supply_margin_mm3": p["minimum_volume_margin_mm3"],
                      "rod_margin_mm": p["shortest_blank_tail_margin_mm"]}, ensure_ascii=False))
