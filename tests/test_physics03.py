"""物理扩展只验证关键守恒链路、相变及证据门，不借旧收敛结果放行。"""
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simulation/thermal-v5"))
from physics import enthalpy, material_tables, solve, temperature_from_enthalpy
from run_physics03 import admissible_cases, deposition_audit


def data():
    materials = yaml.safe_load((ROOT/"project/materials.yaml").read_text(encoding="utf-8"))["materials"]
    spec = yaml.safe_load((ROOT/"project/thermal-physics-v5.3.yaml").read_text(encoding="utf-8"))
    return materials,spec


def test_enthalpy_roundtrip_and_latent_energy():
    materials,spec = data()
    table,lengths,_ = material_tables(materials,spec["materials"])
    sensible,ns,_ = material_tables(materials,spec["materials"],latent=False)
    for m,name in enumerate(("q235b","qt450_10","ernife_ci")):
        p = spec["materials"][name]["phase_change"]
        for t in (20.,150.,799.,p["solidus_c"],(p["solidus_c"]+p["liquidus_c"])/2,p["liquidus_c"],2200.):
            h = enthalpy(t,m,table,lengths)
            assert temperature_from_enthalpy(h,m,table,lengths) == pytest.approx(t,abs=1e-9)
        lo,hi = p["solidus_c"]-10,p["liquidus_c"]+10
        full = enthalpy(hi,m,table,lengths)-enthalpy(lo,m,table,lengths)
        base = enthalpy(hi,m,sensible,ns)-enthalpy(lo,m,sensible,ns)
        assert full-base == pytest.approx(p["latent_heat_j_kg"],abs=1e-7)
        energy = enthalpy(p["solidus_c"],m,table,lengths)+p["latent_heat_j_kg"]/2
        assert temperature_from_enthalpy(energy,m,table,lengths) < temperature_from_enthalpy(energy,m,sensible,ns)
    with pytest.raises(ValueError):
        temperature_from_enthalpy(-10,0,table,lengths)


@pytest.mark.parametrize("mode",[0,1])
def test_conservation_with_void_and_nonzero_birth_enthalpy(mode):
    materials,spec = data()
    tables,lengths,rho = material_tables(materials,spec["materials"])
    s = np.linspace(-4,4,9)
    n = np.linspace(-2,2,5)
    z = np.linspace(-1,1,3)
    ids = np.broadcast_to(np.array([2,2,3,1,1])[None,:,None],(9,5,3)).copy()
    p = np.array([8.,2.,150.,20.,12.,.75])
    source = np.array([-2.,2.,1.,2.,1.,1.,.6,1.4])
    result = solve(s,n,z,ids,tables,lengths,rho,p,source,mode,0.,150.,.2,.005)
    final,peak,active,_,_,_,ledger = result
    source_j,absorbed,birth,conv,rad,delta,mass,*_ = ledger
    assert source_j == pytest.approx(16.,abs=1e-9)
    assert absorbed+birth-conv-rad-delta == pytest.approx(0.,abs=1e-8)
    assert np.isfinite(final).all()
    if mode:
        assert 0 < absorbed < source_j
        assert mass > 0 and birth > 0
        assert np.all(final[~active] == 150.)
    else:
        assert absorbed == pytest.approx(source_j)
        assert birth == 0 and mass == 0


def test_scan_is_energy_constrained_and_mass_mismatch_detected():
    _,spec = data()
    proc = yaml.safe_load((ROOT/"project/process.yaml").read_text(encoding="utf-8"))
    config = yaml.safe_load((ROOT/"project/g-inputs-v5.2.yaml").read_text(encoding="utf-8"))
    cases = admissible_cases(spec,proc)
    assert cases and len(cases)<27
    for c in cases:
        assert 240 <= c["net_line_energy_j_per_mm"] <= 420
        assert c["net_line_energy_j_per_mm"] == pytest.approx(c["efficiency"]*c["current_a"]*c["voltage_v"]/c["travel_speed_mm_s"])
    mass = deposition_audit(config,proc)
    assert mass["wire_volume_per_length_mm2"] == pytest.approx(np.pi*.6**2*2/1.5)
    assert mass["band_to_wire_volume_ratio"]>80
    assert mass["status"]=="FAIL"


def test_parent_t85_zero_and_rejects_corrupted_history():
    path = ROOT/"simulation/metallurgy-v5/run_metallurgy0.py"
    spec = importlib.util.spec_from_file_location("metallurgy03_test",path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with np.load(ROOT/"simulation/thermal-v5/results/thermal0-field.npz") as f:
        field = {k:f[k] for k in f.files}
    for code in (1,2):
        assert module._material_stats(field,code)["t8_5_valid_node_count"]==0
    field["t8_5_s"][field["material_id"]==1] = 2.
    with pytest.raises(ValueError,match="t8/5"):
        module._material_stats(field,1)


def test_solver_crosses_phase_interval_without_losing_latent_energy():
    materials,spec = data()
    tables,lengths,rho = material_tables(materials,spec["materials"])
    axes = np.array([-1.,0.,1.])
    ids = np.full((3,3,3),3,dtype=np.int8)
    params = np.array([10.,.2,1360.,20.,0.,0.])
    source = np.array([-1.,1.,100.,100.,100.,100.,1.,1.])
    result = solve(axes,axes,axes,ids,tables,lengths,rho,params,source,0,0.,20.,0.,.01)
    final,_,_,_,_,_,ledger = result
    assert final.min()>spec["materials"]["ernife_ci"]["phase_change"]["liquidus_c"]
    # 独立对分段 cp 作梯形积分，再加潜热，复算完整相变后的能量增量。
    cpdata = spec["materials"]["ernife_ci"]["high_temperature"]
    absorbed = 0.
    for t in final.ravel():
        knots = np.r_[1360.,[v for v in cpdata["temperatures_c"] if 1360.<v<t],t]
        cp = np.interp(knots,cpdata["temperatures_c"],cpdata["specific_heat_j_kgk"])
        absorbed += (np.sum(np.diff(knots)*(cp[:-1]+cp[1:])/2)+260000.)*rho[2]
    assert absorbed == pytest.approx(100.,abs=1e-7)
    assert ledger[5] == pytest.approx(100.,abs=1e-7)
