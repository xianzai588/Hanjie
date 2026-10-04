"""Write the engineering verification section from completed, accepted runs."""
from pathlib import Path
import json
import math
import re
import yaml

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'simulation/competition-r4/results'


def main():
    verified = json.loads((RESULTS/'verification.json').read_text(encoding='utf8'))
    service = json.loads((RESULTS/'service-verification.json').read_text(encoding='utf8'))
    if not verified['position_design_pass'] or not service['static_service_design_pass']:
        raise ValueError('须先完成位置度离散精度与整件静载验证，不能发布未通过的设计结论')
    if not verified.get('bore_size_design_pass',False):
        raise ValueError('须先完成孔径尺寸链及有限微珩的孔轴预算')
    process = json.loads((RESULTS/'process-temperature-verification.json').read_text(encoding='utf8'))
    if not process['process_temperature_design_pass']:
        raise ValueError('段前温控条件尚未验证')
    peen=json.loads((RESULTS/'peening-verification.json').read_text(encoding='utf8'))
    if not peen['design_checks_pass']:
        raise ValueError('随动轻击温度时序或空间尚未通过')
    rows = verified['records']
    if len(rows) != 3:
        raise ValueError('需要三组完整冷态记录')
    inputs = [json.loads((RESULTS/case/'input.json').read_text(encoding='utf8')) for case in verified['cases']]
    for case in service['cases']:
        service_input = json.loads((RESULTS/case/'input.json').read_text(encoding='utf8'))
        if service_input.get('initial_bore_diameter_mm') != inputs[0]['initial_bore_diameter_mm']:
            raise ValueError('服役算例孔径与已接受焊接制造窗口不一致，须按相同实体孔径重算并核验')
    if any(not inp.get('fixture_thermal') for inp in inputs):
        raise ValueError('冷态工具参考家族不能替代芯/胀套及托垫热耦合的最终家族')
    if not verified.get('fixture_thermal_model_pass',False):
        raise ValueError('工装传热域尚未通过实际边界历程的离散复核')
    if any(Path(inp['seat_geometry']).name != '8P-R2-t15.step' for inp in inputs):
        raise ValueError('实际算例实体与当前15 mm设计不一致')
    peen_input=json.loads((RESULTS/peen['source_run']/'input.json').read_text(encoding='utf8'))
    peen_fine_input=json.loads((RESULTS/peen['fine_reference_run']/'input.json').read_text(encoding='utf8'))
    for key in ('materials','fusion_enthalpy_model','stage_sequence','travel_mm_s','net_W',
                'seat_geometry','source_r_mm','source_radius_mm','source_depth_mm',
                'copper_contact_W_m2K','copper_water_model','initial_bore_diameter_mm',
                'fixture_thermal','fixture_thermal_coupling_policy'):
        if peen_input.get(key)!=inputs[0].get(key):
            raise ValueError('轻击温窗与控形模型物理条件不同：'+key)
    if not peen.get('material_specific_fusion_enthalpy'):
        raise ValueError('轻击温窗未使用当前分材料热焓')
    carriers=[json.loads((RESULTS/case/'carrier-verification.json').read_text(encoding='utf8')) for case in verified['cases']]
    pads=[json.loads((RESULTS/case/'pad-contact-audit.json').read_text(encoding='utf8')) for case in verified['cases']]
    heads=inputs[0]['maximum_simultaneous_heads']
    stages=len(inputs[0]['stage_sequence'])
    mode='180°对向双头同步' if heads==2 else '单头对称跳焊'
    sequence=' / '.join('+'.join(str(v[1]+1) for v in stage) for stage in inputs[0]['stage_sequence'][:stages//2])
    fusion=inputs[0]['fusion_enthalpy_model']
    fusion_table='| 材料 | 固相线 / ℃ | 液相线 / ℃ | 潜热 / kJ·kg⁻¹ | 依据 |\n| --- | ---: | ---: | ---: | --- |\n'
    for name,prop,basis in zip(('Q235B','QT450-10','NiFe55'),fusion,('Q235文献设计数据[37]','球铁温区包络[38]；潜热工程估值','高镍低碳相图包络[39]；潜热工程估值')):
        fusion_table+=f"| {name} | {prop['solidus_C']:g} | {prop['liquidus_C']:g} | {prop['latent_heat_J_kg']/1000:g} | {basis} |\n"
    header = '| 项目 | ' + ' | '.join(f"h{r['h_mm']:g} / Δt{r['dt_s']:g}" for r in rows) + ' |\n| --- | ---: | ---: | ---: |\n'
    metrics = [
        ('节点 / 四面体', [f"{r['nodes']} / {r['tetrahedra']}" for r in rows]),
        ('热 / 结构步长，s', [f"{r['dt_s']:g} / {inp['structural_step_s']:g}" for r, inp in zip(rows, inputs)]),
        ('后期冷却结构步长，s', [f"{inp['cold_structural_step_s']:g}" for inp in inputs]),
        ('结构温增事件阈值，℃', [f"{inp['mechanical_event_temperature_increment_C']:g}" for inp in inputs]),
        ('最高节点温度，℃', [f"{r['peak_nodal_C']:.1f}" for r in rows]),
        ('孔壁最高节点温度，℃', [f"{r['bore_wall_peak_C']:.1f}" for r in rows]),
        ('铜环计算平均温度峰值，℃', [f"{r['copper_max_C']:.2f}" for r in rows]),
        ('钢壳密封带峰值，℃', [f"{r['seal_band_max_C']:.1f}" for r in rows]),
        ('能量闭合相对误差', [f"{abs(r['energy_balance_relative']):.2e}" for r in rows]),
        ('最大平衡残差，N', [f"{r['max_equilibrium_residual_N']:.4f}" for r in rows]),
        ('最大胀套反力，N', [f"{r['max_mandrel_reaction_N']:.1f}" for r in rows]),
        ('下托较大承压，MPa', [f"{p['maximum_pressure_MPa']:.2f}" for p in pads]),
        ('支承含根部径向弹性位移，μm', [f"{c['total_radial_axis_deflection_mm']*1000:.3f}" for c in carriers]),
        ('冷态解除壳底约束平衡残差，N', [f"{r['cold_shell_clamp_release']['release_equilibrium_residual_N']:.6f}" for r in rows]),
        ('冷态卸夹位置度直径，μm', [f"{r['fit']['position_diameter_mm']*1000:.3f}" for r in rows]),
        ('36点两点孔径范围，mm', [f"{r['fit']['sampled_bore_two_point_diameter_min_mm']:.5f}～{r['fit']['sampled_bore_two_point_diameter_max_mm']:.5f}" for r in rows]),
        ('较大截面两点尺寸差，μm', [f"{max(r['fit']['sampled_section_diameter_spreads_mm'])*1000:.3f}" for r in rows]),
    ]
    table = header + ''.join('| '+name+' | '+' | '.join(values)+' |\n' for name, values in metrics)
    spatial = verified['spatial_response_relative_error']*100
    temporal = verified['temporal_response_relative_error']*100
    worst = verified['thermal_position_worst_mm']
    budget = verified['position_budget_mm']
    bore = verified['bore_size_verification']
    after_finish = bore['post_finish_position_budget_mm']
    fixture_checks = verified['fixture_thermal_records']
    release = max(r['release_time_s'] for r in rows)
    measured = max(r['final_time_s'] for r in rows)
    station = stages*(18/inputs[0]['travel_mm_s']+inputs[0]['idle_s'])
    pallets = math.ceil((120+release+60)/station)
    ambient_buffers = math.ceil(max(0,measured-release)/station)
    steps = [f"{r['dt_s']:g}/{inp['structural_step_s']:g}/{inp['cold_structural_step_s']:g}" for r, inp in zip(rows, inputs)]
    target_statement = ('当前结果达到0.016 mm内部目标' if worst <= .016 else '当前结果高于内部目标而仍满足0.020 mm允许上限')
    section = f'''## 4 全件热—结构数值验证

### 4.1 模型、载荷与测量协议

模型采用当前15 mm座体、32处实际R2过渡、Q235B钢壳和八段两道焊缝。母材网格独立生成，焊接界面以16近邻仿射插值连接，常数和线性位移精确再现；三组均通过平移/转动补片检查。QT侧1.20 mm高镍层以导热率40 W/(m·K)的薄层边界表示，钢侧数值连接刚度按E/h缩放。制造孔径取{inputs[0]["initial_bore_diameter_mm"]:.3f} mm，压缩接触胀套按实际面积及90%六指覆盖计，100 N设定预载、500 N独立压环、1500 N密封径向载荷先行平衡。

热场采用隐式导热、温变导热率/比热及分材料熔化焓H(T)=∫Cp(T)dT＋L·f(T)；熔化区内f线性从0增至1，热切线和冷态出生扣焓采用同一焓函数。三种材料的设计输入如下，来料热分析在试制阶段复核批次差异。

{fusion_table}

NIST-JANAF在Ni/Fe各自熔点给出的固液焓差为17.155/13.807 kJ/mol，换算约292.3/247.2 kJ/kg；本件Ni含量55～58.23 wt.%的纯组元质量加权量级272.0～273.5 kJ/kg，NiFe取275作工程整定值。[40] 合金混合焓及次要组元差异由批次热分析复核。

高斯移动热源横向/深度半轴1.270/0.924 mm，中心半径74.8 mm；采用{mode}，每层阶段次序{sequence}，每头净功率495 W，第1焊段的根道与盖面均提高5%作为热输入不平衡工况，实际积分净热{rows[-1]['input_J']/1000:.2f} kJ。结构采用温变J2弹塑性、无应力单元出生及1200℃高温退火；1200℃为本构阈值，与熔化判据分开。材料出生、已观察高温退火状态、启停弧及温增均触发结构求解，三组已观察高温漏采体积均为0。新增焊材节点采用完备仿射位移续接，近邻云按16/32/64/128自适应扩展，所有出生事件坐标误差<10⁻⁷ mm及权重绝对值和≤4。铜环计26.02 J/K热容量、22℃进水、5.60 W/K有限水冷；孔内工装和铜环达到释放条件后撤除，壳体轴向基准底座保持至冷态，测量前再完全解除其约束并求平衡。

下托接触在真实QT底面上对三个Ø8圆盘积分，E200 GPa、钢垫高6 mm，只受压且允许抬离。均匀压缩、整体抬离及半盘倾斜均经解析校核；三组反力全部非负。由实际支承矩叠加轻击峰值，校核柱端横移、柱转角及螺栓/法兰柔度；整体承力链按§3.1的6.5 μm径向夹紧分配验收，基准转移、工装轴线和胀套定心各分配2 μm。局部背承压缩用于面积归一化接触刚度，整体轴移另计，不混用这两种柔度。

固定反锥、柱盘法兰、六指胀套、上承力筒及三个托垫采用六个周向分区的轴向有限体积传热域，按实际截面与热容量建模；工件—工具的换热包括接触热阻与脱离后的氩气间隙热阻。接触热导2000 W/(m²·K)为设计输入，试制通过热电偶资格确认。45钢及17-4PH热物性按供方资料选取，氩气热导按NIST数据插值。[31,46–48] 每个热增量保存真实工件温度与前一收敛位移边界，网络加密时使用相同边界重放；基准网络温度/膨胀先再现原耦合结果，再比较两倍轴向及周向划分。三组工装径向膨胀响应离散差最大{max(r['relative_growth_error'] for r in fixture_checks)*100:.2f}%，满足≤5%；工件网格及时间精度另见§4.2。工具温升和托垫差胀在结构接触间隙中逐步反馈，不作为始终20℃的刚性冷源。

QT测点按最终焊趾向内10 mm固定于R61、z115，盖面前另核对应根道温度。三组完整耦合运行直接记录全部16次起弧温度，段次及实际阶段时刻逐项核对；较大段前温度{process['maximum_start_C']:.2f}℃，满足首次15～35℃及后续≤100℃条件，名义18 s段间工序在该热模型下无需额外层间等待。热态轻击仍由焊道表面400～500℃信号触发，按WPS执行。

最终冷态评价另解壳底轴向约束的释放平衡，继承实际残余应力、累计塑性与界面连接刚度；从保存应力恢复的原状态平衡残差≤0.05 N，释放求解残差<0.001 N。模型只保留六个刚体坐标规范，其约束反力<0.1 N，不约束底面翘曲；原夹持场与完全卸夹场分别保存。基准A为实际变形后的壳体下端安装面，B以壳体z20/z180两带各24点建立、按A法向定向。孔壁z100/107.5/115三截面各12点；直线拟合轴及三个提取截面中心的包络取大值，避免平均拟合掩盖弯曲。不同网格采用相同36/48测点，而非各自网格节点数量。

### 4.2 完整冷却卸夹与收敛结果

{table}

表中三组采用同一分材料热焓、只受压下托接触和事件积分模型，材料、热源、焊序、装夹和水冷输入一致。固定h{rows[0]['h_mm']:g}网格，热/结构/后期冷却步长从{steps[0]}变为{steps[2]} s，位置度响应差为{temporal:.2f}%；固定{steps[0]} s，将母材网格h{rows[0]['h_mm']:g}改为h{rows[1]['h_mm']:g}，响应差为{spatial:.2f}%。两项均满足≤5%，同时满足冷态释放、能量闭合、非线性平衡、胀套5000 N承载限值及密封温控要求，停止继续细化。全件模型验证热收缩与控形；熔合、首次QT/Ni99界面组织和硬化按HJ-W-00/HJ-W-01的宏观截面、金相与硬度程序确认。

![相同测点的空间/时间复核与位置度预算](docs/report/figures/r4-mesh-budget.png)
![计算热历程、铜环平均温度和胀套反力](docs/report/figures/r4-thermal-contact.png)
![冷态卸夹位移与残余应力场](docs/report/figures/r4-residual-fields.png)

### 4.3 位置度预算与工程判定

径向分项为基准转移0.002、工装轴线0.002、胀套定心0.002、夹紧0.0065、搬运永久偏移0.0005、支点倾斜0.0010 mm，合计0.0140 mm。热残余允许上限由官方公差扣除非热分项及测量不确定度后得到直径0.020 mm，内部裕量目标为0.016 mm；{target_statement}。采用线性直径叠加，取三组较大热残余、同口径测量扩展不确定度，并为可选的短孔微珩另保留6 μm位置度直径变化量：

| 项目 | 直径口径 / μm |
| --- | ---: |
| 非热径向分项的2倍 | 28.000 |
| 较大FE热残余 | {worst*1000:.3f} |
| CMM扩展不确定度设计值 | 2.000 |
| 焊后精整前合成设计值 | **{budget*1000:.3f}** |
| 可选微珩的孔轴变化包络 | {bore['honing_position_allowance_mm']*1000:.3f} |
| 包含微珩的最终保守合成值 | **{after_finish*1000:.3f}** |
| 官方位置度上限 | **50.000** |

经理论计算与数值仿真验证，在设定工况及上述公差分配下满足焊后位置度≤Ø0.05 mm要求；建议后续试制通过A类实物试验完成最终工程验证。冷却至20±1℃、完全卸夹后先检位置度；孔径比较测量另在20±0.2℃执行，方法扩展不确定度≤0.5 μm。焊前制造窗口由40.006/40.008 mm两端实际实体及冷态结果确定，焊后孔径包络{bore['cold_diameter_envelope_before_finish_mm'][0]:.5f}～{bore['cold_diameter_envelope_before_finish_mm'][1]:.5f} mm。合格孔不精整；欠尺寸孔仅允许以现有孔轴稳向、Ø40.001定尺寸工具选择性微珩，局部单边去除≤3 μm、直径去除≤6 μm，精整后重新CMM和洁净检验，不以机加工纠正孔轴。[42,43]

### 4.4 冷却占用与工作站配置

三组取较长孔内工装释放时刻{release:.1f} s（从首次起弧计），到20±1℃测量状态的较长计算时刻{measured:.1f} s。焊接站名义工作{station:.1f} s；装配120 s、上提转运60 s为节拍设计输入。按N≥ceil[(120＋释放时刻＋60)/{station:.1f}]配置至少{pallets}套相同定位的固定反锥、水冷铜盘定位窝；释放前保持胀套、压环及规定水气条件，温度及回缩联锁通过后，打开上止挡并上提胀套260 mm，A托环保持壳底夹紧，壳体连托环上提140 mm后横移；反锥、铜盘、水路原位留置。另设至少{ambient_buffers}个带壳体轴向基准底座的环境冷却位，底座保持至20±1℃，随后解除底座并转入独立CMM；冷却位不继续使用已撤出的铜环水冷。单件历时与流水线出件间隔分别统计，现场温控等待计入实际节拍。

'''
    path = ROOT/'deliverables/report/technical-report-v4-unified.md'
    text = path.read_text(encoding='utf8')
    start = text.index('## 4 全件热—结构数值验证')
    end = text.index('## 5 载荷、疲劳与检测',start)
    text = text[:start]+section+text[end:]
    hot=peen['traces']
    gap=min(g['remaining_clearance_mm'] for g in peen['tool_geometry'])
    peen_section=f"""### 2.2 冷焊与随动热态轻击

TWI铸铁指南支持镍/镍铁填充、短焊道与趁热轻击[4]。本件将Ni99隔离、低热输入、≤100℃层间及缓冷共同执行；400～500℃为设计轻击窗口。18 mm焊段弧燃10.91 s，段首提前进入温窗，因此配置独立随动轴，在焊接过程中覆盖段首与段中，停弧后加速扫完段尾。枪与丝在停弧后0.20 s内同步上提40 mm，轻击结束后枪丝先升至120 mm，再升轻击头，随后抽吸刷净及转位。名义18 s段间时间包含上述动作，温控等待计入实用节拍。

| 工具与控制项 | 设计执行值 |
| --- | --- |
| 接触头及横臂 | Ø6圆头，Ø5 H13横臂；驱动位于R45、z123～135，Ø10竖向气动活塞 |
| 气压/频率/冲击力 | 0.2～0.4 MPa、100 Hz；驱动行程≤2 mm，首件三分量力传感校准，接触合力峰值≤200 N |
| 温度与响应 | 焊道表面400～500℃硬联锁；轨迹内部410～490℃；测温与指令总延迟≤20 ms |
| 接触形貌 | 首件实测接触宽0.72～1.09 mm、压痕深≤0.05 mm，无撕裂/剥离；沿程搭接≥75% |
| 运动与避让 | 扫尾速度≤18 mm/s、加速度≤300 mm/s²；枪未上提前沿程间距4.5～7.0 mm |
| 接触位置 | 根道R73.6/z116.4、盖面R73.0/z117.0；各段端部0.5 mm及QT母材/熔合线/焊趾不施击 |

按100 Hz、最小接触宽0.72及最大速度18，点距≤0.18 mm、重叠≥75%。供气压力不能直接代替冲击力；额定力、压痕宽深与温窗覆盖分别验收，缺信号或覆盖异常停止该段，不为轻击重新加热。气动尾气导入上排烟罩。

实际15 mm模型记录16段次，每段沿程0.5～17.5 mm均由其自身温度历程规划；轨迹上温度为{min(r['minimum_surface_C'] for r in hot):.1f}～{max(r['maximum_surface_C'] for r in hot):.1f}℃，最高扫尾速度{max(r['maximum_speed_mm_s'] for r in hot):.2f} mm/s、加速度{max(r['maximum_acceleration_mm_s2'] for r in hot):.1f} mm/s²，停弧后最长{max(r['completed_after_arc_s'] for r in hot):.2f} s完成覆盖。第一段根/盖面以{peen_input['dt_s']:g}/{peen_fine_input['dt_s']:g} s两级热步复核，温窗交叉时刻最大变化{max(peen['first_segment_time_crossing_difference_s']):.3f} s。温窗与控形计算采用相同孔径和工具热耦合条件；实机由逐点测温触发，首件按HJ-W-02校准测温、接触力及成形。

![真实热场的轻击温窗与随动轨迹](docs/report/figures/peening-temperature-timing.png)

根/盖面送丝棒端分别为R73.20/z116.00、R72.70/z116.70，棒材从电弧前侧进入，15 mm后导管转为竖直；枪—丝实际净隙2.169 mm。温窗所需间距内，实体采样并用运动位移上界补齐连续间距，扣除热态工作位姿误差合计0.10 mm及圆头径向热增长0.02 mm后，工具净隙下界{gap:.3f} mm；各工作落点标定误差≤0.05 mm。工具竖直上提由低位横臂/球心、喷嘴及远置驱动的轴向/径向分离约束保证。H13横臂按200 N峰值计算弯曲{peen['tool_arm_bending_MPa']:.1f} MPa、弹性挠度{peen['tool_arm_deflection_mm']:.3f} mm，低于600 MPa设计许用；驱动行程补偿横臂挠度，压痕深度由工件表面测量。工具材料参考Uddeholm H13原始技术数据[30]的45±1 HRC热态曲线，500℃屈服强度保守按900 MPa选材下限。

随动气动轻击架构可参照Li等[28]的装置控制思路，其TiCN熔覆性能不移植到本件；100 Hz气动往复技术参考MECCO/COUTH[29]，采购及工艺评定仍按本件圆头、热态力和压痕规格。全件位置度和疲劳核算不计轻击增益。Ni99前工序采用壳体外开放夹具和独立Z高度、直达圆头工具，按HJ-W-00/HJ-W-02确认自己的温窗覆盖，不套用组焊内腔轨迹。

"""
    pa=text.index('### 2.2 冷焊与');pb=text.index('## 3 接头、工装与洁净防护',pa)
    condition_end=text.index('TWI铸铁指南支持',pa)
    substrate_conditions=text[pa+len('### 2.2 冷焊与随动热态轻击\n\n'):condition_end]
    peen_section=peen_section.replace('### 2.2 冷焊与随动热态轻击\n\n',
        '### 2.2 冷焊与随动热态轻击\n\n'+substrate_conditions,1)
    peen_section=peen_section.replace('400～500℃为设计轻击窗口。',
        '400～500℃为本设计执行窗口，趁热轻击文献不等于已确定该材料组合的最佳温区。',1)
    text=text[:pa]+peen_section+text[pb:]
    for label,zone,material in [('QT槽根与座体','QT_slot_root','QT'),('NiFe焊缝','NiFe_weld','NiFe'),('Q235壳体','Q235_shell','Q235')]:
        row=(f"| {label} | {service['worst_zone_peaks_MPa'][zone]:.2f} | "
             f"{service['records'][0]['elastic_yield_screen']['allowable_MPa'][material]:.2f} | "
             f"{service['peak_response_relative_errors'][zone]*100:.2f}% |")
        text,count=re.subn(r'\| '+re.escape(label)+r' \|[^\n]+',row,text,count=1)
        if count!=1:raise ValueError('服役强度正文表未找到对应部位')
    text=text.replace('此表为40.014 mm孔径的已完成参考，最终服役验证须与接受的制造窗口同步重算。',
        f"此表按接受的制造孔径{inputs[0]['initial_bore_diameter_mm']:.3f} mm实际重算，并独立核验两级槽根网格。")
    window=bore['manufacturing_window_mm']
    size_paragraph=(f'主轴承孔焊前制造窗口为{window[0]:.3f}～{window[1]:.3f} mm，焊后目标40.000～40.025 mm。'
        '完全卸夹后先检焊后位置度，位置度不合格件不得用终镗纠正轴线。'
        '孔径在20±0.2℃以扩展U≤0.5 μm的方法判定，合格孔不精整；'
        '局部欠尺寸仅允许单边去除≤3 μm的选择性微珩，另留6 μm位置度变化包络，精整前后均CMM及洁净复检。'
        '制造两端由各自实际孔壁实体、完整热耦合和完全卸夹结果核验，尺寸链及空间/时间精度见§4。')
    text,count=re.subn(r'主轴承孔(?:当前)?焊前(?:制造)?窗口[^\n]+',size_paragraph,text,count=1)
    if count!=1:raise ValueError('制造孔径正文段落未找到；请先核对当前说明书')
    text=text.replace('孔40.010～40.014、座体外缘',f'孔{window[0]:.3f}～{window[1]:.3f}、座体外缘')
    support_thermal=max(r['maximum_support_thermal_height_spread_mm'] for r in fixture_checks)
    support_combined=max(r['combined_support_height_spread_mm'] for r in fixture_checks)
    support_text=(f'芯/胀套与三托垫的实际耦合热历程已积分到接触间隙；'
        f'两级工具传热域的三托垫高度差上界{support_thermal*1000:.3f} μm，'
        f'计制造等高极差2.5 μm后合计{support_combined*1000:.3f} μm≤3 μm。')
    text=re.sub(r'热态支点差及胀套导热、热膨胀另按接触热历程复核。\s*(?:冷工具参考家族的)?三托垫全增量温差[^\n]+',support_text,text,count=1)
    text=text.replace('完整工具热耦合家族正在核验，结果按§4固化，不以假定疲劳曲线单独裁决布局。',
        '完整工具热耦合、冷态卸夹、孔轴/孔径及空间时间精度按§4核验通过；后续试制按§5完成A类实物工程确认，不以假定疲劳曲线单独裁决布局。')
    path.write_text(text,encoding='utf8')
    design_path = ROOT/'project/competition-design.yaml'
    design = yaml.safe_load(design_path.read_text(encoding='utf8'))
    design['fixture']['manufacturing_bore_window_mm'] = bore['manufacturing_window_mm']
    design['precision']['bore_finish_strategy'] = '焊前孔40.006～40.008；焊后先验位置度；孔径测量20±0.2℃、U≤0.0005；40.000～40.025合格孔不精整；欠尺寸孔以现有孔轴稳向、40.001定尺寸工具选择性微珩，局部单边去除≤0.003、直径去除≤0.006；精整前后均CMM及洁净验收，禁止修正孔轴'
    design['precision']['post_weld_machining'] = '局部单边去除≤0.003、直径≤0.006；孔轴变化直径另分配0.006，精整前后独立CMM，不重镗、不修轴'
    design['precision']['finish_allowance_diameter_mm'] = [0,bore['maximum_allowed_diameter_stock_mm']]
    design['precision']['status'] = '公差设计分配及当前15 mm整件冷态位置度预算通过；空间/时间响应差分别≤5%；后续试制按CMM与重复装夹程序完成A类实物验证'
    design_path.write_text(yaml.safe_dump(design,allow_unicode=True,sort_keys=False),encoding='utf8')
    card_path=ROOT/'deliverables/process/bore-compensation-and-finish-card.md'
    card=card_path.read_text(encoding='utf8')
    card=card.replace('焊前40.006～40.008 mm为当前尺寸补偿核验窗口；须以完整冷态三组及同网格制造上下界的实际结果冻结。',
        '焊前40.006～40.008 mm制造窗口已经完整热耦合、冷态三组及同网格制造上下界计算核验；按本卡在后续试制完成A类实物工程验证。')
    card_path.write_text(card,encoding='utf8')
    print(f'已同步三组有效冷态结果：空间{spatial:.2f}%，时间{temporal:.2f}%，位置度合成{budget*1000:.3f} μm')


if __name__ == '__main__':
    main()
