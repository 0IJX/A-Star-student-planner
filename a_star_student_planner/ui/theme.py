from __future__ import annotations

from typing import Dict, List


THEMES: Dict[str, Dict[str, str]] = {
    "Studio Light": {
        "app_bg": "#F3F3F3",
        "sidebar_bg": "#ECECEC",
        "panel_bg": "#FFFFFF",
        "panel_alt": "#F5F5F5",
        "panel_soft": "#FAFAFA",
        "border": "#DCDCDC",
        "text": "#131820",
        "muted": "#5A6675",
        "accent": "#2F2F2F",
        "accent_hover": "#3D3D3D",
        "button_brown": "#5A3E30",
        "button_brown_hover": "#4A3227",
        "button_text": "#F7FAFC",
        "success": "#A7F3D0",
        "success_hover": "#86EFAC",
        "warning": "#FDBA74",
        "danger": "#FCA5A5",
        "track": "#D7D7D7",
        "slider_progress": "#4A4A4A",
        "scrollbar": "#515151",
        "scrollbar_hover": "#393939",
        "textbox": "#FFFFFF",
        "notch": "#3D3D3D",
        "topbar_bg": "#FAFAFA",
        "hero_bg": "#EFEFEF",
        "focus": "#6B7280",
    },
    "Graphite Paper": {
        "app_bg": "#F1F1EF",
        "sidebar_bg": "#E8E7E3",
        "panel_bg": "#FCFBF9",
        "panel_alt": "#F1EFEB",
        "panel_soft": "#F7F5F2",
        "border": "#D8D4CD",
        "text": "#1D1B18",
        "muted": "#5F5A53",
        "accent": "#2F2F2F",
        "accent_hover": "#3D3D3D",
        "button_brown": "#5A3E30",
        "button_brown_hover": "#4A3227",
        "button_text": "#FBF9F6",
        "success": "#A7F3D0",
        "success_hover": "#86EFAC",
        "warning": "#FDBA74",
        "danger": "#FCA5A5",
        "track": "#D7D7D7",
        "slider_progress": "#4A4A4A",
        "scrollbar": "#515151",
        "scrollbar_hover": "#393939",
        "textbox": "#FFFEFD",
        "notch": "#3D3D3D",
        "topbar_bg": "#FAF8F5",
        "hero_bg": "#ECE8E1",
        "focus": "#2F6FEB",
    },
}


def available_themes() -> List[str]:
    return list(THEMES.keys())


def planner_palette(theme_name: str = "Studio Light") -> dict[str, str]:
    if theme_name not in THEMES:
        theme_name = "Studio Light"
    return dict(THEMES[theme_name])


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    clean = value.lstrip("#")
    if len(clean) != 6:
        return (0, 0, 0)
    return int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16)


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def _mix_hex(a: str, b: str, t: float) -> str:
    t = max(0.0, min(1.0, float(t)))
    ar, ag, ab = _hex_to_rgb(a)
    br, bg, bb = _hex_to_rgb(b)
    return _rgb_to_hex(
        (
            round(ar + (br - ar) * t),
            round(ag + (bg - ag) * t),
            round(ab + (bb - ab) * t),
        )
    )


def risk_color(score: float, threshold: float = 35.0, palette: dict[str, str] | None = None) -> str:
    p = palette or THEMES["Studio Light"]
    # Real-world, distinct color mapping for risk categories
    # Excellent: <= 10, Good: <= 25, Mid: <= 50, Below Avg: <= 75, Fail: > 75
    # Use risk_status to determine color
    status = risk_status(score, threshold)
    if status == "On Track":
        return "#14532D"  # Dark Green
    else:  # "Watch Closely" or "At Risk"
        return "#7F1D1D"  # Dark Red


def risk_status(score: float, threshold: float = 35.0) -> str:
    if score <= threshold:
        return "On Track"
    if score <= threshold + 15:
        return "Watch Closely"
    return "At Risk"


