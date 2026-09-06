"""定位 Continuous 共形网格低 minSICN 四面体及其邻近材料界面。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import gmsh
import numpy as np
from scipy.spatial import cKDTree


ROOT=Path(__file__).resolve().parents[2]
MESH=ROOT/"simulation/structural-v4/results/struct0-prep/continuous-unified-prep.msh"
OUTPUT=ROOT/"simulation/structural-v4/results/struct0-prep/continuous-mesh-quality-diagnosis.json"
QUALITY_LIMIT=.1


def _physical_entities(dimension):
    result={}
    for dim,tag in gmsh.model.getPhysicalGroups(dimension):
        name=gmsh.model.getPhysicalName(dim,tag)
        result[name]=gmsh.model.getEntitiesForPhysicalGroup(dim,tag).tolist()
    return result


def _element_tags(entities,element_type=4):
    tags=[]
    for entity in entities:
        values,_=gmsh.model.mesh.getElementsByType(element_type,int(entity))
        tags.extend(np.asarray(values,dtype=np.int64).tolist())
    return np.asarray(tags,dtype=np.int64)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mesh",type=Path,default=MESH)
    parser.add_argument("--output",type=Path,default=OUTPUT)
    args=parser.parse_args()
    mesh=args.mesh if args.mesh.is_absolute() else ROOT/args.mesh
    output=args.output if args.output.is_absolute() else ROOT/args.output
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal",0)
        gmsh.open(str(mesh))
        tetra_tags,tetra_nodes=gmsh.model.mesh.getElementsByType(4)
        tetra_tags=np.asarray(tetra_tags,dtype=np.int64)
        tetra_nodes=np.asarray(tetra_nodes,dtype=np.int64).reshape(-1,4)
        qualities=np.asarray(gmsh.model.mesh.getElementQualities(tetra_tags,"minSICN"),dtype=float)
        node_tags,node_values,_=gmsh.model.mesh.getNodes()
        coordinates=np.asarray(node_values,dtype=float).reshape(-1,3)
        tag_to_row={int(tag):index for index,tag in enumerate(node_tags)}
        connectivity=np.asarray([[tag_to_row[int(tag)] for tag in row] for row in tetra_nodes],dtype=int)
        centroids=coordinates[connectivity].mean(axis=1)

        volumes=_physical_entities(3)
        tag_to_region={int(tag):name for name,entities in volumes.items() for tag in _element_tags(entities)}
        regions=np.asarray([tag_to_region[int(tag)] for tag in tetra_tags])
        interface_names=("WELD_SHELL_INTERFACE","WELD_SEAT_INTERFACE","SEAT_GAP_FACE","SHELL_GAP_FACE")
        surfaces=_physical_entities(2)
        trees={}
        for name in interface_names:
            tags=set()
            for entity in surfaces.get(name,[]):
                tags.update(int(tag) for tag in gmsh.model.mesh.getNodes(2,int(entity),includeBoundary=True)[0])
            if tags:
                trees[name]=cKDTree(coordinates[[tag_to_row[tag] for tag in sorted(tags)]])

        bad=np.flatnonzero(qualities<QUALITY_LIMIT)
        distances=np.column_stack([tree.query(centroids[bad])[0] for tree in trees.values()])
        names=list(trees)
        nearest=np.argmin(distances,axis=1)
        nearest_distance=distances[np.arange(len(bad)),nearest]
        nearest_name=np.asarray(names)[nearest]
        cylindrical=np.column_stack((np.linalg.norm(centroids[bad,:2],axis=1),np.degrees(np.arctan2(centroids[bad,1],centroids[bad,0])),centroids[bad,2]))

        by_region={}
        for name in volumes:
            values=qualities[regions==name]
            by_region[name]={
                "tetrahedra":int(len(values)),"minimum":float(values.min()),
                "p01":float(np.percentile(values,1)),"p05":float(np.percentile(values,5)),
                "below_0p1_count":int(np.count_nonzero(values<QUALITY_LIMIT)),
            }
        adjacent={}
        for name in names:
            selected=nearest_name==name
            adjacent[name]={
                "nearest_low_quality_tetrahedra":int(np.count_nonzero(selected)),
                "distance_to_interface_node_mm":{"minimum":float(nearest_distance[selected].min()) if selected.any() else None,"median":float(np.median(nearest_distance[selected])) if selected.any() else None,"maximum":float(nearest_distance[selected].max()) if selected.any() else None},
                "within_0p25_mm":int(np.count_nonzero(selected&(nearest_distance<=.25))),
                "within_0p5_mm":int(np.count_nonzero(selected&(nearest_distance<=.5))),
                "within_1p0_mm":int(np.count_nonzero(selected&(nearest_distance<=1.0))),
            }
        theta_edges=np.linspace(-180,180,13)
        theta_counts=np.histogram(cylindrical[:,1],theta_edges)[0]
        result={
            "stage":"STRUCT-0-PREP-MESH-QUALITY-DIAGNOSIS","evidence_level":"executed_mesh_diagnostic",
            "mesh_file":mesh.relative_to(ROOT).as_posix(),"quality_metric":"Gmsh minSICN","low_quality_threshold":QUALITY_LIMIT,
            "global":{"tetrahedra":int(len(tetra_tags)),"minimum":float(qualities.min()),"p01":float(np.percentile(qualities,1)),"p05":float(np.percentile(qualities,5)),"below_0p1_count":int(len(bad))},
            "by_material_region":by_region,
            "spatial_distribution":{
                "cartesian_bbox_xyz_mm":{"minimum":centroids[bad].min(axis=0).tolist(),"maximum":centroids[bad].max(axis=0).tolist()},
                "cylindrical_bbox_r_theta_z":{"minimum":cylindrical.min(axis=0).tolist(),"maximum":cylindrical.max(axis=0).tolist()},
                "theta_bins_deg":theta_edges.tolist(),"theta_counts":theta_counts.tolist(),
                "nearest_registered_interface":adjacent,
                "distance_definition":"低质量四面体质心到已登记界面网格节点的最近距离；用于局部重划分定位，不冒充精确点面距离。",
            },
            "low_quality_tetrahedra":[
                {"element_tag":int(tetra_tags[index]),"min_sicn":float(qualities[index]),"material_region":str(regions[index]),
                 "centroid_xyz_mm":centroids[index].tolist(),"cylindrical_r_theta_z_mm_deg":[float(v) for v in cylindrical[row]],
                 "nearest_registered_interface":str(nearest_name[row]),"nearest_interface_node_distance_mm":float(nearest_distance[row])}
                for row,index in enumerate(bad)
            ],
            "decision":"低质量单元若集中于焊缝/界面高梯度区，则仅对焊缝拓扑和局部尺寸重划分，不扩大母材远场网格。",
        }
        output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print(json.dumps({"output":str(output),"global":result["global"],"by_material_region":by_region,"nearest_interface":adjacent},ensure_ascii=False))
    finally:
        gmsh.finalize()


if __name__=="__main__":
    main()
