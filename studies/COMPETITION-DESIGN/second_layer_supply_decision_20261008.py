"""One stock-size decision for DMNA099, with finite geometry/supply/heat accounts.

Reads the existing nine CAD tolerance members; does not regenerate them or run
thermal/mechanical solvers. The 16 supply corners are diameter/feed/speed/
utilization combinations. Total-volume sufficiency does not establish a local
deposit contour, dilution, fusion, or a retained manufacturing stress state.
"""
from pathlib import Path
import itertools
import json
import math

import gmsh
import yaml

ROOT = Path(__file__).resolve().parents[2]
NAME = "second-layer-supply-decision-20261008"
OUT = ROOT / "studies/COMPETITION-DESIGN/results"
FAMILY = "cad/generated/precoat-tolerance-family-20261007"


def projected_roofs(cases):
    """Read the planar pocket roofs of the existing, named 17-solid STEP files."""
    records = []
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    try:
        for row in cases:
            gmsh.clear()
            path = ROOT / FAMILY / (row["case"] + ".step")
            gmsh.model.occ.importShapes(str(path))
            gmsh.model.occ.synchronize()
            solids = gmsh.model.getEntities(3)
            # The one QT seat exceeds 136000 mm3; the 16 existing coating
            # solids are each below 100 mm3. Use their recorded size separation.
            patches = [tag for dim, tag in solids
                       if gmsh.model.occ.getMass(dim, tag) < 200.]
            if len(solids) != 17 or len(patches) != 16:
                raise ValueError("Existing STEP material partition differs")
            ids = {tag for s in patches for dim, tag in
                   gmsh.model.getBoundary([(3, s)], False, False) if dim == 2}
            roof = []
            for tag in ids:
                bb = gmsh.model.getBoundingBox(2, tag)
                if abs(bb[2] - 115.) < 1e-5 and abs(bb[5] - 115.) < 1e-5:
                    roof.append(tag)
            area = sum(gmsh.model.occ.getMass(2, f) for f in roof) / 8
            records.append(dict(case=row["case"], source=path.relative_to(ROOT).as_posix(),
                                planar_pocket_roof_area_one_wing_mm2=area,
                                retained_second_volume_one_wing_mm3=row["final_second_volume_one_wing_mm3"]))
    finally:
        gmsh.finalize()
    return records


def supply(diam, diam_tol, feed, feed_tol, speed, speed_tol, eta, length):
    rows = []
    for d, f, v, e in itertools.product(
            [diam-diam_tol, diam+diam_tol], [feed-feed_tol, feed+feed_tol],
            [speed*(1-speed_tol), speed*(1+speed_tol)], eta):
        t = length/v
        volume = math.pi*d*d/4*f*t*e
        rows.append(dict(diameter_mm=d, feed_mm_s=f, travel_mm_s=v,
                         deposition_utilization=e, arc_time_per_wing_s=t,
                         consumed_length_per_wing_mm=f*t,
                         deposited_volume_per_wing_mm3=volume,
                         deposited_mass_per_wing_g=volume*.00889))
    return rows


