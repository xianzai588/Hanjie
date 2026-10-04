"""Use identical measurement samples and separate numerical precision from tolerance margin."""
from pathlib import Path
import json,sys,argparse
import numpy as np
from scipy.interpolate import LinearNDInterpolator
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from hanjie.simulation.structural_prep import fit_position_diameter
OUT=Path(__file__).parent/'results';FIG=ROOT/'docs/report/figures'
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'],'axes.unicode_minus':False})
CASES=['8p-birthpatch-h20-dt025-s05','8p-birthpatch-h15-dt025-s05','8p-birthpatch-h20-dt0125-s025']
def section_axis_envelope(a,b,hole):
 # Retain the three extracted section centres as well as the straight cylinder
 # fit: a bowed median line must not disappear in an average fitted axis.
 origin=a.mean(axis=0)
 _,_,basis=np.linalg.svd(a-origin,full_matrices=False)
 frame=basis.T
 lb=(b-origin)@frame
 design=np.column_stack((2*lb[:,0],2*lb[:,1],np.ones(len(lb))))
 shell_center=np.linalg.lstsq(design,np.sum(lb[:,:2]**2,axis=1),rcond=None)[0][:2]
 lh=(hole-origin)@frame;lh[:,:2]-=shell_center
 centres=[]
 for section in lh.reshape(3,12,3):
  design=np.column_stack((2*section[:,0],2*section[:,1],np.ones(12)))
  centre=np.linalg.lstsq(design,np.sum(section[:,:2]**2,axis=1),rcond=None)[0][:2]
  centres.append(centre)
 centres=np.asarray(centres)
 sections=lh.reshape(3,12,3)
 diameters=np.linalg.norm(sections[:,:6,:]-sections[:,6:,:],axis=2)
 return dict(section_axis_envelope_diameter_mm=float(2*np.linalg.norm(centres,axis=1).max()),section_centres_relative_B_mm=centres.tolist(),
     sampled_bore_two_point_diameter_min_mm=float(diameters.min()),
     sampled_bore_two_point_diameter_max_mm=float(diameters.max()),
     sampled_section_diameter_spreads_mm=np.ptp(diameters,axis=1).tolist())

