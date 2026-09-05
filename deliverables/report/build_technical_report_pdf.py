"""生成 Hanjie 技术说明书 V2 的参赛 PDF。

本脚本只编排已经冻结的数字证据和工程边界，不重新计算或改写模型结果。
生成物固定写入 output/pdf/，便于提交前复核与归档。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "pdf" / "technical-report-v2.pdf"
FONT_REGULAR = Path(r"C:\Windows\Fonts\Deng.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\Dengb.ttf")
CHARTS = {
    "reduced": ROOT / "simulation" / "results" / "summary.png",
    "fe": ROOT / "simulation" / "fe" / "results" / "fe-summary.png",
    "mc": ROOT / "simulation" / "results" / "monte-carlo" / "monte-carlo.png",
    "vision": ROOT / "automation" / "vision" / "results" / "difficult-summary.png",
}

NAVY = colors.HexColor("#0F172A")
SLATE = colors.HexColor("#475569")
MUTED = colors.HexColor("#64748B")
TEAL = colors.HexColor("#0F766E")
TEAL_LIGHT = colors.HexColor("#CCFBF1")
AMBER = colors.HexColor("#D97706")
AMBER_LIGHT = colors.HexColor("#FEF3C7")
RED = colors.HexColor("#B91C1C")
RED_LIGHT = colors.HexColor("#FEE2E2")
LINE = colors.HexColor("#CBD5E1")
PAPER = colors.HexColor("#F8FAFC")


def register_fonts() -> None:
    if not FONT_REGULAR.exists() or not FONT_BOLD.exists():
        raise FileNotFoundError("Windows Deng 字体不可用，无法保证中文 PDF 字形完整")
    pdfmetrics.registerFont(TTFont("Deng", str(FONT_REGULAR)))
    pdfmetrics.registerFont(TTFont("Deng-Bold", str(FONT_BOLD)))


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="CoverTitle", fontName="Deng-Bold", fontSize=25, leading=33,
    textColor=NAVY, spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="CoverSub", fontName="Deng", fontSize=11, leading=17,
    textColor=SLATE, spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="H1CN", fontName="Deng-Bold", fontSize=16, leading=22,
    textColor=NAVY, spaceBefore=3, spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="H2CN", fontName="Deng-Bold", fontSize=11, leading=16,
    textColor=TEAL, spaceBefore=8, spaceAfter=4,
))
styles.add(ParagraphStyle(
    name="BodyCN", fontName="Deng", fontSize=9.15, leading=14.1,
    textColor=NAVY, spaceAfter=5,
))
styles.add(ParagraphStyle(
    name="BodySmall", fontName="Deng", fontSize=7.6, leading=10.4,
    textColor=SLATE, spaceAfter=3,
))
styles.add(ParagraphStyle(
    name="Caption", fontName="Deng", fontSize=7.4, leading=10,
    textColor=MUTED, alignment=TA_CENTER, spaceBefore=3, spaceAfter=7,
))
styles.add(ParagraphStyle(
    name="TableText", fontName="Deng", fontSize=7.4, leading=9.6,
    textColor=NAVY,
))
styles.add(ParagraphStyle(
    name="TableHead", fontName="Deng-Bold", fontSize=7.4, leading=9.6,
    textColor=colors.white,
))
styles.add(ParagraphStyle(
    name="TableCaption", fontName="Deng-Bold", fontSize=7.4, leading=10,
    textColor=MUTED, spaceBefore=4, spaceAfter=3,
))
styles.add(ParagraphStyle(
    name="Callout", fontName="Deng", fontSize=9, leading=13.4,
    textColor=NAVY, leftIndent=2, rightIndent=2,
))
styles.add(ParagraphStyle(
    name="Metric", fontName="Deng-Bold", fontSize=18, leading=22,
    textColor=TEAL, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="MetricLabel", fontName="Deng", fontSize=7.4, leading=10,
    textColor=SLATE, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    name="Footer", fontName="Deng", fontSize=7, leading=8,
    textColor=MUTED,
))


def P(text: str, style: str = "BodyCN") -> Paragraph:
    return Paragraph(text, styles[style])


_TABLE_COUNTER = 0


def table(data: list[list[object]], widths: list[float], header: bool = True, compact: bool = False) -> Table:
    global _TABLE_COUNTER
    _TABLE_COUNTER += 1
    converted: list[list[object]] = []
    caption = [P(f"表 {_TABLE_COUNTER}", "TableCaption")]
    caption.extend(["" for _ in range(len(widths) - 1)])
    converted.append(caption)
    for row_index, row in enumerate(data):
        converted.append([
            item if isinstance(item, Flowable) else P(str(item), "TableHead" if header and row_index == 0 else "TableText")
            for item in row
        ])
    t = Table(converted, colWidths=widths, repeatRows=2 if header else 1, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("SPAN", (0, 0), (-1, 0)),
        ("GRID", (0, 0), (-1, 0), 0, colors.white),
        ("LEFTPADDING", (0, 0), (-1, 0), 0),
        ("RIGHTPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5 if not compact else 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5 if not compact else 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4 if not compact else 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if not compact else 3),
        ("ROWBACKGROUNDS", (0, 2 if header else 1), (-1, -1), [colors.white, PAPER]),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 1), (-1, 1), NAVY),
            ("TEXTCOLOR", (0, 1), (-1, 1), colors.white),
        ])
    t.setStyle(TableStyle(commands))
    return t


def callout(text: str, tone: str = "teal") -> Table:
    background, border = {
        "teal": (TEAL_LIGHT, TEAL),
        "amber": (AMBER_LIGHT, AMBER),
        "red": (RED_LIGHT, RED),
    }[tone]
    t = Table([[P(text, "Callout")]], colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("BOX", (0, 0), (-1, -1), 0.8, border),
        ("LINEBEFORE", (0, 0), (0, -1), 4, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def metric_card(value: str, label: str) -> Table:
    t = Table([[P(value, "Metric")], [P(label, "MetricLabel")]], colWidths=[39 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


class Pipeline(Flowable):
    def __init__(self, width: float = 170 * mm, height: float = 25 * mm) -> None:
        super().__init__()
        self.width = width
        self.height = height

    def draw(self) -> None:
        labels = [
            ("题面\n约束", NAVY), ("焊接性\n机理", TEAL), ("候选工艺\n与结构", AMBER),
            ("降阶筛选\n+代理 FE", TEAL), ("不确定性\n与自动化", AMBER), ("误差预算\n+验证接口", NAVY),
        ]
        gap = 4
        box_w = (self.width - gap * (len(labels) - 1)) / len(labels)
        for index, (label, color) in enumerate(labels):
            x = index * (box_w + gap)
            self.canv.setFillColor(color)
            self.canv.roundRect(x, 6, box_w, self.height - 12, 4, fill=1, stroke=0)
            self.canv.setFillColor(colors.white)
            self.canv.setFont("Deng-Bold", 7.4)
            lines = label.split("\n")
            for line_index, line in enumerate(lines):
                self.canv.drawCentredString(x + box_w / 2, self.height - 16 - line_index * 10, line)
            if index < len(labels) - 1:
                self.canv.setStrokeColor(MUTED)
                self.canv.setLineWidth(0.8)
                self.canv.line(x + box_w + 1, self.height / 2, x + box_w + gap - 1, self.height / 2)


class DatumDiagram(Flowable):
    def __init__(self, width: float = 170 * mm, height: float = 43 * mm) -> None:
        super().__init__()
        self.width = width
        self.height = height

    def draw(self) -> None:
        c = self.canv
        c.setStrokeColor(LINE)
        c.setFillColor(PAPER)
        c.roundRect(0, 0, self.width, self.height, 5, fill=1, stroke=1)
        origin_x = 48 * mm
        axis_x = origin_x
        plane_y = 12 * mm
        c.setStrokeColor(NAVY)
        c.setLineWidth(1.2)
        c.line(18 * mm, plane_y, 78 * mm, plane_y)
        c.setStrokeColor(TEAL)
        c.setDash(3, 3)
        c.line(axis_x, 5 * mm, axis_x, 37 * mm)
        c.setDash()
        c.setStrokeColor(AMBER)
        c.circle(axis_x, 27 * mm, 7 * mm, fill=0, stroke=1)
        c.setFont("Deng-Bold", 8)
        c.setFillColor(NAVY)
        c.drawString(19 * mm, plane_y + 3, "A  壳体安装基准平面")
        c.setFillColor(TEAL)
        c.drawString(axis_x + 5 * mm, 33 * mm, "B  壳体理论中心轴")
        c.setFillColor(AMBER)
        c.drawString(87 * mm, 28 * mm, "C  独立周向定位特征")
        c.setFillColor(SLATE)
        c.setFont("Deng", 7.2)
        c.drawString(87 * mm, 20 * mm, "受控特征：Ø40 孔轴线")
        c.drawString(87 * mm, 14 * mm, "位置度：Ø0.05 | A | B")
        c.setStrokeColor(MUTED)
        c.setLineWidth(0.6)
        c.line(axis_x, plane_y, axis_x + 22 * mm, plane_y)
        c.setFont("Deng", 6.7)
        c.drawString(axis_x + 2 * mm, plane_y - 5 * mm, "A 与 B 交点为数字原点")


class BudgetBar(Flowable):
    def __init__(self, width: float = 170 * mm, height: float = 22 * mm) -> None:
        super().__init__()
        self.width = width
        self.height = height

    def draw(self) -> None:
        segments = [
            (0.010, "视觉", TEAL), (0.004, "标定", colors.HexColor("#0EA5E9")),
            (0.003, "TCP", colors.HexColor("#8B5CF6")), (0.003, "机器人", AMBER),
            (0.003, "夹具", colors.HexColor("#F97316")), (0.002, "热变形", RED),
        ]
        total = sum(item[0] for item in segments)
        x = 0
        bar_y = 10
        bar_h = 10
        for value, label, color in segments:
            w = self.width * value / total
            self.canv.setFillColor(color)
            self.canv.rect(x, bar_y, w, bar_h, fill=1, stroke=0)
            self.canv.setFillColor(NAVY)
            self.canv.setFont("Deng", 6.4)
            if w > 26:
                self.canv.drawCentredString(x + w / 2, 2, f"{label} {value:.3f}")
            x += w
        self.canv.setFillColor(SLATE)
        self.canv.setFont("Deng", 7)
        self.canv.drawRightString(self.width, bar_y + bar_h + 3, "总径向预算 0.025 mm（对应 Ø0.05 mm）")


def figure(path: Path, caption: str, width: float = 160 * mm) -> list[Flowable]:
    if not path.exists():
        return [callout(f"图表缺失：{path}", "red")]
    image = Image(str(path), width=width, height=width * 0.56)
    image.hAlign = "CENTER"
    return [image, P(caption, "Caption")]


def source_note(text: str) -> Paragraph:
    return P(f"数据源：{text}", "BodySmall")


def section(title: str, number: str) -> list[Flowable]:
    return [P(f"{number}  {title}", "H1CN")]


def on_page(canvas, doc) -> None:
    page = canvas.getPageNumber()
    canvas.saveState()
    if page > 1:
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(doc.leftMargin, A4[1] - 18 * mm, A4[0] - doc.rightMargin, A4[1] - 18 * mm)
        canvas.setFont("Deng-Bold", 7.3)
        canvas.setFillColor(NAVY)
        canvas.drawString(doc.leftMargin, A4[1] - 13 * mm, "Hanjie | Technical Baseline V2")
        canvas.setFont("Deng", 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(A4[0] - doc.rightMargin, A4[1] - 13 * mm, "数字工程参赛方案 | 参赛评审版")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 13 * mm, A4[0] - doc.rightMargin, 13 * mm)
    canvas.setFont("Deng", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 8 * mm, "QT450-10 / Q235B | V2 | 参赛提交版")
    canvas.drawRightString(A4[0] - doc.rightMargin, 8 * mm, f"{page}")
    canvas.restoreState()


def build_story() -> list[Flowable]:
    story: list[Flowable] = []

    # Cover
    story.extend([
        Spacer(1, 22 * mm),
        P("辽宁省大学生材料焊接与铸造工艺设计大赛", "CoverSub"),
        P("QT450-10 / Q235B 主轴承座异种材料焊接\n数字工程技术说明书", "CoverTitle"),
        P("TECHNICAL REPORT V2  |  FORMAL PDF / SUBMISSION", "CoverSub"),
        P("“中铁山桥杯”焊接工艺设计赛道 · 固定命题：某型压缩机主轴承座与壳体连接", "CoverSub"),
        Spacer(1, 8 * mm),
        callout("核心目标：焊后 Ø40 轴承孔轴线位置度不超过 Ø0.05 mm，同时避免焊渣和飞溅进入壳体内部。", "teal"),
        Spacer(1, 8 * mm),
        Pipeline(),
        Spacer(1, 13 * mm),
        table([
            ["版本", "证据状态", "当前候选路线", "关键保留项"],
            ["V2 | 2026-09-02", "数字工程参赛版 · 证据分级", "自动 TIG + 镍基填充\n六点短焊段 / S3", "柔顺方案仍为候选\n二维代理 FE 保留反例"],
        ], [34 * mm, 44 * mm, 47 * mm, 45 * mm]),
        Spacer(1, 10 * mm),
        P("本报告可作为数字工程设计方案参赛提交。仿真、渲染和注入信号均按证据等级标识；实际制造放行仍需独立的工艺评定、焊后测量和无损/组织检验。", "BodyCN"),
        Spacer(1, 15 * mm),
        P("主线判断", "H2CN"),
        P("降阶模型支持六点柔顺结构的相对优势，但二维热-结构代理交叉检查给出了相反排序。因此本版不把柔顺结构包装成唯一最优解，而把模型冲突作为下一等级验证的入口。", "BodyCN"),
        PageBreak(),
    ])

    # 1 overview
    story.extend(section("项目概览与评审读法", "1"))
    story.append(P("本项目针对 Q235B 薄壁圆柱壳体与 QT450-10 球墨铸铁主轴承座的异种材料连接，围绕焊接性、焊后位置度和内腔洁净度组织数字工程证据。报告的结论分为题面事实、设计假设、模型结果和待验证接口四层。", "BodyCN"))
    story.append(Table([[metric_card("Ø0.05 mm", "官方位置度限值"), metric_card("15", "降阶方案算例"), metric_card("5", "二维代理 FE 案例"), metric_card("1000", "36 因子组合扰动")]], colWidths=[42 * mm] * 4, style=TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)])))
    story.extend([Spacer(1, 5 * mm), P("证据链", "H2CN"), Pipeline(), Spacer(1, 3 * mm)])
    story.append(callout("三分钟读法：题目要求什么 → 主方案是什么 → 数字证据做了什么 → 哪些数字只是代理指标 → 下一步如何实测裁决。", "amber"))
    story.extend([Spacer(1, 4 * mm), P("1.1 命题响应对照", "H2CN"), table([
        ["命题要求", "本方案对策", "对应章节"],
        ["QT450-10 / Q235B 异种材料可靠连接", "镍铁基焊材 + 低热输入自动 TIG + 预热/层间控制", "§3、§12"],
        ["焊后位置度 ≤ Ø0.05 mm", "六点短焊段 + S3 跳焊 + 柔顺夹具 + 0.025 mm 径向误差预算", "§4–§9"],
        ["焊缝承受高频振动交变载荷（疲劳寿命）", "镍基韧性焊缝 + 焊段端部修整 + IIW 疲劳设计基线与试验计划", "§5"],
        ["内腔不得有焊渣 / 飞溅", "TIG 无飞溅工艺特性 + 内腔防护罩 + 焊后内窥终检与追溯放行", "§10、§11"],
        ["自动化稳定批量生产", "视觉定位 P95 门控 + 路径规划 + 在线异常监测", "§8、§9、§10"],
    ], [52 * mm, 88 * mm, 36 * mm], compact=True)])
    story.extend([Spacer(1, 4 * mm), P("本版交付一套可复算、边界透明的数字工程设计：所有数字结论均标注证据等级，实测裁决路径见物理验证接口。", "BodyCN"), PageBreak()])

    # 2 constraints and datums
    story.extend(section("题面约束、验收目标与统一基准", "2"))
    story.append(table([
        ["项目", "官方条件", "本报告处理方式"],
        ["壳体", "Q235B，Ø160 × H200，壁厚 5 mm", "固定输入；材料批次待质保书确认"],
        ["主轴承座", "QT450-10，中心孔 Ø40 mm", "固定材料/孔径；座厚等为设计假设"],
        ["几何验收", "焊后位置度 ≤ Ø0.05 mm", "按径向 0.025 mm 做数字预算；实测需解除夹具后建立基准"],
        ["内腔洁净度", "不得有可能落入内部的焊渣或飞溅物", "内腔防护 + 内窥检查；数字图不能替代实物证据"],
    ], [32 * mm, 66 * mm, 72 * mm]))
    story.extend([Spacer(1, 4 * mm), P("2.1 装配后的独立基准系", "H2CN"), DatumDiagram(), P("图 1  装配基准关系示意。A、B、C 的定义同时用于工程图、夹具映射、降阶结果、FE 后处理和位置度接口。", "Caption")])
    story.append(table([
        ["基准", "统一定义", "用途"],
        ["A", "壳体安装基准平面（z=0）", "确定高度/轴向基准"],
        ["B", "由 Q235B 壳体建立的理论中心轴（x=0, y=0）", "位置度名义轴；与 A 交点为数字原点"],
        ["C", "独立周向定位特征", "装配姿态和起始方向；不进入圆孔轴线位置度框"],
        ["受控特征", "Ø40 轴承孔轴线", "POSITION | Ø0.05 | A | B"],
    ], [25 * mm, 85 * mm, 60 * mm], compact=True))
    story.extend([Spacer(1, 4 * mm), callout("P0 修正：A 不再定义为被控 Ø40 孔轴线，避免用受控特征自引用为基准。", "red"), PageBreak()])

    # 3 materials/process
    story.extend(section("材料与候选焊接路线", "3"))
    story.append(P("QT450-10 侧需关注石墨组织、熔合区硬脆组织和裂纹风险；Q235B 薄壁壳体需关注局部热输入导致的椭圆化和装配基准漂移。候选路线为自动 TIG + 镍铁基填充，配合低热输入、分段对称焊和热管理。文献用于机理和相近对象旁证，不替代本批材料和工艺评定。", "BodyCN"))
    story.append(P("3.1 候选工艺对比矩阵", "H2CN"))
    story.append(P("围绕命题三条硬指标（异种材料连接质量、Ø0.05 位置度、内腔洁净）与工程可行性，对四条候选路线作降阶对比打分（◎优 ○良 △中 ×差）：", "BodyCN"))
    story.append(table([
        ["评估维度", "自动 TIG（主候选）", "CMT-MAG（对比路线）", "激光填丝（对比路线）", "熔化极钎焊（排除）"],
        ["白口 / 裂纹控制", "◎ 热输入精确可调，熔合比低", "○ 低热输入，熔合比中等", "○ 热输入可控，但快冷硬倾向", "× 界面金属间化合物脆性"],
        ["变形与位置度", "◎ 线能量小、分段跳焊灵活", "○ 较优，熔滴过渡稳定", "○ 变形小，但对装配间隙敏感", "○ 热输入最低"],
        ["飞溅 / 焊渣风险", "◎ 无熔滴过渡飞溅，天然满足洁净约束", "○ CMT 近无飞溅", "△ 高能密度气化飞溅需防护", "○ 飞溅小但钎剂残留需清理"],
        ["环形可达性 / 工装", "◎ 枪体小，内孔环缝可达性好", "○ 枪体较大，需定制工装", "△ 光学头尺寸与反射防护要求高", "○ 可达性尚可"],
        ["接头强度 / 疲劳潜力", "◎ 镍基焊缝韧性高、止裂强", "◎ 熔敷率与韧性兼顾", "○ 焊缝窄、硬化带需评估", "× 接头强度受钎料限制"],
        ["自动化成熟度 / 成本", "◎ 焊接机器人标配，成本低", "◎ 设备成熟，成本中", "△ 设备昂贵，参数窗口窄", "○ 成本低但工序多"],
    ], [26 * mm, 38 * mm, 36 * mm, 36 * mm, 34 * mm]))
    story.extend([Spacer(1, 4 * mm), callout("选型结论：自动 TIG 在热输入控制、飞溅/洁净度、环形可达性和疲劳潜力四项同时占优，确定为主候选；CMT-MAG 与激光填丝保留为对比路线，待设备可得性与小试结果裁决；熔化极钎焊因界面脆性与强度上限排除。", "teal")])
    story.append(P("3.2 主候选参数窗口", "H2CN"))
    story.append(table([
        ["输入", "候选设定", "证据属性"],
        ["焊接方法", "自动 TIG", "候选路线；设备与小试可用性待确认"],
        ["填充材料", "ERNiFe-CI / 镍铁基候选", "牌号、规格、货源和小试相容性待确认"],
        ["参数窗口", "75 A / 12 V / 1.5 mm/s / η=0.55", "数字算例入口，不是合格 WPS"],
        ["热管理", "预热 150 °C；层间上限 200 °C；Ar 99.99%", "候选控制值，需工艺评定"],
    ], [32 * mm, 65 * mm, 73 * mm]))
    story.extend([Spacer(1, 4 * mm), P("3.3 线热输入", "H2CN"), callout("q_l = η U I / v = 0.55 × 12 × 75 / 1.5 = 330 J/mm  （公式 1）", "teal"), Spacer(1, 4 * mm), P("3.4 选型逻辑", "H2CN"), P("TIG 的价值在于热输入和路径可控、便于分段/跳焊和过程记录；镍基填充是降低异种材料界面风险的候选假设。ERNiFe-CI 对本题组合的直接有效性仍由真实接头小试、金相、硬度和裂纹/NDT结果裁决。", "BodyCN"), callout("一句话边界：这是“值得验证的工艺候选”，不是“已评定工艺”。", "amber"), PageBreak()])

    # 4 design and fixture
    story.extend(section("结构、接头与夹具", "4"))
    story.append(table([
        ["设计变量", "V2 设定", "性质/用途"],
        ["中心刚性区", "Ø82 mm", "为六个径向连接单元留热隔离区"],
        ["连接单元", "6 个，短焊段 18 mm", "主方案；4/8 点为对照"],
        ["翼端半径", "R74.98 mm", "与壳体内半径 75 mm 形成 H7/h6 精密间隙配合 (0.01~0.04 mm)"],
        ["柔顺槽", "宽 4 mm", "降低中心孔与焊区收缩耦合的设计变量"],
        ["夹具", "1/50 锥形心轴 (Ø39.90~40.10 mm)；Ø190 mm 底板；6 个径向支撑", "1200 N/mm 为等效刚度假设"],
    ], [34 * mm, 51 * mm, 85 * mm]))
    story.extend([Spacer(1, 5 * mm), P("夹具约束映射", "H2CN"), table([
        ["装配自由度", "夹具特征", "映射"],
        ["轴向/高度", "底板上表面", "A"],
        ["径向位置", "中心定位销轴线", "B"],
        ["切向/周向", "独立定位孔/时钟特征", "C"],
    ], [52 * mm, 66 * mm, 52 * mm], compact=True), Spacer(1, 4 * mm), callout("图纸包：cad/generated/engineering-drawings/（7 张 SVG 与 pdf/ 图集，A4 矢量导出）。所有图纸状态均为 design-review；未完成三维关联、公差叠加、干涉检查和制造签审。", "amber"), PageBreak()])

    # 5 fatigue
    story.extend(section("焊缝疲劳与寿命评估", "5"))
    story.append(P("命题明确焊缝在压缩机长期高频振动工况下承受交变载荷，疲劳寿命与位置度同为设计主线。本节按 IIW 推荐的名义应力法建立焊缝疲劳设计基线，并给出实物阶段的验证试验计划。", "BodyCN"))
    story.append(P("5.1 疲劳热点与设计对策", "H2CN"))
    story.append(table([
        ["疲劳热点", "成因", "设计对策"],
        ["焊段起止端（弧坑/焊趾）", "六段环缝端部刚度突变，应力集中系数高", "延迟收弧填满弧坑；端部打磨圆滑过渡，必要时 TIG 重熔修整焊趾"],
        ["焊缝根部未焊透区", "局部熔透不足形成内部缺口", "坡口与钨极对中控制；小试金相确认熔透"],
        ["熔合区硬脆组织", "白口/马氏体在交变载荷下萌生裂纹", "镍基填充（韧性好、止裂能力强）+ 预热缓冷改善组织"],
        ["整体不平衡激励", "焊缝非对称布置引入附加振动", "六点周向对称布置 + S3 跳焊均衡残余应力"],
    ], [36 * mm, 56 * mm, 78 * mm]))
    story.append(P("设计基线：环向角焊缝按 IIW 名义应力法取 FAT 63–80 等级（2×10⁶ 循环参考强度）作保守评估；压缩机工况应力谱需以实测载荷谱标定后计算安全裕度。镍基焊缝的良好延性与低残余应力设计是本方案的疲劳裕度来源。", "BodyCN"))
    story.append(P("5.2 验证试验计划", "H2CN"))
    story.append(P("实物阶段按三级验证：① 接头级——轴向载荷疲劳试样（应力比 R=0.1，10⁷ 循环，≥3 件）验证 FAT 基线；② 部件级——焊后壳体组件振动台耐久试验，跟踪位置度漂移；③ 整机级——装机耐久试验后内窥复检焊缝与内腔。试验数据以独立 source_type 回填证据链，用于校准本节设计基线。", "BodyCN"))
    story.append(callout("边界：本节为疲劳设计基线与验证门，实测载荷谱与接头疲劳数据回填前，不作为寿命达标证明。", "amber"))
    story.append(PageBreak())

    # 6 reduced order
    story.extend(section("降阶模型与位置度后处理", "6"))
    story.append(P("降阶模型把每个焊段等效为热收缩向量，根据布局、顺序、结构因子和夹具刚度估算孔中心平移与轴线倾斜，再按有效孔高内的最大径向偏差构造与位置度同量纲的比较指标。", "BodyCN"))
    story.append(callout("P_sim = 2 × max_z sqrt(x(z)^2 + y(z)^2) ；P_sim 与 Ø0.05 具有相同直径量纲，但不是 CMM 结果。  （公式 2）", "teal"))
    story.extend([Spacer(1, 3 * mm), *figure(CHARTS["reduced"], "图 2  15 组降阶方案的 P_sim 与椭圆度代理指标。来源：simulation/results/summary.csv。", 150 * mm)])
    story.append(table([
        ["方案", "P_sim (mm)", "模型内状态", "解读"],
        ["baseline rigid 6P-S1", "0.049701", "接近限值", "刚性基准"],
        ["flex compliant 6P-S3", "0.008787", "低于限值", "主候选；优势依赖模型预设"],
        ["flex compliant 8P-S2/S3", "0.008201", "低于限值", "数字指标更小，但焊段更多"],
    ], [48 * mm, 30 * mm, 35 * mm, 57 * mm]))
    story.extend([Spacer(1, 4 * mm), P("关键判断", "H2CN"), P("S2 与 S3 在当前降阶模型中因对称性相同，不能据此宣称 S3 优于 S2。6 点被保留为主方案，是热输入、焊段数量和模型内裕度的折中，而非唯一数学最优。", "BodyCN"), PageBreak()])

    # 7 FE
    story.extend(section("二维热-结构代理交叉检查", "7"))
    story.append(P("FE 使用三角形网格、瞬态热传导、外边界对流、等效残余本征应变、平面应力弹性和等效径向弹簧夹具。每个案例导出内孔节点，送入 position_tolerance.fit_axis，在统一 A/B 基准系中完成三层圆拟合和轴线评价。", "BodyCN"))
    story.append(table([
        ["Case", "结构/夹具/顺序", "节点/单元", "峰值温度", "P_FE (mm)"],
        ["FE-001", "baseline / rigid / S1", "2800 / 5312", "462.413 °C", "0.001449982"],
        ["FE-002", "baseline / rigid / S3", "2800 / 5312", "458.511 °C", "0.001412091"],
        ["FE-003", "flex / compliant / S3", "1678 / 2632", "561.755 °C", "0.002599523"],
        ["FE-004", "baseline / compliant / S3", "2800 / 5312", "458.511 °C", "0.002051051"],
        ["FE-005", "flex / rigid / S3", "1678 / 2632", "561.755 °C", "0.001403186"],
    ], [20 * mm, 57 * mm, 38 * mm, 31 * mm, 34 * mm]))
    story.extend([Spacer(1, 4 * mm), *figure(CHARTS["fe"], "图 3  FE-001..005 的二维代理几何响应指标。来源：simulation/fe/results/fe-summary.csv。", 125 * mm)])
    story.append(callout("匹配对照：FE-002/003 统一 S3 比较结构与柔顺夹具，FE-004/005 进一步交换夹具边界。41/51/61/81 网格检查的最细相邻变化为 29.224%，未通过 5% 参考门；柔顺结构仍不能被当前二维代理升级为唯一最优。", "red"))
    story.extend([Spacer(1, 4 * mm), P("模型物理边界", "H2CN"), P("五组峰值约 458-562 °C，远未达到钢/铸铁熔化温度，未模拟熔池形成、熔合、焊缝金属激活；同时未包含温度相关塑性、相变、三维壳体高度、真实焊缝几何/本构、接触和夹具预紧。因此 P_FE 是二维代理模型几何响应指标，不是“FE 证明焊后位置度为 0.0026 mm”。", "BodyCN"), PageBreak()])

    # 8 MC
    story.extend(section("不确定性传播与结构因子边界", "8"))
    story.append(P("1000 次共同输入扰动覆盖 4/6/8 点、baseline/flex、rigid/compliant、S1/S2/S3 共 36 个因子组合；热效率、电流、电压、焊速 ±10%，材料导热率 ±10%，线膨胀系数/弹性模量 ±5%，夹具刚度 ±20%，初始偏心 [-0.03, 0.03] mm。", "BodyCN"))
    story.append(table([
        ["设计", "P5", "P50", "P95", "worst", "超限比例"],
        ["baseline rigid 6P-S3", "0.015012", "0.035529", "0.065942", "0.072866", "23.7%"],
        ["flex rigid 6P-S3", "0.010685", "0.033053", "0.062009", "0.068371", "20.7%"],
    ], [43 * mm, 24 * mm, 24 * mm, 24 * mm, 27 * mm, 28 * mm]))
    story.extend([Spacer(1, 3 * mm), *figure(CHARTS["mc"], "图 4  降阶模型共同输入扰动分布。来源：simulation/results/monte-carlo/monte-carlo-summary.json。", 145 * mm)])
    story.append(callout("模型内鲁棒性，不是独立结构证据：统一 6P-S3、刚性夹具后，柔顺结构配对更优比例为 84.3%；混合 S1/S3 和刚性/柔顺夹具的旧口径 100% 不再作为因果结论。structure_factor 与 fixture_factor 未由 FE/实测标定。", "amber"))
    story.extend([Spacer(1, 4 * mm), P("一句话回答", "H2CN"), P("为什么降阶与 FE 相反？因为两者对结构连接、夹具边界和材料表达不同；冲突不是需要删除的异常，而是决定下一步三维/物理验证优先级的证据。", "BodyCN"), PageBreak()])

    # 9 vision and budget
    story.extend(section("自动化定位与工程误差预算", "9"))
    story.append(P("视觉数字样本用于验证算法链路，不代表真实工业相机/镜头/光源精度。工程门限采用 P95，避免少量大误差被 MAE 掩盖。", "BodyCN"))
    story.extend([P("9.1 Ø0.05 mm 的径向预算", "H2CN"), BudgetBar(), Spacer(1, 3 * mm)])
    story.append(table([
        ["来源", "径向预算 (mm)", "当前证据状态"],
        ["视觉定位", "0.010", "数字样本；用径向/角度 P95 门控"],
        ["相机标定", "0.004", "待真实镜头与标定板实测"],
        ["TCP", "0.003", "待机器人标定实测"],
        ["机器人重复定位", "0.003", "待设备重复性试验"],
        ["夹具定位", "0.003", "等效刚度假设；待装配后检查"],
        ["焊接热变形", "0.002", "降阶/二维代理指标；待冷却后 CMM"],
        ["合计", "0.025", "对应 Ø0.05 直径限值"],
    ], [43 * mm, 34 * mm, 91 * mm], compact=True))
    story.extend([Spacer(1, 3 * mm), P("9.2 困难视觉工程门", "H2CN"), table([
        ["条件", "原始返回率", "质量接受率", "径向 P95", "工程判定"],
        ["clean", "100%", "100%", "0.003422", "PASS"],
        ["noise", "100%", "0%", "0.079638", "FAIL"],
        ["blur", "100%", "100%", "0.002769", "PASS"],
        ["illumination", "100%", "0%", "0.356118", "FAIL"],
        ["perspective", "100%", "0%", "10.690229", "FAIL"],
        ["occlusion", "100%", "0%", "3.205838", "FAIL"],
        ["missing_edges", "100%", "0%", "0.264525", "FAIL"],
        ["low_contrast", "100%", "100%", "0.002923", "PASS"],
        ["distortion", "100%", "100%", "0.003572", "PASS"],
        ["large_offset", "100%", "100%", "0.003830", "PASS"],
    ], [29 * mm, 25 * mm, 28 * mm, 34 * mm, 34 * mm], compact=True)])
    story.extend([PageBreak(), P("9.3 视觉工程判定", "H2CN"), P("困难集揭示了“能返回结果”和“能用于定位”之间的差别。运行时质量门根据轮廓圆度、椭圆轴比和标记面积拒绝 noise、illumination、perspective、occlusion、missing_edges 等低可信结果，避免错误坐标进入路径规划。质量接受仍不等于真实工业精度认证。", "BodyCN"), source_note("automation/vision/results/difficult-summary.json；姿态门限由 0.010 mm / 74.98 mm 换算为 0.0076°。"), *figure(CHARTS["vision"], "图 5  困难视觉条件的工程门结果；质量接受率与误差门同时使用。", 145 * mm), PageBreak()])

    # 10/11 automation and cleanliness
    story.extend(section("过程监测、追溯与内腔洁净度", "10"))
    story.append(P("规则检测器按电流、电压、焊速和温度窗口识别连续越界事件，并加入在线偏置估计、10% 窗口滞回、5 点中值滤波和 50 ms 最小持续时间。数字基准包含 100 个正常试验和 100 个异常注入试验；电弧中断可同时产生电流/电压事件，总真实事件数为 243。", "BodyCN"))
    story.append(table([
        ["指标", "数字基准结果", "边界"],
        ["TP / FP / FN", "243 / 0 / 0", "只覆盖当前注入模式"],
        ["Precision / Recall / F1", "100% / 100% / 100%", "阈值需真实焊机数据重标定"],
        ["正常试验级 FPR", "0%", "不代表量产误报率"],
        ["平均/中位延迟", "0 s / 0 s", "仿真时间戳，不是设备闭环延迟"],
    ], [53 * mm, 53 * mm, 70 * mm]))
    story.extend([Spacer(1, 4 * mm), callout("名义基准的 100% 只覆盖当前注入模式。压力曲线显示 10–30 ms 脉冲按设计去抖，50 ms 及以上可检出；中值滤波后噪声倍数 2.0 的试验级误报率为 0%，3.0 为 10%；±4 A 静态偏置在线校正后误报率为 0%。真实焊机数据仍需重标定阈值、误报率和延迟。", "amber"), Spacer(1, 6 * mm), P("10  洁净度是硬约束", "H1CN"), P("候选路线采用无焊渣工艺、内腔防护、焊前清洁、分段短焊、焊后目视和内窥检查。数字图、仿真和“无异常事件”都不能替代内腔实物检查；正式记录应建立一件一码、焊材批次、操作者、参数曲线、内窥照片和放行记录的关联。", "BodyCN"), callout("洁净度的最终证据不是算法准确率，而是焊后内窥/目视记录和可追溯放行表。", "red"), PageBreak()])
    story.extend([Spacer(1, 4 * mm), callout("名义基准的 100% 只覆盖当前注入模式。压力曲线显示 10–30 ms 脉冲按设计去抖，50 ms 及以上可检出；中值滤波后噪声倍数 2.0 的试验级误报率为 0%，3.0 为 10%；±4 A 静态偏置在线校正后误报率为 0%。真实焊机数据仍需重标定阈值、误报率和延迟。", "amber"), Spacer(1, 6 * mm), P("11  洁净度是硬约束", "H1CN"), P("候选路线采用无焊渣工艺、内腔防护、焊前清洁、分段短焊、焊后目视和内窥检查。数字图、仿真和“无异常事件”都不能替代内腔实物检查；正式记录应建立一件一码、焊材批次、操作者、参数曲线、内窥照片和放行记录的关联。", "BodyCN"), callout("洁净度的最终证据不是算法准确率，而是焊后内窥/目视记录和可追溯放行表。", "red"), PageBreak()])

    # 12 risks and 13 reproducibility
    story.extend(section("风险、可复现性与物理验证接口", "12"))
    story.append(table([
        ["风险", "现有控制", "尚未闭合的证据"],
        ["球铁侧裂纹/脆硬组织", "镍基候选、低热输入、预热/热管理", "真实接头金相、硬度、NDT"],
        ["薄壁壳体椭圆化", "短段/跳焊、夹具、误差预算", "焊后几何实测"],
        ["夹具过拘束", "柔顺支撑和释放设计", "实物刚度/预紧标定"],
        ["内部飞溅/残留", "内腔防护、无焊渣路线、内窥", "焊后内腔记录"],
        ["视觉误检", "困难集 P95 工程门", "真实镜头标定与在线门限"],
    ], [43 * mm, 64 * mm, 69 * mm]))
    story.extend([Spacer(1, 5 * mm), P("13  可复现性索引", "H1CN"), table([
        ["证据", "主入口", "结果"],
        ["降阶筛选", "simulation/scripts/run_reduced_order.py", "summary.csv / summary-r1.md"],
        ["二维代理 FE", "simulation/fe/run_fe_cases.py", "fe-summary.csv / fe-convergence.csv / bore-nodes.csv"],
        ["蒙特卡洛", "simulation/scripts/run_monte_carlo.py", "monte-carlo-summary.json / .md"],
        ["视觉门控", "automation/vision/run_benchmark.py", "difficult-summary.json / .md"],
        ["工程图", "cad/parametric/generate_engineering_drawings.py", "7 张 SVG / manifest"],
        ["图集 PDF", "cad/parametric/export_drawing_pdfs.py", "pdf/ 7 页单图 + 合集"],
        ["位置度接口", "simulation/scripts/position_tolerance.py", "A/B 基准系 + 分层拟合"],
    ], [43 * mm, 76 * mm, 57 * mm], compact=True)])
    story.extend([Spacer(1, 5 * mm), P("14  物理验证接口", "H1CN"), P("样件和设备具备后，按“焊前基准测量 → 候选 WPS 焊接并记录 → 完全冷却并解除夹具 → CMM/校准替代测量 → 内孔分层拟合 → 外观、内窥、NDT、金相和硬度评价”的顺序执行。数字样本与实物数据使用不同 source_type，不互相覆盖。", "BodyCN"), PageBreak()])

    # 15/16/17 and referee answers
    story.extend(section("结论、提交状态与评审关注点速答", "15"))
    story.append(P("降阶模型和二维代理 FE 的排序不同，说明结果对结构表达、连接刚度和边界条件敏感。V2 的贡献不是提前宣称实物性能，而是把模型适用域、反例、自动化门限和下一步验证门完整串联。", "BodyCN"))
    story.extend([P("15.1 关键质疑与回答", "H2CN"), table([
        ["评委问题", "正文一句话回答"],
        ["为什么 TIG？", "热输入、路径、分段策略和过程记录可控；仍需设备/小试评定。"],
        ["ERNiFe-CI 有直接证据吗？", "目前是材料相容性候选，直接有效性由真实接头金相、硬度、裂纹/NDT裁决。"],
        ["为什么 6 点？", "它是热输入、焊段数量和模型内裕度的折中，不是唯一数学最优。"],
        ["为什么降阶与 FE 相反？", "结构连接、夹具边界和材料表达不同；冲突被保留作为验证优先级。"],
        ["FE 不到熔点有什么意义？", "它不能预测熔池或绝对位置度，但能提供独立的结构反例检查。"],
        ["0.025 mm 为什么这样分？", "它是 Ø0.05 的径向设计分配，采用线性最坏情况；不是三维 GD&T 误差等价分解。"],
        ["透视误差 10 mm 还叫自动化？", "检测器会返回结果但工程门 FAIL；系统应拒绝该结果，而不是继续定位。"],
        ["异常检测 100% 可信？", "只对当前注入模式回归有效，不代表真实现场泛化。"],
        ["没有实物凭什么参赛？", "官方允许研究报告/设计图/研究实物；本稿明确数字证据等级和物理验证缺口。"],
        ["洁净度怎么证明？", "用焊后内窥/目视和追溯记录证明，数字图和算法不能替代。"],
        ["疲劳寿命怎么证明？", "§5 给出 IIW 名义应力法设计基线与三级试验计划；实测载荷谱回填前不宣称寿命达标。"],
    ], [53 * mm, 123 * mm], compact=True)])
    story.extend([Spacer(1, 4 * mm), P("16  参赛提交 vs 制造放行", "H1CN"), table([
        ["状态", "V2 的结论"],
        ["参赛提交", "可作为数字工程设计方案提交；必须标明代理模型、困难视觉 FAIL 和未完成物理验证。"],
        ["制造放行", "必须补齐材料质保书、WPS/PQR/等效评定、真实焊接记录、焊后 CMM、金相/硬度/NDT、洁净度和设备标定。"],
    ], [35 * mm, 141 * mm])])
    story.extend([Spacer(1, 5 * mm), callout("当前候选路线：自动 TIG + 镍基填充、六点短焊段和 S3 作为继续验证的候选路线；同时保留连续座体/刚性夹具作为 FE 反例基准，最终结构由更高等级证据裁决。", "teal"), Spacer(1, 5 * mm), P("17  参考与数据源", "H1CN"), P("[1] 第一届辽宁省大学生材料焊接与铸造工艺设计大赛实施方案及固定命题附件。\n[2] docs/research/evidence-matrix.md：材料与焊接性证据矩阵。\n[3] simulation/、automation/、cad/：本项目脚本、输入配置、数字结果和工程表达图。\n[4] docs/validation/position-error-budget.md：位置误差预算及数字工程门限。\n[5] IIW《焊接接头疲劳设计推荐》（名义应力法 / FAT 等级）：第 5 章疲劳设计基线的方法依据。", "BodySmall"), source_note("本 PDF 由 deliverables/report/build_technical_report_pdf.py 生成；结果来源和模型边界均在正文及对应归档文件中标注。")])

    # appendix A: WPS design card
    story.extend([PageBreak(), *section("附录 A  WPS V1 工艺卡（设计态）", "A")])
    story.append(P("以下为数字样机的工艺设定卡（同步自 docs/process/wps-v1-design-card.md），定位是“值得验证的工艺候选”的设计基线，不是经评定的 WPS/PQR。", "BodyCN"))
    story.append(table([
        ["项目", "V1 设计值", "状态"],
        ["母材", "QT450-10 / Q235B，Q235B 壳体 t=5 mm", "题面条件"],
        ["方法", "自动 TIG，短段、对称跳焊", "主候选"],
        ["填充材料", "ERNiFe-CI，规格待采购确认", "候选"],
        ["电流/电压", "75 A / 12 V", "数值设定"],
        ["焊速", "1.5 mm/s", "数值设定"],
        ["线热输入", "330 J/mm（η=0.55）", "降阶模型输入"],
        ["预热", "150 °C", "候选设定，需工艺评定"],
        ["层间上限", "200 °C", "候选控制值"],
        ["保护气", "Ar 99.99%，10 L/min", "设备确认项"],
        ["焊缝布局", "6 个柔顺连接单元，单段 18 mm", "设计假设"],
        ["顺序", "S3：1→4→3→6→2→5", "数字样机当前方案"],
        ["冷却", "保温缓冷；不得对球铁熔合区强制急冷", "设计原则"],
        ["内腔防护", "可拆卸环形防护/接料罩 + 焊后内窥检查", "洁净度设计证据"],
    ], [34 * mm, 82 * mm, 54 * mm]))
    story.append(P("放行前必须补齐：QT450-10/Q235B 质保书、焊材批次和烘干/储存记录；设备能力、装配间隙和 TCP 标定；小试中的成形、裂纹、金相、硬度与 NDT 结果；真实焊后 CMM 位置度和测量不确定度。", "BodySmall"))
    return story


def main() -> int:
    register_fonts()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frame = Frame(20 * mm, 18 * mm, A4[0] - 40 * mm, A4[1] - 42 * mm, id="normal", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=24 * mm, bottomMargin=18 * mm, title="QT450-10/Q235B Technical Report V2",
        author="Digital Engineering Team",
    )
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=on_page)])
    doc.build(build_story())
    print(f"已生成 PDF: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
