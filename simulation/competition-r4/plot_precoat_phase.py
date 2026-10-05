"""Plot actual saved Gauss-point peak fields and converged thermal history."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
CASE=ROOT/'simulation/competition-r4/results/ni99-first-whole-seat-4short-P400-overlap15-fenic-minC-p55-w18-d06-z1138-h15-lh05-dt01-hot1450'


def plot():
    result=json.loads((CASE/'result.json').read_text(encoding='utf8'))
    witness=json.loads((CASE/'precoat-interface-observer/melting-depth-witness-audit.json').read_text(encoding='utf8'))['deepest']['1:1']
    if result['partial']:raise ValueError('complete actual first-layer field required')
    with np.load(CASE/'thermal-fields.npz',allow_pickle=False) as f:
        x,e,m=f['x'],f['e'],f['material'];face=f['interface_nodes'];face_peak=f['interface_peak_C']
        qp=f['peak_element_quadrature_C'];bary=f['tetra_quadrature_barycentric']
    face_xyz=np.einsum('qj,fjk->fqk',np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]]),x[face])
    floor=abs(face_xyz[:,:,2]-113.6)<1e-5
    radius=np.linalg.norm(face_xyz[:,:,:2],axis=2);arc=74.98*np.arctan2(face_xyz[:,:,1],face_xyz[:,:,0])
    qt_xyz=np.einsum('qj,fjk->fqk',bary,x[e[m==1]])
    qr=np.linalg.norm(qt_xyz[:,:,:2],axis=2);qs=74.98*np.arctan2(qt_xyz[:,:,1],qt_xyz[:,:,0]);qz=qt_xyz[:,:,2]
    section=(abs(qs)<.35)&(qr>=68)&(qz>=110)&(qz<=114)
    h=np.loadtxt(CASE/'thermal-history.csv',delimiter=',',skiprows=1)
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,axes=plt.subplots(1,3,figsize=(14,4.6),gridspec_kw={'width_ratios':[1.1,1.,1.25]})
    ax=axes[0];dots=ax.scatter(arc[floor],radius[floor],c=face_peak[floor],s=7,cmap='viridis',vmin=700,vmax=2600,rasterized=True)
    molten=floor&(face_peak>=1353.5)
    ax.scatter(arc[molten],radius[molten],facecolors='none',edgecolors='#bd542b',s=10,linewidth=.45,rasterized=True)
    for r,label in [(72.2,'root inner edge'),(71.,'cap inner edge')]:
        ax.axhline(r,color='#555',ls='--',lw=.7);ax.text(-8.8,r+.05,label,fontsize=7)
    ax.set(xlim=(-9,9),ylim=(68.9,75),xlabel='Arc coordinate (mm)',ylabel='Radius (mm)',title='a  QT / Ni99 floor, z=113.6 mm')
    fig.colorbar(dots,ax=ax,label='Point-wise peak temperature (°C)',fraction=.045,pad=.03)
    ax.text(.02,.02,'rings: peak ≥1353.5°C',transform=ax.transAxes,fontsize=7)
    ax=axes[1];ax.scatter(qr[section],qz[section],c=qp[m==1][section],s=5,cmap='viridis',vmin=700,vmax=2600,rasterized=True)
    ax.axhline(113.6,color='#444',lw=1,label='pocket floor')
    ax.axhline(witness['minimum_z_mm'],color='#bd542b',ls='--',lw=.8,label='global P1 minimum height (reference)')
    location=np.array(witness['barycentric'])@x[e[witness['element']]]
    witness_arc=float(74.98*np.arctan2(location[1],location[0]))
    ax.text(.02,.96,f'Global minimum at s={witness_arc:.1f} mm\n(outside this thin section)',transform=ax.transAxes,va='top',fontsize=7)
    ax.set(xlim=(68,75),ylim=(110,114),xlabel='Radius (mm)',ylabel='Height z (mm)',title='b  QT peak samples, |s|<0.35 mm')
    ax.legend(loc='lower left',fontsize=7,frameon=False)
    ax=axes[2];ax.plot(h[:,0],h[:,4],color='#237889',lw=1.3,label='active metal maximum')
    ax.plot(h[:,0],h[:,5],color='#b85e37',lw=1.,ls='--',label='QT maximum')
    for stage in result['stages']:
        ax.axvspan(stage['start_s'],stage['start_s']+stage['arc_s'],color='#237889',alpha=.1)
        ax.plot(stage['end_s'],stage['end_active_max_C'],'o',ms=3,color='#333')
    ax.axhline(90,color='#666',lw=.65,ls=':');ax.set(xlabel='Actual time (s)',ylabel='Temperature (°C)',title='c  Four short tracks and actual cooling')
    ax.legend(loc='upper left',fontsize=8,frameon=False);ax.set_xlim(0,265)
    fig.suptitle('Ni99 first-layer thermal calculation · 400 W · Fe–Ni–C low-carbon corner +5.5°C',fontsize=12)
    fig.text(.5,.02,'Native face / Tet4 Gauss samples: individual time-wise peaks; numerical fields. Global QT minimum-height reference comes from instantaneous P1 witnesses.',ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.055,1,.93))
    target=ROOT/'docs/report/figures/r4-ni99-first-wing-phase-thermal'
    fig.savefig(target.with_suffix('.png'),dpi=240);fig.savefig(target.with_suffix('.pdf'));plt.close(fig)
    print(target)


if __name__=='__main__':plot()
