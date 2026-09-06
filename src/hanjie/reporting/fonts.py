"""从项目配置选择可移植的中文 PDF 字体。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

import yaml
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def register_project_fonts(root: Path) -> Tuple[str,str]:
    config = yaml.safe_load((root/"project/report.yaml").read_text(encoding="utf-8"))["pdf"]
    overrides = config["environment_overrides"]
    pairs = []
    regular_override = os.getenv(overrides["regular"])
    bold_override = os.getenv(overrides["bold"])
    if regular_override and bold_override:
        pairs.append((regular_override,bold_override))
    pairs.extend((item["regular"],item["bold"]) for item in config["font_candidates"])
    for regular,bold in pairs:
        if Path(regular).is_file() and Path(bold).is_file():
            pdfmetrics.registerFont(TTFont("HanjieCN",regular))
            pdfmetrics.registerFont(TTFont("HanjieCN-Bold",bold))
            pdfmetrics.registerFontFamily("HanjieCN",normal="HanjieCN",bold="HanjieCN-Bold",
                                          italic="HanjieCN",boldItalic="HanjieCN-Bold")
            return "HanjieCN","HanjieCN-Bold"
    raise FileNotFoundError("未找到可用中文字体；请配置 HANJIE_PDF_FONT_REGULAR/BOLD 或 project/report.yaml")
