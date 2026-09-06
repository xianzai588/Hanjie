import json
from pathlib import Path

import pytest


ROOT=Path(__file__).resolve().parents[1]


def test_fixed_geometry_study_has_three_executed_levels_and_keeps_gate_closed():
    result=json.loads((ROOT/"simulation/thermal-v5/results/spatial-fix-study/assessment.json").read_text(encoding="utf-8"))
    assert result["fixed_six_strip_geometry_verified"] is True
    assert len(result["mesh_inputs"])==3
    assert len(result["directional_controls"])==2
    assert result["a_control_completed"] is True
    assert result["spatial_gate_pass"] is False
    assert result["thermal_1_allowed"] is False
    assert result["fine_reference_reproduction"]["maximum_peak_field_difference_c"] == 0.0


def test_fixed_geometry_separates_a_large_part_of_old_weld_difference():
    result=json.loads((ROOT/"simulation/thermal-v5/results/spatial-fix-study/assessment.json").read_text(encoding="utf-8"))
    pair=result["pairs"]["A-field-medium-fixed6_to_A-field-fine-fixed6"]
    weld=pair["common_control_volume_peak_field"]["ernife_ci"]
    assert weld["volume_weighted_p95_abs_peak_difference_c"]==pytest.approx(16.682,abs=.001)
    assert weld["local_p95_pass"] is False
    assert pair["common_control_volume_peak_field"]["qt450_10"]["solidus_threshold_flip_volume_mm3"]>0
    geometry=result["supporting_geometry_effect"]["legacy_4_strips_to_fixed_6_at_medium_spacing"]["common_control_volume_peak_field"]["ernife_ci"]
    assert geometry["volume_weighted_p95_abs_peak_difference_c"]>50.


def test_fixed_point_histories_and_energy_partitions_were_recorded():
    result=json.loads((ROOT/"simulation/thermal-v5/results/spatial-fix-study/assessment.json").read_text(encoding="utf-8"))
    for pair in result["pairs"].values():
        assert len(pair["fixed_coordinate_containing_cell_histories"])==5
        assert set(pair["direct_source_by_material_difference_j"])=={"q235b","qt450_10","ernife_ci"}
