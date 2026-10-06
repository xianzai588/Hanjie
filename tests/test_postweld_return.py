"""The full wet-line return counterexample and installation failure limits."""
import importlib.util
from pathlib import Path
import yaml
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('postweld_return',ROOT/'studies/COMPETITION-DESIGN/postweld_isolation.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inputs():
    return yaml.safe_load((ROOT/'project/competition-design.yaml').read_text(encoding='utf8'))['postweld_drain']


def test_full_wet_return_with_normal_inventory_fits_minimum_cup():
    result=module.fault_hold_up(inputs())
    assert result['contributions']['full_line_return_ml']>13
    assert result['contributions']['operating_inventory_ml']==2
    assert result['capacity_margin_ml']>2
    assert result['design_pass'] and not result['check_valve_credit']


def test_old_cup_is_rejected_with_the_same_permitted_line():
    config=inputs()
    config['fault_containment']['cup_liquid_depth_mm']=10
    result=module.fault_hold_up(config)
    assert result['capacity_margin_ml']<0
    assert not result['design_pass']


def test_submerged_bottle_inlet_and_unbounded_wet_line_cannot_pass():
    config=inputs()
    config['fault_containment']['discharge_air_gap_min_mm']=0
    assert not module.fault_hold_up(config)['design_pass']
    config=inputs()
    config['fault_containment']['supply_cartridge_max_ml']=250
    assert not module.fault_hold_up(config)['design_pass']
    config=inputs()
    config['fault_containment']['return_wet_length_max_m']=0.4
    with pytest.raises(ValueError,match='entire permitted'):
        module.fault_hold_up(config)


def test_old_pressure_margin_disappears_before_current_flow_limit():
    config=inputs()
    assert module.drain_capacity(config)['capacity_ml_min']>150
    config['net_differential_pressure_min_Pa']=1800
    assert module.drain_capacity(config)['capacity_ml_min']<120
