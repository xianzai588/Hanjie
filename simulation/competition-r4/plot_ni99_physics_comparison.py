"""Compare actual short-track results; not measured data or whole-seat acceptance."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'simulation/competition-r4/results'
CASES=[
 ('V250 old','ni99-first-whole-seat-P250-three-strips-outerfirst-overlap15-ramp03-fenic-minC-p55-w14-d06-z1140-firsttrack-h15-lh05-dt01-hot1450'),
 ('C0 surface','ni99-physics-C0-source-only-surface-legacy'),
 ('S250 bounds','ni99-physics-S250-3strip-surface-nominal'),
 ('A500 1.4','ni99-physics-A500-full14-surface-nominal'),
 ('B500 0.7','ni99-physics-B500-retained07-surface-nominal')]


def run():
    results=[];screen=[];energy=[]
    for label,name in CASES:
        case=BASE/name;r=json.loads((case/'result.json').read_text(encoding='utf8'))
        f=json.loads((case/'precoat-floor-footprint.json').read_text(encoding='utf8'))
        results.append(r);screen.append(f['QT_molten_volume_screen'])
        h=np.genfromtxt(case/'thermal-history.csv',delimiter=',',names=True)
        if (case/'source-partition-history.csv').exists():
            p=np.genfromtxt(case/'source-partition-history.csv',delimiter=',',names=True)
            energy.append([p['wire_J'].sum(),p['arc_intercept_J'].sum(),p['uncaptured_J'].sum()])
        else:energy.append([h['wire_J'].sum(),h['total_input_J'].sum()-h['wire_J'].sum(),0.])
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,axes=plt.subplots(1,3,figsize=(14,4.8));idx=np.arange(len(CASES));labels=[q[0] for q in CASES]
    ax=axes[0];ax.bar(idx-.18,[r['maximum_temperature_C'] for r in results],.36,color='#387d88',label='active metal')
    ax.bar(idx+.18,[r['maximum_QT_C'] for r in results],.36,color='#b96139',label='QT')
    ax.set(title='a  Actual temperature maxima',ylabel='Temperature (°C)');ax.legend(frameon=False,fontsize=8)
    ax=axes[1];a=np.array([[f['fully_liquid_quadrature_union_mm3'],f['any_liquid_quadrature_union_mm3']] for f in screen])
    ax.bar(idx-.18,a[:,0],.36,color='#387d88',label='fully liquid union')
    ax.bar(idx+.18,a[:,1],.36,color='#93bdc1',label='any liquid union')
    # Legacy file predates this explicit budget key: use exactly the same masses.
    allowed=[]
    for (_,name),f in zip(CASES,screen):
        i=json.loads((BASE/name/'input.json').read_text(encoding='utf8'))
        allowed.append(f['deposited_first_layer_volume_mm3']*i['materials'][3]['nominal_properties_20c']['density_kg_m3']/4/i['materials'][1]['nominal_properties_20c']['density_kg_m3'])
    ax.plot(idx,allowed,'o--',lw=1,color='#bd542b',label='maximum QT entrainment for20%')
    ax.set(title='b  Conditional mixing budget',ylabel='QT volume (mm³)');ax.legend(frameon=False,fontsize=7)
    ax=axes[2];energy=np.array(energy);bottom=np.zeros(len(CASES))
    for j,(label,color) in enumerate([('entering filler','#b96139'),('arc intercepted','#387d88'),('edge not intercepted','#d7dcd9')]):
        ax.bar(idx,energy[:,j],bottom=bottom,color=color,label=label);bottom+=energy[:,j]
    ax.set(title='c  Explicit energy partition',ylabel='Energy (J)');ax.legend(frameon=False,fontsize=7)
    for ax in axes:
        ax.set_xticks(idx,labels,rotation=22,ha='right');ax.grid(axis='y',lw=.35,alpha=.4);ax.set_axisbelow(True)
    fig.suptitle('Ni99 first short track · source model and deposition geometry decision',fontsize=12)
    fig.text(.5,.045,'C0 vs V250 isolates source form. A/B use500 W, 2.2 mm width, 2 mm/s; only first-layer geometry differs.',ha='center',fontsize=8)
    fig.text(.5,.015,'Surface cases predate first-hit shadowing correction. Historical partial comparisons; union is not transported dilution.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.11,1,.93));target=ROOT/'docs/report/figures/r4-ni99-physics-comparison'
    fig.savefig(target.with_suffix('.png'),dpi=240);fig.savefig(target.with_suffix('.pdf'));plt.close(fig)
    print(target)

if __name__=='__main__':run()
