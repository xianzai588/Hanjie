"""Plot actual saved author-database phase calculations for engineering review."""
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
rows=list(csv.DictReader((ROOT/'simulation/competition-r4/results/FeNiC-2026-layer-corners-gibbs-checked/phase-fractions.csv').open()))
def curve(case,limit):
    rr=[row for row in rows if row['case']==case and row['limit']==limit]
    return {key:np.array([float(row[key]) for row in rr]) for key in rr[0] if key not in ['case','limit']}

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
fig,axs=plt.subplots(2,2,figsize=(10.5,7.4),layout='constrained')
colors=['#287888','#BD653D'];a=axs[0,0]
for j,case in enumerate(['first_min_C','first_max_C']):
    for limit,style in [('graphite_allowed','-'),('graphite_suppressed','--')]:
        d=curve(case,limit);a.plot(d['T_C'],100*d['LIQUID_mass_fraction'],style,color=colors[j],
          label=('Low C' if j==0 else 'High C')+'; '+('graphite' if style=='-' else 'no graphite'))
a.set(xlim=(1200,1460),ylim=(-2,102),xlabel='Temperature (°C)',ylabel='Liquid mass fraction (%)',title='a  First layer: two thermodynamic limits');a.legend(frameon=False,fontsize=8)
a=axs[0,1]
for j,group in enumerate(['second','final']):
    for side,style in [('min_C','-'),('max_C','--')]:
        d=curve(group+'_'+side,'graphite_allowed');a.plot(d['T_C'],100*d['LIQUID_mass_fraction'],style,color=colors[j],label=group+'; '+side.replace('_',' '))
a.set(xlim=(1400,1460),ylim=(-2,102),xlabel='Temperature (°C)',ylabel='Liquid mass fraction (%)',title='b  Second layer and final weld');a.legend(frameon=False,fontsize=8)
cases=['first_min_C','first_max_C','second_min_C','second_max_C','final_min_C','final_max_C'];labels=['First, low C','First, high C','Second, low C','Second, high C','Final, low C','Final, high C']
a=axs[1,0];left=np.zeros(6)
for phase,color,name in [('FCC_A1','#287888','FCC'),('BCC_A2','#A8B5BC','BCC'),('GRAPHITE','#383C40','Graphite')]:
    value=[]
    for case in cases:
        d=curve(case,'graphite_allowed');value.append(100*d[phase+'_mass_fraction'][d['T_C']==25][0])
    a.barh(np.arange(6),value,left=left,color=color,label=name,height=.62);left+=value
a.set(yticks=np.arange(6),yticklabels=labels,xlim=(0,100),xlabel='Equilibrium mass fraction (%)',title='c  Graphite allowed, 25°C');a.invert_yaxis();a.legend(frameon=False,fontsize=8,loc='lower left')
a=axs[1,1]
for T,offset,marker,color in [(25,-.12,'o','#BD653D'),(500,.12,'s','#287888')]:
    values=[]
    for case in cases:
        d=curve(case,'graphite_suppressed');values.append(100*d['CEMENTITE_mass_fraction'][d['T_C']==T][0])
    a.scatter(values,np.arange(6)+offset,marker=marker,color=color,label=f'{T}°C',zorder=3)
a.set(yticks=np.arange(6),yticklabels=labels,xlim=(-.25,12.5),xlabel='Cementite mass fraction (%)',title='d  Graphite suppressed');a.invert_yaxis();a.legend(frameon=False,fontsize=8)
for a in axs.flat:a.grid(axis='x',color='#DDE3E7',linewidth=.6);a.set_axisbelow(True)
fig.suptitle('Fe–Ni–C layer composition corners · CALPHAD calculation',fontsize=13)
fig.supxlabel('Oikawa & Ueshima (2026), author Table S1 · Si/Mn/etc removed and Fe/Ni/C renormalized\nEquilibrium limits; spatial PMZ state and welding kinetics evaluated separately',fontsize=8)
out=ROOT/'docs/report/figures/r4-fenic-thermodynamic-corners';fig.savefig(out.with_suffix('.png'),dpi=260);fig.savefig(out.with_suffix('.pdf'));plt.close(fig)
print(out.with_suffix('.png'))
