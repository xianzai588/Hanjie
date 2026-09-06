"""运行一致切线、全局 Newton、热循环释放和应力自由出生基准。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import yaml


ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))
from hanjie.simulation.constitutive3d import affine_mesh_response,instantaneous_thermal_strain,interpolate_curve,j2_update,mandel_to_symmetric,stress_free_birth_state,symmetric_to_mandel,tetrahedral_cube
from hanjie.simulation.nonlinear_fem import solve_incremental_tetra


def constraints(nodes,*,lock_positive_x=False):
    result={}
    for node in np.where(nodes[:,0]==0)[0]: result[3*int(node)]=0.
    for node in np.where(nodes[:,1]==0)[0]: result[3*int(node)+1]=0.
    for node in np.where(nodes[:,2]==0)[0]: result[3*int(node)+2]=0.
    if lock_positive_x:
        for node in np.where(nodes[:,0]==1)[0]: result[3*int(node)]=0.
    return result


def face_force(nodes,stress_mpa):
    force=np.zeros_like(nodes)
    for triangle in ((1,2,6),(1,6,5)):
        force[list(triangle),0]+=stress_mpa/6
    return force


def tangent_audit(material):
    rows=[]; step=1e-8
    samples={"elastic":np.diag([5e-4,-1e-4,-1e-4]),"near_yield":np.diag([1.25e-3,-3e-4,-3e-4]),"plastic":np.diag([4e-3,-1e-3,-1e-3])}
    for name,strain in samples.items():
        base=j2_update(strain,0.,{},**material)
        numerical=np.zeros((6,6))
        for column in range(6):
            perturb=np.zeros(6); perturb[column]=step
            plus=j2_update(strain+mandel_to_symmetric(perturb),0.,{},**material)
            minus=j2_update(strain-mandel_to_symmetric(perturb),0.,{},**material)
            numerical[:,column]=(symmetric_to_mandel(plus["stress_mpa"])-symmetric_to_mandel(minus["stress_mpa"]))/(2*step)
        analytical=base["consistent_tangent_mpa"]
        denominator=max(float(np.linalg.norm(numerical)),1.)
        rows.append({"state":name,"equivalent_stress_mpa":base["equivalent_stress_mpa"],
                     "absolute_frobenius_error_mpa":float(np.linalg.norm(analytical-numerical)),
                     "relative_frobenius_error":float(np.linalg.norm(analytical-numerical)/denominator)})
    return rows


def build_results():
    q235=yaml.safe_load((ROOT/"project/materials.yaml").read_text(encoding="utf-8"))["materials"]["q235b"]
    curve=q235["temperature_dependent"]
    poisson=float(q235["nominal_properties_20c"]["poisson_ratio"])
    base_material=dict(elastic_modulus_mpa=210000.,poisson_ratio=poisson,yield_strength_mpa=235.,hardening_modulus_mpa=2000.)
    nodes,elements=tetrahedral_cube()

    tensile_steps=[{"name":f"traction_{stress:g}_mpa","external_force_n":face_force(nodes,stress),
                    "prescribed_dofs":constraints(nodes),"thermal_strain":0.} for stress in (100.,250.,300.)]
    tensile=solve_incremental_tetra(nodes,elements,base_material,tensile_steps,relative_tolerance=1e-9,max_iterations=20)
    expected=300/210000+(300-235)/2000
    final_tensile=tensile["steps"][-1]
    computed=float(np.mean(np.asarray(final_tensile["displacement_mm"])[nodes[:,0]==1,0]))

    temperatures=np.array([20.,200.,400.,600.])
    thermal_values=instantaneous_thermal_strain(temperatures,curve["temperatures_c"],curve["alpha_per_k"])
    elastic=interpolate_curve(temperatures,curve["temperatures_c"],curve["elastic_modulus_gpa"])*1000
    strengths=interpolate_curve(temperatures,curve["temperatures_c"],curve["yield_strength_mpa"])
    zero=np.zeros_like(nodes); locked=constraints(nodes,lock_positive_x=True); released=constraints(nodes)
    thermal_steps=[]
    for temperature,thermal,e,yield_strength in zip(temperatures,thermal_values,elastic,strengths):
        thermal_steps.append({"name":f"heat_{temperature:g}c","external_force_n":zero,"prescribed_dofs":locked,
                              "thermal_strain":float(thermal),"material":{"elastic_modulus_mpa":float(e),"yield_strength_mpa":float(yield_strength)}})
    thermal_steps.append({"name":"release_at_600c","external_force_n":zero,"prescribed_dofs":released,
                          "thermal_strain":float(thermal_values[-1]),"material":{"elastic_modulus_mpa":float(elastic[-1]),"yield_strength_mpa":float(strengths[-1])}})
    for temperature,thermal,e,yield_strength in zip(temperatures[-2::-1],thermal_values[-2::-1],elastic[-2::-1],strengths[-2::-1]):
        thermal_steps.append({"name":f"cool_{temperature:g}c","external_force_n":zero,"prescribed_dofs":released,
                              "thermal_strain":float(thermal),"material":{"elastic_modulus_mpa":float(e),"yield_strength_mpa":float(yield_strength)}})
    thermal_result=solve_incremental_tetra(nodes,elements,{**base_material,"hardening_modulus_mpa":1000.},thermal_steps,max_iterations=25)

    hot_thermal=float(thermal_values[-1]); hot_material={**base_material,"elastic_modulus_mpa":float(elastic[-1]),"yield_strength_mpa":float(strengths[-1])}
    birth_state=stress_free_birth_state(np.zeros((3,3)),hot_thermal)
    born=affine_mesh_response(np.zeros((3,3)),hot_thermal,hot_material,birth_state)
    constrained_cold=affine_mesh_response(np.zeros((3,3)),0.,base_material,birth_state)
    free_cold=affine_mesh_response(-np.eye(3)*hot_thermal,0.,base_material,birth_state)

    def mesh_stress(response):
        return float(max(np.abs(state["stress_mpa"]).max() for state in response["element_states"]))
    tangent=tangent_audit(base_material)
    thermal_final=thermal_result["steps"][-1]
    checks={key:bool(value) for key,value in {
        "consistent_tangent_relative_error":max(row["relative_frobenius_error"] for row in tangent)<5e-5,
        "tensile_analytic_strain":abs(computed-expected)/expected<1e-7,
        "all_newton_steps_converged":all(row["converged"] for row in tensile["steps"]+thermal_result["steps"]),
        "force_balance":max(np.linalg.norm(row["force_balance_n"]) for row in tensile["steps"]+thermal_result["steps"])<1e-8,
        "moment_balance":max(np.linalg.norm(row["moment_balance_n_mm"]) for row in tensile["steps"]+thermal_result["steps"])<1e-8,
        "plastic_dissipation_nonnegative":all(row["plastic_dissipation_mj"]>=0 for row in tensile["steps"]+thermal_result["steps"]),
        "released_cold_force_free":np.linalg.norm(thermal_final["reaction_force_n"])<1e-8,
        "stress_free_birth":mesh_stress(born)<1e-9,
        "stress_free_birth_cooling_response":mesh_stress(constrained_cold)>0 and mesh_stress(free_cold)<1e-9,
    }.items()}
    return {
        "stage":"STRUCT-0-PREP-GLOBAL-NEWTON","evidence_level":"algorithm_and_small_mesh_verification",
        "consistent_tangent":{"notation":"Mandel-6","finite_difference_step":1e-8,"rows":tangent},
        "tensile_bar":{"expected_final_strain":expected,"computed_final_strain":computed,"steps":tensile["steps"]},
        "constrained_thermal_release":{"temperature_c":temperatures.tolist(),"thermal_strain":thermal_values.tolist(),"steps":thermal_result["steps"],
                                       "final_mean_x_face_displacement_mm":float(np.mean(np.asarray(thermal_final["displacement_mm"])[nodes[:,0]==1,0]))},
        "stress_free_birth":{"activation_temperature_c":600.,"activation_thermal_strain":hot_thermal,
                             "born_max_abs_stress_mpa":mesh_stress(born),"fixed_geometry_cold_max_abs_stress_mpa":mesh_stress(constrained_cold),
                             "free_contraction_cold_max_abs_stress_mpa":mesh_stress(free_cold),
                             "rule":"元素激活时赋予当前总应变减热应变的参考构形；零机械应力出生，随后才参与热收缩和平衡。"},
        "checks":checks,"struct_prep_gate_pass":False,
        "limitations":["仅六四面体小型基准，尚非 Continuous 整件网格","未包含接触、摩擦或热场映射","温变材料曲线为设计假设，非本批材料标定"],
    }


def main() -> int:
    output=ROOT/"simulation/structural-v4/results/struct0-prep"
    output.mkdir(parents=True,exist_ok=True)
    result=build_results()
    target=output/"global-newton-benchmarks.json"
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# STRUCT-0-PREP 全局 Newton 基准","","> 一致切线与任意节点边界小网格验证；不是整件焊接结果。","",
           "| 基准 | 最大 Newton 迭代 | 最大残差 (N) | 合力平衡 (N) | 合矩平衡 (N·mm) |","| --- | ---: | ---: | ---: | ---: |"]
    for name,rows in (("拉杆屈服",result["tensile_bar"]["steps"]),("约束升温—释放—冷却",result["constrained_thermal_release"]["steps"])):
        lines.append(f"| {name} | {max(row['newton_iterations'] for row in rows)} | {max(row['residual_norm_n'] for row in rows):.3e} | {max(np.linalg.norm(row['force_balance_n']) for row in rows):.3e} | {max(np.linalg.norm(row['moment_balance_n_mm']) for row in rows):.3e} |")
    lines += ["",f"拉杆最终应变：解析 {result['tensile_bar']['expected_final_strain']:.9f}，计算 {result['tensile_bar']['computed_final_strain']:.9f}。",
              f"高温应力自由出生最大应力 {result['stress_free_birth']['born_max_abs_stress_mpa']:.3e} MPa；固定几何冷却后 {result['stress_free_birth']['fixed_geometry_cold_max_abs_stress_mpa']:.3f} MPa。","",
              "全部登记检查："+("通过" if all(result["checks"].values()) else "未通过")+"；`struct_prep_gate_pass=false`，统一网格、热映射和接触/释放仍待完成。"]
    (output/"global-newton-benchmarks.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(target)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
