"""局部热场到结构离散的保守、同材料、无外推边界测试。"""
import numpy as np
import pytest

from hanjie.simulation.thermal_mapping import conservative_material_projection,map_material_points


def _field(edges_n,materials,temperatures,volumes):
    n=np.array([(a+b)/2 for a,b in zip(edges_n[:-1],edges_n[1:])])
    return {
        "s_edges":np.array([0.,1.]),"n_edges":np.asarray(edges_n),"z_edges":np.array([0.,1.]),
        "s":np.full(len(n),.5),"n":n,"z":np.full(len(n),.5),
        "material_cross_section":np.asarray(materials,dtype=int)[:,None],
        "material_id":np.asarray(materials,dtype=int),"cell_volume_mm3":np.asarray(volumes,float),
        "filled_fraction":np.ones(len(n)),"temperature_peak":np.asarray(temperatures,float),
    }


def test_nested_projection_conserves_volume_temperature_integral_by_material():
    fine=_field([0.,.5,1.,2.],[2,2,3],[10.,20.,30.],[.5,.5,1.])
    coarse=_field([0.,1.,2.],[2,3],[0.,0.],[1.,1.])
    result=conservative_material_projection(fine,coarse,"temperature_peak")
    np.testing.assert_allclose(result["values"],[15.,30.])
    assert result["matched_volume_fraction"]==pytest.approx(1.)
    assert result["source_integral"]==pytest.approx(result["target_integral"])
    assert result["material_integral_residuals"]==pytest.approx({"2":0.,"3":0.})


def test_point_mapping_is_same_material_and_never_silently_extrapolates():
    field=_field([0.,1.,2.],[2,3],[10.,30.],[1.,1.])
    mapped=map_material_points(field,[[.5,.25,.5]],[2],"temperature_peak")
    assert mapped["values"]==[10.]
    with pytest.raises(ValueError,match="材料"):
        map_material_points(field,[[.5,.25,.5]],[3],"temperature_peak")
    unavailable=map_material_points(field,[[.5,2.1,.5]],[3],"temperature_peak",strict=False)
    assert unavailable["values"]==[None]
    assert unavailable["status"]==["outside_source_domain"]
