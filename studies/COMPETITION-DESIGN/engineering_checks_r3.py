"""Independent weld-group load histories, robust process, tooling and resource checks."""
from pathlib import Path
import json, math
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent/'results'
rows=[]
def _service_stiffness_summary():
 """Wave 2: 服务载荷下开槽座体刚度摘要，完整场数据见 structural-v4 结果文件。"""
 path=ROOT/'simulation/structural-v4/results/service-stiffness-8p.json'
 if not path.exists():return None
 full=json.loads(path.read_text(encoding='utf8'))
 by_id={m['model_id']:m for m in full['models']}
 slotted=by_id['8P-FAIR_B'];cont=by_id['Continuous']
 return dict(source='simulation/structural-v4/results/service-stiffness-8p.json ('+full['version']+')',
  method=full['method'],boundaries=full['boundaries'],
  geometry_scope='historical original 12 mm FAIR_B seat-only comparison; not the current 15 mm R2 full assembly',
  accepted_current_design_evidence=False,
  axis_offset_diameter_mm_at_1000N=slotted['worst_axis_offset_diameter_mm'],
  bore_ovalization_amplitude_mm_at_1000N=slotted['worst_bore_ovalization_amplitude_mm'],
  start_stop_Fr1500N=slotted['service_scaling_linear']['start_stop_amp'],
  continuous_condition_Fr500N=slotted['service_scaling_linear']['continuous_amp'],
  ratio_8p_vs_continuous=full['comparison'],
  interpretation='Historical geometry and seat-only boundary comparison; preserve its relative trend, '
   'but use competition-r4/results/service-verification.json for current 15 mm assembly strength and stiffness')
# Design spectra, explicitly proposed engineering conditions, not measured compressor data.
cycles=[dict(name='continuous',cycles=1e8,Fr_amp=500,Fa_mean=2000,Fa_amp=200,M_amp=25000),
 dict(name='start_stop',cycles=1e4,Fr_amp=1500,Fa_mean=2500,Fa_amp=1000,M_amp=75000)]
for n in (6,8):
 r=74.98;L=n*18;a=3.5/math.sqrt(2);A=a*L;I=a*L*r*r/2
 static_tau=math.hypot(5000,5000)/A;static_sigma=250000*r/I
 static_vm=math.sqrt(static_sigma**2+3*static_tau**2)
 fatigue=[];damage=0.
 for b in cycles:
  ds=2*b['M_amp']*r/I;dt=2*math.hypot(b['Fr_amp'],b['Fa_amp'])/A
  # Equivalent RANGE calculated from synchronized proportional alternating components.
  dr=math.sqrt(ds*ds+3*dt*dt)
  # Design endurance target, no claim of an IIW classified NiFe/QT detail.
  life=2e6*(30/dr)**3;damage+=b['cycles']/life
  fatigue.append({**b,'normal_range_MPa':ds,'shear_range_MPa':dt,'equivalent_range_MPa':dr,'life_at_design_curve_cycles':life,'damage':b['cycles']/life})
 rows.append(dict(n=n,layout=f'{n}P-FAIR_B',length_mm=L,throat_mm=a,area_mm2=A,second_moment_mm4=I,static_equivalent_MPa=static_vm,
 static_allowable_MPa=60,static_margin=60/static_vm,fatigue=fatigue,miner_damage=damage,
 fatigue_curve=dict(reference_range_MPa=30,reference_cycles=2e6,slope=3,basis='proposed qualification target, not a published FAT class for NiFe/QT',qualification_required=True),
 heat_kJ=18*n*2*.300,arc_s=18*n*2/1.65))
# Full-circumference comparison layout (Wave 2): same two-pass legs, no weld ends.
r=74.98;L=2*math.pi*r;a=3.5/math.sqrt(2);A=a*L;I=a*L*r*r/2
static_tau=math.hypot(5000,5000)/A;static_sigma=250000*r/I
static_vm=math.sqrt(static_sigma**2+3*static_tau**2)
fatigue=[];damage=0.
for b in cycles:
 ds=2*b['M_amp']*r/I;dt=2*math.hypot(b['Fr_amp'],b['Fa_amp'])/A
 dr=math.sqrt(ds*ds+3*dt*dt)
 life=2e6*(30/dr)**3;damage+=b['cycles']/life
 fatigue.append({**b,'normal_range_MPa':ds,'shear_range_MPa':dt,'equivalent_range_MPa':dr,'life_at_design_curve_cycles':life,'damage':b['cycles']/life})
