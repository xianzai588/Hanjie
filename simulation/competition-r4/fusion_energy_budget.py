"""Necessary energy accounting, kept distinct from local fusion evidence."""
from pathlib import Path
import argparse,json
import numpy as np


def sensible(table,top,start=20.):
    knots=np.array(table['temperature_dependent']['temperatures_c'],float)
    cp=np.array(table['temperature_dependent']['specific_heat_j_kgk'],float)
    grid=np.unique(np.r_[start,knots[(knots>start)&(knots<top)],top])
    return float(np.trapezoid(np.interp(grid,knots,cp),grid))


def evaluate(input_path):
    inp=json.loads(Path(input_path).read_text(encoding='utf8'))
    steel,qt,filler=inp['materials'];density=filler['nominal_properties_20c']['density_kg_m3']*1e-9
    melt=filler['fusion_enthalpy'];energy_kg=sensible(filler,melt['liquidus_C'])+melt['latent_heat_J_kg']
    areas=[inp['root_leg_mm']**2/2,(inp['leg_mm']**2-inp['root_leg_mm']**2)/2]
    q=inp['net_W_per_head']/inp['travel_mm_s'];rows=[]
    for i,area in enumerate(areas):
        filler_j=area*density*energy_kg
        rows.append(dict(pass_index=i+1,deposited_area_mm2=area,added_filler_mass_kg_per_mm=area*density,
            minimum_filler_heating_and_melting_J_mm=filler_j,net_energy_J_mm=q,
            remaining_energy_for_parent_remelt_conduction_and_loss_J_mm=q-filler_j,
            necessary_filler_energy_fraction=filler_j/q))
    return dict(source_input=str(input_path),scope='necessary enthalpy balance using the exact whole-part input curves; not a melt-pool prediction',
        filler_specific_melting_enthalpy_J_kg=energy_kg,passes=rows,
        layer_inventory=dict(finished_total_min_mm=1.2,finished_second_min_mm=.5,
            root_remelt_design_max_mm=.3,union_remelt_design_max_mm=.4,
            total_remaining_design_min_mm=.8,second_remaining_design_min_mm=.1),
        necessary_filler_energy_condition_pass=all(r['remaining_energy_for_parent_remelt_conduction_and_loss_J_mm']>0 for r in rows),
        both_side_fusion_verified=False,Ni99_remaining_thickness_verified=False,
        first_QT_PMZ_verified=False,
        missing_local_evidence=['Ni99 first/second-layer composition-dependent solidus/liquidus and enthalpy',
            'resolved local heat source and melt depth on Ni99 and steel',
            'cumulative remelting union referenced to the same finished surface',
            'QT first-layer PMZ and second-layer reheating thermal path'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=evaluate(a.input);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2),encoding='utf8');print(json.dumps(r,indent=2))