def base_stylesheet(p: dict[str, str]) -> str:
    return f"""
QWidget {{
    background: {p["app_bg"]};
    color: {p["text"]};
    font-family: Segoe UI, Arial, sans-serif;
    font-size: 13px;
}}

QLabel {{
    background: transparent;
}}

QMainWindow::separator {{
    background: {p["border"]};
    width: 2px;
    height: 2px;
}}

QFrame[role="topbar"] {{
    background: {p["topbar_bg"]};
    border: 1px solid {p["border"]};
    border-radius: 18px;
}}

QFrame[role="hero"] {{
    background: {p["hero_bg"]};
    border: 1px solid {p["border"]};
    border-radius: 22px;
}}

QFrame[role="sidebar_surface"] {{
    background: {p["sidebar_bg"]};
    border: 1px solid {p["border"]};
    border-radius: 22px;
}}

QFrame[role="card"] {{
    background: {p["panel_bg"]};
    border: 1px solid {p["border"]};
    border-radius: 18px;
}}

QFrame[role="card_alt"] {{
    background: {p["panel_alt"]};
    border: none;
    border-radius: 14px;
}}

QFrame[role="chip"] {{
    background: {p["panel_bg"]};
    border: 1px solid {p["border"]};
    border-radius: 12px;
}}

QLabel[role="title"] {{
    font-size: 26px;
    font-weight: 700;
    color: {p["text"]};
}}

QLabel[role="subtitle"] {{
    font-size: 13px;
    color: {p["muted"]};
}}

QLabel[role="section_title"] {{
    font-size: 17px;
    font-weight: 700;
    color: {p["text"]};
}}

QLabel[role="tiny"] {{
    font-size: 12px;
    color: {p["muted"]};
}}

QLabel[role="help_icon"] {{
    background: transparent;
    color: {p["muted"]};
    border: 1px solid {p["border"]};
    border-radius: 9px;
    font-size: 11px;
    font-weight: 700;
    padding: 0;
}}

QPushButton {{
    background: {p["accent"]};
    color: {p["button_text"]};
    border: 1px solid {p["border"]};
    border-radius: 12px;
    padding: 9px 14px;
    font-weight: 600;
}}

QPushButton:hover {{
    background: {p["accent_hover"]};
}}

QPushButton:pressed {{
    padding-top: 10px;
}}

QPushButton[variant="subtle"] {{
    background: {p["panel_alt"]};
    color: {p["text"]};
}}

QPushButton[variant="subtle"]:hover {{
    background: {p["panel_soft"]};
}}

QPushButton[variant="success"] {{
    background: {p["button_brown"]};
    color: {p["button_text"]};
}}

QPushButton[variant="success"]:hover {{
    background: {p["button_brown_hover"]};
}}

QPushButton[role="run"] {{
    min-height: 52px;
    font-size: 15px;
    border-radius: 14px;
}}

QPushButton[role="method"] {{
    min-height: 34px;
    border-radius: 10px;
    background: {p["panel_alt"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
}}

QPushButton[role="method"]:checked {{
    background: {p["button_brown"]};
    color: {p["button_text"]};
}}

QPushButton[role="method"]:checked:hover {{
    background: {p["button_brown_hover"]};
}}

QPushButton[role="method"]:hover {{
    background: {p["panel_soft"]};
}}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {p["panel_alt"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 10px;
    min-height: 34px;
    padding: 4px 10px;
}}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {p["focus"]};
}}

QComboBox::drop-down {{
    width: 24px;
    border: none;
}}

QComboBox QAbstractItemView {{
    background: {p["panel_bg"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    selection-background-color: {p["panel_soft"]};
}}

QCheckBox {{
    spacing: 8px;
    color: {p["text"]};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {p["border"]};
    border-radius: 4px;
    background: {p["panel_bg"]};
}}

QCheckBox::indicator:checked {{
    background: {p["accent"]};
}}

QSlider::groove:horizontal {{
    background: {p["track"]};
    border-radius: 4px;
    height: 8px;
}}

QSlider::sub-page:horizontal {{
    background: {p["slider_progress"]};
    border-radius: 4px;
}}

QSlider::handle:horizontal {{
    width: 16px;
    background: {p["accent"]};
    border-radius: 8px;
    margin: -4px 0;
}}

QSlider::handle:horizontal:hover {{
    background: {p["accent_hover"]};
}}

QTextEdit, QPlainTextEdit {{
    background: {p["textbox"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 12px;
    padding: 8px;
}}

QProgressBar {{
    border: 1px solid {p["border"]};
    background: {p["panel_alt"]};
    border-radius: 8px;
    text-align: center;
    color: {p["muted"]};
}}

QProgressBar::chunk {{
    border-radius: 7px;
    background: {p["success"]};
}}

QTableWidget {{
    background: {p["textbox"]};
    border: 1px solid {p["border"]};
    border-radius: 12px;
    gridline-color: {p["border"]};
}}

QHeaderView::section {{
    background: {p["panel_alt"]};
    color: {p["muted"]};
    border: 1px solid {p["border"]};
    padding: 6px;
    font-weight: 700;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    width: 11px;
    background: transparent;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {p["scrollbar"]};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p["scrollbar_hover"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QToolTip {{
    background: {p["panel_bg"]};
    color: {p["text"]};
    border: 1px solid {p["border"]};
    border-radius: 8px;
    padding: 8px 10px;
}}
"""
