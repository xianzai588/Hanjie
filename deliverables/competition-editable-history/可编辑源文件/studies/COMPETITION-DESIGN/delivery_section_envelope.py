"""Finite analytical section review of the frozen 8P joint and one feed contrast.

This script reads saved geometry and supply results. It does not create new CAD,
run a heat solver, assign fusion, or modify the pWPS. Profiles are mathematical
design sections, not micrographs. The parabolic cases preserve deposited area.
"""
from pathlib import Path
import json
import math

import yaml
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "studies/COMPETITION-DESIGN/results"
FIG = ROOT / "docs/report/figures/delivery"
NAME = "section-forming-envelope-20261008"
WIRE_SOURCE = "simulation/competition-r4/results/explicit-ni99-wing285-r749-z11535-w08-d05-t14-h15-lh05-dt0125-i05-hot1470/input.json"
WIRE_AUDIT = str(Path(WIRE_SOURCE).with_name("wire-energy-audit.json")).replace("\\", "/")


def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def straight(area, ratio):
    x, y = math.sqrt(2 * area * ratio), math.sqrt(2 * area / ratio)
    return dict(leg_long_mm=x, leg_short_mm=y, ratio=ratio,
                geometric_throat_mm=x*y/math.hypot(x, y),
                section_area_mm2=area, max_coordinate_sum_mm=max(x, y))


def parabola(area, ratio, sag):
    """Signed sag: positive concave, negative convex; exact supplied area.

    Face P(t)=(1-t)(x,0)+t(0,y)-4*sag*t*(1-t)*n.
    Its area is xy/2 - (2/3)*sag*sqrt(x*x+y*y). The throat
    is found from the cubic derivative of |P(t)|^2, with both endpoints.
    No parameter search or discretized geometry is used for the result.
    """
    cr = math.sqrt(1 + ratio*ratio)
    b = (2/3)*sag*cr
    y = (b + math.sqrt(b*b + 2*ratio*area))/ratio
    x = ratio*y
    chord = math.hypot(x, y)
    ac = x*y/chord
    t0 = x*x/(chord*chord)
    normal = np.array([y, x])/chord
    # D(t) = (ac - 4*sag*t + 4*sag*t*t)^2 + chord^2*(t-t0)^2.
    u = np.polynomial.Polynomial([ac, -4*sag, 4*sag])
    v = np.polynomial.Polynomial([-chord*t0, chord])
    d2 = u*u + v*v
    roots = d2.deriv().roots()
    ts = [0., 1.] + [float(t.real) for t in roots if abs(t.imag) < 1e-9 and 0 < t.real < 1]
    throat = math.sqrt(min(float(d2(t)) for t in ts))
    # x(t)+y(t) is also quadratic. Inspect endpoints and its stationary point.
    sums = np.polynomial.Polynomial([x, y-x-4*sag*normal.sum(), 4*sag*normal.sum()])
    stationary = sums.deriv().roots()
    ss = [0., 1.] + [float(t.real) for t in stationary if abs(t.imag) < 1e-9 and 0 < t.real < 1]
    return dict(leg_long_mm=x, leg_short_mm=y, ratio=ratio,
                signed_normal_sag_mm=sag, chord_throat_mm=ac,
                geometric_throat_mm=throat, conservative_throat_lower_mm=ac-max(sag, 0),
                section_area_mm2=x*y/2-(2/3)*sag*chord,
                max_coordinate_sum_mm=max(float(sums(t)) for t in ss))


def classify(row, zmin, amin, zmax):
    return {**row, "both_minimum_legs_pass": row["leg_short_mm"] >= zmin,
            "geometric_throat_pass": row["geometric_throat_mm"] >= amin,
            "triangular_keepout_pass": row["max_coordinate_sum_mm"] <= zmax,
            "fusion_verified": False}


def h_from_existing_table(table, temperature):
    tab = table["temperature_dependent"]
    t = np.asarray(tab["temperatures_c"], float)
    cp = np.asarray(tab["specific_heat_j_kgk"], float)
    h = float(np.sum(np.diff(t)*(cp[1:]+cp[:-1])/2))
    h += (temperature-t[-1])*cp[-1]
    return h + table["fusion_enthalpy"]["latent_heat_J_kg"]


