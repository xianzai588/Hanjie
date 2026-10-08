"""Paper figures from saved design geometry and numerical results.

This script changes presentation only. It does not run a solver or substitute
illustrative data for saved calculations. Fixture fields remain at the supplied
original-project path because the isolated worktree stores only their summary.
"""
from pathlib import Path
import csv
import json
import argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.colors import Normalize
from matplotlib.font_manager import FontProperties
from matplotlib.ticker import MaxNLocator

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/report/figures/paper'
FONT = FontProperties(fname=str(ROOT / 'assets/fonts/NotoSerifSC-Regular.ttf'))
plt.rcParams.update({
    'font.family': FONT.get_name(), 'axes.unicode_minus': False,
    'font.size': 10.5, 'axes.labelsize': 10.5, 'xtick.labelsize': 9.5,
    'ytick.labelsize': 9.5, 'legend.fontsize': 9.5, 'axes.linewidth': .7,
    'axes.spines.top': False, 'axes.spines.right': False,
    'lines.linewidth': 1.2, 'pdf.fonttype': 42, 'ps.fonttype': 42,
    'savefig.dpi': 300, 'hatch.linewidth': .5,
})
# Register the bundled font with Matplotlib so the same source works on hosts
# without Microsoft fonts. PDF text embeds the glyphs; metadata stays anonymous.
from matplotlib import font_manager
font_manager.fontManager.addfont(ROOT / 'assets/fonts/NotoSerifSC-Regular.ttf')

def save(fig, name):
    fig.savefig(OUT / (name + '.png'), facecolor='white', dpi=300)
    fig.savefig(OUT / (name + '.pdf'), facecolor='white', metadata={'Author': '', 'Title': ''})
    fig.savefig(OUT / (name + '.svg'), facecolor='white', metadata={'Creator': '', 'Title': ''})
    plt.close(fig)

def section():
    source = ROOT / 'cad/generated/independent-precoat-curved/geometry-audit.json'
    geometry = json.loads(source.read_text(encoding='utf8'))
    x = np.linspace(67.0, geometry['outer_radius_mm'], 1800)
    centre = geometry['inner_radius_mm'] + geometry['QT_corner_radius_mm']
    ztop = geometry['finished_z_mm']
    def profile(radius):
        curved = ztop - np.sqrt(np.maximum(radius**2 - (x-centre)**2, 0))
        return np.where(x < centre-radius, ztop, np.where(x < centre, curved, ztop-radius))
    qt = profile(geometry['QT_corner_radius_mm'])
    ni1 = profile(geometry['first_machining_corner_radius_mm'])
    fig, ax = plt.subplots(figsize=(6.3, 3.25))
    fig.subplots_adjust(left=.10, right=.97, bottom=.25, top=.96)
    ax.fill_between(x, 113.0, qt, color='.86', edgecolor='.2', linewidth=.4, label='QT450-10')
    ax.fill_between(x, qt, ni1, facecolor='white', edgecolor='.3', linewidth=.4, hatch='////', label='CI-A1首层')
    ax.fill_between(x, ni1, ztop, facecolor='.98', edgecolor='.3', linewidth=.4, hatch='...', label='低碳Ni99第二层')
    ax.plot(x, qt, color='black', linewidth=1)
    ax.plot(x, ni1, color='black', linewidth=1)
    ax.plot([x.min(), x.max()], [ztop, ztop], color='black', linewidth=1)
    ax.axvline(71.0, color='.3', ls='--', lw=.8, ymax=.80)
    ax.text(71.08, 113.16, 'R71.0', fontsize=9, va='bottom')
    arrow = {'arrowstyle': '->', 'color': 'black', 'lw': .7}
    ax.annotate('R1.50', xy=(69.40, float(np.interp(69.4, x, qt))), xytext=(67.05, 113.62), arrowprops=arrow)
    ax.annotate('R0.80', xy=(69.95, float(np.interp(69.95, x, ni1))), xytext=(67.05, 115.50), arrowprops=arrow)
    for low, high, label in [(113.50,114.20,'0.70±0.05'),(114.20,115.00,'0.80')]:
        ax.annotate('', xy=(73.08, low), xytext=(73.08, high), arrowprops={'arrowstyle':'<->','lw':.65})
        ax.text(73.26, (low+high)/2, label, va='center', fontsize=9.5, bbox={'facecolor':'white','edgecolor':'none','pad':1})
    ax.annotate('', xy=(68.98,115.40), xytext=(74.98,115.40), arrowprops={'arrowstyle':'<->','lw':.65})
    ax.text(71.98,115.52,'6.00',ha='center',fontsize=10)
    ax.set(xlim=(66.9,75.1), ylim=(113.0,115.85), xlabel='半径 r / mm', ylabel='高度 z / mm')
    ax.set_aspect('equal', adjustable='box')
    ax.set_xticks([68,70,72,74]); ax.set_yticks([113,114,115])
    fig.legend(loc='lower center', bbox_to_anchor=(.5,.015), ncol=3, frameon=False, columnspacing=1.5, handlelength=1.8)
    save(fig, 'design-precoat-normal-offset')
    return source

