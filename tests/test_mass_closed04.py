"""0.4物理纠偏验证：填丝积分、材料身份、射线功率和隐式焓守恒。"""
from pathlib import Path
import sys

import numpy as np
import pytest
from scipy.sparse import csr_matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"simulation/thermal-v5"))
from mass_closed_geometry import build_geometry, filled_fraction, surface_weights, source_power, face_geometry, face_half_distances
from run_mass_closed04 import SPEC, load, material_tables, material_state, enthalpy_step, series_face_conductance, _conductance_matrix


@pytest.fixture(scope="module")
def setup():
    spec = load(SPEC)
    config = load(ROOT/spec["inputs"])
    process = load(ROOT/spec["process_input"])
    return spec,config,process,build_geometry(config,process,spec)


def test_deposit_matches_integrated_wire_feed_at_fractional_times(setup):
    spec,config,process,g = setup
    bead = g["ids"]==3
    parent_volume = g["volumes"][~bead].sum()
    nominal = process["process"]["nominal"]
    flow = np.pi*(nominal["filler_diameter_mm"]/2)**2*nominal["filler_feed_rate_mm_s"]*spec["deposition"]["efficiency"]
    for time in (0.,.001,.1,1.,1.33333,9.78,39.999,40.,60.):
        f = filled_fraction(g,-30.,30.,time*config["process"]["travel_speed_mm_s"])
        assert (g["volumes"][bead]*f[bead]).sum()==pytest.approx(flow*min(time,40.),rel=1e-10,abs=1e-12)
        assert (g["volumes"][~bead]*f[~bead]).sum()==parent_volume
        assert np.all(f[~bead]==1.)
    assert g["bead_area_mm2"]==pytest.approx(flow/config["process"]["travel_speed_mm_s"])
    assert g["bead_area_mm2"]<2.


def test_parent_material_identity_and_real_gap_are_preserved(setup):
    _,_,_,g = setup
    nc = (g["n_edges"][:-1]+g["n_edges"][1:])/2
    zc = (g["z_edges"][:-1]+g["z_edges"][1:])/2
    n,z = np.meshgrid(nc,zc,indexing="ij")
    ids = g["ids2"]
    assert np.all(ids[(n<-g["gap_mm"])&(z<0)]==2)
    assert np.all(ids[n>0]==1)
    assert np.all(ids[(n>-g["gap_mm"])&(n<0)&(z<0)]==0)
    assert np.all(z[ids==3]>0)


def test_bead_area_matches_wire_efficiency_without_inflating_feed(setup):
    import copy
    spec,config,process,_ = setup
    modified = copy.deepcopy(spec)
    modified["deposition"]["efficiency"] = .85
    modified["mesh"]["bead_strips"] = 8
    other = build_geometry(config,process,modified)
    expected = np.pi*.6**2*2./1.5*.85
    assert other["bead_area_mm2"]==pytest.approx(expected,rel=1e-12)


def test_fixed_bead_geometry_is_independent_of_field_spacing(setup):
    import copy
    spec,config,process,_ = setup
    profiles = []
    for spacing in (0.8,0.6,0.4):
        modified = copy.deepcopy(spec)
        modified["mesh"].update(near_spacing_mm=spacing,far_spacing_mm=2*spacing,arc_spacing_mm=2*spacing,
                                bead_strips=3,bead_geometry_strips=6)
        geometry = build_geometry(config,process,modified)
        profiles.append((geometry["bead_z"],geometry["bead_widths"],geometry["bead_area_mm2"]))
        assert geometry["bead_geometry_strips"] == 6
    for bead_z,widths,area in profiles[1:]:
        np.testing.assert_allclose(bead_z,profiles[0][0])
        np.testing.assert_allclose(widths,profiles[0][1])
        assert area == pytest.approx(profiles[0][2],rel=1e-12)


def test_local_cross_section_refinement_preserves_background_and_geometry(setup):
    import copy
    spec,config,process,_ = setup
    medium_spec = copy.deepcopy(spec)
    medium_spec["mesh"].update(
        arc_spacing_mm=1.0,
        near_spacing_mm=0.6,
        far_spacing_mm=1.5,
        bead_strips=6,
        bead_geometry_strips=6,
        cross_local_spacing_mm=0.4,
        radial_local_zone_mm=[-3.0,1.5],
        axial_local_zone_mm=[-2.0,2.0],
    )
    fine_spec = copy.deepcopy(medium_spec)
    fine_spec["mesh"]["cross_local_spacing_mm"] = 0.2
    medium = build_geometry(config,process,medium_spec)
    very_fine = build_geometry(config,process,fine_spec)

    # 局部区外背景节点完全冻结，避免把整域细化重新混入对照。
    for key,zone in (("n_edges",(-3.0,1.5)),("z_edges",(-2.0,2.0))):
        medium_outer = medium[key][(medium[key]<zone[0])|(medium[key]>zone[1])]
        fine_outer = very_fine[key][(very_fine[key]<zone[0])|(very_fine[key]>zone[1])]
        np.testing.assert_allclose(medium_outer,fine_outer)
    medium_dn = np.diff(medium["n_edges"])[np.searchsorted(medium["n_edges"],-1.0)]
    fine_dn = np.diff(very_fine["n_edges"])[np.searchsorted(very_fine["n_edges"],-1.0)]
    assert fine_dn < medium_dn
    np.testing.assert_allclose(medium["bead_z"],very_fine["bead_z"])
    np.testing.assert_allclose(medium["bead_widths"],very_fine["bead_widths"])
    assert medium["bead_area_mm2"] == pytest.approx(very_fine["bead_area_mm2"])


