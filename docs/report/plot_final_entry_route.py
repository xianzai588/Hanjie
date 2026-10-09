"""Draw the frozen workshop process route, without running a model."""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

ROOT=Path(__file__).resolve().parents[2]
font_manager.fontManager.addfont(str(ROOT/'assets/fonts/NotoSansSC-Regular.ttf'))
plt.rcParams.update({'font.family':'Noto Sans SC','font.size':10})
fig,ax=plt.subplots(figsize=(7.1,3.6))
ax.set(xlim=(0,10),ylim=(0,6));ax.axis('off')
boxes=[(2,5,'来料与浅槽加工\n材料、组织、槽形'),(7.6,5,'壳外CI-A1首层\n预热—清渣—缓冷'),
       (7.6,3,'首层法向修整\nNi99双轨—缓冷—延迟PT'),(2,3,'连接面与孔预加工\n清洗干燥—封存'),
       (2,1,'入壳定位与屏障\n八段两道GTAW—冷却'),(7.6,1,'保夹转运—一次孔成形\n全收集—完全卸夹检验')]
for x,y,label in boxes:
    ax.add_patch(FancyBboxPatch((x-1.75,y-.55),3.5,1.1,boxstyle='round,pad=.04,rounding_size=.07',
        fc='#f0f3f5',ec='#40586a',lw=1))
    ax.text(x,y,label,ha='center',va='center',linespacing=1.65)
for start,end in [((3.9,5),(5.7,5)),((7.6,4.4),(7.6,3.6)),((5.7,3),(3.9,3)),((2,2.4),(2,1.6)),((3.9,1),(5.7,1))]:
    ax.annotate('',xy=end,xytext=start,arrowprops={'arrowstyle':'-|>','color':'#40586a','lw':1.2})
ax.plot([.2,9.5],[2,2],color='.55',lw=.8,ls='--')
ax.text(9.65,3.9,'壳\n外',ha='center',va='center',color='#40586a')
ax.text(9.65,1,'壳\n内',ha='center',va='center',color='#40586a')
fig.subplots_adjust(left=.015,right=.985,top=.98,bottom=.04)
fig.savefig(ROOT/'docs/report/figures/final-entry/process-route.png',dpi=300,facecolor='white')
plt.close(fig)
