"""Freeze one speed revision and its single spatial comparison from real runs."""
import json
import yaml
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from audit_mma_continuous import evaluate
from audit_mma_three_cases import audit
from plot_mma_continuous import plane_triangles
from mma_literature_profile import ROOT

BASE=ROOT/'simulation/competition-r4/results'
OLD='mma-first-end80-r12-phase-front-dt0125-20261007'
COARSE='mma-first-speed120-end80-r12-20261007'
FINE='mma-first-speed120-end80-r12-h045-20261007'
OUT=ROOT/'output/review/first-precoat-speed120-20261007'

def main():
    names=[OLD,COARSE,FINE]
    summaries=[]
    for name in names:
        result=json.loads((BASE/name/'result.json').read_text())
        if result['partial'] or result['error']:raise RuntimeError('Preserve incomplete run; no comparison pass')
        summaries.append(evaluate(BASE/name))
    old,coarse,fine=summaries
    keys=['maximum_temperature_C','maximum_QT_C','central18mm_min_face_peak_C',
          'maximum_observed_QT_full_melt_depth_mm']
    delta={key:abs(coarse[key]-fine[key])/abs(fine[key]) for key in keys}
    for j in range(2):
        key=f'interface_t8_5_{"min" if j==0 else "max"}'
        delta[key]=abs(coarse['interface_centroid_final_t8_5_s_range'][j]-fine['interface_centroid_final_t8_5_s_range'][j])/fine['interface_centroid_final_t8_5_s_range'][j]
    passed=all(s['one_wing_thermal_connection_screen_pass'] for s in [coarse,fine]) and max(delta.values())<=.05
    comparison=dict(baseline=old,speed120_coarse=coarse,speed120_fine=fine,
                    new_spatial_response_relative_errors=delta,
                    maximum_new_spatial_response_relative_error=max(delta.values()),
                    speed120_spatial_thermal_connection_passed=bool(passed),
                    QT_ever_melt_depth_reduction_mm=old['maximum_observed_QT_full_melt_depth_mm']-coarse['maximum_observed_QT_full_melt_depth_mm'],
                    actual_cold_mechanical_state_qualified=False,full_manufacturing_chain_passed=False,
                    scope='One physical speed revision, one h0.65-to0.45 comparison. New spatial response convergence only; no new temporal-convergence, transport/dilution, PMZ capacity, actual retained cut or full component qualification. Stop more thermal variants after this comparison.')
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'speed120-thermal-comparison.json').write_text(json.dumps(comparison,indent=2,ensure_ascii=False),encoding='utf8')
    card_path=ROOT/'project/precoat-speed120-candidate.yaml'
    card=yaml.safe_load(card_path.read_text(encoding='utf8'))
    card['state']='spatial_thermal_screen_passed_supply_and_manufacturing_unqualified' if passed else 'thermal_revision_failed_screen'
    card['thermal_screen_evidence']=dict(comparison='output/review/first-precoat-speed120-20261007/speed120-thermal-comparison.json',
        actual_completed_runs=[COARSE,FINE],spatial_response_passed=bool(passed),
        maximum_spatial_relative_error=max(delta.values()),new_temporal_convergence_verified=False,
        physical_source_calibrated=False,actual_cold_mechanical_state_qualified=False)
    card_path.write_text(yaml.safe_dump(card,allow_unicode=True,sort_keys=False),encoding='utf8')
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':9,
                         'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,2,figsize=(11.6,8),layout='constrained')
    colours=['#848a91','#1a6778','#bf723b'];labels=['100 mm/min基线','120 mm/min，h0.65','120 mm/min，h0.45']
    for name,label,colour in zip(names,labels,colours):
        h=np.loadtxt(BASE/name/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
        axes[0,0].plot(h[:,0],h[:,4],color=colour,label=label,lw=1.4)
    axes[0,0].axhline(2800,color='#a94646',ls='--',lw=1)
    axes[0,0].set(title='a  实际温度历程与一次空间对照',xlabel='时间 / s',ylabel='金属最高温度 / ℃',xlim=(0,96),ylim=(250,2900))
    axes[0,0].legend(frameon=False,fontsize=7.5)
    folder=BASE/COARSE
    inp=json.loads((folder/'input.json').read_text())
    _,polygons,peak_min,positions,minimum=audit(folder)
    pc=PolyCollection(polygons,array=peak_min,cmap='inferno',clim=(1400,2600),edgecolors='none')
    axes[0,1].add_collection(pc)
    axes[0,1].set(title='b  各界面三节点同时峰温',xlabel='s=74.98θ / mm',ylabel='半径 / mm',xlim=(-10.5,10.5),ylim=(68.8,75.2))
    for boundary in [-9,9]:axes[0,1].axvline(boundary,color='#777',ls=':',lw=1)
    fig.colorbar(pc,ax=axes[0,1],label='max_t[min三节点(T)] / ℃',shrink=.82)
    for name,label,colour in zip(names,labels,colours):
        _,_,_,p,t=audit(BASE/name);valid=t>0
        axes[1,0].plot(p[valid],t[valid],color=colour,label=label,lw=1.3)
    axes[1,0].axhline(1400,color='#a94646',ls='--',lw=1)
    axes[1,0].axvspan(-9,9,color=colours[1],alpha=.05)
    axes[1,0].set(title='c  中央18 mm各截面最弱面',xlabel='s=74.98θ / mm',ylabel='最弱面峰温 / ℃',xlim=(-10.5,10.5),ylim=(1200,2300))
    axes[1,0].text(.03,.95,f'120候选最低{coarse["central18mm_min_face_peak_C"]:.0f}℃\n全部界面{coarse["simultaneous_full_liquid_face_area_mm2"]:.3f} mm²',transform=axes[1,0].transAxes,va='top',fontsize=8)
    arc_end=inp['tracks'][0]['arc_duration_s'];state=None
    for path in sorted((folder/'nodal-thermal-history').glob('*.npz')):
        with np.load(path) as f:
            ids=np.flatnonzero(abs(f['time_s']-arc_end)<1e-8)
            if len(ids):state=f['temperature_C'][ids[0]].copy();break
    if state is None:raise RuntimeError('Actual arc-end field missing')
    f=np.load(folder/'thermal-fields.npz')
    triangulation,values,materials=plane_triangles(f['x'],f['e'],state,f['material'],inp['tracks'][0]['angle_end'])
    cloud=axes[1,1].tripcolor(triangulation,values,shading='gouraud',cmap='inferno',vmin=300,vmax=2800,rasterized=True)
    axes[1,1].set(title=f'd  t={arc_end:.3f} s收弧截面实际温度',xlabel='径向r / mm',ylabel='轴向z / mm',xlim=(61,76),ylim=(102,116),aspect='equal')
    fig.colorbar(cloud,ax=axes[1,1],label='温度 / ℃',shrink=.82)
    for ax in axes.flat:ax.grid(alpha=.12)
    fig.suptitle('CI-A1首层120 mm/min修订：质量覆盖与减热输入后的连续连接\n110→80 A/1.2 s；输入与实算记录一致，冷态制造状态另行核对',fontsize=12)
    for ext in ['png','pdf','svg']:fig.savefig(OUT/f'first-layer-speed120-thermal-connection.{ext}',dpi=300)
    print(json.dumps(dict(spatial_pass=passed,errors=delta,baseline_melt_depth_mm=old['maximum_observed_QT_full_melt_depth_mm'],new_melt_depth_mm=coarse['maximum_observed_QT_full_melt_depth_mm']),indent=2))
    if not passed:raise RuntimeError('Speed revision failed its connection/spatial screen; do not broaden variants')

if __name__=='__main__':main()
