"""生成当前参赛工艺提案；不改写历史单道诊断输入。"""
from pathlib import Path
import sys
import json
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from hanjie.domain.competition_design import current_assessment
ROOT = Path(__file__).resolve().parents[2]


def main():
    r = current_assessment(ROOT)
    p = r["process"]
    fixture = r["spec"]["fixture"]
    machining = r["machining_allowance"]
    selected = machining["selected_candidate"]
    selected_row = next(row for row in machining["candidates"] if row["id"] == selected)
    out = ROOT / "deliverables/process"
    out.mkdir(parents=True, exist_ok=True)
    card = f"""# COMPETITION-R1 焊接工艺提案
状态：设计提案，不是经评定合格的WPS/PQR。详细依据见当前说明书。
历史Ø1.2单道局部热诊断仍保留在project/process.yaml；本卡按project/competition-design.yaml显式修订。

| 项目 | 当前设计 |
| --- | --- |
| 母材 | QT450-10座体 / Q235B壳体 |
| 接头 | 6P-FAIR_B，6×18 mm角焊缝 |
| 方法 | 自动TIG，直流电极负极 |
| 焊材 | EN ISO 1071 S C NiFe-2 实心TIG棒，Ø1.6；AWS分类待批次证书/供方确认 |
| 界面与过渡层 | NiFe 55型镍铁基实心TIG棒候选填充（EN ISO 1071 S C NiFe-2；AWS分类待批次证书确认）；Ni/ENiCrFe-3高镍打底列为A/B对比路线，须以稀释率、宏观截面、硬度和裂纹检查决定 |
| 稀释控制 | 第一道低电流、不摆动、小熔深；后三道热循环可能继续影响铸铁侧；“不增加熔深”仅作待验证工艺目标 |
| 表面预处理 | 焊接界面机械打磨至金属光泽，去除石墨层与氧化皮；丙酮或无水乙醇去油，禁用含氯溶剂；处理后24 h内施焊；每道层间机械清理 |
| 电参数 | 75 A、12 V、焊速1.5 mm/s |
| 道数 / 顺序 | 4道，每道1→4→3→6→2→5 |
| 反变形 | 主：焊序对称化；辅：逐件装配预偏置（上限受0.01～0.04 mm径向间隙约束，超限拒绝）；辅：卸夹时机控制 |
| 应力释放 / 隔热 | 6条径向柔顺释放槽，宽4.0 mm、槽根R2.0、槽底最小半径R39.0；兼作孔心至焊道的热阻隔离 |
| 固定送丝 | {p['fixed_feed_mm_s']:.6f} mm/s |
| 沉积效率 η_dep | 0.85～1.00；固定送丝按下界反算 |
| 电弧热效率 η_arc | {p['eta_arc']:.2f}；只用于净热输入 |
| 等面积焊脚 | 3.500～3.796 mm；最大可达性包络3.8 |
| 气体 | 99.999% Ar，10 L/min；设计监控区间8～12 |
| 预热 / 层间 | QT450-10列入铁素体至珠光体型牌号系列，但实际批次组织未核实；150℃仍是未放行候选。TWI的RT～150℃/200～330℃是MMA/MIG类比，没有TIG栏；层间≤200℃须经TIG试件评定 |
| 后热 | I：NiFe、150℃候选预热＋覆盖缓冷；II：NiFe、250℃＋650℃×90 min；III：Ni-CI、250℃＋650℃×90 min。三者均为对比方案，尚无WPS放行 |
| 单道毛弧能 / 净热输入 | 600 / 330 J/mm |
| 本件四道净热输入 | {p['total_net_heat_j']/1000:.2f} kJ |
| 弧燃时间 | {p['arc_on_time_s']:.0f} s；不含等待、装卸与预热 |
| 理想耗棒长度 | {p['wire_length_mm']:.2f} mm；不含夹持残段与损耗 |
| 条件承载 | 参考载荷包络下所需许用应力量级见说明书第3节；切换阈值随载荷倍率给出 |
| 疲劳口径 | 52.17 MPa为静力等效喉部筛查值；1.150为60/52.17静力条件比值。焊趾、焊根/喉部和翼根/槽根分开评定，本接头FAT等级和寿命均未评定 |
| 防护与夹紧 | 连续薄裙接料组件、圆柱胀套、独立500 N端面压环 |
| 松夹 | 停弧后≥120 s且最高温度<55℃；确认主动回退 |
| 回收 | 底口开放、盘面朝上贴壁下撤，离开底口后封盖 |
| 焊后加工 | 候选{selected}：预加工孔Ø{selected_row['pre_weld_bore_min_mm']:.3f}～Ø{selected_row['pre_weld_bore_max_mm']:.3f}，最小径向余量{selected_row['geometric_min_radial_allowance_mm']:.3f} mm；装入/接触/回退端点已筛查；焊后检查→终镗→最终CMM |
| 洁净判据 | 项目设计限值：≥0.5 mm颗粒0个、0.2～0.5 mm不超过5个，内窥覆盖率≥95%；ISO 16232/VDA 19.1仅作取样与报告方法依据 |
| 测量 | 20±1℃；测得位置度直径＋同口径不确定度≤0.05 mm |

### 材料组织与热循环决策门

| 分支 | 文献参照结果 | 方案取舍 |
| --- | --- | --- |
| I：NiFe、无PWHT | R007灰铸铁FC250、250℃预热时，NiFe HAZ约442.5 HB；其四种填料HAZ为约432～489 HB | 风险量级对标，不预测本接头；须以QT450-10同批TIG试件确认 |
| II：NiFe＋650℃×90 min | R007 HAZ约249.9 HB、焊缝约403.5 HB | HAZ软化与NiFe焊缝升硬并存，核验强度、硬度梯度与热变形 |
| III：Ni-CI＋650℃×90 min | R007 HAZ约223.8 HB、焊缝约195.9 HB；仅此组合满足该FC250研究的组织/硬度要求 | 强度匹配和本项目TIG接头性能仍未知，不直接替换NiFe候选 |

放行前必须取得QT450-10批次质保书、热处理状态及按GB/T 9441-2021记录的金相组织和相比例。未完成前，预热窗口、PWHT分支选择和WPS/PQR均阻断；珠光体强化批次须重定TIG窗口，不能直接照搬TWI的MMA/MIG温度。

### 焊接装备功能规格

| 装备单元 | 功能要求（待采购/联调确认） |
| --- | --- |
| TIG电源 | DCEN，稳定覆盖75 A/12 V名义窗口；载流持续率满足四道节拍 |
| 行走机器人/轴 | 六段轨迹稳定1.5 mm/s；有效负载、臂展、枪姿与线缆包络通过整段彩排 |
| 冷丝送进 | Ø1.6 mm实心棒，稳定覆盖1.343967 mm/s；支持连续送进、尾料管理与速度追溯 |
| 在线监控 | 同步记录电流、电压、焊速、送棒速度、氩流量与多点温度；信号缺失或越限闭锁 |

既定压力情景所需径向余量为{machining['required_radial_allowance_mm']:.6f} mm；候选{selected}按预加工孔最大允许直径{selected_row['pre_weld_bore_max_mm']:.3f} mm计算，最小几何余量{selected_row['geometric_min_radial_allowance_mm']:.3f} mm，压力与尺寸端点筛查已闭合。终镗刀具包络、孔壁最薄处和胀套弹性重复性尚未完成数字检查，保持待判；真实焊后变形、制造能力与终检仍待工业验证。薄裙热接触、四道熔合与裂纹也尚未验证。终镗前必须独立记录焊后几何检查，终镗后再做CMM和最终洁净检查。焊材规格依据：https://certilas.com/en/product/nife-55-tig ，供方AWS分类待批次证书确认；Rm 450 MPa、Rp0.2 300 MPa为供方典型熔敷金属值，只用于强度匹配量级说明，不作本接头许用值。
"""
    (out / "joint-process-card.md").write_text(card, encoding="utf-8")
    (out / "joint-process-card.json").write_text(json.dumps({"version":r["version"], "process":p, "proposal":r["spec"]["process"], "release":r["release"]},ensure_ascii=False,indent=2),encoding="utf-8")
    print("已更新当前参赛工艺卡")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