def phase():
    source = ROOT / 'simulation/competition-r4/results/design-precoat-materials-20261006/gibbs-checked/phase-fractions.csv'
    with source.open(encoding='utf8') as stream:
        rows = list(csv.DictReader(stream))
    fig, ax = plt.subplots(figsize=(6.3,3.15))
    fig.subplots_adjust(left=.115,right=.97,bottom=.18,top=.96)
    for product, style, marker in [('CI-A1','-','o'),('CI-A2','--','s')]:
        points = sorted([r for r in rows if r['case']==product+'-QT20' and r['limit']=='graphite_suppressed'],key=lambda r:float(r['T_C']))
        ax.plot([float(r['T_C']) for r in points],[100*float(r['CEMENTITE_mass_fraction']) for r in points],
                style,color='black',marker=marker,markersize=3.5,markerfacecolor='white',markeredgewidth=.7,label=product+' + 20% QT')
    allowed = [float(r['CEMENTITE_mass_fraction']) for r in rows if r['case'] in ('CI-A1-QT20','CI-A2-QT20') and r['limit']=='graphite_allowed']
    assert max(allowed) < 1e-8, 'The stable-branch annotation must follow the saved data.'
    ax.set(xlabel='温度 / ℃', ylabel='渗碳体质量分数 / %', ylim=(0,28))
    ax.set_xlim(0,1450); ax.set_xticks([0,300,600,900,1200,1400])
    ax.grid(axis='y',color='.88',linewidth=.5); ax.set_axisbelow(True)
    ax.legend(frameon=False,loc='upper right')
    ax.text(.98,.62,'抑制石墨的亚稳分支\n允许石墨平衡分支：0%',transform=ax.transAxes,ha='right',fontsize=9.5)
    save(fig,'design-precoat-phase')
    return source

def fixture(source):
    with np.load(source) as field:
        x,e,u,s = (field[k] for k in ('x','e','u','stress'))
    xx = x[e]
    selected = np.flatnonzero((xx[:,:,1].min(axis=1)<0)&(xx[:,:,1].max(axis=1)>0))
    normal = s[:,:3].mean(axis=1)
    dev = s.copy(); dev[:,:3] -= normal[:,None]
    vm = np.sqrt(1.5*np.sum(dev*dev,axis=1))  # Saved Kelvin stress representation.
    polygons, displacement, stresses = [],[],[]
    for cell in selected:
        points,values = [],[]
        for a,b in ((0,1),(0,2),(0,3),(1,2),(1,3),(2,3)):
            pa,pb = xx[cell,a],xx[cell,b]
            if pa[1]*pb[1] < 0:
                t = -pa[1]/(pb[1]-pa[1])
                points.append((pa+t*(pb-pa))[[0,2]])
                values.append((u[e[cell,a],0]+t*(u[e[cell,b],0]-u[e[cell,a],0]))*1000)
        if len(points)<3: continue
        points=np.array(points); centre=points.mean(axis=0)
        order=np.argsort(np.arctan2(points[:,1]-centre[1],points[:,0]-centre[0]))
        polygons.append(points[order]); displacement.append(np.mean(values)); stresses.append(vm[cell])
    fig,axes = plt.subplots(1,2,figsize=(6.3,3.85))
    fig.subplots_adjust(left=.085,right=.945,bottom=.15,top=.91,wspace=.52)
    norms = (Normalize(vmin=min(0,float(u[:,0].min()*1000)),vmax=float(u[:,0].max()*1000)),
             Normalize(vmin=0,vmax=float(vm.max())))
    for ax,values,label,norm in zip(axes,(displacement,stresses),('(a) 径向位移 $u_x$ / μm','(b) von Mises应力 / MPa'), norms):
        coll=PolyCollection(polygons,array=np.asarray(values),cmap='Blues',norm=norm,edgecolors='none',rasterized=True)
        ax.add_collection(coll); ax.autoscale(); ax.set_aspect('equal')
        ax.set(xlabel='x / mm',ylabel='z / mm')
        ax.xaxis.set_major_locator(MaxNLocator(3)); ax.yaxis.set_major_locator(MaxNLocator(4))
        ax.set_title(label,fontsize=10,pad=12)
        cb=fig.colorbar(coll,ax=ax,fraction=.075,pad=.05,shrink=.90)
        cb.ax.tick_params(labelsize=9); cb.locator=MaxNLocator(5); cb.update_ticks()
    save(fig,'fixture-axis-solid-fe')
    return {'source':str(source),'section':'y=0','radial_u_min_um':float(u[:,0].min()*1000),'radial_u_max_um':float(u[:,0].max()*1000),'von_mises_max_MPa':float(vm.max()),'stress_representation':'Kelvin'}

