"""Freeze the engineering proposal separately from historical thermal inputs."""
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'project/competition-design.yaml';s=yaml.safe_load(p.read_text(encoding='utf8'))
s['version']='COMPETITION-R3'
s['layout']='8P-FAIR_B'
s['geometry_manifest']='simulation/structural-v4/models/8p-fair-b/geometry-manifest.json'
s['seat_brep']='simulation/structural-v4/models/8p-fair-b/8P-FAIR_B.brep'
s['process_source']='project/process-r3.yaml'
s['process'].update(pass_count=2,feed_nominal_mm_s=3.5,feed_tolerance_mm_s=.05,
 sequence=[1,5,3,7,2,6,4,8],
 wire_diameter_tolerance_mm=.01,travel_relative_tolerance=.02,deposition_efficiency_range=[.9,.98],clearance_leg_mm=4.3,
 feed_policy='送丝3.50±0.05 mm/s，实际分辨率≤0.01；速度与丝径公差均入守恒边界',
 filler_candidate='Ni99预制隔离层＋NiFe55两道承载焊；隔离层制作在轴承孔最终精加工之前')
s['thermal_regime'].update(design_basis='选择不预热短段冷焊，局部温度与卸夹位移由当前整件计算评价；预制Ni99层抑制QT侧直接稀释',
 preheat_policy='组焊不预热；Ni99预制堆焊是独立前工序，之后完成精加工及来料检验',
 shielding='停弧后维持装夹；按温度门控退出；铜环冷却保持低流量，避免强制骤冷')
for k in ['temperature_gradient_for_full_radial_limit_k','component_temperature_rise_k']:
 s['thermal_regime'].pop(k,None)
s['peening'].update(mechanism='热态轻击使焊缝局部塑性延展，减轻收缩拉应力；强度与位置度计算不计锤击增益',
 coverage='仅熔敷焊道中部；与QT母材、熔合线、焊趾各留≥0.5 mm，禁止直接敲击脆硬HAZ',
 acceptance='无撕裂、剥离；压痕深度≤0.05 mm；首件确定最低有效气压，不追求深麻点',
 air_pressure_mpa=[.2,.4],sequence='两道×八段；实测400～500℃才轻击，超出窗口则跳过并记录，不为锤击二次加热',
 lower_prohibited_below_c=400)
s['fixture'].update(radial_force_limit_n=100,radial_force_limit_scope='装夹预载≤100 N；热收缩反力另按胀套/芯轴结构强度校核',
 contact_bands_z_mm=[[100.2,111.8]],
 finger_thickness_mm=.8,finger_length_mm=30,finger_count=6,finger_width_mm=19,
 mechanical_backstop='芯轴到位后机械止挡承受热收缩反力；气缸用于预载及正向回退')
s['shield'].update(ring_inner_radius_mm=71.8,ring_outer_radius_mm=74.8,ring_wall_thickness_mm=3,
 seal_radial_thickness_mm=.3,ring_bottom_z_mm=94,ring_top_z_mm=99,
 ring_contact_mode='铜环OD149.60；环缘可更换0.30 mm厚耐热石英纤维密封；分体径向回缩0.5 mm后下撤',
 ring_material='C11000；水冷通道Ø2.0，0.20 L/min，入口20±5℃；接触导热取设计范围500～2000 W/(m²K)',
 design_basis='刚性接料盘及静态密封阻断落屑路径，气幕辅助吹扫；不以气流阻止所有颗粒')
s['shield']['gas_curtain'].update(inlet='盘下环形气道3×2，12孔Ø1.0朝上；接头M5，独立于水路',
 outlet='顶部封闭罩，抽气22～28 L/min；护气8～12＋气幕10～15合计18～27',
 pressure_mode='罩外补气，腔内压差保持0～+20 Pa；不抽空保护区')
s['precision'].update(finish_allowance_diameter_mm=[0,0],bore_finish_strategy='焊前孔40.010～40.018；焊后先验位置度，孔径合格不精整；仅在孔径低于40.020时定尺寸微珩，最终≤40.025',
 post_weld_machining='不预留固定余量；不得以机加工修正孔轴；微珩尺寸增量≤min(0.005,40.025−实测孔径)')
p.write_text(yaml.safe_dump(s,allow_unicode=True,sort_keys=False),encoding='utf8')
nom=yaml.safe_load((ROOT/'project/process.yaml').read_text(encoding='utf8'))['process']['nominal']
nom.update(travel_speed_mm_s=1.65,heat_input_j_per_mm=300,preheat_c=20,interpass_limit_c=100,filler_feed_rate_mm_s=3.5,filler_diameter_mm=1.6,
 pulse_peak_a=100,pulse_base_a=50,pulse_duty=.5,pulse_frequency_hz=20)
(ROOT/'project/process-r3.yaml').write_text(yaml.safe_dump({'version':'PROCESS-R3','process':{'nominal':nom}},allow_unicode=True,sort_keys=False),encoding='utf8')
r=ROOT/'project/report.yaml';cfg=yaml.safe_load(r.read_text(encoding='utf8'));cfg['pdf']['page_footer']='中铁山桥杯 · 焊接工艺设计固定题';r.write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf8')
print('两道脉冲TIG、硬件公差、预制镍层及无占位代码的配置已写入')

