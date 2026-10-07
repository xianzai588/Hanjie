"""Compare the frozen continuous-track case and its two engineering checks."""
import json
import numpy as np
from mma_literature_profile import ROOT
from audit_mma_continuous import evaluate

BASE=ROOT/'simulation/competition-r4/results'
CASES=['mma-first-end80-r12-trace-20261007','mma-first-end80-r12-endpoint-dt00625-20261007','mma-first-end80-r12-h045-trace-20261007']


def summarize():
    rows=[evaluate(BASE/name) for name in CASES]
    reference=np.loadtxt(BASE/CASES[0]/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
    comparisons={}
    keys=['maximum_temperature_C','maximum_QT_C','central18mm_min_face_peak_C','total_interface_area_mm2','maximum_observed_QT_full_melt_depth_mm']
    for name,row,label in zip(CASES[1:],rows[1:],['endpoint_time_half','local_space']):
        diff={key:abs(row[key]-rows[0][key])/rows[0][key] for key in keys}
        other=np.loadtxt(BASE/name/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
        times=reference[:,0]
        if label=='endpoint_time_half':times=times[times>=9.375]
        for key,column in [('common_time_peak_history',4),('common_time_QT_history',5)]:
            a=np.interp(times,reference[:,0],reference[:,column]);b=np.interp(times,other[:,0],other[:,column])
            diff[key]=float(np.max(abs(a-b)/a))
        comparisons[label]=diff
    startup=json.loads((BASE/'mma-startup-end80-r12-20261007/startup-verification.json').read_text(encoding='utf8'))
    passed=bool(startup['startup_discretization_pass'] and all(row['one_wing_thermal_connection_screen_pass'] for row in rows)
        and all(value<=.05 for group in comparisons.values() for value in group.values()))
    for row in rows:
        row['numerical_response_convergence_verified']=passed
        row['comparison_basis']='three complete frozen-case histories plus current-geometry startup time check; all listed relative responses <=5%'
    result=dict(cases=rows,relative_response_differences=comparisons,startup_check=startup['relative_differences'],
        one_wing_thermal_connection_and_discretization_pass=passed,
        source_parameter_scope='saved volume-equivalent deposited shape and effective3.2mm net heat-source model with liquid factor3; no measured bead/source calibration',
        manufacturing_transfer_requirement='QT observed fully-molten depth about8mm: carry solidification and remelted-material state; do not infer low dilution from an assumed chemistry table',
        full_eight_wing_precoat_verified=False,retained_thermomechanical_state_verified=False,
        final_connection_verified=False,position_design_pass=False,bore_size_design_pass=False,complete_joint_strength_pass=False)
    destination=BASE/'mma-continuous-end80-r12-20261007';destination.mkdir(exist_ok=True)
    (destination/'thermal-connection-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({key:value for key,value in result.items() if key!='cases'},ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':summarize()
