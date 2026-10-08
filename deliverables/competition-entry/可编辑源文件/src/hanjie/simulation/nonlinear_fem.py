"""小型四面体温变弹塑性全局 Newton 求解器。"""

from __future__ import annotations

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import MatrixRankWarning, spsolve
import warnings

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


def _strain_tensor(nodes,element,displacement):
    dofs=np.ravel([[3*int(node)+axis for axis in range(3)] for node in element])
    b,_=_element_operators(nodes[element])
    value=b@displacement.ravel()[dofs]
    return np.array([[value[0],value[5]/np.sqrt(2),value[4]/np.sqrt(2)],
                     [value[5]/np.sqrt(2),value[1],value[3]/np.sqrt(2)],
                     [value[4]/np.sqrt(2),value[3]/np.sqrt(2),value[2]]])


def _assemble(nodes,elements,displacement,material,thermal_strain,old_states,active_elements,*,build_tangent=True):
    degrees=3*len(nodes)
    internal=np.zeros(degrees)
    tangent_rows=[]; tangent_columns=[]; tangent_values=[]
    trial_states=[]
    elastic_energy=0.; plastic_dissipation=0.
    for index,element in enumerate(elements):
        if not active_elements[index]:
            trial_states.append(old_states[index])
            continue
        dofs=np.ravel([[3*int(node)+axis for axis in range(3)] for node in element])
        b,volume=_element_operators(nodes[element])
        strain=_strain_tensor(nodes,element,displacement)
        thermal=thermal_strain[index] if np.ndim(thermal_strain)>0 else thermal_strain
        response=j2_update(strain,thermal,old_states[index],**material)
        stress=symmetric_to_mandel(response["stress_mpa"])
        element_force=b.T@stress*volume
        element_tangent=b.T@response["consistent_tangent_mpa"]@b*volume if build_tangent else None
        internal[dofs]+=element_force
        if build_tangent:
            tangent_rows.extend(np.repeat(dofs,12)); tangent_columns.extend(np.tile(dofs,12)); tangent_values.extend(element_tangent.ravel())
        trial_states.append({key:response[key] for key in ("stress_mpa","stress_free_strain","plastic_strain","equivalent_plastic_strain","plastic_dissipation_mj_mm3")})
        elastic_energy+=response["elastic_energy_mj_mm3"]*volume
        plastic_dissipation+=response["plastic_dissipation_mj_mm3"]*volume
    tangent=coo_matrix((tangent_values,(tangent_rows,tangent_columns)),shape=(degrees,degrees)).tocsr() if build_tangent else None
    return internal,tangent,trial_states,elastic_energy,plastic_dissipation


def _contact_response(nodes,displacement,specification):
    """罚函数无摩擦刚性平面接触；仅活动法向自由度贡献力和切线。"""
    degrees=3*len(nodes)
    force=np.zeros(degrees); rows=[]; columns=[]; values=[]
    if not specification:
        return force,csr_matrix((degrees,degrees)),None
    normal=np.asarray(specification["normal"],float)
    norm=float(np.linalg.norm(normal))
    if norm<=0:
        raise ValueError("接触面法向量不能为零")
    normal/=norm
    side=specification.get("allowed_side","positive")
    if side not in ("positive","negative"):
        raise ValueError("接触允许侧必须为 positive 或 negative")
    direction=1. if side=="positive" else -1.
    gradient=direction*normal
    node_indices=np.asarray(specification["node_indices"],dtype=int)
    if np.any(node_indices<0) or np.any(node_indices>=len(nodes)):
        raise ValueError("接触节点编号越界")
    penalty=float(specification["penalty_n_per_mm"])
    if penalty<=0:
        raise ValueError("接触罚刚度必须为正")
    current=nodes[node_indices]+displacement[node_indices]
    signed_gap=direction*(current@normal-float(specification["offset_mm"]))
    active=signed_gap<=0
    penetration=np.maximum(-signed_gap,0.)
    for local,node in enumerate(node_indices[active]):
        dofs=np.arange(3*int(node),3*int(node)+3)
        force[dofs]+=penalty*penetration[active][local]*gradient
        block=penalty*np.outer(gradient,gradient)
        rows.extend(np.repeat(dofs,3)); columns.extend(np.tile(dofs,3)); values.extend(block.ravel())
    report={
        "formulation":"frictionless_normal_penalty_rigid_plane",
        "active_node_count":int(np.count_nonzero(active& (penetration>0))),
        "maximum_penetration_mm":float(penetration.max(initial=0.)),
        "minimum_clearance_mm":float(np.maximum(signed_gap,0.).min(initial=np.inf)),
        "normal_reaction_n":float(np.sum(force.reshape((-1,3))@gradient)),
        "resultant_force_n":force.reshape((-1,3)).sum(axis=0).tolist(),
    }
    stiffness=coo_matrix((values,(rows,columns)),shape=(degrees,degrees)).tocsr()
    return force,stiffness,report