def test_nested_local_refinement_is_exact_integer_subdivision(setup):
    import copy
    spec,config,process,_=setup
    geometries=[]
    for factor in (1,2,4):
        nested=copy.deepcopy(spec)
        nested["mesh"].update(
            arc_spacing_mm=1.0,near_spacing_mm=0.6,far_spacing_mm=1.5,
            bead_strips=6,bead_geometry_strips=6,
            cross_local_base_spacing_mm=0.6,cross_local_subdivision_factor=factor,
            radial_local_zone_mm=[-3.0,1.5],axial_local_zone_mm=[-2.0,2.0],
        )
        geometries.append(build_geometry(config,process,nested))
    assert len(geometries[0]["n_edges"])<len(geometries[1]["n_edges"])<len(geometries[2]["n_edges"])
    assert len(geometries[0]["z_edges"])<len(geometries[1]["z_edges"])<len(geometries[2]["z_edges"])
    for coarse,fine in zip(geometries[:-1],geometries[1:]):
        for key in ("s_edges","n_edges","z_edges"):
            assert all(np.any(np.isclose(edge,fine[key],atol=1e-12)) for edge in coarse[key])
        for key in ("n_edges","z_edges"):
            counts=np.searchsorted(fine[key],coarse[key][1:])-np.searchsorted(fine[key],coarse[key][:-1])
            assert set(counts).issubset({1,2})
    np.testing.assert_allclose(geometries[0]["bead_z"],geometries[-1]["bead_z"])
    np.testing.assert_allclose(geometries[0]["bead_widths"],geometries[-1]["bead_widths"])


def test_surface_flux_hits_first_material_and_never_unborn_bead(setup):
    _,config,_,g = setup
    bare = surface_weights(g,False,2.5)
    bead = surface_weights(g,True,2.5)
    assert bare[g["ids2"]==3].sum()==0.
    assert bead[g["ids2"]==3].sum()>0.
    for center in (-30.,-29.925,-17.13,0.,29.9,30.):
        q = source_power(g,bare,bead,-30.,30.,center,config["heat_source"],495.)
        f = filled_fraction(g,-30.,30.,center+30.)
        assert np.all(q[f==0]==0.)
        assert q.sum()==pytest.approx(495.,rel=1e-10)


def test_missing_receiver_is_reported_as_lost_not_renormalized(setup):
    _,config,_,g = setup
    bare = surface_weights(g,False,2.5)
    bead = surface_weights(g,True,2.5)
    # 独立删除一侧接收面，剩余面必须保持原功率，不能自动补回495W。
    full = source_power(g,bare,bead,-30.,30.,-30.,config["heat_source"],495.)
    bare[g["ids2"]==1] = 0.
    missing = source_power(g,bare,bead,-30.,30.,-30.,config["heat_source"],495.)
    assert missing.sum()<.75*full.sum()
    assert np.allclose(missing[g["ids"]==2],full[g["ids"]==2])


def test_visible_surface_integral_matches_independent_ray_box_oracle(setup):
    _,_,_,g = setup
    n,z,ids = g["n_edges"],g["z_edges"],g["ids2"]
    root2 = np.sqrt(2.)
    du = .001
    rays = np.arange(-8.+du/2,8.,du)
    gaussian = np.sqrt(3/np.pi)/2.5*np.exp(-3*(rays/2.5)**2)*du
    for with_bead in (False,True):
        j,k = np.where((ids>0)&((ids!=3)|with_bead))
        oracle = np.zeros_like(ids,dtype=float)
        for start in range(0,len(rays),200):
            u = rays[start:start+200,None]
            lower = np.maximum(u-root2*n[j+1],root2*z[k]-u)
            upper = np.minimum(u-root2*n[j],root2*z[k+1]-u)
            entry = np.where(upper>=lower,upper,-np.inf)
            selected = np.argmax(entry,axis=1)
            assert np.isfinite(entry[np.arange(len(u)),selected]).all()
            np.add.at(oracle,(j[selected],k[selected]),gaussian[start:start+200])
        exact = surface_weights(g,with_bead,2.5)
        assert np.max(np.abs(oracle-exact))<5e-4


