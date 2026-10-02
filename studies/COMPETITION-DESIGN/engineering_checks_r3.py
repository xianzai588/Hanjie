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
result=dict(load_basis='proposed design conditions, official problem gives no numerical load spectrum',load_spectrum=cycles,
 layout_checks=rows,tooling=tools,cleanliness=clean,cycle_resource=process,
 scoring=dict(weights=[.2,.2,.2,.15,.1,.1,.05],weighted_scores=[6.8,6.15,7.1,8.4],role='subjective decision aid with explicit anchors, not official points or measured performance'))
OUT.mkdir(exist_ok=True);(OUT/'engineering-checks-r3.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