continuous_damage=damage
rows.append(dict(n=None,layout='Continuous',length_mm=round(L,2),throat_mm=a,area_mm2=A,second_moment_mm4=I,static_equivalent_MPa=static_vm,
 static_allowable_MPa=60,static_margin=60/static_vm,fatigue=fatigue,miner_damage=damage,
 fatigue_curve=dict(reference_range_MPa=30,reference_cycles=2e6,slope=3,basis='same assumed qualification curve for nominal stress-range comparison; local end/toe/root effects require separate verification',qualification_required=True),
 heat_kJ=L*2*.300,arc_s=L*2/1.65,
 role='qualification comparison for weld layout and service stiffness; metallurgy uses the same independently assessed Ni99 transition; '
      'its weld thermal distortion has no FE evidence and must not inherit the 8P 31.34 um synthesis'))
# Slotted finger beam conservatively all six fingers carry radial preload.
E=200000.;w=19.;th=.8;leng=30.;arm=115.4-107.5;I=w*th**3/12
# The backed terminal block transmits the free setting force below the neck.
# Include its rigid arm in both compliance and neck-root moment.
k=6*E*I/(leng**3/3+arm*leng**2+arm**2*leng)
u=(40.025-39.94)/2;F=k*u;rootstress=6*(F/6)*(leng+arm)/(w*th**2)
tools=dict(finger_radial_stiffness_N_mm=k,max_free_expand_radial_mm=u,elastic_expand_N=F,
 finger_root_stress_MPa=rootstress,preload_N=100,radial_backstop_capacity_N=5000,
 shaft_area_mm2=math.pi*(36**2-24**2)/4,thermal_reaction_separate_from_preload=True)
tools['backstop_average_axial_MPa']=5000/tools['shaft_area_mm2']
tools['cone_half_angle_deg']=10
tools['cone_friction_assumed']=.20
tools['axial_drive_N_at_radial_5000N']=5000*(math.tan(math.radians(10))+.20)/(1-.20*math.tan(math.radians(10)))
tools['derived_shaft_axial_stress_MPa']=tools['axial_drive_N_at_radial_5000N']/tools['shaft_area_mm2']
tools['shaft_design_axial_capacity_N']=5000
tools['three_pad_average_pressure_MPa_at_500N']=500/(3*math.pi*4**2)
tools['terminal_block_rigid_arm_mm']=arm
tools['locked_band_length_mm']=14.6
tools['locked_compliance_source']='simulation/competition-r4/results/mandrel-compliance-verification.json'
tools['thermal_load_path']='full-band mating cone, annular stem and positive axial shoulder; M12 rod sets and returns only'
from seal_design import evaluate as seal_evaluate
jet_area=12*math.pi*.5**2
clean=seal_evaluate()
argon_density=101325/(208.13*293.15)
jet_velocity=[q*1e6/60/jet_area/1000 for q in (10,15)]
jet_pressure=[argon_density/2*(jet_velocity[0]/.9)**2,argon_density/2*(jet_velocity[1]/.5)**2]
clean.update(cavity_pressure_basis='open upper mouth, approximately atmospheric; no whole-cavity positive-pressure barrier credited',
 curtain_manifold_pressure_target_Pa=[250,2800],argon_density_at_20C_kg_m3=argon_density,
 curtain_orifice_discharge_coefficient_design_range=[.5,.9],curtain_orifice_pressure_estimate_Pa=jet_pressure,
 open_mouth_5Pa_flow_estimate_L_min=.6*math.pi*.075**2*math.sqrt(2*5/argon_density)*60000,
 makeup_Ar_L_min=[0,12],
 worst_required_makeup_Ar_L_min=28-8-10+.5,
 gas_balance_rule='Q_makeup=max(0,Q_exhaust-Q_shield-Q_curtain+0.5); flow balance limits air entrainment at the open mouth; independently interlock actual curtain flow and manifold pressure',
 nozzle_area_mm2=jet_area,jet_velocity_at_10_15L_min_m_s=jet_velocity,
 full_bore_average_velocity_m_s=[q*1e6/60/(math.pi*75**2)/1000 for q in (10,15)],
 coolant_capacity_W_at_10K=.6/60*4180*10,
 function='mechanical collection and captured static seal block debris; jets assist transport; seal and copper temperature interlocks are independent',
 inspection_design=dict(card='HJ-Q-02',scope='process acceptance goals, not measured cleanliness or a product-standard limit',
     membrane_pore_um=1,optical_minimum_particle_um=5,net_mass_plus_uncertainty_limit_mg=.50,
     method_quantification_limit_mg=.10,blank_mass_limit_mg=.05,
     metal_or_hard_particle_reject_from_um=5,other_particle_reject_from_um=25,fibre_length_reject_from_um=100,
     weld_slag_spatter_machining_chips='reject whenever identified, regardless of size',
     initial_rinse_rounds=3,initial_liquid_L_per_round=.5,final_round_fraction_limit=.1,
     qualification_recovery_range=[.90,1.10]))
