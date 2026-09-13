from pathlib import Path
import importlib.util, csv, json, sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'simulation/scripts'))
src=ROOT/'simulation/scripts/run_reduced_order.py'
spec=importlib.util.spec_from_file_location('reduced',src); reduced=importlib.util.module_from_spec(spec); spec.loader.exec_module(reduced)
def main():
 cfg=reduced.load_yaml(ROOT/'simulation/configs/default.yaml'); rows=[]
 for p in (150.,200.,250.,300.,350.):
  cfg['process']['preheat_c']=p
  for layout in (6,8):
   for seq in ('S1','S2','S3'):
    r=reduced.evaluate_case(cfg,layout,seq,'baseline','rigid'); r['preheat_c']=p; rows.append(r)
 out=ROOT/'studies/COMPETITION-DESIGN/results/preheat-sensitivity.csv'; out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
 summary={'version':'COMPETITION-R1-PREHEAT-SENSITIVITY-1','preheat_range_c':[150,350],'case_count':len(rows),'best_by_preheat':[],'interpretation':'降阶热结构代理仿真；用于预热窗口和焊序相对比较，不替代实物热循环或CMM。'}
 for p in (150.,200.,250.,300.,350.):
  x=[r for r in rows if r['preheat_c']==p]; b=min(x,key=lambda r:r['position_metric_p_sim_mm']); summary['best_by_preheat'].append({'preheat_c':p,'case_id':b['case_id'],'p_sim_mm':b['position_metric_p_sim_mm']})
 out.with_suffix('.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__': main()

