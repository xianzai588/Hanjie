from pathlib import Path
import json,yaml,sys
ROOT=Path(__file__).resolve().parents[2]
r=json.loads((ROOT/'studies/COMPETITION-DESIGN/results/assessment.json').read_text(encoding='utf8'));p=r['process'].copy()
baseline=yaml.safe_load((ROOT/'project/submission-baseline.yaml').read_text(encoding='utf8'))
layout=baseline['weld_layout'];current_process=baseline['final_GTAW']
forming=json.loads((ROOT/current_process['local_forming_source']).read_text(encoding='utf8'))
# Old assessment supplies unchanged fixture dimensions only; process numbers use the finite current decision.
capacity=json.loads((ROOT/'studies/COMPETITION-DESIGN/results/delivery-joint-capacity-20261008.json').read_text(encoding='utf8'))
p.update(actual_weld_length_per_pass_mm=layout['length_per_pass_mm'],effective_connection_length_mm=layout['effective_length_per_pass_mm'],
         actual_segment_length_mm=layout['segment_length_mm'],stable_segment_length_mm=layout['effective_segment_length_mm'],
         total_actual_path_mm=layout['total_arc_length_mm'],start_transition_mm=layout['start_allowance_mm'],end_transition_mm=layout['end_allowance_mm'],
         minimum_area_mm2=current_process['minimum_total_leg_mm']**2/2,
         total_net_heat_j=current_process['net_energy_kJ']*1000,arc_on_time_s=current_process['nominal_arc_time_s'],
         wire_length_mm=current_process['nominal_wire_consumption_length_mm'],
         fixed_feed_mm_s=current_process['wire_feed_mm_s'],feed_role=current_process['wire_feed_role'],
         pass_feed_mm_s=current_process['pass_feed_mm_s'],
         area_range_mm2=forming['total_tolerance_ranges']['total_section_area_mm2'],
         deposited_volume_range_mm3=[area*layout['length_per_pass_mm'] for area in forming['total_tolerance_ranges']['total_section_area_mm2']],
         equivalent_leg_range_mm=forming['original_comparison']['revised_equivalent_total_equal_leg_range_mm'])
