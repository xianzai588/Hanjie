"""用解析几何、失败对照和力平衡校核工装筛查。"""

import math
from pathlib import Path

import pytest

import hanjie.domain.tooling_access as tooling

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def study():
    return tooling.run_tooling_study(ROOT)


def test_cylinder_boolean_volume_and_clearance_have_independent_answers():
    a = tooling.cylinder(3., 0., 4.)
    b = tooling.cylinder(2., 1., 2.)
    c = tooling.cylinder(1., 8., 2.)
    assert tooling.common_volume(a, b) == pytest.approx(8 * math.pi)
    assert tooling.common_volume(a, c) == pytest.approx(0., abs=1e-10)
    assert tooling.clearance(a, c) == pytest.approx(4.)


def test_top_withdrawal_fails_and_bottom_swept_body_is_clear(study):
    result, _ = study
    for row in result["shield"]["cases"]:
        assert row["swept_body_geometry_clear"] == (row["route"] == "bottom")
    ring = next(row for row in result["shield"]["cases"] if row["layout"] == "Continuous" and row["route"] == "top")
    assert ring["seat_intersection_volume_mm3"] == pytest.approx(math.pi * (74**2 - 20**2) * 12, rel=1e-10)
    assert result["shield"]["nominal_shell_clearance_mm"] == pytest.approx(1.)
    assert result["shield"]["vertical_drop_at_interface_captured"] is False
    assert result["shield"]["cleanliness_validated"] is False


def test_bottom_closed_rejects_process_even_when_swept_geometry_is_clear(monkeypatch):
    read = tooling.read_yaml

    def changed(path):
        data = read(path)
        if path == ROOT / tooling.SPEC:
            data["assembly"]["bottom_access_open"] = False
        return data

    monkeypatch.setattr(tooling, "read_yaml", changed)
    result, _ = tooling.run_tooling_study(ROOT)
    for row in result["shield"]["cases"]:
        if row["route"] == "bottom":
            assert row["swept_body_geometry_clear"] is True
            assert row["process_route_admissible"] is False


def test_bent_torch_certificate_and_straight_failure_controls(study):
    result, _ = study
    for row in result["torch"]["cases"]:
        expected = row["body_style"] == "bent_vertical" and row["tilt_deg"] in (30., 45.)
        assert row["sampled_poses_clear"] == expected
        certificate = row["vertical_path_certificate"]
        if certificate:
            assert certificate["continuous_vertical_lift_clear"] == expected
            if expected:
                assert row["nominal_shell_clearance_mm"] >= certificate["shell_gap_lower_bound_mm"] - 1e-8
                assert row["nominal_mandrel_clearance_mm"] >= certificate["mandrel_gap_lower_bound_mm"] - 1e-8
    assert all(result["shape_validity"].values())
    assert all(flag is False for flag in result["release"].values())


def test_naive_cone_insertion_overlap_matches_integrated_annular_volume(study):
    result, _ = study
    # 圆柱孔半径20；超径锥段 r=20+0.01*z，z为0至5，直接积分环面积。
    expected = math.pi * (20 * .01 * 5**2 + .01**2 * 5**3 / 3)
    assert result["mandrel"]["naive_full_length_insertion_overlap_mm3"] == pytest.approx(expected, rel=1e-9)
    assert result["mandrel"]["rigid_seating_shift_mm"] == pytest.approx(5.)
    assert result["mandrel"]["seated_cone_overlap_mm3"] == pytest.approx(0., abs=1e-8)
    assert result["mandrel"]["repeatability_validated"] is False


def test_cone_force_balance_and_self_lock_boundary():
    zero = tooling.cone_force_balance(39.9, 40.1, 10., 500., 0.)
    assert zero["radial_compression_scalar_sum_n"] == pytest.approx(50000.)
    for mu in (0., .01, .05, .1, .2):
        row = tooling.cone_force_balance(39.9, 40.1, 10., 500., mu)
        assert row["axial_force_balance_n"] == pytest.approx(500.)
        assert row["self_lock_possible"] == (mu >= .01)
        assert row["net_radial_vector_for_axisymmetry_n"] == 0.
        assert row["contact_pressure_mpa"] is None
    with pytest.raises(ValueError):
        tooling.cone_force_balance(40.1, 39.9, 10., 500., .1)


@pytest.mark.parametrize("changed_geometry", [False, True])
def test_report_rejects_changed_tooling_sources(tmp_path, changed_geometry):
    import hashlib
    import json
    from hanjie.reporting.current_status import collect_tooling_status

    output = tmp_path/"studies/TOOLING-ACCESS/results"
    output.mkdir(parents=True)
    (tmp_path/"source.yaml").write_text("radius: 74\n",encoding="utf-8")
    (tmp_path/"source.brep").write_bytes(b"new geometry")
    expected = {"structured_inputs":{"source.yaml":{"radius":74 if changed_geometry else 73}},
                "geometry_sha256":{"source.brep":hashlib.sha256(b"old geometry").hexdigest()}}
    (output/"run-inputs.json").write_text(json.dumps(expected),encoding="utf-8")
    with pytest.raises(ValueError,match="工装检查.*已变化"):
        collect_tooling_status(tmp_path)


def test_exported_step_roundtrip_matches_six_named_envelopes(study):
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    _, bodies = study
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(ROOT/"cad/generated/tooling-access/nominal-envelope.step")) == IFSelect_RetDone
    assert reader.TransferRoots() == 6
    shape = reader.OneShape()
    assert BRepCheck_Analyzer(shape).IsValid()
    names = ("shell","Continuous","shield","upper_mandrel_envelope","weld_keepout","torch_envelope")
    assert tooling.volume(shape) == pytest.approx(sum(tooling.volume(bodies[name]) for name in names),rel=1e-9)