def calculate():
    cfg = yaml.safe_load((ROOT / "project/precoat-process-design.yaml").read_text(encoding="utf-8"))
    b, cut = cfg["second"], cfg["machining"]
    family = json.loads((ROOT / FAMILY / "geometry-and-feed-audit.json").read_text(encoding="utf-8"))
    roofs = projected_roofs(family["cases"])
    area = max(r["planar_pocket_roof_area_one_wing_mm2"] for r in roofs)
    length, speed = b["track_length_per_wing_mm"], b["travel_mm_s"]
    corners = supply(b["diameter_mm"], b["diameter_tolerance_mm"], b["feed_mm_s"],
                     b["feed_tolerance_mm_s"], speed, b["travel_relative_tolerance"],
                     b["deposition_efficiency_range"], length)
    old = supply(1.20, .02, 7.20, .20, speed, b["travel_relative_tolerance"],
                 b["deposition_efficiency_range"], length)
    lower = min(corners, key=lambda r:r["deposited_volume_per_wing_mm3"])
    upper = max(corners, key=lambda r:r["deposited_volume_per_wing_mm3"])
    minimum_added = cut["second_deposited_top_min_mm"] - min(cut["first_retained_mm"])
    required = area*minimum_added
    required_diameter = math.sqrt(4*required*speed*(1+b["travel_relative_tolerance"])/
                                 (math.pi*(b["feed_mm_s"]-b["feed_tolerance_mm_s"])*
                                  length*min(b["deposition_efficiency_range"])))
    wire_area = math.pi*b["diameter_mm"]**2/4
    t = 8*length/speed
    wire = t*b["feed_mm_s"]
    mass = wire_area*wire*.00889
    rods = b["rod_feed_interface"]
    max_use = max(r["consumed_length_per_wing_mm"] for r in corners)
    blanks = rods["cut_blank_length_per_wing_mm"]*rods["blanks_per_part"]
    prep = blanks+rods["cutting_loss_per_blank_mm"]*rods["blanks_per_part"]
    purchased = rods["stock_rods_per_part"]*b["stock_length_mm"]
    # Same existing pure incoming Ni reference, evaluated directly from the
    # primary JANAF Ni(ref) table at its melting point and liquid Cp. This is
    # a supplied-metal heat account, not a diluted Ni-C-Fe-Si-Mn material law.
    entry = 1470.
    molar_h = 64.516 + 38.911*(entry+273.15-1728.)/1000 + 25.987*5/1000
    h = molar_h/.05869*1000
    power = b["current_A"]*b["voltage_V_reference"]*b["efficiency_for_design_accounting"]
    for row in corners:
        rate = math.pi*row["diameter_mm"]**2/4*row["feed_mm_s"]*row["deposition_utilization"]*.00889
        row["entering_deposit_power_W"] = rate/1000*h
        row["same_net_power_remainder_W"] = power-row["entering_deposit_power_W"]
        row["same_net_heat_eight_wings_kJ"] = 8*row["arc_time_per_wing_s"]*power/1000
        row["entering_enthalpy_eight_wings_kJ"] = 8*row["deposited_mass_per_wing_g"]/1000*h/1000
    nominal_eta = sum(b["deposition_efficiency_range"])/2
    nominal_volume = wire_area*b["feed_mm_s"]*length/speed*nominal_eta
    machining_rows = []
    for row, roof in zip(family["cases"], roofs):
        demand = row["final_second_volume_one_wing_mm3"]
        # Volume demand for a level cap at the requested z plus the retained
        # CAD layer. The full pocket footprint is used above the stock top,
        # so this is a geometric allocation bound, not a solved bead profile.
        extra = max(cut["second_deposited_top_min_mm"]-row["pocket_depth_mm"],0)
        cap_demand = demand+extra*roof["planar_pocket_roof_area_one_wing_mm2"]
        machining_rows.append(dict(case=row["case"], final_second_retained_mm3=demand,
                                   level_cap_target_above_stock_mm=extra,
                                   conservative_level_cap_volume_demand_mm3=cap_demand,
                                   lower_supply_minus_cap_demand_mm3=lower["deposited_volume_per_wing_mm3"]-cap_demand,
                                   second_nominal_material_to_remove_mm3=nominal_volume-demand,
                                   second_lower_material_to_remove_mm3=lower["deposited_volume_per_wing_mm3"]-demand,
                                   second_upper_material_to_remove_mm3=upper["deposited_volume_per_wing_mm3"]-demand))
    result = dict(date="2026-10-08", decision="Adopt documented DMNA099 0.045in x36in stock; diameter acceptance1.143+/-0.020mm; feed8.00+/-0.20mm/s; retain75A/11V design heat budget",
        identity=dict(product="DMNA099 / ERNi-CI", diameter_in=0.045, diameter_mm=b["diameter_mm"], stock_length_in=36., stock_length_mm=b["stock_length_mm"],
                      diameter_acceptance_mm=b["diameter_acceptance_mm"], tolerance_source="Frozen purchaser acceptance requirement calculated from existing geometry and supply task, not a TDS tolerance or supplier guarantee",
                      nominal_source=b["product_TDS_path"], nominal_url=b["product_TDS_url"], page=1,
                      supplier_nominal_size_documented=True, actual_batch_inspected=False),
        selected_input=b, geometry=dict(existing_roof_reads=roofs, maximum_roof_area_one_wing_mm2=area,
                                      minimum_added_height_for_volume_allocation_mm=minimum_added,
                                      conservative_volume_allocation_demand_mm3=required,
                                      continuous_diameter_lower_bound_mm=required_diameter,
                                      diameter_negative_tolerance_limit_from_volume_mm=b["diameter_mm"]-required_diameter,
                                      lower_supply_volume_margin_mm3=lower["deposited_volume_per_wing_mm3"]-required,
                                      lower_supply_uniform_allocation_top_mm=min(cut["first_retained_mm"])+lower["deposited_volume_per_wing_mm3"]/area,
                                      local_contour_proven=False),
        nominal=dict(wire_cross_section_mm2=wire_area, equal_original_volume_feed_mm_s=7.2*(1.2/b["diameter_mm"])**2,
                     volume_rate_change_percent=(b["diameter_mm"]**2*b["feed_mm_s"]/(1.2**2*7.2)-1)*100,
                     total_arc_time_s=t, wire_length_eight_wings_mm=wire, wire_with_15pct_purchase_allowance_mm=1.15*wire,
                     minimum_36in_rods_for_15pct_length=math.ceil(1.15*wire/b["stock_length_mm"]),
                     incoming_consumed_mass_eight_wings_g=mass, deposited_volume_per_wing_at_eta_094_mm3=nominal_volume,
                     deposited_mass_eight_wings_at_eta_094_g=mass*nominal_eta,
                     nominal_second_retained_volume_per_wing_mm3=family["cases"][0]["final_second_volume_one_wing_mm3"],
                     nominal_second_material_to_remove_mm3=nominal_volume-family["cases"][0]["final_second_volume_one_wing_mm3"]),
        rod_preparation=dict(input=rods, maximum_consumed_length_one_wing_mm=max_use,
                             maximum_use_plus_tail_and_trim_mm=max_use+rods["inactive_clamping_tail_min_mm"]+rods["front_trim_allowance_mm"],
                             blank_length_margin_at_max_use_mm=rods["cut_blank_length_acceptance_mm"][0]-max_use-rods["inactive_clamping_tail_min_mm"]-rods["front_trim_allowance_mm"],
                             four_maximum_blanks_plus_cut_loss_per_stock_mm=rods["blanks_per_stock_rod"]*(rods["cut_blank_length_acceptance_mm"][1]+rods["cutting_loss_per_blank_mm"]),
                             eight_blank_length_mm=blanks, preparation_with_cut_loss_mm=prep,
                             purchased_full_stock_length_mm=purchased, unused_stock_length_after_blank_preparation_mm=purchased-prep,
                             purchased_full_stock_mass_g=purchased*wire_area*.00889,
                             purchased_mass_diameter_corner_range_g=[purchased*math.pi*d*d/4*.00889 for d in b["diameter_acceptance_mm"]],
                             prepared_blank_mass_g=blanks*wire_area*.00889,
                             minimum_feed_stroke_mm=rods["minimum_available_feed_stroke_mm"],
                             old_15pct_length_short_of_actual_preparation_mm=prep-1.15*wire,
                             feed_device_capability_verified=False, stock_product_exists=True,
                             purchase_cost_policy="Conservatively charge two914.4mm rods per part, not old1.15 multiplier; reusable remainder not deducted from part cost"),
        supply=dict(corners=corners, lower_corner=lower, upper_corner=upper,
                    old_volume_range_mm3=[min(r["deposited_volume_per_wing_mm3"] for r in old), max(r["deposited_volume_per_wing_mm3"] for r in old)],
                    supply_volume_range_mm3=[lower["deposited_volume_per_wing_mm3"],upper["deposited_volume_per_wing_mm3"]],
                    total_volume_allocation_sufficient=lower["deposited_volume_per_wing_mm3"] >= required, local_coverage_qualified=False),
        machining=dict(cases=machining_rows, minimum_finished_second_thickness_mm=min(cut["total_finished_mm"])-max(cut["first_retained_mm"]),
                       final_remelt_union_limit_mm=cut["final_union_remelt_limit_mm"], minimum_geometric_second_after_final_remelt_mm=min(cut["total_finished_mm"])-max(cut["first_retained_mm"])-cut["final_union_remelt_limit_mm"],
                       physical_remelt_verified=False, actual_cut_history_transferred=False),
        heat=dict(current_A=b["current_A"], reference_voltage_V=b["voltage_V_reference"], gross_power_W=b["current_A"]*b["voltage_V_reference"], net_power_W=power,
                  net_line_energy_J_mm=power/speed, net_heat_eight_wings_kJ=t*power/1000,
                  entering_Ni_temperature_reference_C=entry, specific_enthalpy_relative20C_J_kg=h,
                  enthalpy_source="NIST-JANAF Ni(ref), H(l,1728K)-H(298.15K)=64.516kJ/mol; Cp(liquid)=38.911J/molK; 20->25C reference correction from25.987J/molK; molar mass58.69g/mol; existing1470C engineering incoming-metal reference",
                  enthalpy_url="https://janaf.nist.gov/tables/Ni-001.html",
                  incoming_enthalpy_nominal_mass_eta_range_kJ=[mass*e/1000*h/1000 for e in b["deposition_efficiency_range"]],
                  parent_pool_and_loss_remainder_nominal_mass_kJ=[t*power/1000-mass*e/1000*h/1000 for e in reversed(b["deposition_efficiency_range"])],
                  entering_power_corner_range_W=[min(r["entering_deposit_power_W"] for r in corners),max(r["entering_deposit_power_W"] for r in corners)],
                  net_power_remainder_corner_range_W=[min(r["same_net_power_remainder_W"] for r in corners),max(r["same_net_power_remainder_W"] for r in corners)],
                  supplier_recommended_range_A=[80,110], supplier_recommended_range_V=[13,16],
                  selected_minus_supplier_lower_current_A=-5, selected_minus_supplier_lower_voltage_V=-2,
                  changed_net_arc_input=False, heat_allocation_updated=True, heat_partition_is_fusion_evidence=False),
        qualification=dict(production_WPS_frozen=False, second_layer_continuous_fusion=False, mixed_zone_material_qualified=False, full_manufacturing_verified=False,
                           required_response_checks=["actual accepted diameter and feeder length", "local two-track cap and curved-lip coverage", "fusion at lower-current/short-arc pWPS and actual absorption", "first-layer remelt and surviving composition", "new feed geometry and preserved residual manufacturing chain"]),
        operation_scope="One same-material documented stock revision plus finite supply/heat/machining arithmetic. Nine saved CADs read only. No new CAD, heat or mechanical run.")
    return result


