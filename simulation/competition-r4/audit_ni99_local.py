"""Extract real local thermal fields, without inferring a PMZ strength."""
from pathlib import Path
import argparse,json
import numpy as np


def audit(folder):
    folder=Path(folder);inp=json.loads((folder/'input.json').read_text(encoding='utf8'))
    d=np.load(folder/'checkpoint.npz',allow_pickle=False);m=d['mat'];v=d['v'];r=d['r'];z=d['z'];s=d['s']
    peaks=d['stage_peaks'];rows=[]
    first_mass=8890e-9*v[m==3].sum()
    for j,p in enumerate(peaks):
        qt=(m==1);fully=qt&(p>=1180);partial=qt&(p>=1100)&(p<1180)
        qt_liq_mass=7200e-9*v[fully].sum();qt_any_mass=7200e-9*v[fully|partial].sum()
        # These are melt-volume mixing bounds conditional on entrainment;
        # conduction alone is not a fluid-mixing or chemistry calculation.
        rows.append(dict(stage=j,QT_fully_liquid_peak_volume_mm3=float(v[fully].sum()),
          QT_partial_melt_peak_volume_mm3=float(v[partial].sum()),
          QT_fully_liquid_depth_cell_envelope_mm=float(d['floor']-d['ze'][np.searchsorted(d['ze'],z[fully].min())-1]) if fully.any() else 0.,
          first_layer_peak_above_solidus_volume_fraction=float(v[(m==3)&(p>=inp['ni1_solidus'])].sum()/v[m==3].sum()),
          potential_QT_mass_fraction_if_fully_entrained=[float(qt_liq_mass/(qt_liq_mass+first_mass)),float(qt_any_mass/(qt_any_mass+first_mass))]))
    if 'pair' in d:
        a,b=d['pair'].T
        interface=(m[a]==1)&(m[b]==3)&(z[a]<d['floor'])&(z[b]>d['floor'])
        p=peaks[0];mixed=interface&(p[a]>=1100)&(p[b]>=inp['ni1_solidus'])
        liquid=interface&(p[a]>=1180)&(p[b]>=1446)
        area=d['area'];surface=dict(QT_Ni99_interface_area_mm2=float(area[interface].sum()),
           both_sides_above_solidus_face_area_mm2=float(area[mixed].sum()),
           both_sides_above_liquidus_face_area_mm2=float(area[liquid].sum()))
        if 'stage_face_peaks' in d:
            fp=d['stage_face_peaks'][0];foot=interface&(r[a]>=71)&(abs(s[a])<=8)
            surface.update(actual_resistance_interpolated_face_above_both_solidus_area_mm2=float(area[interface&(fp>=max(1100,inp['ni1_solidus']))].sum()),
              final_weld_footprint_R71_to_7497_central16mm_area_mm2=float(area[foot].sum()),
              footprint_minimum_face_peak_C=float(fp[foot].min()),
              footprint_above_both_solidus_fraction=float(area[foot&(fp>=max(1100,inp['ni1_solidus']))].sum()/area[foot].sum()))
    else:surface={}
    result=dict(stages=rows,interface_peak_screen=surface,
      status='local numerical thermal screening; finite-domain, spatial/time and source/material sensitivity remain to be evaluated',
      mixing_scope='melted QT volume does not prove complete entrainment; listed mass fractions are conditional bounds',
      PMZ_capacity_assigned=False,full_assembly_feedback_completed=False)
    (folder/'fusion-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    return result


def plot(folder,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    folder=Path(folder);d=np.load(folder/'checkpoint.npz',allow_pickle=False);shape=tuple(d['shape'])
    k=int(np.argmin(abs((d['se'][:-1]+d['se'][1:])/2)))
    p=d['stage_peaks'][0].reshape(shape)[:,:,k].T;m=d['mat'].reshape(shape)[:,:,k].T
    p=np.ma.masked_where((m!=1)&(m!=3),p)
    fig,ax=plt.subplots(figsize=(7,4.5),layout='constrained')
    im=ax.pcolormesh(d['re'],d['ze'],p,cmap='inferno',vmin=20,vmax=1650,shading='flat')
    rr=(d['re'][:-1]+d['re'][1:])/2;zz=(d['ze'][:-1]+d['ze'][1:])/2
    qt=np.ma.masked_where(m!=1,p)
    c=ax.contour(rr,zz,qt,levels=[1100,1180],colors=['#00c7de','#99f0ff'],linewidths=.9)
    ax.clabel(c,fontsize=8);ax.plot([69,74.97],[float(d['floor'])]*2,c='#b9d866',lw=2,label='QT / first Ni99 interface')
    ax.set(xlim=(67,75.5),ylim=(110,116),xlabel='r (mm)',ylabel='z (mm)',title='Computed first-precoat peak temperature, s nearest 0')
    ax.legend(fontsize=8);fig.colorbar(im,ax=ax,label='Peak temperature (C)')
    fig.savefig(output,dpi=240);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--case',type=Path,required=True);p.add_argument('--plot',type=Path)
    a=p.parse_args();print(json.dumps(audit(a.case),ensure_ascii=False,indent=2))
    if a.plot:plot(a.case,a.plot)