def calculate():
    cfg = yaml.safe_load((ROOT/"project/submission-baseline.yaml").read_text(encoding="utf-8"))
    pre = yaml.safe_load((ROOT/"project/precoat-process-design.yaml").read_text(encoding="utf-8"))
    joint = read("deliverables/process/joint-process-card.json")
    cap = read("studies/COMPETITION-DESIGN/results/delivery-joint-capacity-20261008.json")
    geom = read("cad/generated/independent-precoat-curved/geometry-audit.json")
    family = read("cad/generated/precoat-tolerance-family-20261007/geometry-and-feed-audit.json")
    interface = read("studies/COMPETITION-DESIGN/results/current-section-interface.json")
    mat = read(WIRE_SOURCE)["materials"][2]
    old_wire = read(WIRE_AUDIT)
    p, spec = joint["process"], joint["spec"]
    zmin, zmax = cfg["final_GTAW"]["minimum_total_leg_mm"], cfg["final_GTAW"]["maximum_geometric_envelope_leg_mm"]
    amin = zmin/math.sqrt(2)
    smin, smax = p["area_range_mm2"]
    h = h_from_existing_table(mat, 1470.)
    rho = mat["nominal_properties_20c"]["density_kg_m3"]*1e-9
    h_audit = old_wire["entering_wire_enthalpy_J"]/(old_wire["born_volume_mm3"]*rho)
    original = dict(area_range_mm2=[smin, smax], equivalent_leg_range_mm=p["equivalent_leg_range_mm"],
        equal_leg_throat_margin_mm=math.sqrt(smin)-amin,
        straight_max_leg_ratio_at_min_area=2*smin/zmin**2,
        straight_max_leg_ratio_at_max_area=zmax**2/(2*smax),
        half_leg_difference_limit_at_min_area_mm=(smin-zmin*zmin/2)/zmin,
        allowable_non_throat_area_at_min_area_mm2=smin-zmin*zmin/2,
        allowable_non_throat_area_fraction_at_min_area=(smin-zmin*zmin/2)/smin,
        equal_leg_area_preserving_parabolic_sag_limit_mm=amin-math.sqrt(4*amin*amin-3*smin),
        inputs_have_local_distribution_or_contour_guarantee=False)
    k = 2*smin/(amin*amin)
    original["straight_max_ratio_if_throat_only"] = (k+math.sqrt(k*k-4))/2
    original["tracking_0_05mm_toe_response_gain_required_if_zero_bias"] = original["half_leg_difference_limit_at_min_area_mm"]/.05
    rows = []
    for label, area, ratio, sag in [
        ("原最差·直线等腿", smin, 1., 0.),
        ("原最差·直线脚长比1.02", smin, 1.02, 0.),
        ("原最差·直线脚长比1.20", smin, 1.20, 0.),
        ("原最差·等腿凹面0.020", smin, 1., .020),
        ("原最差·等腿凹面0.080", smin, 1., .080),
    ]:
        row = straight(area, ratio) if sag == 0 else parabola(area, ratio, sag)
        rows.append({"name": label, **classify(row, zmin, amin, zmax)})
    # One explicitly requested contrast, without changing current process sources.
    feed_new = 3.68
    nsmin = smin*(feed_new-spec["feed_tolerance_mm_s"])/(spec["feed_nominal_mm_s"]-spec["feed_tolerance_mm_s"])
    nsmax = smax*(feed_new+spec["feed_tolerance_mm_s"])/(spec["feed_nominal_mm_s"]+spec["feed_tolerance_mm_s"])
    crows=[]
    for label, area, ratio, sag in [
        ("3.68下端·直线脚长比1.05", nsmin, 1.05, 0.),
        ("3.68下端·固定面积脚长比1.05/凹面0.080", nsmin, 1.05, .080),
        ("3.68上端·直线脚长比1.05", nsmax, 1.05, 0.),
        ("3.68上端·固定面积脚长比1.05/凹面0.080", nsmax, 1.05, .080),
    ]:
        row=straight(area,ratio) if sag==0 else parabola(area,ratio,sag)
        crows.append({"name":label,**classify(row,zmin,amin,zmax)})
    high_long=zmax
    high_short=zmax/1.05
    high_chord=math.hypot(high_long,high_short)
    excess=nsmax-high_long*high_short/2
    convex=(3/2)*excess/high_chord
    convex_row=classify(parabola(nsmax,1.05,-convex),zmin,amin,zmax)
    arc_time=cfg["final_GTAW"]["nominal_arc_time_s"]
    wire_area=math.pi*spec["wire_diameter_mm"]**2/4
    net=cfg["final_GTAW"]["net_energy_kJ"]*1000
    eta=spec["deposition_efficiency_range"]
    energy=[]
    for feed in [spec["feed_nominal_mm_s"],feed_new]:
        length=arc_time*feed
        mass=wire_area*length*rho
        deposited=[mass*v for v in eta]
        entering=[mass*v*h for v in eta]
        energy.append(dict(feed_mm_s=feed,wire_length_mm=length,wire_length_with_15pct_allowance_mm=1.15*length,
            incoming_consumed_mass_g=mass*1000,deposited_mass_at_nominal_dimensions_g=[v*1000 for v in deposited],
            entering_enthalpy_at_nominal_dimensions_J=entering,
            same_net_heat_budget_J=net,parent_pool_and_loss_remainder_J=[net-v for v in entering],
            net_heat_per_actual_pass_path_J_mm=300.,
            scope="Existing NiFe engineering enthalpy at 1470 C; same 300 J/mm partition, no fusion or thermal qualification"))
    delta=[b-a for a,b in zip(energy[0]["entering_enthalpy_at_nominal_dimensions_J"],energy[1]["entering_enthalpy_at_nominal_dimensions_J"])]
    min_first=min(q["retained_normal_mm"] for q in family["cases"])
    max_first=max(q["retained_normal_mm"] for q in family["cases"])
    min_total=min(q["pocket_depth_mm"] for q in family["cases"])
    min_second=min(q["pocket_depth_mm"]-q["retained_normal_mm"] for q in family["cases"])
    remelt=pre["machining"]["final_union_remelt_limit_mm"]
    result=dict(date="2026-10-08",role="Finite section geometry, local contour envelope and one feed contrast",
        sources=["project/submission-baseline.yaml","project/precoat-process-design.yaml","deliverables/process/joint-process-card.json",
                 "cad/generated/independent-precoat-curved/geometry-audit.json","cad/generated/precoat-tolerance-family-20261007/geometry-and-feed-audit.json",
                 "studies/COMPETITION-DESIGN/results/delivery-joint-capacity-20261008.json","studies/COMPETITION-DESIGN/results/current-section-interface.json",
                 "src/hanjie/domain/tooling_access.py:83",WIRE_SOURCE,WIRE_AUDIT],
        current_requirements=dict(minimum_each_leg_mm=zmin,minimum_geometric_throat_mm=amin,
            maximum_triangular_envelope_mm=zmax,keepout_equation="x>=0, y>=0, x+y<=4.30 mm",
            stable_length_mm=cfg["weld_layout"]["effective_segment_length_mm"],
            clarification="current-section-interface.json carries a historical 3.5 mm throat; current baseline and capacity use 3.8/sqrt(2)"),
        coordinate_definition="x is inward radial distance from Q235B inner wall, y is height above finished seat face; virtual root is their intersection. Nominal gap 0.02 mm is drawn and not assigned fusion.",
        nominal_curved_section=geom,
        saved_tolerance_family_summary=dict(case_count=len(family["cases"]),QT_radius_mm=[min(q["QT_radius_mm"] for q in family["cases"]),max(q["QT_radius_mm"] for q in family["cases"])],
            first_retained_normal_mm=[min_first,max_first],finished_total_flat_depth_mm=[min_total,max(q["pocket_depth_mm"] for q in family["cases"])],
            minimum_finished_second_flat_mm=min_second,final_root_remelt_design_limit_mm=interface["proposed_maximum_root_depth_mm"],
            final_union_remelt_design_limit_mm=remelt,conditional_minimum_second_remaining_flat_mm=min_second-remelt,
            conditional_minimum_total_remaining_flat_mm=min_total-remelt,
            root_depth_limit_basis="Existing conditional uniform-mixing mass screen: at 0.30 mm root depth worst Ni-layer origin 0.191019; declared 20% diagnostic window, not proven actual dilution or acceptable material threshold",
            retained_layer_scope="Flat final contact region, conditional on actual remelt not exceeding registered limit. Neither 0.25 nor 1.00 mm is a literature-qualified PMZ/crack/capacity threshold; no surviving manufacturing stress history is assigned.",
            PMZ_thickness_mm=None,PMZ_drawing_policy="Dashed interface line only; actual width and properties unqualified"),
        formulas=dict(straight="S=z1*z2/2; r=z1/z2>=1; z1=sqrt(2*S*r), z2=sqrt(2*S/r); a0=z1*z2/sqrt(z1^2+z2^2)",
            sag_bound="Measured chord a0 and maximum inward normal sag c give a_geom>=a0-c. If substituting supply S for chord triangle area this is a conservative screen, not a predicted actual profile.",
            fixed_area_parabola="P(t)=(1-t)(z1,0)+t(0,z2)-4*c*t*(1-t)*n; S=z1*z2/2-(2/3)*c*sqrt(z1^2+z2^2). Throat is min|P(t)| via cubic stationary roots and endpoints.",
            equal_parabola="z=(2*sqrt(2)/3)*c+sqrt(2*S+(8/9)*c^2); a_geom=sqrt(S+(4/9)*c^2)-c/3 for small c", 
            toe_asymmetry="e=(z1-z2)/2; equal-product mean m=sqrt(2*S+e^2); a0=S/sqrt(S+e^2). Both legs>=zmin requires |e|<=(S-zmin^2/2)/zmin.",
            torch="e=e_bias+G*delta_torch would require independently established response e_bias,G. Tracking +/-0.05 mm alone gives neither toe limits nor fusion.",
            supply="S_total = 2*eta_dep*pi*d^2/4 * wire_feed/travel; all two-pass supplied deposition locally represented, without reinforcement/gap/end or redistribution sinks",
            heat="E_net=eta_arc*integral(U*I dt); E_net=E_entering_wire+E_parent_pool+E_loss. Extra wire enthalpy comes from the same budget."),
        original_supply_envelope=original,original_analytic_cases=rows,
        single_feed_contrast=dict(feed_nominal_mm_s=feed_new,feed_tolerance_mm_s=spec["feed_tolerance_mm_s"],
            area_range_mm2=[nsmin,nsmax],equivalent_leg_range_mm=[math.sqrt(2*nsmin),math.sqrt(2*nsmax)],
            target_ratio=1.05,target_inward_normal_sag_mm=.08,
            lower_corner_conservative_throat_mm=straight(nsmin,1.05)["geometric_throat_mm"]-.08,
            straight_high_corner_max_ratio_for_4_30=zmax*zmax/(2*nsmax),analytic_cases=crows,
            high_corner_both_toes_capped_for_ratio_1_05=dict(long_leg_mm=high_long,short_leg_mm=high_short,
                triangle_area_mm2=high_long*high_short/2,required_extra_convex_area_mm2=excess,
                equivalent_parabolic_outward_normal_convexity_mm=convex,profile=convex_row,
                scope="This one smooth convex shape is area-preserving but exceeds triangular keepout; does not prove all conceivable contour shapes impossible"),
            status="Condition candidate only: lower feed corner has geometric room; claimed independent r<=1.05/c<=0.08 window fails existing 4.30 triangle at upper corner. No pWPS/baseline mutation or fusion qualification.",
            energy_cases=energy,extra_wire_enthalpy_J=delta,
            extra_wire_enthalpy_per_actual_total_path_J_mm=[v/cfg["weld_layout"]["total_arc_length_mm"] for v in delta],
            density_kg_m3=mat["nominal_properties_20c"]["density_kg_m3"],specific_incoming_enthalpy_relative_20C_J_kg=h,
            specific_enthalpy_crosscheck_from_saved_wire_audit_J_kg=h_audit,
            enthalpy_basis=mat["property_basis"]+"; "+mat["fusion_enthalpy"]["basis"],
            enthalpy_scope="Existing NiFe55 design Cp interpolation and estimated latent heat at 1470 C, not a supplier certificate, Ni99 JANAF substitution, or new thermal-field evidence."),
        saved_capacity=dict(source="studies/COMPETITION-DESIGN/results/delivery-joint-capacity-20261008.json",minimum_throat_mm=cap["rows"]["8P_leg_3.8"]["effective_throat_mm"],
            required_nominal_static_capacity_MPa=cap["rows"]["8P_leg_3.8"]["required_nominal_static_capacity_MPa"],capacity_not_recomputed=True),
        inspection_instructions=[
            "定义截面虚拟根为实测钢内壁与加工后座体上平面的交点；记录0.01~0.04 mm间隙，先标定两侧实际熔合边界。",
            "稳定16 mm范围各段起/中/末分别记录两脚、轮廓、根部与两侧熔合；端区各1 mm另检，不计入128 mm承载长度。",
            "双脚测量下界zi_meas-Uzi>=3.80 mm；实际自由面每一点均位于x+y<=4.30 mm外包络内（含外向不确定度）。",
            "从确认的根部到实际自由面求最短距离；a_geom_meas-Ua>=2.687006 mm。若用弦距/凹陷法，需a0_meas-c_meas-Ucombined>=2.687006。U由实际方法资格确定，不臆设为零。",
            "喉部区域还须双侧连续熔合、无裂纹/未熔合及不可计承载缺陷；几何喉部合格后再登记有效喉部，不以静态图或总增重授予融合资格。",
            "同截面记录CI-A1修整留层、Ni99加工后厚度及根道/两道时域并集的实际重熔；0.30/0.40为待确认设计上限，0.25/1.00仅是其条件几何余层。",
            "总增重/耗丝与局部轮廓分别记账。偏枪、丝速、总质量或等效焊脚不能替代短脚、凹陷、实际喉部和熔合检验。",
        ],
        verification=dict(arithmetic_executed=True,area_preserving_profiles_analytic=True,real_cad_source_reused=True,
            continuous_first_interface_fusion_verified=False,final_bilateral_fusion_verified=False,local_forming_window_qualified=False,
            PMZ_capacity_verified=False,complete_manufacturing_state_verified=False))
    return result


