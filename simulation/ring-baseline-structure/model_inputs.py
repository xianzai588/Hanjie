"""Pure structural inputs and publication identity; no FE/native imports."""
from pathlib import Path
import hashlib
import json
import yaml

ROOT = Path(__file__).resolve().parents[2]
CAD = ROOT / "cad/generated/ring-baseline"
P2_LEVELS = {"coarse": (6., .9), "medium": (4.5, .65)}
REFERENCE_LOADS = (5000, 5000, 250000)
MATERIALS = {
    1: {"name": "QT450-10", "E_MPa": 169000., "nu": .27,
        "basis": "existing structural-v4 design elastic input; batch modulus not measured"},
    2: {"name": "Q235B", "E_MPa": 206000., "nu": .30,
        "basis": "engineering room-temperature elastic input"},
    3: {"name": "CI-A1 retained first layer", "E_MPa": 200000., "nu": .30,
        "basis": "design elastic assumption; deposited chemistry and strength require qualification"},
    4: {"name": "Ni99 retained second layer", "E_MPa": 200000., "nu": .30,
        "basis": "design elastic assumption; deposited chemistry and strength require qualification"},
    5: {"name": "NiFe55 final effective fillet", "E_MPa": 200000., "nu": .30,
        "basis": "design elastic assumption; effective interface and joint strength require qualification"},
}


def step_geometry_digest(path):
    """Hash actual STEP DATA entities, excluding export filename/date headers."""
    data=Path(path).read_text(encoding="utf8")
    if "DATA;" not in data:
        raise ValueError("STEP entity section missing")
    entities=data.split("DATA;",1)[1].split("ENDSEC;",1)[0]
    return hashlib.sha256("".join(entities.split()).encode()).hexdigest()


def p2_cache_inputs(level):
    far,local=P2_LEVELS[level]
    baseline=yaml.safe_load((ROOT/"project/submission-baseline.yaml").read_text())
    seat=baseline["geometry"]["seat"];shell=baseline["geometry"]["shell"];layout=baseline["weld_layout"]
    geometry=[seat["nominal_bore_diameter_mm"],seat["outside_radius_mm"],seat["thickness_mm"],seat["bottom_z_mm"],
              shell["outside_diameter_mm"],shell["wall_thickness_mm"],shell["height_mm"],layout["segment_count"],
              layout["effective_segment_length_mm"],baseline["final_GTAW"]["minimum_total_leg_mm"]]
    if geometry!=[40.,74.98,15.,100.,160.,5.,200.,8,18.,3.5]:
        raise RuntimeError("Current baseline geometry/effective connection differs from this fixed ring P2 model; revise geometry inputs before reuse")
    return {"schema":"RING-P2-STRAIGHT-QUARTER-2","geometry_DATA_sha256":step_geometry_digest(CAD/"ring-precoat-eight-windows-17solids.step"),
            "bulk_size_mm":far,"local_size_mm":local,"shell_surface_size_function":f"Min({far},2.0+Max(0,Abs(z-107.5)-17.5)*.3)",
            "leg_mm":3.5,"effective_arc_mm":18.,"quadrant":"x>=0,y>=0","displacement_order":2,"geometry_order":1,
            "material_inputs":MATERIALS,"loads_N_N_Nmm":list(REFERENCE_LOADS),
            "boundary":"z=0 clamped; y=0 symmetric; x=0 symmetric for axial and antisymmetric for radial/My"}


def current_publication_identity():
    """Current expected identity, read-only and JSON-normalized for equality.

    This is an expectation.  The assessment must retain the verified raw
    identity rather than obtaining a replacement label from this function.
    """
    baseline=yaml.safe_load((ROOT/"project/submission-baseline.yaml").read_text())
    return json.loads(json.dumps({"process_version":baseline["version"],
                                 "input_identity":p2_cache_inputs("medium")}))
