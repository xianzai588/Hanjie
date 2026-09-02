"""把 generated/engineering-drawings 下的 SVG 工程图忠实导出为提交级 PDF 图包。

转换器只做渲染搬运：不改动任何几何、尺寸、注记与 design-review 状态。
SVG 由 generate_engineering_drawings.py 程序化生成，仅含 line/circle/rect/
polygon/text 五种元素，样式集中于 <style> 块，因此按“CSS 类 → PDF 属性”
映射重绘即可保持矢量保真。
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[2]
SVG_DIR = ROOT / "cad" / "generated" / "engineering-drawings"
PDF_DIR = SVG_DIR / "pdf"
NS = "{http://www.w3.org/2000/svg}"
FONT_REGULAR = Path("C:/Windows/Fonts/Deng.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/Dengb.ttf")
COMBINED_NAME = "HJ-DRW-drawing-set.pdf"


def register_fonts() -> None:
    if not FONT_REGULAR.exists() or not FONT_BOLD.exists():
        raise FileNotFoundError("Windows Deng 字体不可用，无法保证中文 PDF 字形完整")
    pdfmetrics.registerFont(TTFont("Deng", str(FONT_REGULAR)))
    pdfmetrics.registerFont(TTFont("Deng-Bold", str(FONT_BOLD)))


def parse_css(css_text: str) -> dict[str, dict[str, str]]:
    rules: dict[str, dict[str, str]] = {}
    for match in re.finditer(r"([^{}]+)\{([^}]*)\}", css_text):
        declarations: dict[str, str] = {}
        for part in match.group(2).split(";"):
            if ":" in part:
                key, value = part.split(":", 1)
                declarations[key.strip()] = value.strip()
        for selector in match.group(1).split(","):
            rules[selector.strip()] = declarations
    return rules


def color(value: str | None):
    if not value or value == "none":
        return None
    return HexColor(value)


def dash_array(value: str | None, scale: float) -> list[float] | None:
    if not value or value == "none":
        return None
    return [float(v) * scale for v in value.replace(",", " ").split()]


def style_for(rules: dict[str, dict[str, str]], tag: str, cls: str, attrib: dict) -> dict:
    merged: dict[str, str] = {}
    merged.update(rules.get(tag, {}))
    if cls:
        merged.update(rules.get(f".{cls}", {}))
    for key, value in attrib.items():
        if key in ("stroke", "fill", "stroke-width", "stroke-dasharray", "font-size", "font-weight"):
            merged[key] = value
    return merged


def export_sheet(svg_path: Path, canvas: Canvas, page_pw: float, page_ph: float, rules: dict[str, dict[str, str]]) -> str:
    root = ET.parse(svg_path).getroot()
    view_box = [float(v) for v in root.get("viewBox").split()]
    vw, vh = view_box[2], view_box[3]
    scale = min(page_pw / vw, page_ph / vh)
    off_x = (page_pw - vw * scale) / 2
    off_y = (page_ph - vh * scale) / 2

    def X(x: float) -> float:
        return off_x + x * scale

    def Y(y: float) -> float:
        return off_y + (vh - y) * scale

    title = ""
    for element in root:
        tag = element.tag.replace(NS, "")
        if tag == "style":
            continue
        attrib = dict(element.attrib)
        cls = attrib.get("class", "")
        style = style_for(rules, tag, cls, attrib)
        stroke = color(style.get("stroke"))
        fill = color(style.get("fill"))
        width = max(float(style.get("stroke-width", "1")) * scale, 0.35)
        dash = dash_array(style.get("stroke-dasharray"), scale)
        if tag == "text":
            if not title and cls == "title":
                title = element.text or ""
            size = float(style.get("font-size", "14").removesuffix("px")) * scale
            canvas.setFont("Deng-Bold" if style.get("font-weight") == "700" else "Deng", size)
            canvas.setFillColor(fill or HexColor("#111827"))
            text = element.text or ""
            anchor = attrib.get("text-anchor", "start")
            if anchor == "middle":
                canvas.drawCentredString(X(float(attrib["x"])), Y(float(attrib["y"])), text)
            elif anchor == "end":
                canvas.drawRightString(X(float(attrib["x"])), Y(float(attrib["y"])), text)
            else:
                canvas.drawString(X(float(attrib["x"])), Y(float(attrib["y"])), text)
            continue
        if stroke:
            canvas.setStrokeColor(stroke)
        canvas.setLineWidth(width)
        if dash:
            canvas.setDash(dash)
        else:
            canvas.setDash()
        if fill:
            canvas.setFillColor(fill)
        if tag == "line":
            canvas.line(X(float(attrib["x1"])), Y(float(attrib["y1"])), X(float(attrib["x2"])), Y(float(attrib["y2"])))
        elif tag == "circle":
            canvas.circle(X(float(attrib["cx"])), Y(float(attrib["cy"])), float(attrib["r"]) * scale, stroke=1, fill=1 if fill else 0)
        elif tag == "rect":
            rx = float(attrib.get("rx", "0")) * scale
            x = X(float(attrib.get("x", "0")))
            y = Y(float(attrib.get("y", "0")) + float(attrib.get("height", "0")))
            w, h = float(attrib.get("width", "0")) * scale, float(attrib.get("height", "0")) * scale
            if rx > 0:
                canvas.roundRect(x, y, w, h, rx, stroke=1, fill=1 if fill else 0)
            else:
                canvas.rect(x, y, w, h, stroke=1, fill=1 if fill else 0)
        elif tag == "polygon":
            points = re.findall(r"(-?[\d.]+),(-?[\d.]+)", attrib["points"])
            path = canvas.beginPath()
            for index, (px, py) in enumerate(points):
                if index == 0:
                    path.moveTo(X(float(px)), Y(float(py)))
                else:
                    path.lineTo(X(float(px)), Y(float(py)))
            path.close()
            canvas.drawPath(path, stroke=1, fill=1 if fill else 0)
    return title


def main() -> None:
    register_fonts()
    svg_paths = sorted(SVG_DIR.glob("*.svg"))
    if not svg_paths:
        raise FileNotFoundError(f"未找到 SVG 图纸: {SVG_DIR}")
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    page_pw, page_ph = landscape(A4)
    today = _dt.date.today().isoformat()
    sheets: list[dict[str, str]] = []

    for index, svg_path in enumerate(svg_paths, start=1):
        root = ET.parse(svg_path).getroot()
        style_element = root.find(f"{NS}style")
        rules = parse_css(style_element.text or "") if style_element is not None else {}
        pdf_path = PDF_DIR / (svg_path.stem + ".pdf")
        canvas = Canvas(str(pdf_path), pagesize=landscape(A4))
        title = export_sheet(svg_path, canvas, page_pw, page_ph, rules)
        canvas.setFont("Deng", 7)
        canvas.setFillColor(HexColor("#475569"))
        canvas.drawCentredString(
            page_pw / 2, 10,
            f"HJ 数字工程图集 · {today} · 第 {index}/{len(svg_paths)} 页 · 状态 design-review（未完成制造签审）",
        )
        canvas.showPage()
        canvas.save()
        sheets.append({"pdf": f"pdf/{pdf_path.name}", "title": title, "source": svg_path.name})

    combined = Canvas(str(PDF_DIR / COMBINED_NAME), pagesize=landscape(A4))
    for sheet in sheets:
        root = ET.parse(SVG_DIR / sheet["source"]).getroot()
        style_element = root.find(f"{NS}style")
        rules = parse_css(style_element.text or "") if style_element is not None else {}
        title = export_sheet(SVG_DIR / sheet["source"], combined, page_pw, page_ph, rules)
        combined.setFont("Deng", 7)
        combined.setFillColor(HexColor("#475569"))
        position = sheets.index(sheet) + 1
        combined.drawCentredString(
            page_pw / 2, 10,
            f"HJ 数字工程图集 · {today} · 第 {position}/{len(sheets)} 页 · 状态 design-review（未完成制造签审）",
        )
        combined.showPage()
    combined.save()

    manifest = {
        "generated_at": today,
        "source": "cad/parametric/generate_engineering_drawings.py 生成的 SVG（本脚本仅渲染，不改几何）",
        "status": "design-review; not manufacturing release",
        "page_size": "A4 landscape, vector",
        "sheet_count": len(sheets),
        "combined": f"pdf/{COMBINED_NAME}",
        "sheets": sheets,
    }
    (PDF_DIR / "pdf-exports.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已导出 {len(sheets)} 张 PDF 至 {PDF_DIR}")


if __name__ == "__main__":
    main()