def budget():
    fig,ax = plt.subplots(figsize=(6.3,3.45))
    fig.subplots_adjust(left=.205,right=.965,bottom=.28,top=.91)
    labels=['内部设计目标','完整允许分配','历史组焊算例']
    values=[(28,2,6.5,12),(28,2,6.5,13.5),(28,2,6.5,15.583947)]
    names=['制造、装配与定心','测量扩展不确定度','有限微珩轴线变化','焊接热残余']
    shades=['.78','white','.95','white']; hatches=['','xx','//','..']
    left=np.zeros(3)
    for j,(name,shade,hatch) in enumerate(zip(names,shades,hatches)):
        vals=np.array([v[j] for v in values])
        ax.barh(labels,vals,left=left,color=shade,edgecolor='.2',linewidth=.6,label=name,hatch=hatch,height=.56)
        for i,v in enumerate(vals):
            if j != 1:
                ax.text(left[i]+v/2,i,f'{v:.2f}'.rstrip('0').rstrip('.'),ha='center',va='center',fontsize=9.5,bbox={'facecolor':shade,'edgecolor':'none','pad':.8})
        left += vals
    for i,v in enumerate(left):ax.text(v+.6,i,f'{v:.2f}'.rstrip('0').rstrip('.'),va='center',fontsize=9.5)
    ax.axvline(50,color='black',ls='--',lw=.9)
    ax.text(50,-.6,'50 μm上限',ha='center',fontsize=9.5)
    ax.set_xlim(0,57.5);ax.set_ylim(2.52,-.88)
    ax.set_xlabel('位置度直径分配 / μm'); ax.set_xticks([0,10,20,30,40,50])
    fig.legend(loc='lower center',ncol=2,frameon=False,bbox_to_anchor=(.53,.006),columnspacing=1.8,handlelength=2)
    save(fig,'position-budget')
    return {'components_um':values,'uncertainty_um':2,'limit_um':50,'historic_is_current_validation':False}

def capacity():
    source=ROOT/'studies/COMPETITION-DESIGN/results/delivery-joint-capacity-20261008.json'
    data=json.loads(source.read_text(encoding='utf8'))
    keys=['6P_16mm_leg_3.8','8P_leg_3.8','Continuous_leg_3.8']
    labels=['6段×16 mm','8段×16 mm','全周连续']
    fig,axes=plt.subplots(1,2,figsize=(6.3,3.45))
    fig.subplots_adjust(left=.105,right=.98,bottom=.18,top=.90,wspace=.42)
    for ax,key,title,unit in [(axes[0],'required_nominal_static_capacity_MPa','(a) 静载计算','等效应力 / MPa'),
                            (axes[1],'required_reference_range_MPa_at_2e6','(b) 疲劳计算','参考应力范围 / MPa')]:
        vals=[data['rows'][k][key] for k in keys]
        bars=ax.bar(np.arange(3),vals,color=['white','.72','white'],edgecolor='black',linewidth=.7,width=.57)
        bars[0].set_hatch('///');bars[2].set_hatch('..')
        for i,v in enumerate(vals):ax.text(i,v+1,f'{v:.2f}',ha='center',fontsize=10)
        ax.set_xticks(np.arange(3),labels,fontsize=8.9);ax.set_ylim(0,max(vals)*1.26)
        ax.set_ylabel(unit);ax.set_title(title,fontsize=10.5,pad=10)
        ax.grid(axis='y',color='.88',linewidth=.5);ax.set_axisbelow(True)
    axes[1].axhline(30,color='.25',ls='--',lw=.9)
    axes[1].text(.97,.72,'预设目标：30 MPa\n$N_C=2×10^6$',transform=axes[1].transAxes,ha='right',fontsize=9.5,
                 bbox={'facecolor':'white','edgecolor':'none','pad':1})
    save(fig,'joint-capacity')
    return source

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--fixture-fields',type=Path,default=Path('E:/AI/bisai/Hanjie/simulation/competition-r4/results/fixture-axis-solid-core-h1.5/fields.npz'))
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    sources={'geometry':str(section().relative_to(ROOT)),'phase':str(phase().relative_to(ROOT)),
             'fixture':fixture(args.fixture_fields),'position':budget(),'capacity':str(capacity().relative_to(ROOT)),
             'operation':'Presentation from saved data; no new solver or changed design parameters.'}
    (OUT/'figure-sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(sources,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
