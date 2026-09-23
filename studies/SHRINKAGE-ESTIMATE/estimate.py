"""角焊缝自由收缩的一阶包络筛查；不替代热—结构求解或实测。"""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[2]
segments=6; length=18.0; plate=5.0; leg=3.5
per_segment_min=0.0048; per_segment_max=0.80; asymmetry=0.02
free_min=segments*per_segment_min; free_max=segments*per_segment_max
payload={"version":"SHRINKAGE-ESTIMATE-1","evidence_level":"literature_order_screening","inputs":{"segments":segments,"segment_length_mm":length,"plate_thickness_mm":plate,"fillet_leg_mm":leg,"free_transverse_shrinkage_per_segment_mm":[per_segment_min,per_segment_max],"asymmetry_fraction":asymmetry},"formula":"residual_range = segments * free_shrinkage_per_segment * asymmetry_fraction","free_shrinkage_total_mm":[free_min,free_max],"residual_asymmetry_mm":[free_min*asymmetry,free_max*asymmetry],"thermal_allowance_comparison_mm":0.0102,"exceeds_thermal_allowance_possible":free_max*asymmetry>0.0102,"decision":"焊后终加工作为主路线；焊序和夹具用于降低加工余量需求，不宣称直接达到位置度限值"}
out=root/'studies/SHRINKAGE-ESTIMATE/results/estimate.json';out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(out)
