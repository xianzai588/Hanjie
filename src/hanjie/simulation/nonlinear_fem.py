"""小型四面体温变弹塑性全局 Newton 求解器。"""

from __future__ import annotations

import numpy as np

from .constitutive3d import j2_update,symmetric_to_mandel


def _element_operators(coordinates):
    matrix=np.column_stack((np.ones(4),coordinates))
    gradients=np.linalg.inv(matrix)[1:,:].T
    volume=abs(np.linalg.det((coordinates[1:]-coordinates[0]).T))/6
    root_two=np.sqrt(2.)
    b=np.zeros((6,12))
    for local,(gx,gy,gz) in enumerate(gradients):
        column=3*local
        b[0,column]=gx; b[1,column+1]=gy; b[2,column+2]=gz
        b[3,column+1]=gz/root_two; b[3,column+2]=gy/root_two
        b[4,column]=gz/root_two; b[4,column+2]=gx/root_two
        b[5,column]=gy/root_two; b[5,column+1]=gx/root_two
    return b,volume


def _assemble(nodes,elements,displacement,material,thermal_strain,old_states):
    degrees=3*len(nodes)
    internal=np.zeros(degrees)
    tangent=np.zeros((degrees,degrees))
    trial_states=[]
    elastic_energy=0.; plastic_dissipation=0.
    for index,element in enumerate(elements):
        dofs=np.ravel([[3*int(node)+axis for axis in range(3)] for node in element])
        b,volume=_element_operators(nodes[element])
        strain_vector=b@displacement.ravel()[dofs]
        strain=np.array([[strain_vector[0],strain_vector[5]/np.sqrt(2),strain_vector[4]/np.sqrt(2)],
                         [strain_vector[5]/np.sqrt(2),strain_vector[1],strain_vector[3]/np.sqrt(2)],
                         [strain_vector[4]/np.sqrt(2),strain_vector[3]/np.sqrt(2),strain_vector[2]]])
        thermal=thermal_strain[index] if np.ndim(thermal_strain)>0 else thermal_strain
        response=j2_update(strain,thermal,old_states[index],**material)
        stress=symmetric_to_mandel(response["stress_mpa"])
        element_force=b.T@stress*volume
        element_tangent=b.T@response["consistent_tangent_mpa"]@b*volume
        internal[dofs]+=element_force
        tangent[np.ix_(dofs,dofs)]+=element_tangent
        trial_states.append({key:response[key] for key in ("stress_free_strain","plastic_strain","equivalent_plastic_strain","plastic_dissipation_mj_mm3")})
        elastic_energy+=response["elastic_energy_mj_mm3"]*volume
        plastic_dissipation+=response["plastic_dissipation_mj_mm3"]*volume
    return internal,tangent,trial_states,elastic_energy,plastic_dissipation


def solve_incremental_tetra(nodes,elements,material,steps,*,relative_tolerance=1e-8,absolute_tolerance_n=1e-8,max_iterations=25):
    """对任意节点约束和外载增量求解小应变四面体平衡。

    每个 Newton 试算都从上一个已收敛积分点状态重算，避免迭代过程重复累积塑性。
    """
    nodes=np.asarray(nodes,float); elements=np.asarray(elements,int)
    if nodes.ndim!=2 or nodes.shape[1]!=3 or elements.ndim!=2 or elements.shape[1]!=4:
        raise ValueError("节点或四面体连接格式无效")
    displacement=np.zeros_like(nodes)
    states=[{} for _ in elements]
    records=[]
    all_dofs=np.arange(3*len(nodes))
    for step_index,step in enumerate(steps):
        external=np.asarray(step.get("external_force_n",np.zeros_like(nodes)),float).reshape(-1)
        if external.shape!=(3*len(nodes),):
            raise ValueError("外载必须与节点自由度数一致")
        prescribed={int(key):float(value) for key,value in step.get("prescribed_dofs",{}).items()}
        fixed=np.array(sorted(prescribed),dtype=int)
        free=np.setdiff1d(all_dofs,fixed,assume_unique=True)
        trial=displacement.copy().reshape(-1)
        if len(fixed):
            trial[fixed]=[prescribed[int(dof)] for dof in fixed]
        material_step={**material,**step.get("material",{})}
        thermal=np.asarray(step.get("thermal_strain",0.),float)
        if thermal.ndim>0 and thermal.shape!=(len(elements),):
            raise ValueError("热应变必须为标量或逐单元数组")
        history=[]; converged=False
        for iteration in range(max_iterations+1):
            internal,tangent,trial_states,elastic_energy,plastic_dissipation=_assemble(
                nodes,elements,trial.reshape((-1,3)),material_step,thermal,states)
            residual=external-internal
            norm=float(np.linalg.norm(residual[free]))
            scale=max(float(np.linalg.norm(external[free])),1.)
            history.append({"iteration":iteration,"residual_norm_n":norm})
            if norm<=absolute_tolerance_n+relative_tolerance*scale:
                converged=True
                break
            if iteration==max_iterations:
                break
            try:
                increment=np.linalg.solve(tangent[np.ix_(free,free)],residual[free])
            except np.linalg.LinAlgError as error:
                raise RuntimeError(f"第{step_index}增量切线奇异，检查刚体约束") from error
            # 约束突然释放时可能跨越反向屈服面；用残差回溯避免完整 Newton 步越过可收敛支路。
            accepted=False
            for line_search in range(12):
                factor=0.5**line_search
                candidate=trial.copy(); candidate[free]+=factor*increment
                candidate_internal,_,_,_,_=_assemble(nodes,elements,candidate.reshape((-1,3)),material_step,thermal,states)
                candidate_norm=float(np.linalg.norm((external-candidate_internal)[free]))
                if candidate_norm<norm:
                    trial=candidate
                    history[-1]["accepted_step_factor"]=factor
                    accepted=True
                    break
            if not accepted:
                trial[free]+=increment
                history[-1]["accepted_step_factor"]=1.
        if not converged:
            raise RuntimeError(f"第{step_index}增量在{max_iterations}次 Newton 迭代内未收敛；残差={norm:.6e} N")
        displacement=trial.reshape((-1,3))
        states=trial_states
        reaction=(internal-external).reshape((-1,3))
        total_force=external.reshape((-1,3))+reaction
        records.append({
            "name":step.get("name",f"step_{step_index}"),"converged":True,
            "newton_iterations":len(history)-1,"newton_history":history,"residual_norm_n":norm,
            "displacement_mm":displacement.tolist(),"reaction_force_n":reaction.tolist(),
            "external_force_n":external.reshape((-1,3)).tolist(),
            "force_balance_n":total_force.sum(axis=0).tolist(),
            "moment_balance_n_mm":np.cross(nodes,total_force).sum(axis=0).tolist(),
            "elastic_energy_mj":float(elastic_energy),"plastic_dissipation_mj":float(plastic_dissipation),
        })
    return {"nodes_mm":nodes.tolist(),"elements":elements.tolist(),"steps":records,
            "final_states":[{"stress_free_strain":state["stress_free_strain"].tolist(),
                             "plastic_strain":state["plastic_strain"].tolist(),
                             "equivalent_plastic_strain":float(state["equivalent_plastic_strain"]),
                             "plastic_dissipation_mj_mm3":float(state["plastic_dissipation_mj_mm3"])} for state in states]}
