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
| 焊材 | NiFe 55类实心TIG棒，Ø1.6；牌号按批次证书核实 |
| 电参数 | 75 A、12 V、焊速1.5 mm/s |
| 道数 / 顺序 | 4道，每道1→4→3→6→2→5 |
| 固定送丝 | {p['fixed_feed_mm_s']:.6f} mm/s |
| 沉积效率假设 | 0.85～1.00 |
| 等面积焊脚 | 3.500～3.796 mm；最大可达性包络3.8 |
| 气体 | 99.999% Ar，10 L/min；设计监控区间8～12 |
| 预热 / 层间 | 名义150℃；起弧前各点≥130℃且最高<200℃ |
| 单道毛弧能 / 净热输入 | 600 / 330 J/mm |
| 本件四道净热输入 | {p['total_net_heat_j']/1000:.2f} kJ |
| 弧燃时间 | {p['arc_on_time_s']:.0f} s；不含等待、装卸与预热 |
| 理想耗棒长度 | {p['wire_length_mm']:.2f} mm；不含夹持残段与损耗 |
| 防护与夹紧 | 连续薄裙接料组件、圆柱胀套、独立500 N端面压环 |
| 松夹 | 停弧后≥120 s且最高温度<55℃；确认主动回退 |
| 回收 | 底口开放、盘面朝上贴壁下撤，离开底口后封盖 |
| 测量 | 20±1℃；测得位置度直径＋同口径不确定度≤0.05 mm |

薄裙热接触、胀套柔性、四道熔合与裂纹、完整热残余尚未验证；等面积守恒不等于实际成形。焊材规格依据：https://certilas.com/en/product/nife-55-tig ，该页典型强度不作本接头许用值。
"""
    (out / "joint-process-card.md").write_text(card, encoding="utf-8")
    (out / "joint-process-card.json").write_text(json.dumps({"version":r["version"], "process":p, "proposal":r["spec"]["process"], "release":r["release"]},ensure_ascii=False,indent=2),encoding="utf-8")
    print("已更新当前参赛工艺卡")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