def section_polygons(geom):
    top, depth, r = geom["finished_z_mm"], geom["pocket_depth_mm"], geom["QT_corner_radius_mm"]
    first=geom["first_flat_retained_mm"]
    centre=np.array([geom["inner_radius_mm"]+r,top-depth+r])
    ro=geom["outer_radius_mm"]
    theta=np.linspace(math.pi,1.5*math.pi,121)
    lower=centre+np.column_stack((np.cos(theta),np.sin(theta)))*r
    upper=centre+np.column_stack((np.cos(theta),np.sin(theta)))*(r-first)
    qt=np.vstack(([67.,111.7],[ro,111.7],[ro,top-depth],lower[::-1],[67.,top]))
    ci=np.vstack((lower,[ro,top-depth],[ro,top-depth+first],upper[::-1]))
    ni=np.vstack((upper,[ro,top-depth+first],[ro,top]))
    return qt,ci,ni,lower,centre


def plot(result):
    FIG.mkdir(parents=True,exist_ok=True)
    font=FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
    plt.rcParams.update({"font.family":font.get_name(),"font.size":9.5,"axes.unicode_minus":False,
                         "svg.fonttype":"none","pdf.fonttype":42,"axes.spines.top":False,"axes.spines.right":False})
    fig,ax=plt.subplots(2,2,figsize=(14.4,9.7),layout="constrained")
    colors={"QT":"#ced5dc","CI":"#bb8c66","Ni":"#e2ce84","final":"#75afbb","steel":"#a7bdca"}
    geom=result["nominal_curved_section"]
    qt,ci,ni,pmz,centre=section_polygons(geom)
    a=ax[0,0]
    for poly,col in [(qt,colors["QT"]),(ci,colors["CI"]),(ni,colors["Ni"])]:
        a.add_patch(Polygon(poly,closed=True,facecolor=col,edgecolor="#42535f",lw=.7))
    a.add_patch(Rectangle((75,111.7),5,8.2,color=colors["steel"],ec="#42535f",lw=.7))
    a.add_patch(Polygon([[75,115],[71,115],[75,119]],facecolor=colors["final"],edgecolor="#287184",lw=1.2))
    a.plot([70.7,75,75],[115,115,119.3],ls=":",color="#983847",lw=1)
    a.plot(pmz[:,0],pmz[:,1],ls=(0,(3,2,1,2)),color="#913449",lw=1.6)
    a.plot([centre[0],74.98],[113.5,113.5],ls=(0,(3,2,1,2)),color="#913449",lw=1.6)
    a.plot([75,73],[115,117],color="#244c59",lw=1.8)
    a.text(72.85,116.2,"a名义=2.828\n验收下界≥2.687",fontsize=8.7,ha="center",color="#244c59")
    a.text(77.3,117.5,"Q235B\n壁厚5.0",ha="center")
    a.text(69.0,112.1,"QT450-10",ha="center",fontsize=10)
    a.annotate("CI-A1首层\n法向修整0.70",xy=(72.2,113.85),xytext=(67.25,113.3),arrowprops={"arrowstyle":"->","lw":.8},fontsize=8.7)
    a.annotate("低碳Ni99第二层\n平直区名义0.80",xy=(71.,114.6),xytext=(67.1,116.9),arrowprops={"arrowstyle":"->","lw":.8},fontsize=8.7)
    a.annotate("最终NiFe55两道\n名义双脚4.00",xy=(74.2,116.5),xytext=(71.1,119.15),arrowprops={"arrowstyle":"->","lw":.8},fontsize=8.7)
    a.annotate("QT/CI界面区（PMZ）\n厚度未定，虚线仅指界面",xy=(69.2,114.2),xytext=(67.25,119.1),arrowprops={"arrowstyle":"->","lw":.8},fontsize=8.4,color="#913449")
    a.text(74.85,111.96,"名义径向间隙0.02\n设计范围0.01～0.04",ha="right",fontsize=8.3)
    a.text(71.65,114.0,"R1.50 / R0.80同心",fontsize=8.1,color="#344c56")
    a.set(xlim=(66.9,80.2),ylim=(111.65,120.25),xlabel="半径 r / mm",ylabel="轴向 z / mm")
    a.set_aspect("equal");a.set_title("A  本件名义截面：复用真实同心圆角CAD尺寸",loc="left",fontweight="bold")
    # Conditional retention: flat area corner D1.40/N0.75, not a metallurgical minimum.
    b=ax[0,1]
    b.add_patch(Rectangle((0,0),5,.75,fc=colors["CI"],ec="#42535f"))
    b.add_patch(Rectangle((0,.75),5,.65,fc=colors["Ni"],ec="#42535f"))
    b.add_patch(Rectangle((0,1.),5,.4,fc="none",ec="#a14d42",hatch="////",lw=.5))
    b.axhline(1.10,color="#377c91",lw=1.3,ls="--")
    b.axhline(1.,color="#a14d42",lw=1.3,ls="--")
    b.text(2.5,.36,"CI-A1：本角点0.75\n九组首层0.65～0.75",ha="center",va="center")
    b.text(2.5,.86,"Ni99条件最低余层0.25",ha="center",va="center",fontsize=8.7)
    b.text(2.5,1.29,"最终两道允许重熔并集≤0.40",ha="center",va="center",color="#8b493f",fontsize=8.7)
    b.annotate("根道设计上限0.30",xy=(5,1.10),xytext=(5.16,1.20),fontsize=8.6,arrowprops={"arrowstyle":"->","lw":.8})
    b.annotate("总条件余层≥1.00",xy=(5,1.),xytext=(5.16,.66),fontsize=8.6,arrowprops={"arrowstyle":"->","lw":.8})
    b.text(0,1.7,"九组公差：总层1.40～1.60；第二层平直区≥0.65\n本图为D1.40/N0.75最小第二层角点，实际重熔深度未证",fontsize=9)
    b.text(0,-.33,"0.25/1.00是既定重熔上限的几何结果；材料可接受最小值尚未取得依据。\n圆角切换区与局部混合带按实际截面核查，不能套用平直区厚度。",fontsize=8.4,color="#725242")
    b.set(xlim=(-.2,8.2),ylim=(-.48,2.12),yticks=[0,.75,1.,1.10,1.4],ylabel="距QT/首层平直界面法向高度 / mm")
    b.set_xticks([]);b.set_title("B  最低留层与重熔限值：条件几何关系",loc="left",fontweight="bold")
    # Exact area-preserving faces, drawn in local x/y coordinates.
    c=ax[1,0]
    p= result["original_analytic_cases"]
    for row,co,ls in [(p[0],"#276b80","-"),(p[1],"#a7673b","--"),(p[4],"#a44254","-")]:
        x,y=row["leg_long_mm"],row["leg_short_mm"]
        t=np.linspace(0,1,201)
        xy=np.column_stack((x*(1-t),y*t))
        sag=row.get("signed_normal_sag_mm",0)
        xy-=4*sag*(t*(1-t))[:,None]*np.array([y,x])[None,:]/math.hypot(x,y)
        c.plot(xy[:,0],xy[:,1],color=co,ls=ls,lw=1.7,label=row["name"])
    c.plot([0,4.3],[4.3,0],ls=":",color="#666e73",lw=1.2,label="现行三角包络4.30")
    c.plot([0,4.3],[0,0],color="#647a87",lw=2);c.plot([0,0],[0,4.3],color="#647a87",lw=2)
    c.text(.15,.28,f"各截面积同为 S={p[0]['section_area_mm2']:.6f} mm²\n等腿直线 a={p[0]['geometric_throat_mm']:.6f}\n脚长比1.02短脚={p[1]['leg_short_mm']:.6f} <3.80\n凹面0.080实际 a={p[4]['geometric_throat_mm']:.6f} <2.687",fontsize=8.7)
    c.set(xlim=(-.18,4.5),ylim=(-.18,4.5),xlabel="局部内向径向 x / mm",ylabel="局部高度 y / mm")
    c.set_aspect("equal");c.legend(loc="upper right",fontsize=7.6,frameon=False)
    c.set_title("C  固定面积的合法截面：面积充足仍可短脚或喉部不足",loc="left",fontweight="bold")
    d=ax[1,1]
    # Two analytic functions sampled only to draw their envelopes; no search.
    ratios=np.linspace(1,1.20,201)
    old_s=result["original_supply_envelope"]["area_range_mm2"][0]
    new_s=result["single_feed_contrast"]["area_range_mm2"][0]
    req=result["current_requirements"]["minimum_geometric_throat_mm"]
    for s,col,label in [(old_s,"#276b80","原3.50下端"),(new_s,"#a7673b","对照3.68下端")]:
        margin=np.sqrt(2*s/(ratios+1/ratios))-req
        d.plot(ratios,margin*1000,color=col,lw=1.9,label=label+"：供料代入的保守凹陷界")
    d.axvline(result["original_supply_envelope"]["straight_max_leg_ratio_at_min_area"],ls="--",color="#276b80",lw=1)
    d.axhline(80,color="#a14d42",ls="--",lw=1)
    d.scatter([1.05],[result["single_feed_contrast"]["lower_corner_conservative_throat_mm"]*1000-req*1000+80],color="#a7673b",s=22)
    d.text(1.026,14,"原供料同时双脚≥3.80\n直线脚长比≤1.014739",fontsize=8.3,color="#276b80")
    d.text(1.063,101,"3.68上端若脚长比1.05：\n长脚4.396508，超4.30\n不能冻结独立1.05/0.080全窗",fontsize=8.6,color="#8f4738")
    d.text(1.002,-17,"曲线为充分条件；固定面积凹面应另解实际几何。\n偏枪±0.05没有脚长差或双侧熔合的已知传递关系。",fontsize=8.3)
    d.set(xlim=(.997,1.205),ylim=(-25,125),xlabel="脚长比 r=z长/z短",ylabel="可用法向凹陷上界 a0−a要求 / μm")
    d.grid(alpha=.18);d.legend(loc="upper right",fontsize=8.1,frameon=False)
    d.set_title("D  原包络与唯一供丝对照：保持4.30外包络",loc="left",fontweight="bold")
    fig.suptitle("8P局部成形设计核算：真实参数截面与解析容差包络",fontsize=15,fontweight="bold")
    fig.supxlabel("尺寸为设计值，轮廓为解析构造；PMZ虚线不赋厚度。来源：submission-baseline、九组公差CAD、joint-process-card、现行承载JSON。双侧连续熔合资格仍为false。",fontsize=8.4)
    for ext in ("svg","png","pdf"):
        options=dict(bbox_inches="tight",facecolor="white")
        if ext=="png":options["dpi"]=300
        if ext=="pdf":options["metadata"]={"Author":"","Title":"8P局部成形截面与解析包络"}
        if ext=="svg":options["metadata"]={"Creator":"Engineering design arithmetic","Title":"8P局部成形截面与解析包络"}
        fig.savefig(FIG/f"{NAME}.{ext}",**options)
    plt.close(fig)