process=[]
for layout,n,passes,heads in [('8P-FAIR_B',8,2,1),('6P-FAIR_B',6,2,1),('6P-legacy-fourpass',6,4,1),('8P-opposed-candidate',8,2,2)]:
 arc=18*n/1.65*passes;stages=n*passes/heads;tool=stages*18;assembly=120;qc=120
 station=arc/heads+tool
 process.append(dict(layout=layout,segments=n,segment_length_mm=18,segment_operations=n*passes,passes=passes,
 maximum_simultaneous_heads=heads,stage_count=stages,arc_s=arc,elapsed_arc_s=arc/heads,
 peen_clean_transfer_s=tool,assembly_s=assembly,inspection_s=qc,
 welded_station_work_s=station,serial_before_cooling_s=station+assembly+qc,
 Ni99_precoat_arc_s=144,Ni99_precoat_single_head_minimum_station_s=432,
 Ni99_precoat_stations_to_match_weld_interval=math.ceil(432/station),
 Ni99_delayed_PT_minimum_h=24,shift_design_hours=8,
 Ni99_minimum_one_shift_delay_inventory_parts=math.ceil(8*3600/station),
 total_precoat_and_joining_aggregate_arc_s=144+arc,
 PT_elapsed_range_s=[1980,4080],PT_waiting_positions=math.ceil(4080/station),
 UT_station_time_s=600,UT_parallel_stations=math.ceil(600/station),
 CMM_station_time_s=120,CMM_parallel_stations=math.ceil(120/station),
 NDT_total_operator_work_s=1200,NDT_operator_equivalents=math.ceil(1200/station),
 cleanliness_inspection_elapsed_s=1800,cleanliness_inspection_operator_work_s=480,
 cleanliness_parallel_positions=math.ceil(1800/station),
 inspection_total_operator_work_s=1680,inspection_operator_equivalents=math.ceil(1680/station),
 shielding_Ar_per_head_L_min=[8,12],shielding_Ar_total_L_min=[8*heads,12*heads],
 independent_torch_and_wire_axes=heads,independent_peening_axes=heads,
 power_source_gross_nominal_W_per_head=900,
 role='candidate until full cold release and mesh/time checks pass' if heads==2 else 'single-head resource comparison',
 actual_cooling_s='read full-part thermal history; fixture remains occupied until release temperature',
 pipeline='precoat 432 s minimum excludes temperature waiting and separate 24 h delayed PT; precoat capacity and stock must match the chosen joining interval; dedicated cooling pallets required'))
# First-order reciprocating-compressor load derivation, ported from origin/main
# studies/LOAD-ESTIMATE (LOAD-ESTIMATE-4). Its inputs remain engineering assumptions,
# so the outputs are a reference point, not a measured load spectrum.
di=dict(eccentric_rotating_mass_kg=0.8,orbit_eccentricity_m=0.02,speed_rpm=3000.0,
 effective_pressure_diameter_m=0.04,pressure_difference_pa=1500000.0,bearing_to_weld_plane_m=0.07,pressure_centroid_offset_m=0.01)
