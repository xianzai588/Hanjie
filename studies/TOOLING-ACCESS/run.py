"""执行刚性工装包络检查并导出一个名义装配场景。"""

import csv
import hashlib
import json
from pathlib import Path
import sys
from xml.sax.saxutils import escape

from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from hanjie.domain.tooling_access import SPEC, read_yaml, run_tooling_study


def draw_section(result, points, path):
    config, assembly = result["config"], result["assembly"]
    geometry = read_yaml(ROOT / config["sources"]["geometry"])
    design = geometry["design_assumptions"]
    official = geometry["official"]
    scale, cx, bottom = 2.3, 290, 730
    x = lambda r: cx + scale * r
    y = lambda z: bottom - scale * z
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1250" height="850" viewBox="0 0 1250 850">',
           '<rect width="1250" height="850" fill="#ffffff"/>',
           '<style>text{font-family:"Microsoft YaHei",sans-serif;fill:#172b3a;font-size:16px} .title{font-size:25px;font-weight:700} .small{font-size:14px}</style>']

    def text(px, py, label, cls=""):
        svg.append(f'<text x="{px}" y="{py}" class="{cls}">{escape(label)}</text>')

    def box(r0, r1, z0, z1, color):
        svg.append(f'<rect x="{x(r0)}" y="{y(z1)}" width="{scale*(r1-r0)}" height="{scale*(z1-z0)}" fill="{color}" stroke="#334155"/>')

    def polygon(rz, color):
        values = " ".join(f"{x(r):.2f},{y(z):.2f}" for r, z in rz)
        svg.append(f'<polygon points="{values}" fill="{color}" stroke="#334155"/>')

    text(45, 48, "刚性工装包络与退出路径检查", "title")
    text(45, 78, "名义情景：座体底面 z=100 mm；底口未封闭；仅检查列明实体，未作制造放行")
    ri = assembly["shell_inner_radius_mm"]
    ro, height = official["shell_outer_diameter"] / 2, official["shell_height"]
    bore = official["bearing_bore_diameter"] / 2
    for sign in (-1, 1):
        lo, hi = sorted((sign * ri, sign * ro))
        box(lo, hi, 0, height, "#cbd5e1")
        lo, hi = sorted((sign * bore, sign * design["wing_outer_radius"]))
        box(lo, hi, assembly["seat_bottom_z_mm"], assembly["seat_top_z_mm"], "#edc777")
    sr, sz = config["shield"]["outer_radius_mm"], assembly["shield_floor_z_mm"]
    box(-sr, sr, sz, sz + config["shield"]["floor_thickness_mm"], "#7db8d5")
    for sign in (-1, 1):
        lo, hi = sorted((sign * sr, sign * (sr - config["shield"]["rim_thickness_mm"])))
        box(lo, hi, sz, assembly["shield_top_z_mm"], "#7db8d5")
    mr = design["mandrel_large_diameter"] / 2
    box(-mr, mr, assembly["seat_top_z_mm"], config["mandrel"]["upper_obstruction_top_z_mm"], "#a4bfa5")
    # 轴向剖面直接由同一包络端点与半径生成；不手工移动图形躲避干涉。
    import math
    angle = math.radians(config["torch"]["export_tilt_deg"])
    nx, nz = math.cos(angle), math.sin(angle)
    process = read_yaml(ROOT / config["sources"]["process"])["process"]["nominal"]
    for begin, end, radius, color in ((points["tip"], points["face"], config["torch"]["tungsten_radius_mm"], "#475569"),
                                      (points["face"], points["end"], process["nozzle_diameter_mm"]/2, "#d2a0a0")):
        polygon([(begin[0]+radius*nx,begin[2]+radius*nz),(end[0]+radius*nx,end[2]+radius*nz),
                 (end[0]-radius*nx,end[2]-radius*nz),(begin[0]-radius*nx,begin[2]-radius*nz)],color)
    end, radius = points["end"], config["torch"]["body_radius_mm"]
    svg.append(f'<circle cx="{x(end[0])}" cy="{y(end[2])}" r="{scale*radius}" fill="#d2a0a0" stroke="#334155"/>')
    box(end[0]-radius,end[0]+radius,end[2],config["torch"]["body_top_z_mm"],"#d2a0a0")
    leg, top = design["fillet_leg_length"], assembly["seat_top_z_mm"]
    for sign in (-1,1):
        polygon([(sign*(ri-leg),top),(sign*ri,top),(sign*ri,top+leg)],"#d97657")
    svg.append(f'<line x1="{cx}" y1="{y(sz)-5}" x2="{cx}" y2="{y(-22)}" stroke="#167897" stroke-width="3"/>')
    polygon([(-3,-17),(0,-22),(3,-17)],"#167897")
    text(170,795,"底口退出（需开放底口及下方操作空间）","small")
    text(70,225,"壳体 Ø160 × 200 × 5","small")
    text(135,450,"座体 Ø40 孔","small")
    text(135,555,"截留盘 Ø148","small")
    text(340,555,"壁隙 1 mm","small")
    text(590,160,"检查范围与关键结论","title")
    notes = [
        "蓝色盘：底板1 mm、总高3 mm，位于座体下方6 mm。",
        "整盘向下退出：扫掠圆柱与壳体/三种座体均不相交。",
        "整盘向上退出：与已焊座体相交，不能穿过Ø40孔。",
        "30°弯头后竖直枪体：保留为几何可达性候选。",
        "直线延长枪体与中心定位包络可能冲突，需比较。",
        "绿色仅为上方定位机构占位包络，不是完整夹具。",
        "1:50锥度与圆柱孔是边缘接触，不是全孔贴合。",
        "锥面存在自锁情景；定位重复性及主动退锥待设计。",
        "截留盘外缘未覆盖R74.98接口的垂直落物路径。",
        "仍需可收拢挡边/源头封挡；不得宣称内腔洁净达标。",
        "未包含：支承、腕部、送丝机构、管线与热变形。",
    ]
    for i, note in enumerate(notes):
        text(590,207+i*39,note)
    text(45,825,"来源：既有CAD实体＋TOOLING-ACCESS/config.yaml工装假设；比例用于剖面表达，非加工图。","small")
    svg.append('</svg>')
    path.write_text("\n".join(svg),encoding="utf-8")


