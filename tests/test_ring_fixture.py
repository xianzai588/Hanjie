"""Independent safeguards for real fixture geometry, load and withdrawal."""
import importlib.util
import json
import math
from pathlib import Path

import cadquery as cq

ROOT=Path(__file__).resolve().parents[1]


def evaluate():
    spec=importlib.util.spec_from_file_location("ring_fixture",ROOT/"studies/COMPETITION-DESIGN/ring-fixture-feasibility.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.evaluate_real_fixture()


def test_actual_arbor_includes_water_gas_holes_and_physical_bore_endpoints():
    r=evaluate()
    assert r["inputs"]["bore_endpoint_z_mm"]==[100,115]
    assert r["inputs"]["load_at_z_mm"]>=115
    net=r["service_bore_net_section"]
    assert net["arbor_column_removed_area_mm2"]>16*math.pi*4**2/4
    # Gross-section calculations must not silently become qualification values.
    assert r["lower_arbor_axis_displacement_um"]>4.316
    assert not r["qualification"]["thermal_displacement_validated"]
    assert not r["qualification"]["product_axis_after_welding_validated_by_this_study"]


def test_clamp_is_preloaded_against_opening_and_slip_without_omitting_interfaces():
    r=evaluate();b=r["anchors"]
    assert b["minimum_contact_pressure_MPa"]>0
    assert b["minimum_sliding_capacity_N"]>b["required_transverse_force_N"]
    assert b["maximum_nominal_bolt_tensile_stress_MPa"]<640/1.5
    assert r["anchor_elastic_axis_displacement_um"]>0
    assert r["steel_bed_axis_displacement_um"]>0
    assert r["seated_contact_increment_allocation_um"]>0
    assert 0<r["remaining_foundation_and_seating_budget_um"]<1
    assert r["cold_structural_plus_seating_allocation_um"]+r["remaining_foundation_and_seating_budget_um"]==6.5


def test_small_cone_requires_positive_release_and_adequate_stroke():
    r=evaluate()["release"]
    assert .20>r["friction_self_lock_threshold"]
    assert r["positive_pullout_required"]
    assert r["stroke_mm"]*math.tan(math.radians(3))>r["required_radial_sleeve_release_mm"]


def test_saved_cad_sweep_and_mass_have_actual_identity_and_surviving_solids():
    manifest=json.loads((ROOT/"cad/generated/ring-fixture/geometry-quality-and-bom.json").read_text())
    assert manifest["design_identity"].endswith("-R2")
    assert all(x["all_solids_valid"] for x in manifest["step_rechecks"])
    assert all(x<1e-5 for x in manifest["sweep_intersection_volumes_mm3"].values())
    assert manifest["clearances_mm"]["raised_shell_top_to_bridge_bottom_mm"]==60
    assert manifest["clearances_mm"]["transfer_lid_bottom_to_cone_top_mm"]>2
    # A new fixture must not borrow the old portal's or a small beam's mass.
    assert 100<manifest["mass_summary_kg"]["fabricated_fixture_components"]<300
    shapes=cq.importers.importStep(str(ROOT/"cad/generated/ring-fixture/ring-fixture-assembly.step")).vals()
    assert all(s.isValid() for s in shapes)
    assert sum(len(s.Solids()) for s in shapes)==manifest["working_solid_count"]
