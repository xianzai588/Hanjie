"""运行无摩擦法向接触、分离和热膨胀撤夹三项小模型基准。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))
from hanjie.simulation.constitutive3d import tetrahedral_cube
from hanjie.simulation.nonlinear_fem import solve_incremental_tetra


OUTPUT=ROOT/"simulation/structural-v4/results/struct0-prep/contact-benchmarks.json"


def _compression_constraints(nodes,top_z):
    result={}
    for node in np.where(nodes[:,0]==0)[0]: result[3*int(node)]=0.
    for node in np.where(nodes[:,1]==0)[0]: result[3*int(node)+1]=0.
    for node in np.where(nodes[:,2]==1)[0]: result[3*int(node)+2]=top_z
    return result


def build_results():
    nodes,elements=tetrahedral_cube()
    material={"elastic_modulus_mpa":210000.,"poisson_ratio":.3,"yield_strength_mpa":1e9,"hardening_modulus_mpa":1000.}
    bottom_contact={"normal":[0,0,1],"offset_mm":0.,"allowed_side":"positive",
                    "node_indices":np.where(nodes[:,2]==0)[0].tolist(),"penalty_n_per_mm":1e8}
    normal=solve_incremental_tetra(nodes,elements,material,[
        {"name":"block_against_rigid_plane","prescribed_dofs":_compression_constraints(nodes,-.01),"contact":bottom_contact},
        {"name":"unload_and_separate","prescribed_dofs":_compression_constraints(nodes,.01),"contact":bottom_contact},
    ])

    symmetry={}
    for node in np.where(nodes[:,0]==0)[0]: symmetry[3*int(node)]=0.
    for node in np.where(nodes[:,1]==0)[0]: symmetry[3*int(node)+1]=0.
    for node in np.where(nodes[:,2]==0)[0]: symmetry[3*int(node)+2]=0.
    right_contact={"normal":[1,0,0],"offset_mm":1.01,"allowed_side":"negative",
                   "node_indices":np.where(nodes[:,0]==1)[0].tolist(),"penalty_n_per_mm":1e8}
    soft={**material,"elastic_modulus_mpa":1000.}
    zero=np.zeros_like(nodes)
    thermal=solve_incremental_tetra(nodes,elements,soft,[
        {"name":"thermal_expansion_contact","external_force_n":zero,"prescribed_dofs":symmetry,"thermal_strain":.02,"contact":right_contact},
        {"name":"release_fixture_hot","external_force_n":zero,"prescribed_dofs":symmetry,"thermal_strain":.02},
        {"name":"continue_cooling_after_release","external_force_n":zero,"prescribed_dofs":symmetry,"thermal_strain":0.},
    ])
    compressed,separated=normal["steps"]
    thermal_contact,released,cooled=thermal["steps"]
    all_steps=[compressed,separated,thermal_contact,released,cooled]
    checks={
        "compression_contact_active":compressed["contact"]["active_node_count"]>0,
        "penetration_below_0p001_mm":compressed["contact"]["maximum_penetration_mm"]<.001,
        "compression_reaction_positive":compressed["contact"]["normal_reaction_n"]>0,
        "unload_separates":separated["contact"]["active_node_count"]==0 and separated["contact"]["minimum_clearance_mm"]>0,
        "unload_contact_force_zero":separated["contact"]["normal_reaction_n"]==0,
        "thermal_contact_active":thermal_contact["contact"]["active_node_count"]>0,
        "hot_release_force_free":float(np.linalg.norm(released["reaction_force_n"]))<1e-7,
        "post_release_cooling_force_free":float(np.linalg.norm(cooled["reaction_force_n"]))<1e-7,
        "post_release_cooling_residual_displacement_below_1e_minus_9_mm":float(np.max(np.abs(cooled["displacement_mm"])))<1e-9,
        "global_force_balance":max(float(np.linalg.norm(row["force_balance_n"])) for row in all_steps)<1e-7,
        "global_moment_balance":max(float(np.linalg.norm(row["moment_balance_n_mm"])) for row in all_steps)<1e-7,
        "all_newton_steps_converged":all(row["converged"] for row in all_steps),
    }
    return {
        "stage":"STRUCT-0-PREP-NORMAL-CONTACT","evidence_level":"algorithm_and_small_mesh_verification",
        "formulation":"frictionless normal penalty contact against rigid plane; separation and fixture removal allowed",
        "benchmarks":{
            "block_against_rigid_plane":compressed,
            "contact_unload_separation":separated,
            "thermal_expansion_contact_release":{"steps":thermal["steps"],"residual_displacement_after_cooling_mm":float(np.max(np.abs(cooled["displacement_mm"])))},
        },
        "checks":{key:bool(value) for key,value in checks.items()},
        "contact_benchmark_pass":bool(all(checks.values())),
        "limitations":["罚刚度仅在小模型验证，尚未做Continuous整件条件数与尺度敏感性","无摩擦，符合首版准入范围","接触面为刚性平面，不代表锥形芯轴的最终几何离散"],
        "struct_prep_gate_pass":False,
    }


def main():
    result=build_results()
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(OUTPUT),"contact_benchmark_pass":result["contact_benchmark_pass"],"checks":result["checks"]},ensure_ascii=False))


if __name__=="__main__":
    main()
