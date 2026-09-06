"""用 Plan 5 局部热场验证保守投影、材料边界和固定点映射。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np


ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))
from hanjie.simulation.thermal_mapping import conservative_material_projection,map_material_points


SOURCE=ROOT/"simulation/thermal-v5/results/nested-refinement-study/NEST-F"
TARGET=ROOT/"simulation/thermal-v5/results/nested-refinement-study/NEST-M"
OUTPUT=ROOT/"simulation/structural-v4/results/struct0-prep/thermal-mapping-benchmark.json"
MATERIAL_NAMES={1:"q235b",2:"qt450_10",3:"ernife_ci"}


def build_results():
    with np.load(SOURCE/"field.npz") as source,np.load(TARGET/"field.npz") as target:
        projections={}
        for field_name in ("temperature_final","temperature_peak"):
            mapped=conservative_material_projection(source,target,field_name)
            projections[field_name]={
                "matched_volume_fraction":mapped["matched_volume_fraction"],
                "source_volume_temperature_integral_c_mm3":mapped["source_integral"],
                "target_volume_temperature_integral_c_mm3":mapped["target_integral"],
                "absolute_integral_residual_c_mm3":abs(mapped["target_integral"]-mapped["source_integral"]),
                "material_integral_residuals_c_mm3":mapped["material_integral_residuals"],
            }

        # 每种材料的源峰值控制体中心必须原值传递，避免点映射人为削峰。
        peak_points=[]
        for material_id,name in MATERIAL_NAMES.items():
            candidates=np.flatnonzero(source["material_id"]==material_id)
            cell=int(candidates[np.argmax(source["temperature_peak"][candidates])])
            peak_points.append({"material":name,"material_id":material_id,"source_cell":cell,
                                "coordinate_s_n_z_mm":[float(source[axis][cell]) for axis in ("s","n","z")],
                                "source_peak_temperature_c":float(source["temperature_peak"][cell])})
        peak_mapping=map_material_points(source,[row["coordinate_s_n_z_mm"] for row in peak_points],[row["material_id"] for row in peak_points],"temperature_peak")
        for row,value in zip(peak_points,peak_mapping["values"]):
            row["mapped_peak_temperature_c"]=value
            row["difference_c"]=abs(value-row["source_peak_temperature_c"])

        source_history=json.loads((SOURCE/"fixed-point-history.json").read_text(encoding="utf-8"))
        coordinates=[row["requested_coordinate_s_n_z_mm"] for row in source_history["points"]]
        material_ids=[row["material_id"] for row in source_history["points"]]
        final_mapping=map_material_points(source,coordinates,material_ids,"temperature_final")
        fixed=[]
        for point,value in zip(source_history["points"],final_mapping["values"]):
            history_value=float(source_history["rows"][-1][point["name"]])
            fixed.append({"name":point["name"],"coordinate_s_n_z_mm":point["requested_coordinate_s_n_z_mm"],
                          "source_history_final_c":history_value,"mapped_field_final_c":value,"difference_c":abs(value-history_value)})

        outside=[float(source["s_edges"][0]-1),0.,0.]
        unsupported=map_material_points(source,[outside],[1],"temperature_final",strict=False)
        material_mismatch=map_material_points(source,[coordinates[0]],[1],"temperature_final",strict=False)

    checks={
        "full_common_volume_matched":all(row["matched_volume_fraction"]>1-1e-12 for row in projections.values()),
        "global_integral_conserved":all(row["absolute_integral_residual_c_mm3"]<1e-6 for row in projections.values()),
        "each_material_integral_conserved":all(abs(value)<1e-6 for row in projections.values() for value in row["material_integral_residuals_c_mm3"].values()),
        "source_peaks_not_smoothed":max(row["difference_c"] for row in peak_points)<1e-12,
        "fixed_points_consistent":max(row["difference_c"] for row in fixed)<1e-10,
        "outside_domain_explicitly_unavailable":unsupported["status"]==["outside_source_domain"] and unsupported["values"]==[None],
        "cross_material_explicitly_unavailable":material_mismatch["status"]==["material_mismatch_or_void"] and material_mismatch["values"]==[None],
    }
    return {
        "stage":"STRUCT-0-PREP-THERMAL-MAPPING","evidence_level":"local_thermal_field_mapping_benchmark",
        "source":"simulation/thermal-v5/results/nested-refinement-study/NEST-F/field.npz",
        "target":"simulation/thermal-v5/results/nested-refinement-study/NEST-M/field.npz",
        "scope":"仅用局部嵌套热场验证映射算法边界，不是Continuous整圈正式STRUCT-0热载荷。",
        "conservative_control_volume_projection":projections,
        "same_material_peak_point_mapping":peak_points,
        "fixed_point_final_mapping":fixed,
        "unsupported_position_probe":{"coordinate_s_n_z_mm":outside,**unsupported},
        "cross_material_probe":{"coordinate_s_n_z_mm":coordinates[0],"requested_material":"q235b",**material_mismatch},
        "checks":{key:bool(value) for key,value in checks.items()},
        "thermal_mapping_benchmark_pass":bool(all(checks.values())),
        "formal_struct_0_thermal_load_allowed":False,
    }


def main():
    result=build_results()
    OUTPUT.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(OUTPUT),"pass":result["thermal_mapping_benchmark_pass"],"checks":result["checks"]},ensure_ascii=False))


if __name__=="__main__":
    main()
