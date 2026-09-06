"""局部热场到结构离散的材料安全映射原语。"""
from __future__ import annotations

import numpy as np


def _lattice(field):
    cross=np.asarray(field["material_cross_section"],dtype=int)
    shape=(len(field["s_edges"])-1,*cross.shape)
    occupied=np.broadcast_to(cross>0,shape)
    lattice=np.full(shape,-1,dtype=int)
    lattice[occupied]=np.arange(int(occupied.sum()))
    return lattice


def map_material_points(field,points_s_n_z_mm,material_ids,value_key,*,strict=True):
    """分片常数点映射；不跨材料、不平滑峰值且不允许隐式外推。"""
    edges=[np.asarray(field[f"{axis}_edges"],float) for axis in ("s","n","z")]
    lattice=_lattice(field)
    source_ids=np.asarray(field["material_id"],int)
    values=np.asarray(field[value_key],float)
    output=[]; status=[]; cells=[]
    for point,material_id in zip(np.asarray(points_s_n_z_mm,float),material_ids):
        outside=any(value<edge[0] or value>edge[-1] for value,edge in zip(point,edges))
        if outside:
            if strict: raise ValueError("目标点超出局部热源计算域，禁止外推")
            output.append(None); status.append("outside_source_domain"); cells.append(None); continue
        index=[]
        for value,edge in zip(point,edges):
            candidate=int(np.searchsorted(edge,value,side="right")-1)
            index.append(min(candidate,len(edge)-2))
        cell=int(lattice[tuple(index)])
        if cell<0 or source_ids[cell]!=int(material_id):
            if strict: raise ValueError("目标点与源控制体材料不一致，禁止跨材料插值")
            output.append(None); status.append("material_mismatch_or_void"); cells.append(None); continue
        output.append(float(values[cell])); status.append("mapped_same_material"); cells.append(cell)
    return {"method":"same_material_containing_control_volume","values":output,"status":status,"source_cell_indices":cells,
            "no_extrapolation":True,"no_cross_material_interpolation":True}


def conservative_material_projection(source,target,value_key):
    """按目标控制体和材料累计源体积积分，适用于嵌套/重叠局部场验证。"""
    axes=("s","n","z")
    indices=[np.searchsorted(target[f"{axis}_edges"],source[axis],side="right")-1 for axis in axes]
    sizes=tuple(len(target[f"{axis}_edges"])-1 for axis in axes)+(4,)
    valid=np.ones(len(source["material_id"]),dtype=bool)
    for index,size in zip(indices,sizes[:3]):
        valid&=(index>=0)&(index<size)
    source_ids=np.asarray(source["material_id"],int)
    keys=np.ravel_multi_index(tuple(index[valid] for index in indices)+(source_ids[valid],),sizes)
    weight=np.asarray(source["cell_volume_mm3"],float)[valid]*np.asarray(source.get("filled_fraction",np.ones(len(valid))),float)[valid]
    source_values=np.asarray(source[value_key],float)[valid]
    count=int(np.prod(sizes))
    volume=np.bincount(keys,weights=weight,minlength=count)
    integral=np.bincount(keys,weights=weight*source_values,minlength=count)

    target_indices=[np.searchsorted(target[f"{axis}_edges"],target[axis],side="right")-1 for axis in axes]
    target_ids=np.asarray(target["material_id"],int)
    target_keys=np.ravel_multi_index(tuple(target_indices)+(target_ids,),sizes)
    matched_volume=volume[target_keys]
    target_integrals=integral[target_keys]
    mapped=np.divide(target_integrals,matched_volume,out=np.full(len(target_ids),np.nan),where=matched_volume>0)
    target_active_volume=np.asarray(target["cell_volume_mm3"],float)*np.asarray(target.get("filled_fraction",np.ones(len(target_ids))),float)
    material_residuals={}
    for material_id in sorted(set(source_ids[valid])|set(target_ids)):
        source_part=float(np.sum(weight[source_ids[valid]==material_id]*source_values[source_ids[valid]==material_id]))
        target_part=float(np.sum(target_integrals[target_ids==material_id]))
        material_residuals[str(int(material_id))]=target_part-source_part
    return {
        "method":"material_partitioned_control_volume_integral",
        "values":mapped,
        "matched_volume_mm3":matched_volume,
        "matched_volume_fraction":float(matched_volume.sum()/max(target_active_volume.sum(),1e-30)),
        "source_integral":float(np.sum(weight*source_values)),
        "target_integral":float(np.sum(target_integrals)),
        "material_integral_residuals":material_residuals,
    }
