"""STRUCT-0-PREP 无摩擦法向接触、分离与释放基准。"""
import numpy as np

from hanjie.simulation.constitutive3d import tetrahedral_cube
from hanjie.simulation.nonlinear_fem import solve_incremental_tetra


def _constraints(nodes,top_z):
    fixed={}
    for node in np.where(nodes[:,0]==0)[0]: fixed[3*int(node)]=0.0
    for node in np.where(nodes[:,1]==0)[0]: fixed[3*int(node)+1]=0.0
    for node in np.where(nodes[:,2]==1)[0]: fixed[3*int(node)+2]=top_z
    return fixed


def test_rigid_plane_contact_then_unload_separates_without_friction():
    nodes,elements=tetrahedral_cube()
    contact={"normal":[0,0,1],"offset_mm":0.0,"allowed_side":"positive",
             "node_indices":np.where(nodes[:,2]==0)[0].tolist(),"penalty_n_per_mm":1e8}
    material={"elastic_modulus_mpa":210000.0,"poisson_ratio":0.3,"yield_strength_mpa":1e9,"hardening_modulus_mpa":1000.0}
    result=solve_incremental_tetra(nodes,elements,material,[
        {"name":"compress","prescribed_dofs":_constraints(nodes,-0.01),"contact":contact},
        {"name":"unload_and_separate","prescribed_dofs":_constraints(nodes,0.01),"contact":contact},
    ])
    compressed,separated=result["steps"]
    assert compressed["contact"]["active_node_count"]>0
    assert 0<compressed["contact"]["maximum_penetration_mm"]<1e-3
    assert compressed["contact"]["normal_reaction_n"]>0
    assert separated["contact"]["active_node_count"]==0
    assert separated["contact"]["normal_reaction_n"]==0
    assert separated["contact"]["minimum_clearance_mm"]>0
    assert np.linalg.norm(separated["force_balance_n"])<1e-7


def test_thermal_expansion_contacts_plane_and_fixture_release_is_force_free():
    nodes,elements=tetrahedral_cube()
    fixed={}
    for node in np.where(nodes[:,0]==0)[0]: fixed[3*int(node)]=0.0
    for node in np.where(nodes[:,1]==0)[0]: fixed[3*int(node)+1]=0.0
    for node in np.where(nodes[:,2]==0)[0]: fixed[3*int(node)+2]=0.0
    contact={"normal":[1,0,0],"offset_mm":1.01,"allowed_side":"negative",
             "node_indices":np.where(nodes[:,0]==1)[0].tolist(),"penalty_n_per_mm":1e8}
    material={"elastic_modulus_mpa":1000.0,"poisson_ratio":0.25,"yield_strength_mpa":1e9,"hardening_modulus_mpa":1000.0}
    zero=np.zeros_like(nodes)
    result=solve_incremental_tetra(nodes,elements,material,[
        {"name":"thermal_contact","external_force_n":zero,"prescribed_dofs":fixed,"thermal_strain":0.02,"contact":contact},
        {"name":"fixture_release_hot","external_force_n":zero,"prescribed_dofs":fixed,"thermal_strain":0.02},
        {"name":"cool_after_release","external_force_n":zero,"prescribed_dofs":fixed,"thermal_strain":0.0},
    ])
    contacted,released,cooled=result["steps"]
    assert contacted["contact"]["active_node_count"]==4
    assert contacted["contact"]["normal_reaction_n"]>0
    assert released["contact"] is None
    assert np.linalg.norm(released["reaction_force_n"])<1e-7
    assert np.linalg.norm(cooled["reaction_force_n"])<1e-7
    np.testing.assert_allclose(np.asarray(cooled["displacement_mm"]),0.0,atol=1e-10)
