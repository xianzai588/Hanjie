import pytest

from hanjie.domain.joint_load import build_load_basis


def test_weld_group_lengths_match_cad_manifests():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    result=build_load_basis(root)
    for layout in result["layouts"].values():
        assert layout["effective_weld_length_mm"]==pytest.approx(layout["cad_effective_weld_length_mm"],rel=1e-12)
        assert layout["line_group_isotropy_ratio"]==pytest.approx(1.0,abs=1e-12)


def test_capacity_scales_with_leg_and_no_false_design_freeze():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    result=build_load_basis(root)
    rows=result["layouts"]["6P-FAIR_B"]["rows"]
    current=rows[0]
    target=rows[-1]
    assert current["force_capacity_n_per_allowable_mpa"]/target["force_capacity_n_per_allowable_mpa"]==pytest.approx(1.73664301094/3.5)
    assert target["reference_envelope_corner_required_allowable_mpa"]<current["reference_envelope_corner_required_allowable_mpa"]
    assert result["decision"]["three_point_five_mm_necessary"] is None
    assert result["existing_radial_static_screening"]["Continuous"]["compliance_mm_per_n"] < result["existing_radial_static_screening"]["6P-FAIR_B"]["compliance_mm_per_n"]
    assert "未显式建模焊缝" in result["existing_radial_static_screening"]["6P-FAIR_B"]["limitation"]