def markdown(r):
    n, g, s, h, m, rods = [r[k] for k in ["nominal", "geometry", "supply", "heat", "machining", "rod_preparation"]]
    lo, hi = s["supply_volume_range_mm3"]
    return f'''# 第二层DMNA099裸棒供货与供料工程决定（2026-10-08）

## 1. 冻结采购和操作尺寸

采用原厂TDS第1页已有的DMNA099／ERNi-CI **0.045 in×36 in**裸棒，精确换算**Ø1.143 mm×914.4 mm**。尺寸身份不再写为“Ø1.20须专项确认”。本设计采购验收直径**1.123～1.163 mm（Ø1.143±0.020）**；公差来自本件供料计算，不是原TDS公布公差或供方保证。来料用分辨率0.001 mm的外径测量器在每根两端和中段、互相垂直两方向检查，所有读数满足验收范围才投入该pWPS；测量不确定度计入验收守界。批次证书核对DMNA099、ERNi-CI和低碳组成身份。尚无实批来料检验结果。

供料冻结**8.00±0.20 mm/s**；原截面守恒补偿是7.20×(1.20/1.143)²={n['equal_original_volume_feed_mm_s']:.6f} mm/s，取8.00后名义体积供料增加{n['volume_rate_change_percent']:.6f}%，原±0.20绝对送进控制保持。两覆盖轨迹、38.563544 mm/翼、焊速2.00±2% mm/s及沉积利用率设计区间0.90～0.98保持。

**直棒备料与设备接口决定**：每翼一段180±0.5 mm定长棒、同棒完成两覆盖轨迹，8翼共8段。最高送进8.20、最低焊速1.96时双轨消耗{rods['maximum_consumed_length_one_wing_mm']:.9f} mm；规定非消耗夹持余尾≥15 mm、前端修整2 mm，合计{rods['maximum_use_plus_tail_and_trim_mm']:.9f}<179.5 mm，最短备料棒仍余{rods['blank_length_margin_at_max_use_mm']:.9f} mm。所需连续送进有效行程≥162 mm，夹持不得侵入余尾。180±0.5、15、2及行程是本设计自动棒材送进接口要求，不能称为已核实现机参数。只在离弧换翼时换棒，换棒和清理计入既有第二层清理换翼时间预留，现机执行时间仍按设备交接核查，不另造产能。

8段名义净备料1440 mm，按每段1 mm切口/端面损失计名义实际备料1448 mm；考虑备料棒+0.5偏差上端为1452 mm。采购**2根914.4 mm完整库存棒，名义1828.8 mm、{rods['purchased_full_stock_mass_g']:.9f} g**；每根只分配4段，按180.5上端及1 mm切口需726 mm，来料棒长验收≥726 mm，不对原TDS未列的长度公差作保证。名义剩余380.8 mm可以库存复用，本件成本保守按2根整棒计。实际采购质量仍随验收直径/棒长记录；仅按直径验收角点、914.4名义长度核算为{rods['purchased_mass_diameter_corner_range_g'][0]:.9f}～{rods['purchased_mass_diameter_corner_range_g'][1]:.9f} g。旧名义15%长度{n['wire_with_15pct_purchase_allowance_mm']:.6f} mm比定长名义备料少{rods['old_15pct_length_short_of_actual_preparation_mm']:.6f} mm，不作为本次实际采购依据。

来源：[DMNA099原TDS](https://www.weldwire.net/_files/ugd/f42bc4_2132a75a538c4a2e90fd6dea7426a91b.pdf)，本机原件docs/sources/Weldwire-Duramax-DMNA099-ERNi-CI-TDS.pdf第1页；旧WWNA99原TDS同列该尺寸，当前订货以DMNA099身份为准。

## 2. 实际供料、余高与加工存留

| 核算项 | 结果 |
| --- | --- |
| 名义截面积 | {n['wire_cross_section_mm2']:.9f} mm² |
| 八翼弧燃／送进长度 | {n['total_arc_time_s']:.6f} s／{n['wire_length_eight_wings_mm']:.6f} mm |
| 8段定长备料含切口／整棒采购 | 1448.000000／1828.800000 mm（2根） |
| 名义消耗质量／η=0.94沉积质量 | {n['incoming_consumed_mass_eight_wings_g']:.9f} g／{n['deposited_mass_eight_wings_at_eta_094_g']:.9f} g |
| 新供料16角点，新增体积/翼 | {lo:.9f}～{hi:.9f} mm³ |
| 原Ø1.20、7.20供料体积/翼 | {s['old_volume_range_mm3'][0]:.9f}～{s['old_volume_range_mm3'][1]:.9f} mm³ |
| η=0.94名义沉积／名义最终第二层存留 | {n['deposited_volume_per_wing_at_eta_094_mm3']:.9f}／{n['nominal_second_retained_volume_per_wing_mm3']:.9f} mm³/翼 |
| 名义几何待去除第二层 | {n['nominal_second_material_to_remove_mm3']:.9f} mm³/翼 |
| 齐平最小第二层／累计重熔0.40后几何余层 | {m['minimum_finished_second_thickness_mm']:.2f}／{m['minimum_geometric_second_after_final_remelt_mm']:.2f} mm |

只读既有9个STEP的槽口顶面，最大每翼投影面积{g['maximum_roof_area_one_wing_mm2']:.9f} mm²。以首层最小0.65和要求堆焊顶面1.75构成1.10 mm整面积补高，保守体积分配需求{g['conservative_volume_allocation_demand_mm3']:.9f} mm³/翼。固定最低送进7.80、最高焊速2.04和η=0.90，按

d_min=√[4·V_req·v_max/(π·f_min·L·η_min)]={g['continuous_diameter_lower_bound_mm']:.9f} mm。

得到供料允许的直径负偏差{g['diameter_negative_tolerance_limit_from_volume_mm']:.9f} mm；取±0.020的采购验收要求保留{g['lower_supply_volume_margin_mm3']:.9f} mm³/翼总供料余量。相同面积均匀分配时最低等效顶面为{g['lower_supply_uniform_allocation_top_mm']:.9f} mm，高于1.75。**这是总供料充足性，局部双轨铺展、圆角覆盖、起停和连续熔合仍由实际轮廓及有效热史核查，不能用此等效顶面授予局部通过。**

9个既有槽公差的最终存留和待去料量分别保存在JSON的machining.cases；未新建CAD、未移动槽或加大最终孔微珩额度。各槽顶面加工余高要求仍为至少0.15～0.35 mm。预制连接面齐平加工发生在最终孔加工之前，不能用于补偿最终焊接位置度。

## 3. 同一净热分配与75 A/11 V的适用范围

保留75 A/11 V、η=0.6、2.00 mm/s的本件**设计pWPS**：毛功率825 W、净功率495 W、净247.5 J/mm、八翼净热{h['net_heat_eight_wings_kJ']:.9f} kJ。选值保持200～300℃预热的薄层、短弧和原定线能量；11 V是工作弧压参考而非设备强制电压。此组合比原TDS的0.045 in推荐80～110 A/13～16 V下限低5 A/2 V。原厂范围是该规格通用操作建议，不提供本槽预热、间隙及重熔深度；因此没有直接抄入增加本槽热量，也没有把75 A/11 V写成供方保证或生产窗口。

按现有1470℃来料参考和[NIST-JANAF Ni(ref)原表](https://janaf.nist.gov/tables/Ni-001.html)，用1728 K液态焓64.516 kJ/mol、液态Cp38.911 J/(mol·K)、20→25℃基准修正及58.69 g/mol得到H={h['specific_enthalpy_relative20C_J_kg']:.6f} J/kg。它约束低碳纯镍来料进入焓记账，不赋予实际稀释第二层、Si/Mn混合区或PMZ热力学和力学资格。

名义尺寸在η=0.90～0.98时，进入沉积焓为{h['incoming_enthalpy_nominal_mass_eta_range_kJ'][0]:.9f}～{h['incoming_enthalpy_nominal_mass_eta_range_kJ'][1]:.9f} kJ，从同一净{h['net_heat_eight_wings_kJ']:.9f} kJ扣除；母材/熔池及损失余额为{h['parent_pool_and_loss_remainder_nominal_mass_kJ'][0]:.9f}～{h['parent_pool_and_loss_remainder_nominal_mass_kJ'][1]:.9f} kJ。全部供料角点来料功率{h['entering_power_corner_range_W'][0]:.9f}～{h['entering_power_corner_range_W'][1]:.9f} W，净功率余额{h['net_power_remainder_corner_range_W'][0]:.9f}～{h['net_power_remainder_corner_range_W'][1]:.9f} W。正余额仅说明热账可分配；不足以证明弧能实际截获、首次层重熔量或双轨连续连接。

本轮尺寸决定已落实到YAML和两张预制pWPS卡；有效第二层连接、混合区物性、加工后残余历史和完全卸夹性能仍未通过。换规格后的出生几何/质量必须使用本次量，旧规格或越温区热史不进入本件下游制造预测。未启动第二层有限元或新参数搜索。
'''


if __name__ == "__main__":
    r = calculate()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/(NAME+".json")).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT/(NAME+".md")).write_text(markdown(r), encoding="utf-8")
    print(json.dumps({k:r[k] for k in ["nominal","geometry","heat"]},ensure_ascii=False,indent=2))
