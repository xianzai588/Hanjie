"""绘制局部截面网格、固定点热循环和 F→VF 峰温差。"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,TwoSlopeNorm
from matplotlib.patches import Rectangle
from matplotlib.collections import PatchCollection
import numpy as np

from analyze_spatial_convergence import _project_fine_to_medium
from run_physics03 import ROOT


RESULTS=ROOT/"simulation/thermal-v5/results/xsec-refinement-study"
LEVELS=("XSEC-M","XSEC-F","XSEC-VF")


def plot_mesh(axis,level):
    with np.load(RESULTS/level/"field.npz") as field:
        n,z=field["n_edges"],field["z_edges"]
        material=field["material_cross_section"].T
        axis.pcolormesh(n,z,material,cmap=ListedColormap(["white","#5b8ff9","#61d9a5","#f6bd16"]),vmin=0,vmax=3,shading="flat")
        for value in n[(n>=-3)&(n<=1.5)]: axis.axvline(value,color="black",lw=.22,alpha=.55)
        for value in z[(z>=-2)&(z<=2)]: axis.axhline(value,color="black",lw=.22,alpha=.55)
    axis.set(xlim=(-3,1.5),ylim=(-2,2),title=level,xlabel="n (mm)")
    axis.set_aspect("equal")


def plot_history(axis,point,title):
    for level,color in zip(LEVELS,("#4e79a7","#f28e2b","#e15759")):
        history=json.loads((RESULTS/level/"fixed-point-history.json").read_text(encoding="utf-8"))
        axis.plot([row["time_s"] for row in history["rows"]],[row[point] for row in history["rows"]],label=level,color=color,lw=1.25)
    axis.set(title=title,xlabel="Time (s)",ylabel="Temperature (°C)")
    axis.grid(alpha=.25); axis.legend(frameon=False,fontsize=7)


def plot_difference(axis):
    with np.load(RESULTS/"XSEC-F/field.npz") as lower,np.load(RESULTS/"XSEC-VF/field.npz") as upper:
        projected,_=_project_fine_to_medium(lower,upper)
        s_values=np.unique(lower["s"]); target=s_values[np.argmin(np.abs(s_values))]
        mask=np.isclose(lower["s"],target)&np.isfinite(projected)&(lower["filled_fraction"]>0)
        difference=projected[mask]-lower["temperature_peak"][mask]
        n_edges,z_edges=lower["n_edges"],lower["z_edges"]
        patches=[]
        for n,z in zip(lower["n"][mask],lower["z"][mask]):
            ni=np.searchsorted(n_edges,n)-1; zi=np.searchsorted(z_edges,z)-1
            patches.append(Rectangle((n_edges[ni],z_edges[zi]),n_edges[ni+1]-n_edges[ni],z_edges[zi+1]-z_edges[zi]))
        maximum=max(float(np.max(np.abs(difference))),1e-9)
        collection=PatchCollection(patches,array=difference,cmap="coolwarm",norm=TwoSlopeNorm(vcenter=0,vmin=-maximum,vmax=maximum),edgecolor="none")
        axis.add_collection(collection)
    axis.set(xlim=(-3,1.5),ylim=(-2,2),title="F→VF peak ΔT at s≈0",xlabel="n (mm)",ylabel="z (mm)")
    axis.set_aspect("equal"); plt.colorbar(collection,ax=axis,label="ΔT (°C)",fraction=.046,pad=.04)


def main() -> int:
    fig,axes=plt.subplots(2,3,figsize=(12,7),constrained_layout=True)
    for axis,level in zip(axes[0],LEVELS): plot_mesh(axis,level)
    axes[0,0].set_ylabel("z (mm)")
    plot_history(axes[1,0],"weld_center","Weld-center containing cell")
    plot_history(axes[1,1],"qt_near_interface","QT near-interface containing cell")
    plot_difference(axes[1,2])
    fig.suptitle("THERMAL-0.5 local cross-section refinement diagnostics")
    for suffix in ("png","svg"):
        fig.savefig(RESULTS/f"xsec-refinement-diagnostics.{suffix}",dpi=300,bbox_inches="tight",facecolor="white")
    plt.close(fig)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
