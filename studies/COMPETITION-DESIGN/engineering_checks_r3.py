"""Independent weld-group load histories, robust process, tooling and resource checks."""
from pathlib import Path
import json, math
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent/'results'
rows=[]
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
 rows.append(dict(n=n,throat_mm=a,area_mm2=A,second_moment_mm4=I,static_equivalent_MPa=static_vm,
 static_allowable_MPa=60,static_margin=60/static_vm,fatigue=fatigue,miner_damage=damage,
 fatigue_curve=dict(reference_range_MPa=30,reference_cycles=2e6,slope=3,basis='proposed qualification target, not a published FAT class for NiFe/QT',qualification_required=True),
 heat_kJ=18*n*2*.300,arc_s=18*n*2/1.65))
# Slotted finger beam conservatively all six fingers carry radial preload.
E=200000.;w=19.;th=.8;leng=30.;I=w*th**3/12;k=6*3*E*I/leng**3
u=(40.025-39.94)/2;F=k*u;rootstress=6*(F/6)*leng/(w*th**2)
tools=dict(finger_radial_stiffness_N_mm=k,max_free_expand_radial_mm=u,elastic_expand_N=F,
 finger_root_stress_MPa=rootstress,preload_N=100,radial_backstop_capacity_N=5000,
 shaft_area_mm2=math.pi*(36**2-24**2)/4,thermal_reaction_separate_from_preload=True)
tools['backstop_average_axial_MPa']=5000/tools['shaft_area_mm2']
ring_mass=math.pi*(74.8**2-71.8**2)*5*8.96e-6
jet_area=12*math.pi*.5**2
clean=dict(copper_mass_kg=ring_mass,radial_hot_growth_at_100C_mm=74.8*17e-6*80,
 hot_metal_radius_mm=74.8*(1+17e-6*80),seal_compression_at_20C_mm=.1,
 nozzle_area_mm2=jet_area,jet_velocity_at_10_15L_min_m_s=[q*1e6/60/jet_area/1000 for q in (10,15)],
 full_bore_average_velocity_m_s=[q*1e6/60/(math.pi*75**2)/1000 for q in (10,15)],
 water_flow_L_min=.2,coolant_capacity_W_at_10K=.2/60*4180*10,
 function='mechanical collection and static seal prevent downward debris; jets assist transport only')
process=[]
for passes in (2,4):
 arc=18*6/1.65*passes;tool=6*passes*18;assembly=120;qc=120
 process.append(dict(passes=passes,arc_s=arc,peen_clean_transfer_s=tool,assembly_s=assembly,inspection_s=qc,
 welded_station_work_s=arc+tool,serial_before_cooling_s=arc+tool+assembly+qc,
 actual_cooling_s='read full-part thermal history; fixture remains occupied until release temperature',
 pipeline='two assembly pallets alone do not reduce occupied welding/holding resource; dedicated holding pallets required'))
# First-order reciprocating-compressor load derivation, ported from origin/main
# studies/LOAD-ESTIMATE (LOAD-ESTIMATE-4). Its inputs remain engineering assumptions,
# so the outputs are a reference point, not a measured load spectrum.
di=dict(reciprocating_mass_kg=0.8,crank_radius_m=0.02,speed_rpm=3000.0,rod_ratio=0.25,
 bore_diameter_m=0.04,pressure_difference_pa=1500000.0,force_line_to_weld_centroid_m=0.07)
omega=2*math.pi*di['speed_rpm']/60
Fi=di['reciprocating_mass_kg']*di['crank_radius_m']*omega**2
Fg=math.pi*di['bore_diameter_m']**2*di['pressure_difference_pa']/4
M=Fi*di['force_line_to_weld_centroid_m']+Fg*di['crank_radius_m']/2  # N·m
M_mm=M*1000.0  # N·mm, same unit as the spectra and the 250000 N·mm official reference
derivation=dict(
 ported_from='origin/main studies/LOAD-ESTIMATE LOAD-ESTIMATE-4',
 inputs=di,
 formulas=dict(omega='2*pi*n/60',inertial_force='Fi=m*r*omega^2',
  gas_force='Fg=pi*D^2*delta_p/4',tipover_moment='M=Fi*e+Fg*(r/2)'),
 not_modelled=['connecting-rod second-order term','cylinder-pressure phase vs crank angle','multi-cylinder superposition'],
 outputs=dict(inertial_force_N=round(Fi,1),gas_force_N=round(Fg,1),tipover_moment_N_mm=round(M_mm,0),
  official_reference_loads=dict(radial_N=5000.0,axial_N=5000.0,moment_N_mm=250000.0,
   note='fixed-problem screening basis; already used by layout_checks static columns and the 5000 N tooling backstop'),
  relation_to_spectra=dict(M_ratio_continuous=round(25000/M_mm,2),M_ratio_start_stop=round(75000/M_mm,2),
   Fr_ratio_continuous=round(500/Fi,2),Fr_ratio_start_stop=round(1500/Fi,2),
   note='proposed fatigue spectra sit below the first-order derivation in the moment channel '
        '(0.19~0.58x); Miner damage is therefore a same-spectrum relative comparison between 6P '
        'and 8P, not an absolute life claim; damage scales with the cube of stress range if loads move up')))
result=dict(load_basis='proposed screening spectra for relative route comparison; official problem gives '
 'no measured spectrum, static columns use its 5000 N reference loads, first-order derivation in load_derivation',
 load_spectrum=cycles,load_derivation=derivation,
 layout_checks=rows,tooling=tools,cleanliness=clean,cycle_resource=process,
 scoring=dict(weights=[.2,.2,.2,.15,.1,.1,.05],weighted_scores=[6.8,6.15,7.1,8.4],role='subjective decision aid with explicit anchors, not official points or measured performance'))
OUT.mkdir(exist_ok=True);(OUT/'engineering-checks-r3.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