omega=2*math.pi*di['speed_rpm']/60
Fi=di['eccentric_rotating_mass_kg']*di['orbit_eccentricity_m']*omega**2
Fg=math.pi*di['effective_pressure_diameter_m']**2*di['pressure_difference_pa']/4
M=Fi*di['bearing_to_weld_plane_m']+Fg*di['pressure_centroid_offset_m']  # N·m
M_mm=M*1000.0  # N·mm, same unit as the spectra and the 250000 N·mm design reference
derivation=dict(
 basis='designer-selected eccentric rotating-mass and effective gas-pressure envelope; no measured machine spectrum',
 inputs=di,
 formulas=dict(omega='2*pi*n/60',inertial_force='Fi=m*r*omega^2',
  gas_force='Fg=pi*D^2*delta_p/4',tipover_moment='M=Fi*L+Fg*e_p'),
 not_modelled=['actual scroll orbit geometry','chamber pressure vs orbit angle','counterweight and bearing load sharing'],
 outputs=dict(inertial_force_N=round(Fi,1),gas_force_N=round(Fg,1),tipover_moment_N_mm=round(M_mm,0),
  design_reference_loads=dict(radial_N=5000.0,axial_N=5000.0,moment_N_mm=250000.0,
   note='designer-selected screening basis; already used by layout_checks static columns and the 5000 N tooling backstop'),
  relation_to_spectra=dict(M_ratio_continuous=round(25000/M_mm,2),M_ratio_start_stop=round(75000/M_mm,2),
   Fr_ratio_continuous=round(500/Fi,2),Fr_ratio_start_stop=round(1500/Fi,2),
   note='proposed fatigue spectra sit below the first-order derivation in the moment channel '
        '(0.19~0.58x); Miner damage is therefore a same-spectrum relative comparison between 6P '
        'and 8P, not an absolute life claim; damage scales with the cube of stress range if loads move up')))
for row in rows:
 row['required_reference_range_MPa_at_2e6']=30*row['miner_damage']**(1/3)
 row['fatigue_decision_role']='same-spectrum qualification demand; not a measured life or a candidate elimination gate'
result=dict(load_basis='proposed screening spectra for relative route comparison; official problem gives '
 'no measured spectrum, static columns use designer-selected 5000 N reference loads, first-order derivation in load_derivation',
 load_spectrum=cycles,load_derivation=derivation,
 layout_checks=rows,tooling=tools,cleanliness=clean,cycle_resource=process,
 continuous_comparison=dict(
  continuous_miner_damage=round(continuous_damage,6),
  ratio_to_8P=round(continuous_damage/rows[1]['miner_damage'],4),
  ratio_to_6P=round(continuous_damage/rows[0]['miner_damage'],4),
  heat_ratio_vs_8P=round(rows[2]['heat_kJ']/rows[1]['heat_kJ'],2),
  arc_ratio_vs_8P=round(rows[2]['arc_s']/rows[1]['arc_s'],2),
  note='continuous weld has lower nominal calculated damage on the same assumed spectra; '
       'its cost is 3.27x heat and arc time, and its weld thermal distortion has no FE evidence, '
       'so it serves as a weld-layout qualification comparison, not a remedy for metallurgy' ),
 service_stiffness=_service_stiffness_summary(),
 method_selection=dict(
  comparison_basis='method capabilities and conditions of use; no arbitrary weighted scores',
  hard_requirements=['released bore axis position diameter <=0.05 mm',
    'physical exclusion of slag and spatter from interior',
    'controlled Ni99/QT first interface and final dilution',
    'accessible tools and adequate deposited section'],
  selected_baseline='pulsed-GTAW with two-layer Ni99 transition',
  reason='controlled filler addition, no flux slag, independent transition-layer fabrication and compatible physical shielding',
  alternatives=['external GMAW plug weld', 'laser fusion weld', 'micro-plasma', 'brazing'],
  selection_status='current engineering recommendation; complete thermal-mechanical checks remain required',
  global_optimum_proven=False))
result['fatigue_sensitivity']=[dict(layout=row['layout'],load_scale=scale,miner_damage=row['miner_damage']*scale**3,critical_scale=(1/row['miner_damage'])**(1/3)) for row in rows for scale in (0.8,1.,1.25,1.3,1.5)]
OUT.mkdir(exist_ok=True);(OUT/'engineering-checks-r3.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
