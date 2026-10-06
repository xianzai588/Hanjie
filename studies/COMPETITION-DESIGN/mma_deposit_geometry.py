"""Required as-deposited mass/section before the 0.70 mm machining operation.

The steady semi-elliptic sections are explicit geometry hypotheses. They check
compatibility of input rates with requested edge coverage; neither their shape
nor a volume-equivalent envelope is a prediction of the actual molten bead.
"""
from pathlib import Path
import itertools
import json
import math
import numpy as np
from scipy.optimize import brentq
import yaml

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'studies/COMPETITION-DESIGN/results/mma-deposit-geometry.json'


def height_at(radius,centre,width,area):
    half=width/2
    offset=(np.asarray(radius)-centre)/half
    peak=2*area/(math.pi*half)
    return peak*np.sqrt(np.maximum(0,1-offset**2))*(np.abs(offset)<=1)


def normal_thickness(area,width):
    """Normal rays on the R1.5 substrate curve and on the flat pocket floor."""
    def floor(r):
        if r<68.98:return 115.
        if r<70.48:return 115.-math.sqrt(max(0,1.5**2-(r-70.48)**2))
        return 113.5
    def top(r):
        return floor(r)+float(height_at(r,70.48,width,area)+height_at(r,73.48,width,area))
    points=[]
    for angle in np.linspace(-math.pi,-math.pi/2,81):
        c,s=math.cos(angle),math.sin(angle)
        r,z=70.48+1.5*c,115.+1.5*s
        nr,nz=-c,-s
        def gap(t):return top(r+t*nr)-(z+t*nz)
        ts=np.linspace(1e-6,12.,601);gs=[gap(t) for t in ts]
        exits=[i for i in range(len(ts)-1) if gs[i]>=0 and gs[i+1]<0]
        if not exits:raise RuntimeError('The first normal-ray exit was not found')
        i=exits[0];thickness=brentq(gap,ts[i],ts[i+1],xtol=1e-10)
        points.append(dict(r_mm=float(r),z_mm=float(z),normal_thickness_mm=thickness))
    for radius in np.linspace(70.48,74.98,151):
        points.append(dict(r_mm=float(radius),z_mm=113.5,
            normal_thickness_mm=top(radius)-113.5))
    return min(points,key=lambda row:row['normal_thickness_mm']),points


def run():
    config=yaml.safe_load((ROOT/'project/independent-precoat-candidates.yaml').read_text(encoding='utf8'))
    budget=json.loads((ROOT/'studies/COMPETITION-DESIGN/results/precoat-input-budget.json').read_text(encoding='utf8'))
    geometry=json.loads((ROOT/config['geometry_source']).read_text(encoding='utf8'))
    rows=[];common=config['common'];requested=common['first_as_deposited_min_normal_thickness_mm']
    for name,inp in config['candidates'].items():
        rho=inp['nominal_density_kg_m3']*1e-6 # g/mm3
        rate=inp['deposited_mass_rate_g_s']['nominal'];speed=common['travel_mm_s']['nominal']
        # Area is added metal per unit of actual arc travel, not total fusion area.
        area=rate/(rho*speed)
        profiles=[]
        for width in (3.5,4.0):
            minimum,points=normal_thickness(area,width)
            edge_delta=74.98-73.48;half=width/2
            edge_factor=math.sqrt(1-(edge_delta/half)**2)
            required_area=requested*math.pi*half/(2*edge_factor)
            profiles.append(dict(width_scenario_mm=width,
                peak_added_height_one_stringer_mm=2*area/(math.pi*half),
                minimum_normal_thickness_mm=minimum['normal_thickness_mm'],
                control_point=minimum,requested_minimum_mm=requested,
                required_added_section_mm2=required_area,
                required_mass_per_travel_g_mm=rho*required_area,
                nominal_mass_per_travel_g_mm=rate/speed,
                minimum_contour_requirement_met_in_this_shape_scenario=minimum['normal_thickness_mm']>=requested,
                normal_ray_points=points))
        corners=[]
        for r,v in itertools.product(inp['deposited_mass_rate_g_s']['engineering_interval'],
                                     common['travel_mm_s']['engineering_interval']):
            a=r/(rho*v)
            for width in (3.5,4.0):
                minimum,_=normal_thickness(a,width)
                corners.append(dict(mass_rate_g_s=r,travel_mm_s=v,width_scenario_mm=width,
                    added_section_mm2=a,minimum_normal_thickness_mm=minimum['normal_thickness_mm'],
                    contour_requirement_met=minimum['normal_thickness_mm']>=requested))
        retained_mass=geometry['material_volumes_mm3']['first_CI_A1']*rho
        nominal_mass=budget['candidates'][name]['nominal_deposited_mass_all_wings_g']
        pocket_volume=sum(geometry['material_volumes_mm3'][k] for k in ('first_CI_A1','second_bare_Ni99'))
        rows.append(dict(candidate=name,density_basis=inp['density_basis'],density_g_mm3=rho,
            nominal_added_section_mm2=area,nominal_deposited_mass_all_wings_g=nominal_mass,
            nominal_deposited_volume_all_wings_mm3=nominal_mass/rho,
            nominal_retained_first_mass_g=retained_mass,
            nominal_machining_removed_mass_g=nominal_mass-retained_mass,
            nominal_total_added_volume_to_full_pocket_ratio=(nominal_mass/rho)/pocket_volume,
            steady_section_scenarios=profiles,input_corner_checks=corners))
    result=dict(date='2026-10-06',inputs='project/independent-precoat-candidates.yaml',
        CAD_source='cad/generated/independent-precoat-curved/precoat-stack-R15-R08.brep',
        candidates=rows,scope='Steady interior semi-elliptic added-section hypotheses, integrated by mass conservation. No predicted bead width, start/stop coverage, transport dilution or fusion.',
        physical_bead_shape_verified=False,first_interface_continuous_fusion_pass=False,
        finding='Uncoupled mass-rate and speed corners cannot all supply the requested 1.20 mm local contour. Freeze coupled mass-per-travel and actual contour before thermal birth; 0.70 mm retained CAD is not the as-deposited mass geometry.')
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


if __name__=='__main__':
    result=run()
    for row in result['candidates']:
        print(row['candidate'],'section mm2',row['nominal_added_section_mm2'],
            'nominal deposited/retained/removed g',row['nominal_deposited_mass_all_wings_g'],
            row['nominal_retained_first_mass_g'],row['nominal_machining_removed_mass_g'])
        for case in row['steady_section_scenarios']:
            print('width/min thickness/required g per mm',case['width_scenario_mm'],
                  case['minimum_normal_thickness_mm'],case['required_mass_per_travel_g_mm'])
        print('Rejected contour corners',sum(not c['contour_requirement_met'] for c in row['input_corner_checks']))
