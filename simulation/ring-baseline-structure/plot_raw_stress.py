"""Two true interface views of unsmoothed P1 local-joint stress."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from plot_and_report import element_face_owner

HERE=Path(__file__).resolve().parent


def main():
    mesh=np.load(HERE/"results/fine/mesh.npz");p=mesh["points"];t=mesh["tetrahedra"];mi=mesh["material_ids"];tri=mesh["triangles"]
    vm=np.load(HERE/"results/fine/combined-field.npz")["element_von_mises_MPa"]
    record=json.loads((HERE/"results/fine/result.json").read_text())
    peak=record["cases"]["combined"]["raw_element_stress_by_material"]["5"]["peak_centroid_mm"]
    center=round(np.arctan2(peak[1],peak[0])/(np.pi/4))*(np.pi/4)
    found,owner=element_face_owner(t,mi,tri,len(p),[5]);faces=tri[found];stress=vm[owner[found]]
    q=p[faces];r=np.linalg.norm(q[:,:,:2],axis=2);ang=np.angle(np.exp(1j*(np.arctan2(q[:,:,1],q[:,:,0])-center)))
    segment=np.all(abs(ang)<.121,axis=1)
    bottom=segment&np.all(abs(q[:,:,2]-115)<1e-5,axis=1)
    shell=segment&np.all(abs(r-75)<1e-5,axis=1)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":9,"svg.fonttype":"none","pdf.fonttype":42})
    fig,axes=plt.subplots(2,1,figsize=(7.6,4.5),layout="constrained")
    vmin=float(stress[bottom|shell].min());vmax=float(vm[mi==5].max());norm=LogNorm(vmin=vmin,vmax=vmax)
    for ax,keep,vertical,title in zip(axes,(bottom,shell),("radial","z"),("Weld base / retained Ni interface","Weld / shell interface")):
        xyz=q[keep];s=75*ang[keep];y=r[keep] if vertical=="radial" else xyz[:,:,2]
        # Independent surface triangles retain their adjacent element values.
        n=len(s);local=np.arange(n*3).reshape(n,3)
        artist=ax.tripcolor(s.ravel(),y.ravel(),local,facecolors=stress[keep],shading="flat",cmap="magma",norm=norm)
        ax.set(xlim=(-9.1,9.1),ylim=(71.45,75.05) if vertical=="radial" else (114.95,118.55),
               xlabel="Effective-segment arc coordinate (mm)",ylabel="r (mm)" if vertical=="radial" else "z (mm)",title=title)
        ax.set_aspect("equal")
    fig.colorbar(artist,ax=axes,label="Raw element von Mises (MPa; log color scale)",shrink=.85,pad=.025)
    fig.suptitle(f"P1 fine / minimum fillet / raw peak {vmax:.1f} MPa at the sharp root",fontsize=10)
    for ext in ("png","pdf","svg"):fig.savefig(HERE/f"figures/ring-joint-raw-stress.{ext}",dpi=220)
    plt.close(fig)


if __name__=="__main__":main()
