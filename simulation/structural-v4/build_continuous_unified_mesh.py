"""构建壳体、Continuous 座体和单道焊缝的分区共形预备网格。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import gmsh
import numpy as np


ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/"simulation/structural-v4/results/struct0-prep"
LEG_MM=1.73664301094


def _weld_volume():
    # 与热模型保持等面积直角三角形；根点跨越0.02 mm间隙，避免人为细长四边形单元。
    points=[(75-LEG_MM,0,12),(75,0,12),(75,0,12+LEG_MM)]
    tags=[gmsh.model.occ.addPoint(*point) for point in points]
    lines=[gmsh.model.occ.addLine(tags[index],tags[(index+1)%len(tags)]) for index in range(len(tags))]
    surface=gmsh.model.occ.addPlaneSurface([gmsh.model.occ.addCurveLoop(lines)])
    return [entity for entity in gmsh.model.occ.revolve([(2,surface)],0,0,0,0,0,1,2*math.pi) if entity[0]==3]


def _boundary_surfaces(volume):
    return {tag for dim,tag in gmsh.model.getBoundary([volume],combined=False,oriented=False) if dim==2}


def _radial_surface(surface,radius,tolerance=.05):
    box=gmsh.model.getBoundingBox(2,surface)
    return abs(max(abs(box[0]),abs(box[1]),abs(box[3]),abs(box[4]))-radius)<tolerance and box[5]-box[2]>1.


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weld-size",type=float,default=.8)
    parser.add_argument("--algorithm-3d",type=int,default=10)
    parser.add_argument("--relocate-iterations",type=int,default=0)
    parser.add_argument("--output-stem",default="continuous-unified-prep")
    parser.add_argument("--report-name",default="continuous-unified-mesh.json")
    args=parser.parse_args()
    if args.weld_size<=0:
        parser.error("焊缝局部尺寸必须为正")
    OUTPUT.mkdir(parents=True,exist_ok=True)
    mesh_path=OUTPUT/f"{args.output_stem}.msh"
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal",1)
        gmsh.option.setNumber("Mesh.Binary",1)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin",min(.8,args.weld_size))
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax",5.)
        gmsh.option.setNumber("Mesh.Algorithm3D",args.algorithm_3d)
        gmsh.option.setNumber("Mesh.Optimize",1)
        gmsh.model.add(args.output_stem)
        shell=gmsh.model.occ.importShapes(str(ROOT/"simulation/structural-v4/common/shell.step"))
        seat=gmsh.model.occ.importShapes(str(ROOT/"simulation/structural-v4/models/continuous/Continuous.step"))
        weld=_weld_volume()
        _,mapping=gmsh.model.occ.fragment(shell+seat,weld)
        gmsh.model.occ.synchronize()
        volumes=[mapped[0] for mapped in mapping]
        shell_volume,seat_volume,weld_volume=volumes
        region_names=(("Q235B_SHELL",shell_volume),("QT450_10_SEAT",seat_volume),("ERNIFE_CI_WELD",weld_volume))
        for physical_id,(name,entity) in enumerate(region_names,1):
            gmsh.model.addPhysicalGroup(3,[entity[1]],physical_id)
            gmsh.model.setPhysicalName(3,physical_id,name)

        shell_surfaces=_boundary_surfaces(shell_volume); seat_surfaces=_boundary_surfaces(seat_volume); weld_surfaces=_boundary_surfaces(weld_volume)
        surfaces={
            "WELD_SHELL_INTERFACE":sorted(weld_surfaces&shell_surfaces),
            "WELD_SEAT_INTERFACE":sorted(weld_surfaces&seat_surfaces),
            "SEAT_GAP_FACE":sorted(surface for surface in seat_surfaces-weld_surfaces if _radial_surface(surface,74.98)),
            "SHELL_GAP_FACE":sorted(surface for surface in shell_surfaces-weld_surfaces if _radial_surface(surface,75.0)),
            "FIXTURE_BORE":sorted(surface for surface in seat_surfaces if _radial_surface(surface,20.0)),
            "DATUM_B_SHELL_OUTER":sorted(surface for surface in shell_surfaces if _radial_surface(surface,80.0)),
            "DATUM_A_SHELL_Z0":sorted(surface for surface in shell_surfaces if abs(gmsh.model.getBoundingBox(2,surface)[2])<1e-5 and abs(gmsh.model.getBoundingBox(2,surface)[5])<1e-5),
        }
        if any(not values for values in surfaces.values()):
            raise RuntimeError(f"接口或评价面识别失败：{surfaces}")
        for physical_id,(name,entities) in enumerate(surfaces.items(),101):
            gmsh.model.addPhysicalGroup(2,entities,physical_id)
            gmsh.model.setPhysicalName(2,physical_id,name)

        # 焊缝及其接口点局部细化，母材远场保持适中尺寸。
        weld_points=sorted({tag for surface in weld_surfaces for dim,tag in gmsh.model.getBoundary([(2,surface)],recursive=True) if dim==0})
        gmsh.model.mesh.setSize([(0,tag) for tag in weld_points],args.weld_size)
        gmsh.model.mesh.generate(3)
        gmsh.model.mesh.optimize("Netgen")
        if args.relocate_iterations>0:
            gmsh.model.mesh.optimize("Relocate3D",force=True,niter=args.relocate_iterations)
        gmsh.write(str(mesh_path))

        tetra_tags,_=gmsh.model.mesh.getElementsByType(4)
        qualities=np.asarray(gmsh.model.mesh.getElementQualities(tetra_tags,"minSICN"),float)
        node_tags,node_coords,_=gmsh.model.mesh.getNodes()
        region_tetrahedra={name:gmsh.model.mesh.getElementsByType(4,entity[1])[0] for name,entity in region_names}
        region_counts={name:int(len(tags)) for name,tags in region_tetrahedra.items()}
        region_quality={name:{"minimum":float(np.min(values)),"p01":float(np.percentile(values,1)),"below_0p1_count":int(np.count_nonzero(values<.1))}
                        for name,tags in region_tetrahedra.items() for values in [np.asarray(gmsh.model.mesh.getElementQualities(tags,"minSICN"),float)]}
        surface_node_counts={name:len({int(node) for surface in entities for node in gmsh.model.mesh.getNodes(2,surface,includeBoundary=True)[0]}) for name,entities in surfaces.items()}
        result={
            "stage":"STRUCT-0-PREP-CONTINUOUS-UNIFIED-MESH","evidence_level":"geometry_and_mesh_preparation",
            "mesh_file":mesh_path.relative_to(ROOT).as_posix(),"mesh_format":"Gmsh MSH 4.1 binary",
            "geometry":{"shell":"simulation/structural-v4/common/shell.step","seat":"simulation/structural-v4/models/continuous/Continuous.step",
                        "weld_leg_mm":LEG_MM,"weld_rule":"单道质量闭合焊脚的环形等面积直角三角形，根点跨越0.02mm装配间隙","weld_local_size_mm":args.weld_size,
                        "mesh_algorithm_3d":args.algorithm_3d,"relocate_iterations":args.relocate_iterations},
            "regions":{"physical_volume_ids":{"Q235B_SHELL":1,"QT450_10_SEAT":2,"ERNIFE_CI_WELD":3},"tetrahedron_counts":region_counts,"quality_by_region":region_quality},
            "interfaces":{"physical_surface_ids":{name:101+index for index,name in enumerate(surfaces)},"surface_tags":surfaces,"surface_node_counts":surface_node_counts,
                          "seat_shell_relation":"未焊圆柱面保持0.02mm间隙；不做节点绑定，留作法向接触/释放面"},
            "activation_groups":{"weld_ring_1":{"region":"ERNIFE_CI_WELD","status":"registered_not_activated_in_part_solve","stress_reference":"activation-time stress-free reference configuration"}},
            "metrology_sets":{"datum_a":"DATUM_A_SHELL_Z0","datum_b":"DATUM_B_SHELL_OUTER","bore":"FIXTURE_BORE",
                              "status":"mesh_sets_defined_cmm_equivalence_not_confirmed"},
            "counts":{"nodes":int(len(node_tags)),"tetrahedra":int(len(tetra_tags))},
            "quality":{"metric":"Gmsh minSICN","minimum":float(qualities.min()),"p01":float(np.percentile(qualities,1)),"median":float(np.median(qualities)),
                       "nonpositive_count":int(np.count_nonzero(qualities<=0)),"below_0p1_count":int(np.count_nonzero(qualities<.1))},
            "checks":{"three_material_regions":len(region_counts)==3 and all(value>0 for value in region_counts.values()),
                      "weld_interfaces_complete":bool(surfaces["WELD_SHELL_INTERFACE"] and surfaces["WELD_SEAT_INTERFACE"]),
                      "contact_gap_faces_separate":bool(surfaces["SEAT_GAP_FACE"] and surfaces["SHELL_GAP_FACE"]),
                      "evaluation_sets_present":bool(surfaces["FIXTURE_BORE"] and surfaces["DATUM_A_SHELL_Z0"] and surfaces["DATUM_B_SHELL_OUTER"]),
                      "no_inverted_tetrahedra":bool(np.all(qualities>0))},
            "heat_to_structure_mapping":{"status":"not_executed","reason":"当前热场仅为局部60mm移动源诊断窗口，不能伪装成Continuous整圈保守场传递"},
            "contact":{"status":"surfaces_registered_solver_not_implemented","first_model":"normal_contact_releasable_mu_0_then_engineering_mu_sensitivity"},
            "struct_prep_gate_pass":False,
        }
        (OUTPUT/args.report_name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps({"mesh":str(mesh_path),"counts":result["counts"],"quality":result["quality"],"checks":result["checks"]},ensure_ascii=False))
    finally:
        gmsh.finalize()
    return 0


if __name__=="__main__":
    raise SystemExit(main())