def test_faces_to_unborn_bead_are_exposed_not_conducting(setup):
    _,_,_,g = setup
    f = filled_fraction(g,-30.,30.,0.)
    area,_,exposed = face_geometry(g,f)
    i,j = g["edge_i"],g["edge_j"]
    assert np.all(area[(g["ids"][i]==3)|(g["ids"][j]==3)]==0.)
    assert np.all(exposed[g["ids"]==3]==0.)
    f = filled_fraction(g,-30.,30.,.1)
    area,_,exposed = face_geometry(g,f)
    assert np.all(exposed>=0.)
    assert np.any(area[((g["ids"][i]==3)&(g["ids"][j]!=3))|((g["ids"][j]==3)&(g["ids"][i]!=3))]>0.)


@pytest.mark.parametrize(
    "width_i,width_j,k_i,k_j,expected",
    [
        (1.0,3.0,0.010,0.030,0.010),  # 异宽异材独立反例，单位为 mm/W 制下的 W/K
        (2.0,2.0,0.010,0.030,0.0075), # 等宽异材退化为普通调和平均
        (1.0,3.0,0.020,0.020,0.010),  # 异宽同材退化为 kA/中心距
        (3.0,1.0,0.030,0.010,0.010),  # 左右交换不改变串联热阻
    ],
)
def test_series_face_conductance_matches_two_cell_resistance(width_i,width_j,k_i,k_j,expected):
    area = np.array([1.0])
    value = series_face_conductance(area,np.array([width_i/2]),np.array([width_j/2]),np.array([k_i]),np.array([k_j]))
    assert value[0]==pytest.approx(expected,rel=1e-12)


def test_independent_counterexample_quantifies_old_formula_bias():
    width_i,width_j,k_i,k_j = 1.0,3.0,0.010,0.030
    old = 2*k_i*k_j/(k_i+k_j)/((width_i+width_j)/2)
    exact = series_face_conductance(np.array([1.0]),np.array([width_i/2]),np.array([width_j/2]),
                                    np.array([k_i]),np.array([k_j]))[0]
    assert old==pytest.approx(0.0075)
    assert exact==pytest.approx(0.0100)
    assert old/exact==pytest.approx(0.75)


def test_partial_birth_uses_active_half_length_and_preserves_matrix_conservation():
    geometry = {
        "edge_i": np.array([0]), "edge_j": np.array([1]), "edge_axis": np.array([0]),
        "edge_area": np.array([1.0]), "edge_distance": np.array([2.0]),
        "dims": np.array([[1.0,1.0,1.0],[3.0,1.0,1.0]]),
        "index": np.array([[0,0,0],[1,0,0]]),
        "s_edges": np.array([0.0,1.0,4.0]), "n_edges": np.array([0.0,1.0]), "z_edges": np.array([0.0,1.0]),
        "ids": np.array([3,3]),
    }
    fraction = np.array([1.0,0.5])
    di,dj = face_half_distances(geometry,fraction)
    assert di[0]==pytest.approx(0.5)
    assert dj[0]==pytest.approx(0.75)
    matrix,_ = _conductance_matrix(geometry,fraction,np.array([0.010,0.030]),1.0)
    expected = 1.0/(0.5/0.010+0.75/0.030)
    assert matrix[0,0]==pytest.approx(expected)
    assert matrix[0,1]==pytest.approx(-expected)
    np.testing.assert_allclose(matrix.toarray(),matrix.toarray().T)
    np.testing.assert_allclose(np.asarray(matrix.sum(axis=1)).ravel(),0.0,atol=1e-15)


def test_implicit_enthalpy_accounts_for_cold_mass_birth_and_latent_heat(setup):
    spec,_,_,_ = setup
    materials = load(ROOT/spec["material_input"])["materials"]
    physics = load(ROOT/spec["thermal_properties"])
    tables,lengths,_ = material_tables(materials,physics["materials"])
    ids = np.array([3],dtype=np.int8)
    old = np.array([1500.])
    old_h = material_state(old,ids,tables,lengths)[0]
    new_mass = np.array([.002])
    # 原有1g热焊材与新增1g、20°C冷丝混合，新增冷丝零参考焓。
    temperature,_,_ = enthalpy_step(old,new_mass,.001*old_h,csr_matrix((1,1)),np.zeros(1),ids,tables,lengths,1e-9,30)
    assert 20.<temperature[0]<1500.
    assert new_mass*material_state(temperature,ids,tables,lengths)[0]==pytest.approx(.001*old_h,abs=1e-8)
    # 再供能跨越完整相变区，验证隐式相变方程能实际到达液相线以上。
    target_h = material_state(np.array([1600.]),ids,tables,lengths)[0]
    energy = new_mass*target_h-.001*old_h
    hot,_,_ = enthalpy_step(temperature,new_mass,.001*old_h,csr_matrix((1,1)),energy,ids,tables,lengths,1e-9,30)
    assert hot[0]==pytest.approx(1600.,abs=1e-7)
