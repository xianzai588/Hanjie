"""Summarize accepted current-ring calculations and render their actual fields."""
import json
import csv
import math
from pathlib import Path
import numpy as np
import yaml
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];RES=HERE/'results';FIG=HERE/'figures'
font_manager.fontManager.addfont(str(ROOT/'assets/fonts/NotoSansSC-Regular.ttf'))
plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(ROOT/'assets/fonts/NotoSansSC-Regular.ttf')).get_name(),'axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
BLUE='#295c78';AMBER='#b16d3e';GREEN='#557768'

def main():
    FIG.mkdir(exist_ok=True)
    cold=json.loads((RES/'coarse/cold-response.json').read_text())
    version=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text())['version']
    if cold['process_version']!=version or not cold['mesh']['actual_faceted_gap_audit']['unwelded_gap_geometry_verified']:
        raise RuntimeError('cold response is stale or its actual faceted fit gap failed; do not publish this assessment')
    fullpath=RES/'coarse-dt1-root0-r75/thermal-result.json'
    thermal=json.loads(fullpath.read_text()) if fullpath.exists() else None
    refpath=RES/'coarse-dt0.5-stop12.1212-root0-r75/thermal-result.json'
    reference=json.loads(refpath.read_text()) if refpath.exists() else None
    if any(q is not None and q['process_version']!=version for q in (thermal,reference)):
        raise RuntimeError('thermal results and current process identity differ')
    for q in (thermal,reference):
        if q is not None and not q.get('current_evidence_usable',True):
            raise RuntimeError('rejected diagnostic thermal result cannot be adopted as current evidence')
        if q is not None and (q['declared_source']['root_z_mm']!=115. or q['declared_source']['radial_mm']!=75.):
            raise RuntimeError('current report requires actual root-aim source, not legacy offset diagnosis')
    curves=cold['responses'];names=list(curves)
    labels=['平均焊缝收缩','焊缝一阶不对称','焊缝二阶不对称','焊缝单段差异','预制留层一阶变化','预制留层单窗变化']
    fig,axes=plt.subplots(1,2,figsize=(11.4,4.3),layout='constrained')
    yy=np.arange(len(names));axes[0].barh(yy,[curves[n]['position_diameter_um'] for n in names],color=BLUE,height=.6)
    axes[0].set_yticks(yy,labels);axes[0].invert_yaxis();axes[0].set_xlabel('卸夹孔轴位置度响应 / μm');axes[0].set_title('A　单位固有应变输入100 με')
    for i,n in enumerate(names):axes[0].text(curves[n]['position_diameter_um']+.004,i,f"{curves[n]['position_diameter_um']:.3f}",va='center',fontsize=9)
    lo=np.array([curves[n]['minimum_diameter_change_um'] for n in names]);hi=np.array([curves[n]['maximum_diameter_change_um'] for n in names])
    axes[1].barh(yy,hi-lo,left=lo,height=.6,color=AMBER);axes[1].axvline(0,color='#777777',linewidth=.8)
    axes[1].set_yticks(yy,labels);axes[1].invert_yaxis();axes[1].set_xlabel('采样孔径变化区间 / μm');axes[1].set_title('B　平均尺寸与失圆同时评价')
    fig.suptitle('18 mm有效支承、3.5 mm焊脚的冷态条件响应',fontsize=14)
    fig.savefig(FIG/'ring-cold-response.png',dpi=300);plt.close(fig)
    # Show stress alongside the response: high mathematical strain windows do
    # not become a usable process window when the elastic domain is exceeded.
    rows=cold['conditional_scans'];line=[r for r in rows if r['first_harmonic_final_shrink_microstrain']==0 and r['first_harmonic_precoat_redistribution_microstrain']==0]
    fig,axes=plt.subplots(1,2,figsize=(10.6,4.1),layout='constrained')
    xx=[r['mean_final_shrink_microstrain'] for r in line]
    axes[0].plot(xx,[r['minimum_diameter_change_um'] for r in line],color=BLUE,marker='o',label='最小孔径变化')
    axes[0].plot(xx,[r['maximum_diameter_change_um'] for r in line],color=AMBER,marker='s',label='最大孔径变化')
    axes[0].set_xlabel('平均最终收缩输入 / με');axes[0].set_ylabel('采样孔径变化 / μm');axes[0].legend(frameon=False);axes[0].set_title('A　孔径窗口取决于平均收缩')
    axes[1].plot(xx,[r['combined_maximum_von_Mises_MPa'] for r in line],color=GREEN,marker='o');axes[1].set_xlabel('平均最终收缩输入 / με');axes[1].set_ylabel('线弹性局部最大等效应力 / MPa');axes[1].set_title('B　大幅度输入须校核材料适用域')
    fig.suptitle('数学响应与材料可行性分别登记；不以孔轴很小代替整体合格',fontsize=12)
    fig.savefig(FIG/'ring-response-domain.png',dpi=300);plt.close(fig)
    # Plot a declared conditional FE field, with its input amplitudes printed on
    # the figure.  It is not a manufacturing plastic-state prediction.
    source=ROOT/cold['mesh']['source_snapshot'];support=np.load(source/'mesh.npz');px=support['points'];pe=support['tetrahedra'];pm=support['material_ids']
    fields=np.load(RES/'coarse/cold-response-fields.npz');u=fields['symmetric_final_shrink']+.25*fields['first_harmonic_final_shrink']+.25*fields['first_harmonic_precoat_redistribution']
    radius=np.linalg.norm(px[:,:2],axis=1);radial=np.sum(u[:,:2]*px[:,:2],axis=1)/np.maximum(radius,1e-30)*1000
    fig,axes=plt.subplots(1,2,figsize=(10.8,4.6),layout='constrained')
    top=np.flatnonzero((abs(px[:,2]-115)<1e-5)&(radius<=75.));col=axes[0].scatter(px[top,0],px[top,1],c=radial[top],s=3,cmap='coolwarm',rasterized=True)
    axes[0].set(aspect='equal',xlabel='x / mm',ylabel='y / mm',title='A　座体顶面真实FE位移场');fig.colorbar(col,ax=axes[0],label='径向位移 / μm',fraction=.046)
    bore=np.flatnonzero(abs(radius-20)<1e-5);angle=np.arctan2(px[bore,1],px[bore,0])*180/np.pi
    col=axes[1].scatter(angle,px[bore,2],c=radial[bore],s=6,cmap='coolwarm',rasterized=True)
    axes[1].set(xlabel='孔壁周向 / °',ylabel='z / mm',title='B　孔壁径向位移与失圆分布');fig.colorbar(col,ax=axes[1],label='径向位移 / μm',fraction=.046)
    fig.suptitle('条件组合：最终平均100 με + 最终一阶25 με + 预制一阶变化25 με',fontsize=12);fig.savefig(FIG/'ring-cold-displacement.png',dpi=300);plt.close(fig)
    medium_path=RES/'medium/cold-response.json';comparison={}
    if medium_path.exists():
        medium=json.loads(medium_path.read_text())
        if medium['process_version']!=version or medium['elastic_inputs']!=cold['elastic_inputs'] or not medium['mesh']['actual_faceted_gap_audit']['unwelded_gap_geometry_verified']:
            raise RuntimeError('cold medium comparison has mismatched process/material or invalid fit gap')
        for name,v in medium['responses'].items():
            comparison[name]={}
            for metric in ('position_diameter_um','minimum_diameter_change_um','maximum_diameter_change_um','maximum_von_Mises_MPa'):
                a=curves[name][metric];b=v[metric]
                comparison[name][metric]=dict(coarse=a,medium=b,absolute_difference=abs(a-b),relative_difference=abs(a-b)/max(abs(a),abs(b),1e-12))
    mode_rows=[]
    for name,v in curves.items():
        row=dict(mode=name,amplitude_microstrain=100,position_diameter_um=v['position_diameter_um'],minimum_diameter_change_um=v['minimum_diameter_change_um'],maximum_diameter_change_um=v['maximum_diameter_change_um'],raw_maximum_von_Mises_MPa=v['maximum_von_Mises_MPa'])
        if name in comparison:
            for metric,q in comparison[name].items():
                row['medium_'+metric]=q['medium'];row[metric+'_relative_difference']=q['relative_difference']
        mode_rows.append(row)
    with (RES/'cold-mode-summary.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in mode_rows for k in r)));writer.writeheader();writer.writerows(mode_rows)
    state=dict(process_version=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text())['version'],physical_object='complete_ring',
      actual_path_320mm=True,method_scope='current3D thermal enthalpy FE plus independent classical cold eigenstrain kernels; no coupled complete precoat/manufacturing plastic-state solution',
      thermal_model='conforming shared nodes at material interfaces; active-face exterior radiation/convection only; true unwelded fit gap',
      main_source_target=dict(r_mm=75.,root_z_mm=115.,root_model_offset_from_seat_mm=.02,cap_z_mm=117.,cap_source_role='engineering effective source estimate requiring macrosection calibration; not robot TCP/standoff'),
      thermal_result=thermal,first_arc_time_refinement=reference,thermal_cycle_completed=bool(thermal and thermal['complete_final_thermal_cycle']),
      cold_response_summary={n:{k:curves[n][k] for k in ('input_microstrain','position_diameter_um','minimum_diameter_change_um','maximum_diameter_change_um','maximum_von_Mises_MPa','von_Mises_by_material_MPa','free_residual_N','gauge_reaction_N')} for n in names},
      cold_space_comparison=comparison,cold_space_scope='safe current coarse6/.9mm and audited retained medium4.5/.65mm;3 key100microstrain modes. Near-zero symmetry axis values and local stress are reported separately; no blanket convergence or full manufacturing qualification is claimed.',
      cold_support=dict(effective_segment_length_mm=18.,segment_count=8,fillet_leg_mm=3.5,release='all tooling removed; six negligible-reaction coordinate-gauge DOFs only'),
      precoat_residual_state='complete residual stress/plastic field not imported; nonzero redistribution kernels are independent conditional inputs, not state inheritance',
      response_window='conditional-window.csv contains mathematical cold-response/diameter windows and combined per-material elastic stresses; deposited-layer yield/fusion capacity is not assigned',
      current_fusion_verified=False,residual_position_verified=False,bore_size_verified=False,full_manufacturing_chain_passed=False,production_release=False,
      stale_diagnostic_outputs='diagnostic-static-interface/* are rejected for early cap-interface area and duplicate internal-face environment loss; never adopted as current engineering evidence',
      outputs=dict(cold_csv='results/coarse/conditional-window.csv',thermal_csv=str(fullpath.parent.relative_to(HERE)/'thermal-history.csv'),figures=['figures/ring-cold-response.png','figures/ring-response-domain.png','figures/ring-cold-displacement.png']))
    state['example_conditional_state']=next(r for r in rows if r['mean_final_shrink_microstrain']==100 and r['first_harmonic_final_shrink_microstrain']==25 and r['first_harmonic_precoat_redistribution_microstrain']==25)
    if thermal:
        with (RES/'arc-start-temperature.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['process_version','pass_number','segment','start_s','end_s','Ni99_window_max_C','control_minimum_C','control_maximum_C','temperature_permission_pass'])
            writer.writeheader()
            for row in thermal['start_records']:
                writer.writerow(dict(process_version=version,pass_number=row['pass']+1,segment=row['segment'],start_s=row['start_s'],end_s=row['end_s'],Ni99_window_max_C=row['second_layer_current_max_C'],control_minimum_C=row['control_minimum_C'],control_maximum_C=row['control_maximum_C'],temperature_permission_pass=row['temperature_permission_pass']))
        state['outputs']['arc_start_csv']='results/arc-start-temperature.csv'
        state['start_temperature_permissions']=dict(first_pass_maximum_C=max(r['second_layer_current_max_C'] for r in thermal['start_records'] if r['pass']==0),second_pass_maximum_C=max(r['second_layer_current_max_C'] for r in thermal['start_records'] if r['pass']==1),permission_pass=thermal['start_temperature_permissions_pass'],scope=thermal['start_permission_scope'])
        state['current_source_melting_screen']={str(mid):dict(peak_C=thermal['material_peak_C'][str(mid)],declared_solidus_C=thermal['material_inputs'][mid-1]['fusion_enthalpy']['solidus_C'],peak_covers_solidus=thermal['material_peak_C'][str(mid)]>=thermal['material_inputs'][mid-1]['fusion_enthalpy']['solidus_C']) for mid in (2,4,5)}
        state['melting_screen_scope']='temperature coverage under the declared uncalibrated Gaussian source; not continuous interface fusion, melt-transport prediction or evidence of physical300J/mm process failure'
        data=np.load(fullpath.parent/'thermal-fields.npz');mesh=np.load(RES/'coarse/mesh.npz');x,e,m=mesh['x'],mesh['e'],mesh['material'];history=np.loadtxt(fullpath.parent/'thermal-history.csv',delimiter=',',skiprows=1)
        fig,axes=plt.subplots(1,2,figsize=(11.2,4.5),layout='constrained')
        axes[0].plot(history[:,0],history[:,2],color=AMBER,label='工件场最大温度');axes[0].plot(history[:,0],history[:,4],color=BLUE,label='铜环集总温度');axes[0].axhline(100,color='#888888',linestyle='--',linewidth=.8,label='100℃参考；局部起弧门另列')
        axes[0].axvline(thermal['tooling_exit']['time_s'],color=GREEN,linestyle=':',linewidth=.8,label='满足停弧≥120 s与温度双门退铜')
        axes[0].set_xlabel('实际时间 / s');axes[0].set_ylabel('温度 / ℃');axes[0].legend(frameon=False,fontsize=8);axes[0].set_title('A　两道八段及冷却热史')
        nodes=np.unique(e[m!=2]);sel=nodes[abs(x[nodes,2]-115)<1e-5];col=axes[1].scatter(x[sel,0],x[sel,1],c=data['peak_temperature'][sel],s=3,cmap='inferno',rasterized=True)
        axes[1].set_aspect('equal');axes[1].set_xlabel('x / mm');axes[1].set_ylabel('y / mm');axes[1].set_title('B　座体顶面计算峰温分布');fig.colorbar(col,ax=axes[1],label='峰温 / ℃',fraction=.046)
        fig.suptitle('20 mm实际行程、96 kJ输入的圆环最终热过程设计情景',fontsize=13);fig.savefig(FIG/'ring-final-thermal.png',dpi=300);plt.close(fig)
        state['outputs']['figures'].append('figures/ring-final-thermal.png')
        # Compare the same first20mm and6000J, not full-cycle maxima against a
        # first-segment maximum. Report failed precision without threshold edits.
        if reference:
            primary=history[history[:,0]<=20/1.65+1e-7];a=float(primary[:,2].max());b=reference['max_C']
            state['first_arc_peak_time_relative_difference']=abs(a-b)/max(abs(a),abs(b))
            state['first_arc_peak_time_precision_5pct']=state['first_arc_peak_time_relative_difference']<=.05
    (RES/'assessment.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
    print(json.dumps(dict(process_version=state['process_version'],thermal_cycle_completed=state['thermal_cycle_completed'],production_release=False,assessment='results/assessment.json'),ensure_ascii=False))
if __name__=='__main__':main()
