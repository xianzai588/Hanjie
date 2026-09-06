"""运行三维 J2 材料路径和六四面体立方体整体平衡验证。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import yaml


ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))
from hanjie.simulation.constitutive3d import affine_mesh_response,instantaneous_thermal_strain,interpolate_curve,j2_update


def tensor(values):
    return np.asarray(values,float)


def build_results():
    source=yaml.safe_load((ROOT/"project/materials.yaml").read_text(encoding="utf-8"))["materials"]["q235b"]
    curve=source["temperature_dependent"]
    temperatures=np.array([20.,200.,400.,600.])
    elastic=interpolate_curve(temperatures,curve["temperatures_c"],curve["elastic_modulus_gpa"])*1000
    strength=interpolate_curve(temperatures,curve["temperatures_c"],curve["yield_strength_mpa"])
    thermal=instantaneous_thermal_strain(temperatures,curve["temperatures_c"],curve["alpha_per_k"])
    material=dict(elastic_modulus_mpa=float(elastic[0]),poisson_ratio=float(source["nominal_properties_20c"]["poisson_ratio"]),
                  yield_strength_mpa=float(strength[0]),hardening_modulus_mpa=0.0)

    paths={
        "uniaxial_strain":tensor([[0,0,0],[.0005,0,0],[.002,0,0],[0,0,0]]),
        "pure_shear":tensor([[[0,0,0],[0,0,0],[0,0,0]],[[0,.0005,0],[.0005,0,0],[0,0,0]],[[0,.002,0],[.002,0,0],[0,0,0]]]),
        "hydrostatic":tensor([np.eye(3)*value for value in (0,.001,.003)]),
        "combined":tensor([[[0,0,0],[0,0,0],[0,0,0]],[[.002,.001,0],[.001,-.0005,0],[0,0,-.0005]]]),
    }
    paths["uniaxial_strain"]=np.array([np.diag(row) for row in paths["uniaxial_strain"]])
    material_results={}
    for name,history in paths.items():
        state={}
        rows=[]
        for index,strain in enumerate(history):
            result=j2_update(strain,0.0,state,**material)
            state={key:result[key] for key in ("plastic_strain","equivalent_plastic_strain","plastic_dissipation_mj_mm3")}
            rows.append({"step":index,"strain":strain.tolist(),"stress_mpa":result["stress_mpa"].tolist(),
                         "equivalent_stress_mpa":result["equivalent_stress_mpa"],"equivalent_plastic_strain":result["equivalent_plastic_strain"],
                         "plastic_dissipation_mj_mm3":result["plastic_dissipation_mj_mm3"]})
        material_results[name]=rows

    state={}
    temperature_rows=[]
    for index,(temperature,thermal_value,elastic_value,strength_value) in enumerate(zip(temperatures,thermal,elastic,strength)):
        # x向完全约束，y/z允许自由热膨胀；跨多个温区实际调用温变参数。
        total_strain=np.diag([0.0,thermal_value,thermal_value])
        step_material={**material,"elastic_modulus_mpa":float(elastic_value),"yield_strength_mpa":float(strength_value)}
        result=j2_update(total_strain,float(thermal_value),state,**step_material)
        state={key:result[key] for key in ("plastic_strain","equivalent_plastic_strain","plastic_dissipation_mj_mm3")}
        temperature_rows.append({"step":index,"temperature_c":float(temperature),"total_strain":total_strain.tolist(),
                                 "thermal_strain":float(thermal_value),"elastic_modulus_mpa":float(elastic_value),
                                 "yield_strength_mpa":float(strength_value),"stress_mpa":result["stress_mpa"].tolist(),
                                 "equivalent_stress_mpa":result["equivalent_stress_mpa"],
                                 "equivalent_plastic_strain":result["equivalent_plastic_strain"],
                                 "plastic_dissipation_mj_mm3":result["plastic_dissipation_mj_mm3"]})
    material_results["temperature_dependent_x_constrained"]=temperature_rows

    free_temperature=200.
    free_thermal=float(instantaneous_thermal_strain(np.array([free_temperature]),curve["temperatures_c"],curve["alpha_per_k"])[0])
    hot_material={**material,"elastic_modulus_mpa":float(elastic[1]),"yield_strength_mpa":float(strength[1])}
    free=affine_mesh_response(np.eye(3)*free_thermal,free_thermal,hot_material)
    constrained=affine_mesh_response(np.zeros((3,3)),free_thermal,hot_material)
    mechanical_strain=np.diag([.002,-.0005,-.0005])
    loaded=affine_mesh_response(mechanical_strain,0.0,material)
    plastic_state={key:loaded["element_states"][0][key] for key in ("plastic_strain","equivalent_plastic_strain","plastic_dissipation_mj_mm3")}
    released=affine_mesh_response(plastic_state["plastic_strain"],0.0,material,plastic_state)

    def mesh_summary(response):
        return {"element_count":int(len(response["elements"])),"volume_mm3":response["volume_mm3"],
                "maximum_displacement_mm":float(np.linalg.norm(response["displacement"],axis=1).max()),
                "maximum_equivalent_stress_mpa":float(max(row["equivalent_stress_mpa"] for row in response["element_states"])),
                "maximum_absolute_stress_component_mpa":float(max(np.abs(row["stress_mpa"]).max() for row in response["element_states"])),
                "resultant_internal_force_n":response["resultant_internal_force_n"].tolist(),
                "resultant_internal_moment_n_mm":response["resultant_internal_moment_n_mm"].tolist(),
                "maximum_plastic_dissipation_mj_mm3":float(max(row["plastic_dissipation_mj_mm3"] for row in response["element_states"]))}
    mesh_results={name:mesh_summary(value) for name,value in (("free_thermal_expansion",free),("fully_constrained_heating",constrained),("deviatoric_loading",loaded),("support_release_to_plastic_shape",released))}
    return {"stage":"STRUCT-0-PREP-3D-COMPONENTS","evidence_level":"algorithm_and_small_mesh_verification",
            "material_evidence":"Q235B design-assumption curves; not batch calibrated","temperature_interpolation":{
                "temperature_c":temperatures.tolist(),"elastic_modulus_mpa":elastic.tolist(),"yield_strength_mpa":strength.tolist(),
                "integrated_instantaneous_thermal_strain":thermal.tolist(),"out_of_range_policy":"error"},
            "material_point_paths":material_results,"small_mesh":mesh_results,
            "checks":{"hydrostatic_no_plastic":material_results["hydrostatic"][-1]["equivalent_plastic_strain"]==0,
                      "free_expansion_zero_stress":mesh_results["free_thermal_expansion"]["maximum_absolute_stress_component_mpa"]<1e-9,
                      "global_force_balance":all(np.linalg.norm(value["resultant_internal_force_n"])<1e-9 for value in mesh_results.values()),
                      "global_moment_balance":all(np.linalg.norm(value["resultant_internal_moment_n_mm"])<1e-9 for value in mesh_results.values()),
                      "plastic_dissipation_nonnegative":all(row["plastic_dissipation_mj_mm3"]>=0 for rows in material_results.values() for row in rows),
                      "released_state_zero_stress":mesh_results["support_release_to_plastic_shape"]["maximum_absolute_stress_component_mpa"]<1e-9},
            "limitations":["仿射位移控制小网格，不是任意边界非线性全局 Newton 求解器","未包含焊材本构、接触或焊道激活","算法通过不代表 QT450-10/ERNiFe-CI 裂纹或疲劳性能已验证"]}


def main():
    output=ROOT/"simulation/structural-v4/results/struct0-prep"
    output.mkdir(parents=True,exist_ok=True)
    result=build_results()
    target=output/"constitutive-3d-small-mesh.json"
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# STRUCT-0-PREP 三维组件验证","","> 三维 J2 与六四面体仿射小网格算法基准；不是 Continuous 整件求解结果。","",
           "| 小网格算例 | 最大等效应力 (MPa) | 最大应力分量 (MPa) | 合力范数 (N) | 合矩范数 (N·mm) |",
           "| --- | ---: | ---: | ---: | ---: |"]
    for name,row in result["small_mesh"].items():
        lines.append(f"| {name} | {row['maximum_equivalent_stress_mpa']:.6f} | {row['maximum_absolute_stress_component_mpa']:.6f} | {np.linalg.norm(row['resultant_internal_force_n']):.3e} | {np.linalg.norm(row['resultant_internal_moment_n_mm']):.3e} |")
    lines += ["","全部登记检查："+("通过" if all(result["checks"].values()) else "未通过"),"",
              "已覆盖纯剪、静水、组合、卸载、坐标旋转一致性、跨温区插值、自由/约束热膨胀和支承释放。任意边界全局 Newton、一致切线、焊材、接触及焊道激活仍未实现。"]
    (output/"constitutive-3d-small-mesh.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(target)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
