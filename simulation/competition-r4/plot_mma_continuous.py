"""Continuous first-layer plots from the accepted nodal and interface records."""
import json
import itertools
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.tri as tri
from matplotlib.collections import PolyCollection
from audit_mma_three_cases import audit
from mma_literature_profile import ROOT

BASE = ROOT/'simulation/competition-r4/results'
CASES = ['mma-first-end80-r12-trace-20261007',
         'mma-first-end80-r12-h045-trace-20261007',
         'mma-first-end80-r12-endpoint-dt00625-20261007']


def plane_triangles(x, elements, temperature, material, angle):
    normal = np.array([-np.sin(angle), np.cos(angle), 0.])
    radial = np.array([np.cos(angle), np.sin(angle), 0.])
    distances = x@normal
    candidates = (distances[elements].min(axis=1)<0)&(distances[elements].max(axis=1)>0)
    points, values, triangles, triangle_material = [], [], [], []
    for k in np.flatnonzero(candidates):
        vertices = elements[k]
        polygon = []
        for a, b in itertools.combinations(vertices, 2):
            da, db = distances[a], distances[b]
            if da*db <= 0 and abs(da-db)>1e-12:
                f = da/(da-db)
                p = x[a]+f*(x[b]-x[a])
                polygon.append(([float(p@radial), float(p[2])],
                                float(temperature[a]+f*(temperature[b]-temperature[a]))))
        if len(polygon)<3:
            continue
        xy = np.array([p[0] for p in polygon])
        if xy[:,0].max()<61 or xy[:,0].min()>76 or xy[:,1].max()<102:
            continue
        centre = xy.mean(axis=0)
        order = np.argsort(np.arctan2(xy[:,1]-centre[1], xy[:,0]-centre[0]))
        start = len(points)
        points.extend(xy[order].tolist())
        values.extend([polygon[i][1] for i in order])
        for j in range(1, len(polygon)-1):
            triangles.append([start, start+j, start+j+1])
            triangle_material.append(material[k])
    xy = np.array(points)
    return tri.Triangulation(xy[:,0], xy[:,1], np.array(triangles)), np.array(values), np.array(triangle_material)


def run():
    plt.rcParams.update({'font.family':'Microsoft YaHei', 'axes.unicode_minus':False,
        'font.size':9, 'axes.spines.top':False, 'axes.spines.right':False, 'svg.fonttype':'none'})
    fig, axes = plt.subplots(2, 2, figsize=(11.6, 8), layout='constrained')
    colours = ['#205c80', '#4a8262', '#cb6b35']
    labels = ['基准 h0.65 / Δt0.125', '局部 h0.45', '收弧段 Δt0.0625']
    for name, label, colour in zip(CASES, labels, colours):
        history = np.loadtxt(BASE/name/'thermal-history.csv', delimiter=',', skiprows=1, ndmin=2)
        axes[0,0].plot(history[:,0], history[:,4], label=label, color=colour, lw=1.4)
    folder = BASE/CASES[0]
    inp = json.loads((folder/'input.json').read_text())
    arc_end = inp['tracks'][0]['arc_duration_s']
    axes[0,0].axvline(arc_end, color='#666666', ls=':', label='收弧11.569 s')
    axes[0,0].axhline(2800, color='#9f3f3f', ls='--', lw=1)
    axes[0,0].set(title='a  一翼首层热历程与离散对照', xlabel='时间 / s', ylabel='活动金属最高温度 / ℃', xlim=(0,96), ylim=(250,2950))
    axes[0,0].legend(frameon=False, fontsize=7.5)
    summary, polygons, peak_min, positions, minimum = audit(folder)
    pc = PolyCollection(polygons, array=peak_min, cmap='inferno', clim=(1400,2600), edgecolors='none')
    axes[0,1].add_collection(pc)
    axes[0,1].set(title='b  QT/镍界面整面同时最高温度', xlabel='s = 74.98θ / mm', ylabel='半径 / mm', xlim=(-10.5,10.5), ylim=(68.8,75.2))
    axes[0,1].axvline(-9, color='#777777', ls=':')
    axes[0,1].axvline(9, color='#777777', ls=':')
    fig.colorbar(pc, ax=axes[0,1], label='max_t[min面(T)] / ℃', shrink=.82)
    present=minimum>0
    axes[1,0].plot(positions[present], minimum[present], color=colours[0], lw=1.8)
    axes[1,0].axhline(1400, color='#9f3f3f', ls='--', label='QT与未稀释镍均完全液态1400℃')
    axes[1,0].axvspan(-9,9, color=colours[0], alpha=.06)
    axes[1,0].set(title='c  中央18 mm最弱面的热连接检查', xlabel='s = 74.98θ / mm', ylabel='各截面最弱面峰值 / ℃', xlim=(-10.5,10.5), ylim=(1200,2300))
    axes[1,0].legend(frameon=False, fontsize=7.2)
    axes[1,0].text(.03,.94, f'中央18 mm最低：{summary["central18mm_min_face_peak_C"]:.0f}℃', transform=axes[1,0].transAxes, va='top')
    state = None
    for path in sorted((folder/'nodal-thermal-history').glob('*.npz')):
        with np.load(path) as records:
            ids = np.flatnonzero(abs(records['time_s']-arc_end)<1e-8)
            if len(ids):
                state = records['temperature_C'][ids[0]].copy()
                break
    if state is None:
        raise RuntimeError('Actual accepted arc-end field missing')
    with np.load(folder/'mesh.npz') as mesh:
        triangulation, values, mat = plane_triangles(mesh['x'], mesh['e'], state, mesh['material'], inp['tracks'][0]['angle_end'])
    cloud = axes[1,1].tripcolor(triangulation, values, shading='gouraud', cmap='inferno', vmin=300, vmax=2800, rasterized=True)
    for material, threshold, colour in [(1,1180,'#59d3db'), (3,1400,'#f5f5f5')]:
        selected = tri.Triangulation(triangulation.x, triangulation.y, triangulation.triangles)
        selected.set_mask(mat!=material)
        contours = axes[1,1].tricontour(selected, values, levels=[threshold], colors=[colour], linewidths=1.1)
        axes[1,1].clabel(contours, fmt={threshold:f'{threshold}℃'}, fontsize=7)
    axes[1,1].set(title='d  收弧t=11.569 s端部截面瞬时温度', xlabel='径向坐标 r / mm', ylabel='轴向坐标 z / mm', xlim=(61,76), ylim=(102,116), aspect='equal')
    fig.colorbar(cloud, ax=axes[1,1], label='瞬时温度 / ℃', shrink=.82)
    for ax in axes.flat:
        ax.grid(alpha=.12)
    fig.suptitle('CI-A1连续首层：热连接、离散精度与基体重熔区\n110 A稳态，末1.2 s降至80 A；有效源及体积等效填充包络按保存输入', fontsize=12)
    destination = ROOT/'output/review/mma-continuous-end80-r12-20261007'
    destination.mkdir(exist_ok=True, parents=True)
    for extension in ('png','pdf','svg'):
        fig.savefig(destination/f'first-layer-thermal-connection.{extension}', dpi=300)
    print(destination/'first-layer-thermal-connection.png')


if __name__ == '__main__':
    run()
