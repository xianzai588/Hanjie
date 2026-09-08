"""从已归档账本绘制Route B证据；不生成或补造求解数据。"""
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
THERMAL=ROOT/"simulation/thermal-ref/results/plan8"
STRUCT=ROOT/"simulation/structural-v4/results/struct-uncertainty"
COLORS=["#176b9c","#d06b24","#7955a3"]


def draw():
    plt.rcParams.update({"font.size":10,"axes.spines.top":False,"axes.spines.right":False,"savefig.dpi":170})
    fig,ax=plt.subplots(2,2,figsize=(12,8),layout="constrained")
    for solver,style in (("fvm","-"),("elmer","--")):
        d=pd.read_csv(THERMAL/f"{solver}-dynamic/partition-cumulative.csv")
        for material,label,color in zip(("qt","q235","weld"),("QT","Q235","Weld"),COLORS):
            h=d[f"H_{material}_j"]
            ax[0,0].plot(d.time_s,h-h.iloc[0],style,color=color,label=f"{label} {solver.upper()}")
        for material,label,color in zip(("qt","q235"),("QT","Q235"),COLORS):
            ax[0,1].plot(d.time_s,d[f"weld_to_{material}_j"],style,color=color,label=f"{label} {solver.upper()}")
    ax[0,0].set(title="A  Material enthalpy change",xlabel="Time (s)",ylabel="H(t) - H(18 s) (J)")
    ax[0,0].legend(ncol=2,fontsize=8)
    ax[0,1].set(title="B  Weld-to-parent exchange ledger",xlabel="Time (s)",ylabel="Cumulative exchange from 18 s (J)")
    ax[0,1].legend(fontsize=8)
    d=pd.read_csv(THERMAL/"common-probes-dynamic.csv")
    line=d[d.probe.str.startswith("line_") & np.isclose(d.time_s,22.)]
    for material in (2,3,1):
        part=line[line.material_id==material].sort_values("n_mm")
        for solver,style,color in (("fvm","-",COLORS[0]),("elmer","--",COLORS[1])):
            ax[1,0].plot(part.n_mm,part[f"{solver}_common_c"],style,marker="o",markersize=3,color=color,label=solver.upper() if material==2 else None)
    ax[1,0].set(title="C  Common material-wise probes at 22 s",xlabel="n (mm); s = 0, z = n + 1 mm",ylabel="Temperature (°C)")
    ax[1,0].legend()
    result=json.loads((THERMAL/"assessment.json").read_text(encoding="utf-8"))
    names=list(result["observations"]["dynamic"]); x=np.arange(len(names))
    for offset,mode,color in ((-.19,"dynamic",COLORS[0]),(.19,"constant",COLORS[1])):
        ax[1,1].bar(x+offset,[result["observations"][mode][n]["common_peak_gap_c"] for n in names],.38,color=color,label=mode)
    ax[1,1].set(title="D  Common-probe peak gaps, 18–26 s",ylabel="Absolute peak difference (°C)",xticks=x,xticklabels=["Weld","QT near","QT far","Q235 near","Q235 far"])
    ax[1,1].legend()
    for a in ax.flat:
        a.grid(alpha=.18); a.set_axisbelow(True)
    fig.suptitle("Plan 8: persistent local field disagreement — formal thermal gate remains closed",fontsize=13)
    fig.supxlabel("FE exchange uses shared-node reactions (load/storage included); FVM uses conservative face flux. Constant control is preborn.",fontsize=8)
    fig.savefig(THERMAL/"partition-diagnostics.png"); plt.close(fig)

    result=json.loads((STRUCT/"assessment.json").read_text(encoding="utf-8"))
    fig,ax=plt.subplots(1,2,figsize=(12,4.8),layout="constrained")
    candidates=["Continuous","6P-FAIR_B","8P-FAIR_B"]
    for source,offset,color in (("fvm",-.12,COLORS[0]),("elmer",.12,COLORS[1])):
        rows=[next(r for r in result["envelopes"] if r["candidate"]==c and r["source"]==source) for c in candidates]
        for i,r in enumerate(rows):
            ax[0].plot([r["minimum_mm"]*1000,r["maximum_mm"]*1000],[i+offset]*2,color=color,lw=3,label=source.upper() if i==0 else None)
            ax[0].plot([r["minimum_mm"]*1000,r["maximum_mm"]*1000],[i+offset]*2,"|",color=color,markersize=10)
    ax[0].set(yticks=np.arange(3),yticklabels=candidates,xlabel="Conditional position sensitivity diameter (µm)",title="C/M + material + restraint + foundation envelope")
    ax[0].legend(loc="center",bbox_to_anchor=(.5,.77),ncol=2,frameon=False); ax[0].invert_yaxis()
    pairs=result["pairs"]; y=np.arange(3); left=np.zeros(3)
    for key,label,color in (("a_lower","A lower",COLORS[0]),("b_lower","B lower",COLORS[1]),("unresolved","Unresolved / tie","#c4ccd3")):
        value=np.array([p[key] for p in pairs]); ax[1].barh(y,value,left=left,color=color,label=label); left+=value
    ax[1].set(yticks=y,yticklabels=["Continuous / 6P","Continuous / 8P","6P / 8P"],xlabel="Paired scenarios (72 total)",title="A / B comparison: no resolved robust winner")
    ax[1].legend(loc="lower right",fontsize=8); ax[1].invert_yaxis()
    fig.suptitle("STRUCT-UNCERTAINTY: reduced inherent-strain sensitivity, not final weld distortion",fontsize=13)
    fig.supxlabel("Rank resolution: 1 µm + observed C/M changes. Envelopes are deterministic scenarios; no product acceptance or physical validation.",fontsize=8)
    fig.savefig(STRUCT/"sensitivity-ranking.png"); plt.close(fig)


if __name__=="__main__":
    draw()
