"""Temperature windows and a bounded tool trajectory for the actual 16 passes."""
from pathlib import Path
import sys,json,math,argparse
import numpy as np
from scipy.optimize import minimize,Bounds,LinearConstraint
from scipy.interpolate import PchipInterpolator,RegularGridInterpolator
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from hanjie.domain.following_tools import tools
from hanjie.domain.tooling_access import clearance,common_volume,translated

def crossings(t,y):
    peak=int(y.argmax());answer=[]
    for value in (490.,410.):
        candidates=np.where((np.arange(len(t)-1)>=peak)&(y[:-1]>=value)&(y[1:]<=value))[0]
        if not len(candidates):raise ValueError('surface did not traverse the complete hot-peening window')
        k=candidates[0];answer.append(np.interp(value,[y[k+1],y[k]],[t[k+1],t[k]]))
    return answer

def main(run_name='peening-timing-all-dt0125',fine_name='peening-timing-h20-dt005',output_name='peening-verification.json'):
    folder=ROOT/'simulation/competition-r4/results';run=folder/run_name
    fine=folder/fine_name
    coarse_input=json.loads((run/'input.json').read_text(encoding='utf8'))
    fine_input=json.loads((fine/'input.json').read_text(encoding='utf8'))
    # Refinement must follow the same real geometry, source and material model.
    physics_keys=('materials','fusion_enthalpy_model','material_specific_fusion_enthalpy',
                  'stage_sequence','paired_opposed_sources','travel_mm_s','net_W',
                  'net_W_per_head','source_radius_mm','source_depth_mm','source_r_mm',
                  'seat_geometry','weld_mesh_mm','copper_contact_W_m2K','copper_water_model',
                  'initial_bore_diameter_mm','fixture_thermal','fixture_thermal_coupling_policy')
    if any(coarse_input.get(k)!=fine_input.get(k) for k in physics_keys):
        raise ValueError('peening time refinement uses different physical inputs')
    meta=json.loads((run/'peening-trace-sites.json').read_text(encoding='utf8'))
    fine_meta=json.loads((fine/'peening-trace-sites.json').read_text(encoding='utf8'))
    if fine_meta['interface_arc_coordinate_mm']!=meta['interface_arc_coordinate_mm']:
        raise ValueError('peening refinement must use the same physical surface sites')
    data=np.loadtxt(run/'peening-surface-history.csv',delimiter=',',skiprows=1)
    reference=np.loadtxt(fine/'peening-surface-history.csv',delimiter=',',skiprows=1)
    x=np.array(meta['interface_arc_coordinate_mm']);N=len(x);D=np.diff(np.eye(N),axis=0);DD=np.diff(np.eye(N),n=2,axis=0)
    rows=[];differences=[];panels=[]
    for j,trace in enumerate(meta['traces']):
        surface=data[:,1+j*N:1+(j+1)*N];t=data[:,0]
        # Ignore earlier thermal cycles when assessing the cover pass.
        selection=(t>=trace['start_s'])&(t<=trace['start_s']+28.9090909091)
        tt=t[selection];yy=surface[selection]
        windows=np.array([crossings(tt,yy[:,i]) for i in range(N)])
        center=windows.mean(axis=1)
        fun=lambda a:np.sum((a-center)**2)+100*np.sum((DD@a)**2)
        grad=lambda a:2*(a-center)+200*DD.T@DD@a
        fit=minimize(fun,center,jac=grad,bounds=Bounds(windows[:,0]+.04,windows[:,1]-.04),
                     constraints=[LinearConstraint(D,.25/16.,np.inf)],method='SLSQP',options={'ftol':1e-10,'maxiter':500})
        if not fit.success:raise RuntimeError('no feasible smooth trajectory: '+fit.message)
        curve=PchipInterpolator(x,fit.x);xx=np.linspace(x[0],x[-1],3401);arrival=curve(xx)
        speed=1/curve.derivative()(xx);acceleration=-curve.derivative(2)(xx)/curve.derivative()(xx)**3
        temperature=RegularGridInterpolator((tt,x),yy)(np.c_[arrival,xx])
        arc_end=trace['start_s']+18/1.65
        torch_not_yet_lifted=arrival<=arc_end+.20
        lags=np.minimum(18,1.65*(arrival-trace['start_s']))-xx
        needed_lags=lags[torch_not_yet_lifted]
        if trace['segment']==1:
            matches=[q for q,r in enumerate(fine_meta['traces'])
                     if r['pass_index']==trace['pass_index'] and r['segment']==trace['segment']]
            if len(matches)!=1:raise ValueError('first-segment reference trace missing or ambiguous')
            q=matches[0];rf=reference[:,1+q*N:1+(q+1)*N];rt=reference[:,0]
            pick=(rt>=trace['start_s'])&(rt<=trace['start_s']+28.9090909091)
            fwin=np.array([crossings(rt[pick],rf[pick,i]) for i in range(N)])
            differences.append(float(abs(fwin-windows).max()))
            panels.append((trace,windows,fit.x))
        passed=bool(np.min(temperature)>=400 and np.max(temperature)<=500 and np.max(speed)<=18 and np.max(abs(acceleration))<=300 and needed_lags.min()>=4.5 and needed_lags.max()<=7.0)
        rows.append({**trace,'minimum_surface_C':float(temperature.min()),'maximum_surface_C':float(temperature.max()),
                     'maximum_speed_mm_s':float(speed.max()),'maximum_acceleration_mm_s2':float(abs(acceleration).max()),
                     'torch_not_lifted_lag_range_mm':[float(needed_lags.min()),float(needed_lags.max())],
                     'completed_after_arc_s':float(arrival[-1]-arc_end),'trajectory_pass':passed,
                     'site_mm':x.tolist(),'arrivals_s':fit.x.tolist(),'window_490_to_410_s':windows.tolist()})
    # Cover the entire unraised-tool range. A Lipschitz
    # displacement bound bridges sampled poses, instead of claiming only endpoints.
    geometry=[]
    for leg in (2.8,4.):
        minimum=float('inf');overlap=0.
        for lag in np.arange(4.5,7.0001,.5):
            torch,wire,peener=tools(ROOT,leg,float(lag))
            minimum=min(minimum,clearance(torch,peener),clearance(wire,peener))
            fixed_wire_clearance=clearance(torch,wire)
            overlap=max(overlap,common_volume(torch,wire),common_volume(torch,peener),common_volume(wire,peener))
        # Max peener radius <75 mm: a half-step .25 mm along R74.98
        # moves every point by <.251 mm. Unraised clearance remains >.2 mm.
        continuous_bound=min(fixed_wire_clearance,minimum-.251)
        geometry.append(dict(leg_mm=leg,sampled_clearance_mm=minimum,continuous_lower_bound_mm=continuous_bound,maximum_overlap_mm3=overlap,hot_working_pose_error_budget_mm=.10,tool_radius_growth_allowance_mm=.02,remaining_clearance_mm=continuous_bound-.12,pass_check=continuous_bound-.12>=.2 and overlap<1e-6))
    # H13 circular horizontal arm, design force limit incl. dynamic peak.
    length=73.6-3/math.sqrt(2)-45;force=200;diameter=5
    bending=32*force*length/(math.pi*diameter**3)
    deflection=force*length**3/(3*140000*(math.pi*diameter**4/64))
    result=dict(source_run=run_name,fine_reference_run=fine_name,physical_inputs_identical=True,
                material_specific_fusion_enthalpy=coarse_input.get('material_specific_fusion_enthalpy',False),
                scope='actual 15 mm geometry, source stage timings recorded by the actual thermal run; no peening benefit credited to FEA',
                traces=rows,first_segment_time_crossing_difference_s=differences,tool_geometry=geometry,
                torch_lift_certificate={'head_arm_center_below_every_tungsten_point_mm':.44,'nozzle_vs_remote_piston_lower_bound_mm':5.0,'torch_body_above_remote_piston_mm':4.9,'wire_lower_arm_xy_separating_plane_gap_mm':.50,'scope':'vertical torch+wire lift; lower arm clearance increases with z; remote actuator remains radially/axially separated'},
                tool_arm_bending_MPa=bending,tool_arm_deflection_mm=deflection,tool_arm_design_allowable_MPa=600,
                pulse_frequency_Hz=[100,100],minimum_contact_width_mm=.72,maximum_speed_mm_s=18,
                minimum_overlap_fraction=1-18/100/.72,temperature_measurement_and_command_latency_limit_s=.020,
                design_checks_pass=bool(all(r['trajectory_pass'] for r in rows) and all(g['pass_check'] for g in geometry) and bending<=600 and max(differences)<=.1))
    (folder/output_name).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.sans-serif']=['Microsoft YaHei'];plt.rcParams['axes.unicode_minus']=False
    fig,axes=plt.subplots(1,2,figsize=(10,3.5),layout='constrained')
    for ax,(tr,w,a) in zip(axes,panels):
        offset=tr['start_s'];ax.fill_between(x,w[:,0]-offset,w[:,1]-offset,color='#aedcc6',label='490→410℃冷却窗口')
        ax.plot(x,a-offset,color='#253e65',label='平滑随动轨迹');ax.axhline(18/1.65,color='#ad493c',ls='--',label='本段停弧')
        ax.set(xlabel='焊段沿程位置 / mm',ylabel='距本段起弧 / s',title='根道' if tr['pass_index']==0 else '盖面');ax.legend(fontsize=8)
    fig.savefig(ROOT/'docs/report/figures/peening-temperature-timing.png',dpi=240);plt.close(fig)
    print(json.dumps({k:v for k,v in result.items() if k!='traces'},ensure_ascii=False,indent=2))
    if not result['design_checks_pass']:raise RuntimeError('peening design gates failed')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',default='peening-timing-all-dt0125');p.add_argument('--fine',default='peening-timing-h20-dt005');p.add_argument('--output-name',default='peening-verification.json');a=p.parse_args()
    main(a.run,a.fine,a.output_name)
