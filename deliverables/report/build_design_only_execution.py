"""Render the executed precoat revision from actual phase/warmup results."""
from pathlib import Path
import csv
import json
import sys
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import colors
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate
from OCP.STEPControl import STEPControl_Reader
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
from OCP.BRepCheck import BRepCheck_Analyzer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src'))
from hanjie.reporting.fonts import register_project_fonts
from build_technical_report_pdf import build_story

RESULTS = ROOT/'simulation/competition-r4/results'
FIG = ROOT/'docs/report/figures'
SOURCE = ROOT/'deliverables/report/design-only-execution.md'
RENDERED = ROOT/'deliverables/report/design-only-execution-rendered.md'
OUT = ROOT/'output/pdf/无实物设计路线-预制修订审阅稿.pdf'


def main():
    names = ['design-precoat-warmup-200-r12-dt30', 'design-precoat-warmup-300-r12-dt30',
             'design-precoat-warmup-300-r12-dt15', 'design-precoat-warmup-300-r12-coarse-dt30']
    cases = {name:json.loads((RESULTS/name/'result.json').read_text(encoding='utf8')) for name in names}
    history = {name:np.loadtxt(RESULTS/name/'history.csv', delimiter=',', skiprows=1) for name in names}
    base, fine, spatial = names[1:]
    comparisons = []
    for other, label in [(fine, '时间30→15 s'), (spatial, '空间172862→60041单元')]:
        common = min(cases[base]['warmup_time_s'], cases[other]['warmup_time_s'])
        values = {name:np.array([np.interp(common, history[name][:,0], history[name][:,i])
                                for i in [2,3,6]]) for name in [base,other]}
        reference, alternative = values[base], values[other]
        field_error = float(abs(reference[:2]-alternative[:2]).max()/(reference[0]-20)*100)
        energy_error = float(abs(reference[2]-alternative[2])/reference[2]*100)
        time_error = abs(cases[base]['warmup_time_s']-cases[other]['warmup_time_s'])/cases[base]['warmup_time_s']*100
        gradient_error = float(abs(np.diff(reference[:2])[0]-np.diff(alternative[:2])[0])/np.diff(reference[:2])[0]*100)
        comparisons.append(dict(label=label, common_time_s=common, temperature_rise_error_pct=field_error,
                                absorbed_energy_error_pct=energy_error, warmup_duration_error_pct=time_error,
                                common_time_gradient_error_pct=gradient_error,
                                pass_within_5pct=bool(max(field_error, energy_error, time_error, gradient_error)<=5)))
    audit = dict(comparisons=comparisons,
                 warmup_convergence_pass=all(item['pass_within_5pct'] for item in comparisons),
                 full_cycle_gradient_below_10C=all(c['maximum_through_cycle_gradient_C']<=10 for c in cases.values()),
                 maximum_Cp_time_lag_energy_error_pct=max(c['Cp_time_lag_energy_error_pct'] for c in cases.values()),
                 scope='Oven warmup only; temperature endpoints compared at the same physical time. Not welding fusion, PMZ or manufacturing convergence.')
    destination = RESULTS/'design-precoat-warmup-verification.json'
    destination.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf8')
    phase_dir = RESULTS/'design-precoat-materials-20261006/gibbs-checked'
    phase = json.loads((phase_dir/'phase-summary.json').read_text(encoding='utf8'))
    fractions = list(csv.DictReader((phase_dir/'phase-fractions.csv').open(encoding='utf8')))
    phase_lines = ['| 输入情景 | 允许石墨固/液相线℃ | 抑制石墨固/液相线℃ |', '| --- | --- | --- |']
    def interval(values):
        return '～'.join(f'{value:.0f}' for value in values)
    for case in phase['cases']:
        stable, suppressed = [case['limits'][key] for key in ['graphite_allowed','graphite_suppressed']]
        phase_lines.append('| '+case['name']+' | '+interval(stable['solidus_grid_bracket_C'])+' / '+interval(stable['liquidus_grid_bracket_C'])+
                           ' | '+interval(suppressed['solidus_grid_bracket_C'])+' / '+interval(suppressed['liquidus_grid_bracket_C'])+' |')
    selected = [row for row in fractions if row['case']=='CI-A1-QT20' and row['limit']=='graphite_suppressed' and float(row['T_C'])==25]
    cementite = float(selected[0]['CEMENTITE_mass_fraction'])*100
    phase_decision = (f'CI-A1输入20% QT时，抑制石墨分支在25℃得到渗碳体质量分数{cementite:.2f}%；'
                      '与旧低碳裸镍配混结果不同，需重算首次层、低碳第二层和最终混合，不能继承原稿“高镍即免白口”的解释。'
                      f'嵌套Gibbs可行性复核结果：{"通过" if phase["Gibbs_branch_audit"]["nested_phase_feasibility_pass"] else "未通过"}。')
    geometry_dir = ROOT/'cad/generated/independent-precoat-curved'
    geometry = json.loads((geometry_dir/'geometry-audit.json').read_text(encoding='utf8'))
    reader = STEPControl_Reader()
    reader.ReadFile(str(geometry_dir/'precoat-stack-R15-R08.step')); reader.TransferRoots()
    explorer = TopExp_Explorer(reader.OneShape(), TopAbs_SOLID)
    valid_solids = []
    while explorer.More():
        valid_solids.append(BRepCheck_Analyzer(explorer.Current()).IsValid()); explorer.Next()
    if len(valid_solids)!=17 or not all(valid_solids):
        raise RuntimeError('Exported curved STEP does not contain 17 valid material solids')
    audit['exported_curved_STEP_valid_solids'] = len(valid_solids)
    destination.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf8')
    geometry_verification = (f'实际执行CAD布尔分区：首层体积{geometry["material_volumes_mm3"]["first_CI_A1"]:.3f} mm³，'
                             f'第二层{geometry["material_volumes_mm3"]["second_bare_Ni99"]:.3f} mm³；'
                             f'材料替换体积差{geometry["replacement_volume_error_mm3"]:.6f} mm³（相对{geometry["replacement_relative_volume_error"]:.3g}）。'
                             f'QT/首层几何曲面面积{geometry["QT_first_geometric_interface_area_mm2"]:.3f} mm²，'
                             f'第二层/QT共享面面积{geometry["second_QT_shared_face_area_mm2"]:.0f} mm²。'
                             f'导出的STEP中{len(valid_solids)}个材料实体均通过几何有效性检查。'
                             '名义4.0 mm焊脚径向内界R71.0与圆角平直切点R70.48之间有0.52 mm几何间隔，仍需结合焊趾偏差和实际重熔范围核查。')
    warm_lines = ['| 炉温候选 | 到温min | 末态QT最低/最高℃ | 全程最大温差℃ | 工件吸热kJ |', '| --- | --- | --- | --- | --- |']
    for name in names[:2]:
        case = cases[name]
        warm_lines.append(f'| {case["target_C"]:.0f}℃，12℃/min | {case["warmup_time_s"]/60:.2f} | '
                          f'{case["minimum_QT_C"]:.3f} / {case["maximum_QT_C"]:.3f} | '
                          f'{case["maximum_through_cycle_gradient_C"]:.3f} | {case["absorbed_sensible_kJ"]:.3f} |')
    convergence = ['| 复验 | 同时刻s | 温升响应差% | 吸热差% | 到温时间差% | 同时刻温差的相对差% |',
                   '| --- | --- | --- | --- | --- | --- |']
    for item in comparisons:
        convergence.append(f'| {item["label"]} | {item["common_time_s"]:.0f} | {item["temperature_rise_error_pct"]:.3f} | '
                           f'{item["absorbed_energy_error_pct"]:.3f} | {item["warmup_duration_error_pct"]:.3f} | {item["common_time_gradient_error_pct"]:.3f} |')
    convergence.append('预热离散复核'+('满足≤5%判据' if audit['warmup_convergence_pass'] else '有指标超过5%，尚需修订')+
                       f'；温变Cp步内冻结产生的积分蓄热差最大{audit["maximum_Cp_time_lag_energy_error_pct"]:.3f}%。'
                       '能量平衡检查之外另核查温度不超过炉温；这不等于焊接残余变形已收敛。')
    capacity = ['| 炉温候选 | 按231.3 s供料间隔的预热并行工位下界 | 计算依据 |', '| --- | --- | --- |']
    for name in names[:2]:
        case = cases[name]
        capacity.append(f'| {case["target_C"]:.0f}℃ | {math.ceil(case["warmup_time_s"]/231.3)} | 到温时间/供料间隔向上取整，不含装卸、预堆及缓冷 |')
    replacements = {'phase_table':'\n'.join(phase_lines), 'phase_decision':phase_decision,
                    'warmup_table':'\n'.join(warm_lines), 'warmup_convergence':'\n'.join(convergence),
                    'capacity_table':'\n'.join(capacity), 'geometry_verification':geometry_verification}
    text = SOURCE.read_text(encoding='utf8')
    for key, value in replacements.items():
        text = text.replace('{{'+key+'}}', value)
    if '{{' in text:
        raise RuntimeError('Unresolved report field')
    RENDERED.write_text(text, encoding='utf8')
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'], 'axes.unicode_minus':False, 'font.size':9})
    section = np.linspace(66.5,74.98,1700)
    def profile(radius):
        left = 70.48-radius
        curve = 115-np.sqrt(np.maximum(radius**2-(section-70.48)**2,0))
        return np.where(section<left,115,np.where(section<70.48,curve,115-radius))
    qt_top, first_top = profile(1.5), profile(.8)
    fig, ax = plt.subplots(figsize=(11.69,8.27))
    fig.subplots_adjust(left=.09,right=.95,bottom=.32,top=.85)
    ax.fill_between(section,112,qt_top,color='#b8bdc2',label='QT450-10')
    ax.fill_between(section,qt_top,first_top,color='#baa548',label='CI-A1首层，法向0.70')
    ax.fill_between(section,first_top,115,color='#6eafba',label='低碳Ni99第二层')
    ax.plot(section,qt_top,color='#333333',lw=1)
    ax.plot(section,first_top,color='#333333',lw=1)
    ax.plot([66.5,74.98],[115,115],color='#333333',lw=1)
    ax.axvline(71,color='#b34348',ls='--',lw=.8)
    ax.text(71.05,112.25,'4.0焊脚名义内界 R71.0',fontsize=10,color='#8c3434')
    for low,high,label in [(113.5,114.2,'0.70±0.05'),(114.2,115,'名义0.80')]:
        ax.annotate('',xy=(73.4,low),xytext=(73.4,high),arrowprops={'arrowstyle':'<->','color':'#222222'})
        ax.text(73.5,(low+high)/2,label,fontsize=10,va='center')
    ax.annotate('QT槽圆角 R1.50',xy=(69.3,float(np.interp(69.3,section,qt_top))),xytext=(66.7,113.65),
                arrowprops={'arrowstyle':'->'},fontsize=11)
    ax.annotate('首层修整面 R0.80',xy=(69.8,float(np.interp(69.8,section,first_top))),xytext=(66.7,115.6),
                arrowprops={'arrowstyle':'->'},fontsize=11)
    ax.annotate('',xy=(68.98,115.35),xytext=(74.98,115.35),arrowprops={'arrowstyle':'<->'})
    ax.text(71.98,115.42,'径向6.00；R68.98～R74.98',ha='center',fontsize=11)
    ax.set(xlim=(66.5,75.8),ylim=(112,116.1),xlabel='半径 / mm',ylabel='装配基准 z / mm')
    ax.set_aspect('equal'); ax.legend(loc='lower right',fontsize=10)
    fig.text(.09,.91,'HJ-DRW-017  独立预制与首层曲面修整名义断面',fontsize=18)
    fig.text(.09,.23,'槽深1.50±0.10；首层按法向保留0.70±0.05；最终连接面z=115齐平。',fontsize=11)
    fig.text(.09,.19,'尺寸链最小第二层0.65仅用于平直工作区；渐变处按真实曲面和有效传力范围检查。',fontsize=11)
    fig.text(.09,.15,'补图与曲面STEP配套使用。名义CAD材料分区已闭合，公差与焊接热/力验证另计。',fontsize=11)
    fig.text(.09,.08,'材料：QT450-10 / CI-A1类首层 / 低碳Ni99第二层    单位：mm    图类：设计补图',fontsize=10)
    fig.savefig(FIG/'design-precoat-normal-offset.png',dpi=180)
    fig.savefig(geometry_dir/'HJ-DRW-017-precoat-section.pdf',metadata={'Title':'HJ-DRW-017 独立预制名义断面','Author':''})
    fig.savefig(geometry_dir/'HJ-DRW-017-precoat-section.svg'); plt.close(fig)
    fig, axes = plt.subplots(1,2, figsize=(10,3.4), layout='constrained')
    for ax, name in zip(axes, names[:2]):
        data = history[name]
        ax.plot(data[:,0]/60, data[:,1], '--', color='#555555', label='炉温')
        ax.plot(data[:,0]/60, data[:,2], color='#1f7789', label='QT最低')
        ax.plot(data[:,0]/60, data[:,3], color='#b34348', label='QT最高')
        ax.set(xlabel='时间 / min', ylabel='温度 / ℃', title=f'{cases[name]["target_C"]:.0f}℃，12℃/min')
        ax.grid(alpha=.2); ax.legend()
    fig.savefig(FIG/'design-precoat-warmup.png', dpi=220); plt.close(fig)
    fig, axes = plt.subplots(1,2, figsize=(10,3.4), layout='constrained')
    for ax, limit in zip(axes, ['graphite_allowed','graphite_suppressed']):
        for product, colour in [('CI-A1', '#1f7789'), ('CI-A2', '#b34348')]:
            data = [row for row in fractions if row['case']==product+'-QT20' and row['limit']==limit]
            ax.plot([float(row['T_C']) for row in data], [100*float(row['CEMENTITE_mass_fraction']) for row in data],
                    color=colour, label=product+'+20% QT')
        ax.set(xlabel='温度 / ℃', ylabel='渗碳体质量分数 / %',
               title='允许石墨的平衡分支' if limit=='graphite_allowed' else '抑制石墨的亚稳分支')
        ax.grid(alpha=.2); ax.legend()
    fig.savefig(FIG/'design-precoat-phase.png', dpi=220); plt.close(fig)
    with np.load(RESULTS/base/'warmup-state.npz') as data:
        x, faces, T = data['x'], data['boundary_faces'], data['temperature']
    fig = plt.figure(figsize=(9,4.5), layout='constrained'); ax = fig.add_subplot(projection='3d')
    norm = colors.Normalize(vmin=float(T.min()), vmax=float(T.max()))
    collection = Poly3DCollection(x[faces], facecolors=plt.cm.viridis(norm(T[faces].mean(axis=1))), linewidths=0)
    ax.add_collection3d(collection)
    ax.set(xlim=(-80,80), ylim=(-80,80), zlim=(99,116), xlabel='x / mm', ylabel='y / mm', zlabel='z / mm')
    ax.set_box_aspect([160,160,17]); ax.view_init(elev=32, azim=-45)
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap='viridis'), ax=ax, shrink=.75, label='QT表面温度 / ℃')
    fig.savefig(FIG/'design-precoat-warmup-field.png', dpi=220); plt.close(fig)
    register_project_fonts(ROOT)
    def footer(canvas, doc):
        canvas.setFont('HanjieCN', 8)
        canvas.drawString(20*mm, 12*mm, '工艺设计修订稿 / 预制热制度与材料连接')
        canvas.drawRightString(A4[0]-20*mm, 12*mm, str(doc.page))
    document = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=20*mm, rightMargin=20*mm,
                                 topMargin=17*mm, bottomMargin=19*mm,
                                 title='无实物工艺设计路线：独立预制修订', author='',
                                 subject='焊接固定命题工艺设计计算与规程修订')
    document.build(build_story(RENDERED), onFirstPage=footer, onLaterPages=footer)
    print(json.dumps({'pdf':str(OUT), 'warmup_verification':audit}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
