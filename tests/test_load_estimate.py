import pytest
import importlib.util
from pathlib import Path


def test_first_order_load_maps_components_once_into_weld_screen():
    path = Path(__file__).parents[1] / "studies/LOAD-ESTIMATE/estimate.py"
    spec = importlib.util.spec_from_file_location("load_estimate", path)
    estimate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(estimate)

    payload = estimate.calculate()
    results = payload["results"]
    screen = payload["joint_weld_screen"]

    # 径向/轴向分量分别传入焊缝组模型，合力只能在下游合成一次。
    assert results["radial_force_n"] == pytest.approx(results["inertial_force_n"])
    assert results["axial_force_n"] == pytest.approx(results["gas_force_n"])
    assert screen["scales_vs_reference"]["resultant_force_scale"] == pytest.approx(
        (results["inertial_force_n"] ** 2 + results["gas_force_n"] ** 2) ** 0.5
        / (5000.0**2 + 5000.0**2) ** 0.5
    )
    assert screen["rows"]["6P-FAIR_B"]["required_allowable_mpa"] == pytest.approx(
        20.5096052542, rel=1e-10
    )
