"""The two final root meshes have the same actual CAD, load and boundary."""
from pathlib import Path
import json,sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent/'results'
CASES=['service-t15-affine-h2-rootlocal0.35','service-t15-affine-h2-rootlocal0.25']

def main():
    global CASES
    if '--cases' in sys.argv:
        CASES=[c for c in sys.argv[sys.argv.index('--cases')+1:] if c!='--no-plots']
    elif (OUT/'service-increment-verification.json').exists():
        CASES=json.loads((OUT/'service-increment-verification.json').read_text(encoding='utf8'))['cases']
    elif (OUT/'service-verification.json').exists():
        CASES=json.loads((OUT/'service-verification.json').read_text(encoding='utf8'))['cases']
    if len(CASES) not in (2,3):raise ValueError('服役验证要求同孔径、同实体的两级空间或三组空间/时间场')
    records=[json.loads((OUT/c/'service-area-result.json').read_text(encoding='utf8')) for c in CASES]
    inputs=[json.loads((OUT/c/'input.json').read_text(encoding='utf8')) for c in CASES]
    errors={}
    for zone in records[0]['zones']:
        values=[r['zones'][zone]['peak_service_VM_MPa'] for r in records]
        errors[zone]=max(abs(v-values[0])/max(v,values[0],1e-12) for v in values[1:])
    same_geometry=all(all(inputs[0].get(k)==i.get(k) for k in ['seat_geometry','seat_thickness_mm','initial_bore_diameter_mm','weld_mesh_mm','geometry_representation','materials']) for i in inputs[1:])
    same_load=all(records[0]['load_conditions']==r['load_conditions'] and records[0]['boundary']==r['boundary'] for r in records[1:])
    limits=records[0]['elastic_yield_screen']['allowable_MPa']
    peaks={zone:max(r['zones'][zone]['peak_service_VM_MPa'] for r in records) for zone in errors}
    strengths=all(value<=limits['QT' if zone.startswith('QT') else 'NiFe' if zone.startswith('NiFe') else 'Q235'] for zone,value in peaks.items())
    verified=bool(same_geometry and same_load and max(errors.values())<=.05 and all(i['interface_patch']['rigid_translation_and_rotation_patch_pass'] for i in inputs))
    summary=dict(cases=CASES,records=records,input_snapshots=inputs,peak_response_relative_errors=errors,
                 same_geometry_and_load=same_geometry and same_load,discretization_verified=verified,
                 worst_zone_peaks_MPa=peaks,static_service_design_pass=bool(verified and strengths),
                 scope='cold incremental service envelope; separate from welding residual stresses, PMZ fracture and fatigue qualification')
    (OUT/'service-increment-verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    # Always rebuild the aggregate from independently generated evidence.
    # Plotting must neither destroy complete evidence nor preserve a stale True.
    from aggregate_strength import aggregate
    aggregate()
    if '--no-plots' in sys.argv:
        print(json.dumps({k:v for k,v in summary.items() if k not in ('records','input_snapshots')},ensure_ascii=False,indent=2))
        return
    mesh=np.load(OUT/CASES[-1]/'mesh.npz');f=np.load(OUT/CASES[-1]/'service-area-fields.npz')
    print('field keys',list(f.keys()))
    x=mesh['x'];e=mesh['e'];m=mesh['material'];centers=x[e].mean(axis=1)
    vm=f['service_VM']
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False})
    fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout='constrained')
    # 同一(x,y)投影可能覆盖多个厚度位置；按应力升序绘制，
    # 保留内部峰值的可见性，并标注真实峰值单元。
    indices=np.flatnonzero(m==1)
    indices=indices[np.argsort(vm[indices])]
    plot=axes[0].scatter(centers[indices,0],centers[indices,1],c=vm[indices],s=1,cmap='turbo',rasterized=True)
    peak=indices[-1]
    axes[0].annotate(f"峰值 {vm[peak]:.2f} MPa",xy=centers[peak,:2],xytext=(35,-27),
                     arrowprops={'arrowstyle':'->','color':'#111827'},fontsize=9,
                     bbox={'facecolor':'white','edgecolor':'#cbd5e1','alpha':.9})
    axes[0].set_aspect('equal');axes[0].set(xlabel='x / mm',ylabel='y / mm',title=f"座体VM峰值投影（实际网格h{inputs[-1]['h_mm']:g} mm）");fig.colorbar(plot,ax=axes[0],label='MPa')
    axes[1].bar(['QT槽根','NiFe焊缝','Q235壳体'],[peaks[k] for k in ['QT_slot_root','NiFe_weld','Q235_shell']],color='#0284c7')
    axes[1].scatter([0,1,2],[limits['QT'],limits['NiFe'],limits['Q235']],color='#dc2626',marker='_',s=500,label='屈服/SF1.5')
    axes[1].set(ylabel='MPa',title='各算例最不利峰值与设计许用值');axes[1].legend()
    fig.savefig(ROOT/'docs/report/figures/r4-service-strength.png',dpi=220);plt.close(fig)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('records','input_snapshots')},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