def main():
    result, bodies = run_tooling_study(ROOT)
    output = Path(__file__).resolve().parent / "results"
    cad = ROOT / "cad/generated/tooling-access"
    output.mkdir(parents=True, exist_ok=True)
    cad.mkdir(parents=True, exist_ok=True)
    writer = STEPControl_Writer()
    for name in ("shell", "Continuous", "shield", "upper_mandrel_envelope", "weld_keepout", "torch_envelope"):
        if writer.Transfer(bodies[name], STEPControl_AsIs) != IFSelect_RetDone:
            raise ValueError(f"STEP实体转换失败：{name}")
    if writer.Write(str(cad / "nominal-envelope.step")) != IFSelect_RetDone:
        raise ValueError("STEP导出失败")
    draw_section(result, bodies["torch_points"], cad / "section.svg")
    snapshots = {SPEC: read_yaml(ROOT / SPEC)}
    hashes = {}
    for path in result["config"]["sources"].values():
        if path.endswith(".brep"):
            hashes[path] = hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
        else:
            snapshots[path] = read_yaml(ROOT/path)
    load = snapshots[result["config"]["sources"]["load_basis"]]
    for path in load["layouts"].values():
        manifest = read_yaml(ROOT/path)
        snapshots[path] = manifest
        brep = (Path(path).parent / Path(manifest["generation"]["brep_file"]).name).as_posix()
        hashes[brep] = hashlib.sha256((ROOT/brep).read_bytes()).hexdigest()
    (output/"run-inputs.json").write_text(json.dumps({"structured_inputs":snapshots,"geometry_sha256":hashes},ensure_ascii=False,indent=2),encoding="utf-8")
    result["cad_outputs"] = ["cad/generated/tooling-access/nominal-envelope.step","cad/generated/tooling-access/section.svg"]
    (output/"assessment.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    with (output/"result.csv").open("w",encoding="utf-8-sig",newline="") as stream:
        rows=result["shield"]["cases"]
        writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader();writer.writerows(rows)
    print(json.dumps({"shield":result["shield"],"torch":[{k:r[k] for k in ("tilt_deg","body_style","sampled_poses_clear","vertical_path_certificate")} for r in result["torch"]["cases"]],"mandrel":result["mandrel"]},ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