def measure(folder,free_shell=False):
 r=json.loads((folder/'result.json').read_text(encoding='utf8'));inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
 if free_shell:
  release=json.loads((folder/'free-release-verification.json').read_text(encoding='utf8'))
  if not release['free_shell_release_pass']:raise RuntimeError('complete shell clamp release required')
  r['cold_shell_clamp_release']=release
 f=np.load(folder/('free-release-fields.npz' if free_shell else 'fields.npz'));x=f['x'];u=f['u'];rad=np.linalg.norm(x[:,:2],axis=1)
 def sample(radius,zs,count):
  mask=abs(rad-radius)<1e-5;theta=np.arctan2(x[mask,1],x[mask,0]);coords=np.column_stack((theta,x[mask,2]));vals=u[mask]
  coords=np.vstack((coords-[2*np.pi,0],coords,coords+[2*np.pi,0]));vals=np.vstack((vals,vals,vals))
  interp=LinearNDInterpolator(coords,vals);tt=np.tile(np.arange(count)*2*np.pi/count,len(zs));zz=np.repeat(zs,count)
  du=interp(np.column_stack((tt,zz)))
  if not np.all(np.isfinite(du)):raise RuntimeError('measurement samples outside triangulated surface')
  return np.column_stack((radius*np.cos(tt),radius*np.sin(tt),zz))+du
 bottom=x[:,2]<1e-5
 angles=np.arange(24)*2*np.pi/24;axy=np.column_stack((77.5*np.cos(angles),77.5*np.sin(angles)))
 adu=LinearNDInterpolator(x[bottom,:2],u[bottom])(axy)
 if not np.all(np.isfinite(adu)):raise RuntimeError('datum A samples outside lower annulus')
 a=np.column_stack((axy,np.zeros(24)))+adu
 bore_radius=inp['initial_bore_diameter_mm']/2
 b=sample(75,[20,180],24);hole=sample(bore_radius,np.linspace(100,100+inp['seat_thickness_mm'],3),12)
 r['fit_mesh_nodes']=r['fit'];r['fit']=fit_position_diameter(a,b,hole)
 r['fit']['straight_fitted_axis_position_mm']=r['fit']['position_diameter_mm']
 r['fit'].update(section_axis_envelope(a,b,hole))
 r['fit']['position_diameter_mm']=max(r['fit']['position_diameter_mm'],r['fit']['section_axis_envelope_diameter_mm'])
 r['measurement_samples_mm']=dict(datum_A=a.tolist(),datum_B=b.tolist(),bore=hole.tolist())
 r['measurement_protocol']=f"24 datum-A annulus points at R77.5, 36 bore and 48 shell samples, identical across all runs; maximum of fitted straight axis and three extracted section-centre envelope; initial bore {inp['initial_bore_diameter_mm']:g} mm"
 bore=abs(rad-bore_radius)<1e-5;r['bore_wall_peak_C']=float(f['peak_nodal_temperature'][bore].max());r['final_time_s']=float(np.loadtxt(folder/'thermal-history.csv',delimiter=',',skiprows=1)[-1,0])
 eq=np.loadtxt(folder/'equilibrium-history.csv',delimiter=',',skiprows=1);release=eq[eq[:,4]==1];r['release_time_s']=float(release[0,0]) if len(release) else None
 r['contact_area_mm2']=inp['contact_area_mm2'];r['structural_step_s']=inp['structural_step_s']
 (folder/'measurement.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
 return r,f,inp
def error(a,b):return abs(a-b)/max(abs(a),abs(b),1e-12)
def main(cases=None):
 cases=CASES if cases is None else cases
 available=[name for name in cases if (OUT/name/'result.json').exists()]
 if len(available)<2:raise RuntimeError('need at least two completed cold runs')
 physical=[json.loads((OUT/name/'input.json').read_text(encoding='utf8')).get('material_specific_fusion_enthalpy',False) for name in available]
 records=[measure(OUT/name,free_shell=all(physical)) for name in available];rows=[z[0] for z in records]
 if len(rows)!=3:raise RuntimeError('all three final cold runs are required')
 a,b,c=rows
 spatial=error(a['fit']['position_diameter_mm'],b['fit']['position_diameter_mm'])
 same_time=a['dt_s']==b['dt_s'] and a['structural_step_s']==b['structural_step_s'] and records[0][2]['cold_structural_step_s']==records[1][2]['cold_structural_step_s']
 same_time_grid=a['h_mm']==c['h_mm'] and records[0][2]['seat_geometry']==records[2][2]['seat_geometry'] and np.array_equal(records[0][1]['x'],records[2][1]['x']) and np.array_equal(records[0][1]['e'],records[2][1]['e'])
 temporal=error(a['fit']['position_diameter_mm'],c['fit']['position_diameter_mm'])
 physics_keys=['materials','sequence','travel_mm_s','net_W','leg_mm','weld_base_z_mm',
     'seat_thickness_mm','root_leg_mm','idle_s','h_air_W_m2K','emissivity',
     'copper_contact_W_m2K','copper_water_inlet_C','fixture_cooling_removed_on_release',
     'mandrel_penalty_N_mm3','initial_bore_diameter_mm','weld_mesh_mm','annealing_C',
     'latent_heat_J_kg','source_radius_mm','source_depth_mm','source_r_mm',
     'Ni99_thin_layer_mm','Ni99_conductivity_W_mK','seat_geometry','initial_radial_preload_N',
     'stress_free_interface_birth','stress_free_birth','mechanical_interface_N_mm3','support']
 input_physics_same=all(inp[k]==records[0][2][k] for _,_,inp in records for k in physics_keys)
 additional_physics=['unilateral_pads','paired_opposed_sources','stage_sequence',
     'maximum_simultaneous_heads','net_W_per_head','arc_end_s','mechanical_event_policy',
     'material_specific_fusion_enthalpy','fusion_enthalpy_model']
 input_physics_same=input_physics_same and all(inp.get(k)==records[0][2].get(k) for _,_,inp in records for k in additional_physics+['fixture_thermal','fixture_thermal_coupling_policy'])
 input_physics_same=input_physics_same and all(r['imbalance_fraction']==a['imbalance_fraction'] and r['preheat_C']==a['preheat_C'] for r in rows)
 for _,_,inp in records:
  for k in ['copper_heat_capacity_J_K','water_lumped_design_W_K','copper_effective_area_mm2']:
   input_physics_same=input_physics_same and inp['copper_water_model'][k]==records[0][2]['copper_water_model'][k]
 numerical=all(r['released'] and r['final_max_C']<=21 and r['max_equilibrium_residual_N']<.05 and abs(r['energy_balance_relative'])<1e-5 and r['contact_area_mm2']>0 and r['seal_thermal_limits_pass'] and r['max_mandrel_reaction_N']<=5000 and inp['interface_patch']['rigid_translation_and_rotation_patch_pass'] for r,_,inp in records)
 numerical=numerical and all(r.get('cold_shell_clamp_release',{}).get('free_shell_release_pass',False) for r in rows)
 birth_verified=all((OUT/name/'birth-continuation-verification.json').exists() and json.loads((OUT/name/'birth-continuation-verification.json').read_text(encoding='utf8'))['rigid_motion_patch_pass'] for name in available)
 support_records=[];event_records=[]
 from check_carrier import evaluate as evaluate_carrier
 for name,(_,_,inp) in zip(available,records):
  folder=OUT/name;pad_file=folder/'pad-contact-audit.json';event_file=folder/'mechanical-integration-audit.json'
  support_pass=False;event_pass=False
  if inp.get('unilateral_pads') and pad_file.exists():
   pad=json.loads(pad_file.read_text(encoding='utf8'));carrier=evaluate_carrier(folder)
   (folder/'carrier-verification.json').write_text(json.dumps(carrier,ensure_ascii=False,indent=2),encoding='utf8')
   support_pass=bool(pad['analytic_geometry_contact_checks_pass'] and pad['compression_only_reactions_pass']
       and pad['maximum_pressure_MPa']<=355/1.5 and carrier['carrier_design_pass'])
   support_records.append(dict(case=name,unilateral_contact_and_carrier_pass=support_pass,
       maximum_pad_pressure_MPa=pad['maximum_pressure_MPa'],maximum_carrier_moment_N_mm=pad['maximum_carrier_moment_N_mm'],
       carrier_radial_axis_deflection_mm=carrier['total_radial_axis_deflection_mm']))
  else:support_records.append(dict(case=name,unilateral_contact_and_carrier_pass=False,reason='legacy bilateral point supports'))
  if inp.get('mechanical_event_temperature_increment_C') is not None and event_file.exists():
   event=json.loads(event_file.read_text(encoding='utf8'))
   event_pass=bool(all(v==0 for v in event['missed_above_annealing_mm3'].values()))
   event_records.append(dict(case=name,mandatory_thermal_events_pass=event_pass,**event))
  else:event_records.append(dict(case=name,mandatory_thermal_events_pass=False,reason='legacy fixed mechanical cadence'))
 support_verified=all(r['unilateral_contact_and_carrier_pass'] for r in support_records)
 events_verified=all(r['mandatory_thermal_events_pass'] for r in event_records)
 enthalpy_verified=all(inp.get('material_specific_fusion_enthalpy',False) for _,_,inp in records)
 fixture_records=[]
 from check_fixture_thermal import evaluate as evaluate_fixture_thermal
 for name,(_,_,inp) in zip(available,records):
  if inp.get('fixture_thermal'):
   if (OUT/name/'fixture-boundary-trace.npz').exists():fixture_records.append(evaluate_fixture_thermal(name))
   else:fixture_records.append(dict(source_case=name,fixture_thermal_discretization_pass=False,reason='actual fixture boundary trace absent'))
 fixture_verified=len(fixture_records)==len(records) and all(r['fixture_thermal_discretization_pass'] and r.get('support_thermal_height_budget_pass',False) for r in fixture_records)
 verified=bool(enthalpy_verified and numerical and birth_verified and support_verified and events_verified and input_physics_same and same_time and same_time_grid and spatial<=.05 and temporal<=.05)
 worst=max(r['fit']['position_diameter_mm'] for r in rows);budget=2*.014+worst+.002
 result=dict(cases=available,records=rows,spatial_comparison_cases=available[:2],temporal_comparison_cases=[available[0],available[2]],superseded_coarse_time_case='8p-affine-h20-dt05-s1',superseded_incomplete_birth_cases=['8p-affine-h20-dt025-s05','8p-affine-pardiso-h15-dt025-s05','8p-affine-pardiso-h20-dt0125-s025'],input_physics_identical=input_physics_same,spatial_response_relative_error=spatial,spatial_time_steps_identical=same_time,temporal_mesh_identical=same_time_grid,temporal_response_relative_error=temporal,relative_precision_limit=.05,numerical_equilibrium_and_cold_release_pass=numerical,birth_rigid_motion_patch_pass=birth_verified,discretization_verified=verified,thermal_position_worst_mm=worst,position_budget_mm=budget,design_limit_mm=.05,position_design_pass=bool(verified and budget<=.05),metallurgy_scope='full-part model supports residual shape under declared source assumptions; molten pool and PMZ use independent composition and qualification controls, not node-peak proof')
 result.update(material_specific_fusion_enthalpy_pass=enthalpy_verified,unilateral_support_and_carrier_pass=support_verified,support_records=support_records,mandatory_thermal_events_pass=events_verified,event_records=event_records,
    fixture_thermal_model_pass=fixture_verified,fixture_thermal_records=fixture_records)
 result['position_design_pass']=result['position_design_pass'] and fixture_verified
 from check_bore_size import evaluate as evaluate_bore_size
 bore_size=evaluate_bore_size(result)
 result['bore_size_design_pass']=bore_size['bore_size_design_pass']
 result['bore_size_verification']=bore_size
 (OUT/'bore-size-verification.json').write_text(json.dumps(bore_size,ensure_ascii=False,indent=2),encoding='utf8')
 (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 FIG.mkdir(exist_ok=True,parents=True)
 fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
 positions=[r['fit']['position_diameter_mm']*1000 for r in rows]
 axes[0].bar([f"h{r['h_mm']:g} / Δt{r['dt_s']:g}" for r in rows],positions,color=['#0284c7','#059669','#7c3aed'])
 for i,value in enumerate(positions):axes[0].text(i,value,f'{value:.3f}',ha='center',va='bottom',fontsize=9)
 axes[0].set(ylabel='位置度直径 μm',title='相同36/48测点的冷态位置度\n直轴与截面中心包络取大');axes[0].set_ylim(0,max(positions)*1.15)
 vals=[4,4,4,13,1,2,worst*1000,2];labels=['基准','工装轴','定心','夹紧','释放','支点','热残余','测量U']
 axes[1].barh(labels,vals,color='#0284c7');axes[1].set(xlabel='直径口径 μm',title=f'设计合成 {budget*1000:.2f} μm\n空间差 {spatial*100:.2f}% / 时间差 {temporal*100:.2f}%')
 fig.savefig(FIG/'r4-mesh-budget.png',dpi=220);plt.close(fig)
 name=available[-1];r,f,inp=records[-1];hist=np.loadtxt(OUT/name/'thermal-history.csv',delimiter=',',skiprows=1);eq=np.loadtxt(OUT/name/'equilibrium-history.csv',delimiter=',',skiprows=1)
 fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained');axes[0].plot(hist[:,0],hist[:,1],label='最高节点');axes[0].plot(hist[:,0],hist[:,2],label='QT最高单元均温');axes[0].set(xlabel='t / s',ylabel='℃',title='全件实际热历程');axes[0].plot(hist[:,0],hist[:,7],label='铜环计算平均温度');axes[0].plot(hist[:,0],hist[:,8],label='钢壳密封带最高温');axes[0].legend();axes[1].plot(eq[:,0],eq[:,3],label='实际接触反力');axes[1].axhline(5000,color='#dc2626',ls='--',label='机械止挡设计容量');axes[1].set(xlabel='t / s',ylabel='N',title='接触面积有效；热反力按计算值');axes[1].legend();fig.savefig(FIG/'r4-thermal-contact.png',dpi=220);plt.close(fig)
 x=f['x'];e=f['e'];m=f['material'];c=x[e].mean(axis=1);s=f['stress'];pv=np.outer([1,1,1,0,0,0],[1,1,1,0,0,0])/3;vm=np.sqrt(1.5*np.sum((s-s@pv)**2,axis=1));disp=np.linalg.norm(f['u'][e].mean(axis=1),axis=1)*1000
 fig,axes=plt.subplots(1,2,figsize=(11,5),layout='constrained');mask=m!=0
 for ax,val,title,unit in zip(axes,[disp,vm],['卸夹位移','卸夹残余应力'],['μm','MPa']):
  indices=np.flatnonzero(mask);indices=indices[np.argsort(val[indices])]
  sc=ax.scatter(c[indices,0],c[indices,1],c=val[indices],s=2,cmap='turbo',rasterized=True);ax.set_aspect('equal');ax.set(xlabel='x / mm',ylabel='y / mm',title=title+'（单元峰值投影）');fig.colorbar(sc,ax=ax,label=unit)
 fig.savefig(FIG/'r4-residual-fields.png',dpi=220);plt.close(fig)
 print(json.dumps({k:v for k,v in result.items() if k!='records'},ensure_ascii=False,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--cases',nargs=3);a=p.parse_args()
 main(a.cases)