r['spec']['process']['minimum_leg_mm']=current_process['minimum_total_leg_mm']
r['spec']['process']['nominal_leg_mm']=current_process['nominal_leg_mm']
r['spec']['process']['minimum_effective_throat_mm']=current_process['minimum_total_leg_mm']/2**0.5
r['spec']['process']['stable_segment_length_mm']=layout['effective_segment_length_mm']
fixture=r['spec']['fixture']
regime=r['spec']['thermal_regime']
bore=fixture.get('candidate_manufacturing_bore_window_mm',regime['candidate_manufacturing_bore_window_mm'])
bore_state='' if fixture.get('manufacturing_bore_window_state')=='verified_current_window' else '（候选核验窗，未冻结）'
finish_strategy=r['spec']['precision']['bore_finish_strategy']
card=f'''# 主轴承座—壳体连接 pWPS 工艺规程卡

赛道：中铁山桥杯焊接固定题。规程号HJ-W-01，修订13（高镍预制—8P组焊—铜环屏障主线）。适用Q235B壳体5 mm、QT450-10座体15 mm、Ø40孔、8×18 mm实际路径的间断角焊缝（稳定有效8×16 mm）。内容按ISO 15609-1组织。首次QT界面采用HJ-W-00C/00D的CI-A1高镍MMA主线；铁素体主导、珠光体≤20%、无原始白口网为项目来料窗口，按独立预制卡确认。采用状态见current-candidate-state.md。

本卡为最终组焊候选基线。旧300 J/mm完整控形家族未通过，285 J/mm显式接头出现连续熔合缺口；按HJ-W-00C/00D先确定独立预制及保留层，再确定最终双侧连接，不将填充面积作为有效承载面积。采用窗口完成后同步本卡，车间试制按规定的工程确认形成生产WPS。

| 项目 | 规定 |
| --- | --- |
| 接头与位置 | 内周上表面角焊缝，八段等分45°；壳体轴线竖直、工件固定，机器人绕轴移动，焊枪保持平/横角焊位置；稳定区焊脚≥3.80（名义4.00），最大几何包络4.30 |
| QT预制过渡层 | 八处全翼宽×径向6、槽深1.50±0.10、QT圆角R1.5，外缘贯通R74.98。MMA首层按法向修整0.70±0.05，同心R0.80，再加低碳裸Ni99第二层。齐平总层1.40～1.60，平直区第二层≥0.65；根道候选≤0.30、累计≤0.40时几何总残层≥1.00、第二层≥0.25。圆角、实际混合带与重熔同截面核查，几何厚度不等于低碳区 |
| 前工序 | 铸件→独立MMA首层→冷态中间修整→低碳第二层→保温缓冷/延迟PT→连接面及孔加工→清洗干燥→入壳组焊。预制、切削和后续残余状态连续传递 |
| 表面准备 | 铸皮、油污、氧化层去除；镍层、钢侧连接面露出洁净金属；脱脂剂完全挥发，不在封闭内腔内打磨；焊前入腔物料清点 |
| 组装 | 孔{bore[0]:.3f}～{bore[1]:.3f}{bore_state}；座体底面z100；外缘149.94～149.98、壳体内径150.00～150.02；径向间隙0.01～0.04；胀套对独立壳体基准定心 |
| 方法/极性 | 自动脉冲GTAW（TIG），DCEN；不使用焊剂，禁止以低飞溅替代颗粒防护 |
| 焊材 | NiFe55 TIG实心棒Ø1.60±0.01；供方典型Ni55、C0.01、Si0.13、Mn0.70 wt%；按实际产品供货分类及证书订货，禁止把药皮焊条分类直接当作TIG牌号 |
| 电极/气体 | W-La20 Ø2.0，尖端角60°，平顶0.3；喷嘴Ø10，弧长2.5±0.5；99.999% Ar 10 L/min，许可8～12 |
| 脉冲 | 峰值100 A / 基值50 A；占空50%；20 Hz；平均75 A；名义12 V；须采样瞬时U(t)I(t)积分，禁止仅乘两个平均值作为在线能量 |
| 焊速/填充 | 焊速1.65 mm/s±2%；根道3.42±0.05、盖面3.78±0.05 mm/s，分辨率≤0.01；沉积效率设计0.90～0.98，由宏观截面及增重确认 |
| 成形 | 两道：根道名义目标焊脚2.8（供料角点等效2.675～2.926），盖面至名义4.0；稳定16 mm内两侧焊脚均≥3.80 mm、有效喉厚≥2.687006 mm及双侧连续熔合。两道填充面积7.539～9.007 mm²，等效焊脚3.883～4.244；理想最差等腿喉厚余量58.677 μm。实际自由面及两趾满足x≥0、y≥0、x+y≤4.30 mm（坐标与轮廓验收见下文）；总供料不代替局部成形保证 |
| 线能量 | 候选基线毛弧能545.45 J/mm；在线逐段目标偏差≤±2%，按瞬时U(t)I(t)积分并除以实际焊长；设计η电弧0.55，名义净300 J/mm，全件名义净{p['total_net_heat_j']/1000:.2f} kJ；250～350 J/mm为候选评定范围，变更能量点须复核控形与工艺评定，生产窗口以首件评定记录冻结；η为热模型输入 |
| 焊序 | 根道1→5→3→7→2→6→4→8，盖面同序；实际各18 mm，段内不摆动；起弧和收弧过渡各1 mm均在18 mm内，排除两端后稳定有效16 mm/段、合计128 mm。不得延长至翼外；端区和弧坑逐段检查；段间枪/丝上提150 mm并确认后转位，后吹许可按HJ-C-03 |
| 自动跟踪 | 起弧前视觉核对C周向段标记和0.01～0.04 mm装配间隙；激光横向跟踪偏差≤0.05 mm，分辨率≤0.01 mm，更新≥50 Hz；偏差越限或信号中断立即停弧，保持工装与防护；指标为设备选型设计值，首件校准确认 |
| 温控 | 组焊不预热；起焊15～35℃；每段焊前测QT侧按最终成形焊趾向内10 mm布置的固定测点（名义R61、z115）及本段前道邻近测点，全部≤100℃；缺信号或超温禁起弧，等待至≤90℃再恢复 |
| 最终轻击 | 现行主工艺不启用；原随动轻击参数保存在HJ-W-02可编辑历史卡，不进入本卡操作、节拍或性能通过依据 |
| 清理与防护 | 层间用专用刷与顶部局部抽吸清理，禁止腔内磨削；刚性盘＋四瓣水冷铜环＋闭合上圈及独立整环下圈截留颗粒；铜瓣接缝2.00±0.05，滑动桥详图HJ-010；气幕10～15、顶部抽吸22～28、补氩0～12 L/min；开口腔近大气压，气幕歧管表压0.25～2.8 kPa/流量10～15 L/min双联锁，铜环≤45℃、下座≤48℃、壳体密封带≤180℃；水≥0.60 L/min，入口20±2℃，水路独立检漏；抽口退位、前吹30 s/后吹15 s及最后保持120 s按HJ-C-03 |
| 装夹与卸夹 | 径向预载≤100 N；机械止挡承受热反力，额定5000 N；独立压环装机总力500±20 N；密封径向装夹力≤1500 N。最后停弧≥120 s且热区<55℃，枪/丝上提150 mm→副压环独立升150 mm、到位及正向销锁确认→上止挡张开并确认→胀套正向上退1 mm→四瓣铜环/密封径向回缩1.10±0.05并确认全周净隙≥0.10→胀套上提260→关闭补氩，四抽口径退15至R93并锁止、四反馈确认→六指接管托环并锁止→定位窝三锁释放→A托环保持壳体夹紧、壳体连托环上提140；盘原位朝上，气幕到上提140完成后关闭、退态抽吸不计工作位捕烟 |
| 精度检查 | 20±1℃、完全卸夹，A为壳底实际端面、B为z20～30/170～180两带；3截面×12点只作快速找正。最终以5截面连续圆扫描＋4条轴向母线、独立基准拟合，直轴与截面中心包络取大；首件用同次密集点云比较步距/相移重采样，差≤0.1 μm后冻结步距，独立复测重复性另计U；位置度＋扩展U≤0.05；位置度方法U资格≤2 μm，设计分账约1.64 μm，基准/步距按HJ-M-02；容量规划360 s/件 |
| 尺寸精整 | {finish_strategy}；细则及测量护栏见HJ-Q-03 |
| 异常处理 | 断丝、能量越窗、温度/气流/夹紧缺信号、漏水立即停弧；保留工装和防护，故障件隔离；漏水/缺水/失电/卡滞的阀位、机械保持及人工退出按HJ-C-03；返修须有独立评定，禁止自动补焊掩盖裂纹 |

名义弧燃{p['arc_on_time_s']:.1f} s，耗丝{p['wire_length_mm']:.1f} mm；加夹持起停损耗按15%备料。生产节拍按焊接、后吹/清理转位、冷却占用及检测资源逐项计算。
'''
selected=capacity['rows']['8P_leg_3.8']
card+=f"\n## 稳定焊长与承载修订\n\n外缘每翼18 mm含两端各1 mm过渡，承载按128 mm稳定长度，热量和耗丝按两道288 mm实际路径。稳定区最低焊脚3.80、名义4.00，现行分道供丝体积对应几何范围3.882983～4.244292 mm；几何充填与有效熔合喉部分别核对。\n\n5 kN径向、5 kN轴向、250 kN·mm下，轴向正应力与弯曲正应力叠加，静承载需求{selected['required_nominal_static_capacity_MPa']:.6f} MPa。原两设计谱在30 MPa@2×10^6、m=3接头资格目标下条件Miner值{selected['conditional_Miner_at_30MPa_target']:.6f}；参考范围需求{selected['required_reference_range_MPa_at_2e6']:.6f} MPa。此曲线为资格目标，非实测寿命。来源delivery-joint-capacity-20261008.json。\n"
card+='''
## 局部成形与轮廓验收

以实测钢内壁与加工后座体上平面交点为虚拟根，x为向内径向距离、y为向上高度，记录实际0.01～0.04 mm装配间隙。每段稳定16 mm的起/中/末截面核对两侧焊脚、实际自由面、根部及两侧熔合；段端各1 mm另检。

两侧焊脚测量值分别减其U后均≥3.80 mm。实际自由面含外向不确定度应在x+y≤4.30 mm现行可达性包络内。确认根部到实际自由面的最短距离减U≥2.687006 mm；采用弦距a0与法向凹陷c作充分判据时，a0−c−U合成≥2.687006 mm。几何合格后仍检查双侧连续熔合、裂纹及不可计承载缺陷，再登记有效喉部。

本次唯一根/盖分道修订为3.42/3.78±0.05 mm/s，平均3.60只作总量核算。旧3.68对照只排除其指定脚比/轮廓组合，不代表所有轮廓不可行。两道面积7.538777～9.007008 mm²；直线轮廓脚比联合上界由低面积1.044152变为高面积1.026423，等腿抛物凹面凹度界相应0.184273/0.058704 mm，仅为指定几何族反算，不能作为独立制造波动窗。低供料非喉部面积余量0.318777 mm²；0.04 mm间隙若填满15 mm高度需0.600 mm²，这是几何对照，实际下流、母材参与及局部迁移未赋值。根/盖名义进入丝焓5.505～5.994/6.085～6.625 kJ，从各43.2 kJ净热扣一次；较原总进入焓多0.322～0.351 kJ。原重熔候选限根0.30、两道并集0.40 mm及第二层存留0.25 mm的几何预算保持，热账变化后须另获熔合/留层资格。来源C25与C29。
'''
r['spec']['process']['contour_envelope_source']=current_process['local_forming_source']
r['spec']['process']['pass_feed_mm_s']=current_process['pass_feed_mm_s']
r['spec']['process']['feed_policy']='根3.42/盖3.78±0.05 mm/s，平均3.60只作总量核算'
r['spec']['process']['feed_nominal_mm_s']=current_process['wire_feed_mm_s']
r['spec']['process']['local_forming_verified']=False
r['spec']['process']['geometric_keepout_equation']='x>=0,y>=0,x+y<=4.30 mm from virtual root'
r['spec']['process']['feed_3p68_contrast_adopted']=False
out=ROOT/'deliverables/process';(out/'joint-process-card.md').write_text(card,encoding='utf8')
(out/'joint-process-card.json').write_text(json.dumps(dict(version='DELIVERY-8P-20261008',process=p,spec=r['spec']['process'],capacity_source=baseline['verification']['current_joint_capacity_source']),ensure_ascii=False,indent=2),encoding='utf8')
if '--current-only' not in sys.argv:
    (out/'cold-weld-and-peening-card.md').write_text("""# HJ-W-02 可编辑历史：选配随动轻击专项卡

    本卡保留原设备储备设计与输入身份，当前主工艺不执行，不进入HJ-W-01操作指令、节拍或性能通过依据。另行启用时单独确认温度、覆盖与冲击条件。

    原HJ-W-01储备情景为两道八段。组焊不预热，段前及层间≤100℃；每段18 mm、弧燃10.91 s，轻击轴独立随动。工具按原轻击历史图归档，现行HJ-009已改为顶部抽吸接口；轨迹与16段次温度窗口保留在35-随动轻击验证.json历史结果中。

    | 项目 | 执行要求 |
    | --- | --- |
    | 工具 | Ø6圆头，Ø5 H13横臂；Ø10远置竖向气动驱动，R45、z123～135；工作段热态允许弯曲应力设计600 MPa，45±1 HRC；圆滑无棱、无镀层剥落 |
    | 力与频率 | 0.2～0.4 MPa；100 Hz；驱动行程≤2 mm，首件三分量力传感校准并限制接触合力峰值≤200 N，不能将供气压力直接当冲击力 |
    | 成形 | 实测压痕接触宽0.72～1.09、深≤0.05 mm；100 Hz下扫尾速度≤18 mm/s、加速度≤300 mm/s²，沿程重叠≥75%；首件宏观确认无撕裂/剥离 |
    | 温度 | 校准红外逐点跟随接触位置，400～500℃硬联锁，410～490℃作为轨迹规划内部窗口；测温/指令总延迟≤20 ms，缺信号/超窗/缺覆盖停段复核，不强行再热 |
    | 位置 | 根道接触R73.6/z116.4；盖面R73.0/z117.0；只作用于熔敷金属中部，离QT母材/熔合线/焊趾及段端各≥0.5 mm；有效沿程0.5～17.5 mm |
    | 动作 | 随焊接在段中进行轻击；停弧后0.20 s内枪与丝同步上提40 mm，轻击轴加速扫完段尾；结束后枪丝先升至120 mm，再升轻击头，随后抽吸刷净及转位 |
    | 联锁 | 未上提期间枪—锤沿程间距4.5～7.0 mm；独立周向轴和测温跟踪，禁止机械固定间距导致段尾漏覆盖；气动尾气导入上排烟罩，不向内腔吹散颗粒 |

    名义18 s段间工序包括扫尾、清理与转位；温控等待计实际占用。首件用接触热电偶校准红外发射率与响应，同时记录接触力、压痕宽深及温窗覆盖。锤击促使热态焊缝局部塑性延展；整件有限元及疲劳核算均不计轻击增益。A类评定量残余应力、金相与裂纹状态，按HJ-Q-01检测并清洁后测孔轴。

    独立高镍预制按HJ-W-00C/00D在壳体外执行。CI-A1首层按供方道后趁热轻击熔敷金属，不击QT或熔合线；第二层的工具与温度按对应工序确定。本卡最终GTAW的400～500℃候选窗口不移用于预制，也不计未经验证的锤击强度或应力减益。预制冷却、延迟PT和中间修整按独立卡执行。
    """,encoding='utf8')
print('当前pWPS已重建；历史轻击卡仅在非current-only模式写出')


# HJ-W-00 remains a saved comparison; HJ-W-00C/00D are maintained separately.
if not (out/'Ni99-transition-pWPS.md').exists():
    raise FileNotFoundError('maintained HJ-W-00 process card required')
print('HJ-W-00 historical comparison preserved; current precoat uses HJ-W-00C/00D')