def write_markdown(r):
    o=r["original_supply_envelope"];n=r["single_feed_contrast"];ret=r["saved_tolerance_family_summary"]
    req=r["current_requirements"]
    lines=["# 8P本件截面与局部成形解析包络", "", "核算日期：2026-10-08。采用现行SUBMISSION-8P源、已完成的九组公差及供料/承载JSON；只运行有限截面算术和绘图，不重算CAD或热—力场。", "",
        "![真实参数设计截面与包络](../../../docs/report/figures/delivery/section-forming-envelope-20261008.png)", "",
        "## 原供料的设计保证范围", "",
        f"现行两道供料截面积为{o['area_range_mm2'][0]:.9f}～{o['area_range_mm2'][1]:.9f} mm²。最低双脚为3.80 mm，现行最低喉部为3.80/√2={req['minimum_geometric_throat_mm']:.9f} mm。面积守恒按局部均匀分配成立时，可支持这些轮廓的填充需求；没有已证的局部轮廓/分配，不能直接取得双脚、有效喉部或熔合保证。", "",
        "对直线角焊轮廓取S=z₁z₂/2、r=z₁/z₂≥1，则z₁=√(2Sr)、z₂=√(2S/r)，根部至弦的垂距a₀=z₁z₂/√(z₁²+z₂²)=√[2S/(r+1/r)]。", "",
        f"原最差面积下，等腿喉部余量仅{o['equal_leg_throat_margin_mm']*1000:.3f} μm。若只检喉部，直线脚长比可到{o['straight_max_ratio_if_throat_only']:.6f}；同时检双脚≥3.80时，脚长比上界收紧为{o['straight_max_leg_ratio_at_min_area']:.9f}，对应两脚最大差{2*o['half_leg_difference_limit_at_min_area_mm']:.9f} mm。用e=(z₁−z₂)/2表示几何偏心，在固定面积下a₀=S/√(S+e²)，双脚条件要求|e|≤{o['half_leg_difference_limit_at_min_area_mm']:.9f} mm。", "",
        f"最低三角有效填充需要7.22 mm²；原最差供料超出仅{o['allowable_non_throat_area_at_min_area_mm2']:.9f} mm²（{o['allowable_non_throat_area_fraction_at_min_area']*100:.3f}%）。若余高、装配间隙下补料、端区或局部铺展另占这部分面积，原等腿最低尺寸假设即失去余量；现有供料JSON未限定这些分配。", "",
        "## 凹陷与铺展的合法几何", "",
        "以实际两焊趾连线为弦，实测弦喉距a₀与最大向根部的法向凹陷c满足a几何≥a₀−c；这是充分验收条件。不能把固定面积下的凹陷一律等同于喉部减少c，因为补偿后的脚长会增加。", "",
        "选取一族明确定义的平滑轮廓P(t)=(1−t)(z₁,0)+t(0,z₂)−4ct(1−t)n，0≤t≤1，n=(z₂,z₁)/√(z₁²+z₂²)。其真实面积S=z₁z₂/2−(2/3)c√(z₁²+z₂²)。脚长按此面积方程解析求解；最短根距由|P(t)|²一阶导数的三次方程驻点及端点求得。数值表是小量指定几何实例，不是供料搜索或实物结果。", "",
        f"等腿时z=(2√2/3)c+√[2S+(8/9)c²]，a几何=√[S+(4/9)c²]−c/3。在原最差面积这一特定凹面族，最大合格凹陷约{o['equal_leg_area_preserving_parabolic_sag_limit_mm']:.9f} mm；这个值不能转成任意实际焊缝通用凹陷容差。", "",
        "| 指定几何实例 | 长脚/mm | 短脚/mm | 实际几何喉部/mm | 双脚≥3.8 | 喉部≥2.687006 | 三角包络≤4.30 |", "| --- | ---: | ---: | ---: | :---: | :---: | :---: |"]
    for row in r["original_analytic_cases"]+n["analytic_cases"]:
        flags=["是" if row[k] else "否" for k in ["both_minimum_legs_pass","geometric_throat_pass","triangular_keepout_pass"]]
        lines.append(f"| {row['name']} | {row['leg_long_mm']:.6f} | {row['leg_short_mm']:.6f} | {row['geometric_throat_mm']:.6f} | {' | '.join(flags)} |")
    lines += ["", "## 偏枪的设计界限", "",
        f"设备跟踪±0.05 mm控制的是枪轨迹。几何偏心e只有在已知响应关系e=e偏置+Gδ枪时才能传递；原最差供料在零偏置、线性关系的条件下需|G|≤{o['tracking_0_05mm_toe_response_gain_required_if_zero_bias']:.6f}。本件没有这一传递系数，不能由静态截面或跟踪精度推定短脚合格、双侧熔合或热源资格。", "",
        "## 唯一局部供丝对照：3.68±0.05 mm/s", "",
        f"其余丝径、沉积效率、速度与道数公差保持现行值，得到S={n['area_range_mm2'][0]:.9f}～{n['area_range_mm2'][1]:.9f} mm²，等效等腿={n['equivalent_leg_range_mm'][0]:.9f}～{n['equivalent_leg_range_mm'][1]:.9f} mm。下供料角点代入r=1.05并保守扣0.080 mm法向凹陷，喉部下界{n['lower_corner_conservative_throat_mm']:.9f} mm，双脚可支持目标。", "",
        f"上供料角点的直线r=1.05轮廓长脚{n['analytic_cases'][2]['leg_long_mm']:.9f} mm，超4.30约{(n['analytic_cases'][2]['leg_long_mm']-4.3)*1000:.3f} μm；若保持直线轮廓，允许脚长比最多{n['straight_high_corner_max_ratio_for_4_30']:.9f}。当前可达性源定义的是x+y≤4.30的三角形，不能仅检两脚≤4.30就接受任意凸面。", ""]
    conv=n["high_corner_both_toes_capped_for_ratio_1_05"]
    lines += [f"若上端将长脚压到4.30、短脚取4.30/1.05={conv['short_leg_mm']:.9f}，其直线三角面积只有{conv['triangle_area_mm2']:.9f} mm²，需额外凸面容纳{conv['required_extra_convex_area_mm2']:.9f} mm²。对应平滑抛物凸面的法向凸度{conv['equivalent_parabolic_outward_normal_convexity_mm']:.9f} mm，最大x+y={conv['profile']['max_coordinate_sum_mm']:.9f} mm，仍超三角包络。该特定轮廓冲突不证明所有可能轮廓都不可行，但不能支持把独立r≤1.05、c≤0.080当作全供料窗口。", "",
        "**决策：3.68对照仅为条件候选。原3.50基线不改；3.68下端有几何余量，上端仍需受控轮廓与既有4.30可达性边界共同约束。未经双侧熔合、重熔及热残余验证，不冻结新WPS参数。**", "",
        "| 名义供丝 | 耗丝/mm | 15%备料/mm | 来丝质量/g | 名义几何下沉积质量/g（η0.90～0.98） | 进入丝焓/kJ（同η） |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for e in n["energy_cases"]:
        lines.append(f"| {e['feed_mm_s']:.2f} | {e['wire_length_mm']:.6f} | {e['wire_length_with_15pct_allowance_mm']:.6f} | {e['incoming_consumed_mass_g']:.6f} | {e['deposited_mass_at_nominal_dimensions_g'][0]:.6f}～{e['deposited_mass_at_nominal_dimensions_g'][1]:.6f} | {e['entering_enthalpy_at_nominal_dimensions_J'][0]/1000:.6f}～{e['entering_enthalpy_at_nominal_dimensions_J'][1]/1000:.6f} |")
    lines += ["",f"采用已存NiFe55物性：ρ={n['density_kg_m3']:.0f} kg/m³，20→1470℃的H={n['specific_incoming_enthalpy_relative_20C_J_kg']/1e6:.6f} MJ/kg；由现有Cp分段积分及潜热计算，与已存wire-energy-audit反算一致。潜热和高温Cp为原工程输入，不能代替供方热物性证书。", "",
        f"新增进入丝焓{n['extra_wire_enthalpy_J'][0]:.6f}～{n['extra_wire_enthalpy_J'][1]:.6f} J，按288 mm实际两道总路径为{n['extra_wire_enthalpy_per_actual_total_path_J_mm'][0]:.6f}～{n['extra_wire_enthalpy_per_actual_total_path_J_mm'][1]:.6f} J/mm。这些能量须从原净86.4 kJ分配中扣除，余量才进入母材/熔池与损失；不另加第二份热量。电弧300 J/mm名义指令不变，母材截获、双侧熔合与焊态控形资格均未因此取得。", "",
        "## 材料链、留层与承载接口", "",
        f"名义曲面直接复用QT R1.50、CI-A1同心修整R0.80、法向首层0.70和总深1.50。九组公差的首层法向修整范围0.65～0.75，总平直深1.40～1.60，第二层平直区最低{ret['minimum_finished_second_flat_mm']:.2f} mm。根道≤0.30、两道重熔并集≤0.40是现有设计控制值，实际深度未取得验证。此条件下第二层几何余层≥{ret['conditional_minimum_second_remaining_flat_mm']:.2f}、总几何余层≥{ret['conditional_minimum_total_remaining_flat_mm']:.2f} mm；这些是几何预算结果，未被文献或有效接头证据证明为冶金/裂纹/容量最小安全厚度。", "",
        "0.30 mm根道限值的原依据是声明密度与平直接触宽度下均匀混合筛查：Ni过渡层来源比例最差0.191019，低于先设的20%诊断输入。不能用此反向证明实际稀释。PMZ仅以QT/CI界面虚线标注，实际厚度、组织及容量未赋值。圆角切换区不套用平直区最低厚度。", "",
        f"沿用128 mm有效长度和2.687006 mm有效喉部时，现有名义静承载需求为{r['saved_capacity']['required_nominal_static_capacity_MPa']:.6f} MPa。本件截面计算只检查容量输入能否获得几何支持，没有重算或授予材料容量。current-section-interface中的旧3.50 mm喉部只保留其历史来源，现行喉部取submission-baseline和delivery-joint-capacity。", "",
        "## 可执行轮廓验收指令", ""]
    lines += [f"{i}. {s}" for i,s in enumerate(r["inspection_instructions"],1)]
    lines += ["", "## 运行和来源", "", "实际运行：`python studies/COMPETITION-DESIGN/delivery_section_envelope.py`。同名JSON保存完整输入引用、公式、角点、质量与焓。图的PNG/SVG/PDF均由本脚本生成。没有生成实测照片、组织图、熔合数据或额外候选矩阵。", ""]
    lines += [f"- `{s}`" for s in r["sources"]]
    (OUT/f"{NAME}.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def plot_split(r):
    """160 mm print-width figures, reading the completed arithmetic unchanged."""
    font=FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
    plt.rcParams.update({"font.family":font.get_name(),"font.size":7.7,"axes.unicode_minus":False,
                         "svg.fonttype":"none","pdf.fonttype":42,"axes.spines.top":False,"axes.spines.right":False})
    col={"QT":"#ced5dc","CI":"#bb8c66","Ni":"#e2ce84","final":"#75afbb","steel":"#a7bdca"}

    def save(fig,suffix):
        for ext in ("svg","png","pdf"):
            kw=dict(bbox_inches="tight",facecolor="white")
            if ext=="png":kw["dpi"]=400
            if ext=="pdf":kw["metadata"]={"Author":"","Title":"8P截面与局部成形"}
            if ext=="svg":kw["metadata"]={"Creator":"Engineering design arithmetic","Title":"8P截面与局部成形"}
            fig.savefig(FIG/f"{NAME}-{suffix}.{ext}",**kw)
        plt.close(fig)

    fig,axs=plt.subplots(1,2,figsize=(6.5,3.6),layout="constrained",gridspec_kw={"width_ratios":[1.05,1.]})
    qt,ci,ni,pmz,centre=section_polygons(r["nominal_curved_section"])
    a=axs[0]
    for poly,key in [(qt,"QT"),(ci,"CI"),(ni,"Ni")]:
        a.add_patch(Polygon(poly,closed=True,facecolor=col[key],edgecolor="#42535f",lw=.5))
    a.add_patch(Rectangle((75,111.7),5,8.2,color=col["steel"],ec="#42535f",lw=.5))
    a.add_patch(Polygon([[75,115],[71,115],[75,119]],facecolor=col["final"],edgecolor="#287184",lw=.8))
    a.plot(pmz[:,0],pmz[:,1],ls=(0,(3,2,1,2)),color="#913449",lw=1.)
    a.plot([centre[0],74.98],[113.5,113.5],ls=(0,(3,2,1,2)),color="#913449",lw=1.)
    a.plot([75,73],[115,117],color="#244c59",lw=1.)
    a.text(77.5,116.8,"Q235B\n壁厚5",ha="center",fontsize=7.7)
    a.text(69.1,112.75,"QT450-10",ha="center",fontsize=7.7)
    a.text(72.2,113.73,"CI-A1",ha="center",fontsize=7.5)
    a.text(71.85,114.4,"Ni99",ha="center",fontsize=7.5)
    a.text(74.2,116.,"NiFe55",ha="center",fontsize=7.5,rotation=45)
    a.annotate("PMZ界面线\n厚度未定",xy=(69.05,114.4),xytext=(67.5,118.4),arrowprops={"arrowstyle":"->","lw":.55},fontsize=7.5,color="#913449")
    a.text(73.6,119.88,"名义双脚4.00",fontsize=7.5,ha="center")
    a.annotate("a≥2.687",xy=(73.,117.),xytext=(70.6,117.2),arrowprops={"arrowstyle":"->","lw":.55},fontsize=7.5)
    a.set(xlim=(67.,80.15),ylim=(111.7,120.45),xlabel="半径 r / mm",ylabel="轴向 z / mm",xticks=[68,72,76,80],yticks=[112,115,119])
    a.set_aspect("equal");a.set_anchor("N")
    a.set_title("A  本件名义材料截面",loc="left",fontweight="bold",fontsize=9)
    a.text(67.2,111.85,"R1.50/R0.80同心；首层法向0.70",fontsize=7.1,va="bottom")
    b=axs[1]
    b.add_patch(Rectangle((0,0),5,.75,fc=col["CI"],ec="#42535f",lw=.5))
    b.add_patch(Rectangle((0,.75),5,.65,fc=col["Ni"],ec="#42535f",lw=.5))
    b.add_patch(Rectangle((0,1.),5,.4,fc="none",ec="#a14d42",hatch="////",lw=.4))
    b.axhline(1.10,color="#377c91",lw=.7,ls="--")
    b.axhline(1.,color="#a14d42",lw=.7,ls="--")
    b.text(2.5,.37,"CI-A1 本角点0.75\n首层范围0.65～0.75",ha="center",va="center",fontsize=7.7)
    b.text(2.5,.87,"Ni99条件余层≥0.25",ha="center",va="center",fontsize=7.5)
    b.text(2.5,1.26,"两道重熔并集≤0.40",ha="center",va="center",fontsize=7.5,bbox={"fc":"white","ec":"none","alpha":.85,"pad":1})
    b.text(0,1.57,"总层1.40～1.60\n第二层平直区≥0.65",fontsize=7.7)
    b.text(0,-.21,"根道设计上限0.30；总条件余层≥1.00\n厚度是几何预算，材料最小值未获依据",fontsize=7.4)
    b.set(xlim=(-.15,5.15),ylim=(-.34,1.9),yticks=[0,.75,1.,1.1,1.4],ylabel="距QT/CI平直界面高度 / mm")
    b.set_xticks([])
    b.set_title("B  条件留层与重熔限值",loc="left",fontweight="bold",fontsize=9)
    fig.supxlabel("设计截面；名义间隙0.02（范围0.01～0.04）mm。PMZ仅标界面，实际熔合与重熔深度未证。",fontsize=7.5)
    save(fig,"AB")

    fig,axs=plt.subplots(1,2,figsize=(6.5,3.65),layout="constrained")
    a,b=axs
    p=r["original_analytic_cases"]
    for row,color,ls,label in [(p[0],"#276b80","-","等腿直线"),(p[1],"#a7673b","--","直线r=1.02"),(p[4],"#a44254","-","等腿凹面c=0.080")]:
        x,y=row["leg_long_mm"],row["leg_short_mm"]
        t=np.linspace(0,1,201)
        xy=np.column_stack((x*(1-t),y*t))
        xy-=4*row.get("signed_normal_sag_mm",0)*(t*(1-t))[:,None]*np.array([y,x])[None,:]/math.hypot(x,y)
        a.plot(xy[:,0],xy[:,1],color=color,ls=ls,lw=1.15,label=label)
    a.plot([0,4.3],[4.3,0],ls=":",color="#666e73",lw=.9,label="x+y≤4.30包络")
    a.plot([0,4.3],[0,0],color="#647a87",lw=1);a.plot([0,0],[0,4.3],color="#647a87",lw=1)
    a.text(.12,.25,"同面积S=7.326417 mm²\nr=1.02短脚3.790188<3.80\nc=0.080喉部2.680594<2.687",fontsize=7.5)
    a.set(xlim=(-.15,4.5),ylim=(-.15,4.55),xlabel="局部内向径向 x / mm",ylabel="局部高度 y / mm",xticks=[0,2,4],yticks=[0,2,4])
    a.set_aspect("equal")
    a.legend(loc="upper right",fontsize=6.8,frameon=False,handlelength=1.4,labelspacing=.3)
    a.set_title("C  固定面积的合法轮廓",loc="left",fontweight="bold",fontsize=9)
    ratio=np.linspace(1,1.20,201)
    req=r["current_requirements"]["minimum_geometric_throat_mm"]
    for s,color,label in [(r["original_supply_envelope"]["area_range_mm2"][0],"#276b80","原3.50下端"),(r["single_feed_contrast"]["area_range_mm2"][0],"#a7673b","对照3.68下端")]:
        b.plot(ratio,(np.sqrt(2*s/(ratio+1/ratio))-req)*1000,color=color,lw=1.25,label=label)
    b.axvline(r["original_supply_envelope"]["straight_max_leg_ratio_at_min_area"],ls="--",color="#276b80",lw=.7)
    b.axhline(80,color="#a14d42",ls="--",lw=.7)
    b.text(1.043,104,"3.68上端r=1.05\n长脚4.3965>4.30",fontsize=7.6,color="#8f4738")
    b.text(1.025,26,"原双脚≥3.80\nr≤1.014739",fontsize=7.5,color="#276b80")
    b.text(1.003,-20,"边界为供料代入的充分条件\n实际凹面另按轮廓最短根距验收",fontsize=7.1)
    b.set(xlim=(.995,1.205),ylim=(-27,135),xlabel="脚长比 r=z长/z短",ylabel="保守法向凹陷界 a0−a要求 / μm",xticks=[1.,1.1,1.2])
    b.grid(alpha=.18);b.legend(loc="upper right",fontsize=7.2,frameon=False)
    b.set_title("D  原供料与唯一条件对照",loc="left",fontweight="bold",fontsize=9)
    fig.supxlabel("解析设计轮廓；3.68供丝尚未采用。枪跟踪±0.05 mm不直接保证脚长、喉部或双侧熔合。",fontsize=7.5)
    save(fig,"CD")
    print("Saved AB/CD print figures from existing JSON; no arithmetic rerun")


def main():
    r=calculate()
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/f"{NAME}.json").write_text(json.dumps(r,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    write_markdown(r)
    plot(r)
    print(json.dumps(dict(original=r["original_supply_envelope"],feed_contrast={k:r["single_feed_contrast"][k] for k in ["area_range_mm2","equivalent_leg_range_mm","lower_corner_conservative_throat_mm","straight_high_corner_max_ratio_for_4_30","extra_wire_enthalpy_J","status"]}),ensure_ascii=False,indent=2))


if __name__=="__main__":
    import sys
    if "--split-figures-only" in sys.argv:
        plot_split(read(f"studies/COMPETITION-DESIGN/results/{NAME}.json"))
    else:
        main()
