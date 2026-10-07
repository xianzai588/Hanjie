"""Evaluate continuous interface coverage from simultaneous face temperatures."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'simulation/competition-r4/results/mma-literature-three-cases'


def audit(folder):
    result=json.loads((folder/'result.json').read_text())
    if result['partial'] or result['error']:raise ValueError('Require completed physical history')
    inp=json.loads((folder/'input.json').read_text())
    f=np.load(folder/'thermal-fields.npz');c=np.load(folder/'interface-cycles.npz')
    x,e,m=f['x'],f['e'],f['material'];face=c['face_nodes'];temp=c['nodal_temperature_C'];times=c['time_s']
    xyz=x[face];area=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1)/2
    # min over all three vertices at each instant, then max over time:
    # a P1 face satisfies the threshold everywhere simultaneously.
    peak_min=temp.min(axis=2).max(axis=0)
    partial_threshold=max(inp['materials'][1]['fusion_enthalpy']['liquidus_C'],inp['materials'][3]['fusion_enthalpy']['solidus_C'])
    full_threshold=max(inp['materials'][1]['fusion_enthalpy']['liquidus_C'],inp['materials'][3]['fusion_enthalpy']['liquidus_C'])
    sr=74.98*np.arctan2(xyz[:,:,1],xyz[:,:,0]);rr=np.linalg.norm(xyz[:,:,:2],axis=2)
    edges=np.arange(-11.,11.00001,.25);centres=(edges[:-1]+edges[1:])/2
    def clipped_peak(index,lo,hi):
        poly=list(np.eye(3))
        for normal in [np.array([-np.tan(lo/74.98),1.,0.]),np.array([np.tan(hi/74.98),-1.,0.])]:
            output=[]
            for a,b in zip(poly,poly[1:]+poly[:1]):
                da=float((a@xyz[index])@normal);db=float((b@xyz[index])@normal)
                if da>=0:output.append(a)
                if (da>=0)!=(db>=0):output.append(a+(b-a)*da/(da-db))
            poly=output
            if len(poly)<3:return None
        verts=np.array(poly);pts=verts@xyz[index]
        clipped_area=sum(np.linalg.norm(np.cross(pts[j]-pts[0],pts[j+1]-pts[0]))/2 for j in range(1,len(pts)-1))
        if clipped_area<1e-8:return None
        return float((temp[:,index,:]@verts.T).min(axis=1).max())
    covered=[];minimum=[]
    for lo,hi in zip(edges[:-1],edges[1:]):
        selected=(sr.max(axis=1)>lo)&(sr.min(axis=1)<hi)
        values=[value for i in np.flatnonzero(selected) if (value:=clipped_peak(i,lo,hi)) is not None]
        covered.append(bool(values));minimum.append(min(values) if values else 0.)
    minimum=np.array(minimum);covered=np.array(covered)
    # Outside +/-9mm the actual wing narrows; do not count a tiny surviving
    # corner as a full-width connection or shift an18mm weld outside the part.
    qualified=covered&(minimum>=partial_threshold)&(centres>=-9)&(centres<=9)
    intervals=[];i=0
    while i<len(qualified):
        if not qualified[i]:i+=1;continue
        j=i
        while j+1<len(qualified) and qualified[j+1]:j+=1
        intervals.append([float(edges[i]),float(edges[j+1])]);i=j+1
    longest=max(intervals,key=lambda a:a[1]-a[0]) if intervals else None
    target=(sr.max(axis=1)>-9)&(sr.min(axis=1)<9)
    central_peaks=[value for i in np.flatnonzero(target) if (value:=clipped_peak(i,-9,9)) is not None]
    qt=m==1;coords=np.einsum('qj,ejk->eqk',f['tetra_quadrature_barycentric'],x[e[qt]])
    qt_peaks=f['peak_element_quadrature_C'][qt]
    radius=np.linalg.norm(coords[:,:,:2],axis=2);arc=74.98*np.arctan2(coords[:,:,1],coords[:,:,0])
    floor=np.where(radius<70.48,115-np.sqrt(np.maximum(0,1.5**2-(radius-70.48)**2)),113.5)
    depth=floor-coords[:,:,2]
    under=(radius>=68.98)&(radius<=74.98)&(abs(arc)<=9)&(depth>=0)
    molten=under&(qt_peaks>=1180.)
    src=np.loadtxt(folder/'source-partition-history.csv',delimiter=',',skiprows=1,ndmin=2)
    hist=np.loadtxt(folder/'thermal-history.csv',delimiter=',',skiprows=1,ndmin=2)
    # Final cooling of actual interface-centroid histories, separate from HAZ
    # capacity. An absent crossing is reported, never extrapolated.
    tc=temp.mean(axis=2);last_end=inp['tracks'][-1]['arc_duration_s']+result['stages'][-1]['start_s']
    t85=[]
    for trace in tc.T:
        crossings=[]
        for threshold in [800.,500.]:
            ids=np.flatnonzero((times[:-1]>=last_end)&(trace[:-1]>=threshold)&(trace[1:]<threshold))
            if not len(ids):break
            j=int(ids[-1]);crossings.append(float(times[j]+(times[j+1]-times[j])*(trace[j]-threshold)/(trace[j]-trace[j+1])))
        if len(crossings)==2 and crossings[1]>=crossings[0]:t85.append(crossings[1]-crossings[0])
    summary=dict(source_run=folder.name,
        fusion_criterion='max_time(min_3_P1_vertices(T)) >= max(QT liquidus, CI-A1 solidus); entire face simultaneously hot, then spatial continuity',
        partial_fusion_threshold_C=partial_threshold,full_liquid_threshold_C=full_threshold,
        total_interface_area_mm2=float(area.sum()),
        simultaneously_covered_face_area_mm2=float(area[peak_min>=partial_threshold].sum()),
        simultaneous_full_liquid_face_area_mm2=float(area[peak_min>=full_threshold].sum()),
        central18mm_min_face_peak_C=min(central_peaks),
        central18mm_every_face_partial_fusion_pass=bool(min(central_peaks)>=partial_threshold),
        continuous_intervals_mm=intervals,longest_continuous_interval_mm=longest,
        longest_continuous_length_mm=longest[1]-longest[0] if longest else 0.,
        maximum_observed_QT_full_melt_depth_mm=float(depth[molten].max()) if molten.any() else 0.,
        melt_depth_scope='ever-hot tetra quadrature points below actual curved floor in central18mm; not instantaneous dilution, PMZ width or a converged boundary',
        interface_centroid_final_t8_5_s_range=[min(t85),max(t85)] if t85 else None,
        recorded_cooling_crossing_count=len(t85),command_energy_J=float(src[:,5].sum()),
        applied_energy_J=float(hist[:,7].sum()),unintercepted_energy_J=float(src[:,7].sum()),
        maximum_step_energy_balance_error_J=float(abs(hist[:,-1]).max()),
        maximum_temperature_C=result['maximum_temperature_C'],maximum_QT_C=result['maximum_QT_C'],
        net_energy_contract_pass=bool(abs(hist[:,7].sum()-src[:,5].sum())/src[:,5].sum()<.01),
        usable_for_requested_net_energy_decision=False,
        mesh_time_convergence_verified=False,PMZ_capacity_assigned=False)
    return summary,np.stack([sr,rr],axis=-1),peak_min,centres,minimum


if __name__=='__main__':
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':9,'svg.fonttype':'none'})
    rows=[];fig,axs=plt.subplots(2,3,figsize=(12,6.7),layout='constrained')
    for k,(name,folder) in enumerate([('A',BASE/'A-r4'),('B',BASE/'B'),('C',BASE/'C')]):
        row,polys,peak,arc,minimum=audit(folder);row['case']=name;rows.append(row)
        pc=PolyCollection(polys,array=peak,cmap='inferno',clim=(1000,2000),edgecolors='none')
        axs[0,k].add_collection(pc);axs[0,k].set(xlim=(-11,11),ylim=(68.8,75.1),title=f'{name} | 连续有效长度 {row["longest_continuous_length_mm"]:.2f} mm',xlabel='s = 74.98θ / mm',ylabel='径向坐标 r / mm')
        axs[1,k].plot(arc,minimum,color='#174b70');axs[1,k].axhline(1340,color='#b23e30',ls='--',label='整面部分熔化判据1340℃')
        axs[1,k].set(xlim=(-11,11),ylim=(900,2000),xlabel='s / mm',ylabel='各截面最弱面的峰值 / ℃')
        for ax in axs[:,k]:
            ax.axvline(-9,color='#777777',ls=':');ax.axvline(9,color='#777777',ls=':')
        axs[1,k].legend(fontsize=7,loc='upper center')
    fig.colorbar(pc,ax=axs[0,:],label='整面同时达到的最高温度 / ℃',shrink=.9)
    fig.suptitle('CI-A1一翼文献热输入筛查：面内同时温度与沿程连续性\n体积热源及沉积包络为工程假设；此图不赋予PMZ强度或离散收敛资格',fontsize=11)
    dest=ROOT/'output/review/mma-source-diagnostics';dest.mkdir(exist_ok=True,parents=True)
    for ext in ['png','pdf','svg']:fig.savefig(dest/f'mma-literature-three-cases.{ext}',dpi=200)
    (BASE/'comparison.json').write_text(json.dumps(dict(cases=rows,decision='Rejected incident-energy interpretation: applied energy is about half the requested NET energy. These completed runs and their refinements cannot decide CI-A1 qualification.'),ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(rows,ensure_ascii=False,indent=2))