def solve_incremental_tetra(nodes,elements,material,steps,*,relative_tolerance=1e-8,absolute_tolerance_n=1e-8,max_iterations=25):
    """对任意节点约束和外载增量求解小应变四面体平衡。

    每个 Newton 试算都从上一个已收敛积分点状态重算，避免迭代过程重复累积塑性。
    """
    nodes=np.asarray(nodes,float); elements=np.asarray(elements,int)
    if nodes.ndim!=2 or nodes.shape[1]!=3 or elements.ndim!=2 or elements.shape[1]!=4:
        raise ValueError("节点或四面体连接格式无效")
    displacement=np.zeros_like(nodes)
    states=[{} for _ in elements]
    previously_active=np.zeros(len(elements),dtype=bool)
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
        active=np.asarray(step.get("active_elements",np.ones(len(elements),dtype=bool)),dtype=bool)
        if active.shape!=(len(elements),):
            raise ValueError("活动单元掩码长度无效")
        newly_active=active&~previously_active
        if step.get("stress_free_on_activation",False):
            for element_index in np.flatnonzero(newly_active):
                thermal_value=thermal[element_index] if thermal.ndim>0 else thermal
                reference=_strain_tensor(nodes,elements[element_index],trial.reshape((-1,3)))-float(thermal_value)*np.eye(3)
                states[element_index]={"stress_free_strain":reference,"plastic_strain":np.zeros((3,3)),
                                       "equivalent_plastic_strain":0.,"plastic_dissipation_mj_mm3":0.}
        history=[]; converged=False
        for iteration in range(max_iterations+1):
            internal,tangent,trial_states,elastic_energy,plastic_dissipation=_assemble(
                nodes,elements,trial.reshape((-1,3)),material_step,thermal,states,active)
            contact_force,contact_stiffness,contact_report=_contact_response(nodes,trial.reshape((-1,3)),step.get("contact"))
            residual=external+contact_force-internal
            norm=float(np.linalg.norm(residual[free]))
            scale=max(float(np.linalg.norm((external+contact_force)[free])),1.)
            history.append({"iteration":iteration,"residual_norm_n":norm})
            if norm<=absolute_tolerance_n+relative_tolerance*scale:
                converged=True
                break
            if iteration==max_iterations:
                break
            try:
                effective_tangent=tangent+contact_stiffness
                with warnings.catch_warnings():
                    warnings.simplefilter("error",MatrixRankWarning)
                    increment=spsolve(effective_tangent[free][:,free],residual[free])
                if not np.all(np.isfinite(increment)):
                    raise RuntimeError("稀疏切线求解得到非有限增量")
            except (np.linalg.LinAlgError,MatrixRankWarning,RuntimeError) as error:
                raise RuntimeError(f"第{step_index}增量切线奇异，检查刚体约束") from error
            # 约束突然释放时可能跨越反向屈服面；用残差回溯避免完整 Newton 步越过可收敛支路。
            accepted=False
            for line_search in range(12):
                factor=0.5**line_search
                candidate=trial.copy(); candidate[free]+=factor*increment
                candidate_internal,_,_,_,_=_assemble(nodes,elements,candidate.reshape((-1,3)),material_step,thermal,states,active,build_tangent=False)
                candidate_contact,_,_=_contact_response(nodes,candidate.reshape((-1,3)),step.get("contact"))
                candidate_norm=float(np.linalg.norm((external+candidate_contact-candidate_internal)[free]))
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
        previously_active=active.copy()
        reaction=(internal-external-contact_force).reshape((-1,3))
        total_force=external.reshape((-1,3))+contact_force.reshape((-1,3))+reaction
        records.append({
            "name":step.get("name",f"step_{step_index}"),"converged":True,
            "newton_iterations":len(history)-1,"newton_history":history,"residual_norm_n":norm,
            "displacement_mm":displacement.tolist(),"reaction_force_n":reaction.tolist(),
            "external_force_n":external.reshape((-1,3)).tolist(),
            "contact":contact_report,
            "active_element_count":int(np.count_nonzero(active)),
            "newly_activated_element_count":int(np.count_nonzero(newly_active)),
            "maximum_abs_stress_mpa":float(max((np.max(np.abs(state["stress_mpa"])) for state,is_active in zip(states,active) if is_active),default=0.)),
            "force_balance_n":total_force.sum(axis=0).tolist(),
            # 小应变内力由参考构形 B 矩阵组装，合矩也必须在同一参考坐标中核对。
            "moment_balance_n_mm":np.cross(nodes,total_force).sum(axis=0).tolist(),
            "elastic_energy_mj":float(elastic_energy),"plastic_dissipation_mj":float(plastic_dissipation),
        })
    return {"nodes_mm":nodes.tolist(),"elements":elements.tolist(),"linear_solver":"scipy_sparse_direct","steps":records,
            "final_states":[{"stress_mpa":state["stress_mpa"].tolist(),"stress_free_strain":state["stress_free_strain"].tolist(),
                             "plastic_strain":state["plastic_strain"].tolist(),
                             "equivalent_plastic_strain":float(state["equivalent_plastic_strain"]),
                             "plastic_dissipation_mj_mm3":float(state["plastic_dissipation_mj_mm3"])} for state in states]}
