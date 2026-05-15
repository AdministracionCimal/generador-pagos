"""Sistema de diseño: tokens, QSS global y helpers de badges."""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QWidget

# ── Icon paths ────────────────────────────────────────────────────────────
_ICONS_DIR     = Path(__file__).parent / "icons"
_ICO_CH_RIGHT  = str(_ICONS_DIR / "chevron_right.svg").replace("\\", "/")
_ICO_CH_DOWN   = str(_ICONS_DIR / "chevron_down.svg").replace("\\", "/")
_BRANCH_CLOSED = f"image: url({_ICO_CH_RIGHT});" if (_ICONS_DIR / "chevron_right.svg").exists() else "image: none;"
_BRANCH_OPEN   = f"image: url({_ICO_CH_DOWN});"  if (_ICONS_DIR / "chevron_down.svg").exists()  else "image: none;"

# ── Paleta ────────────────────────────────────────────────────────────────
BG_APP        = "#F5F7FA"
BG_SURFACE    = "#FDFEFE"
BG_SUBTLE     = "#F0F3F7"
BG_HOVER      = "#EAF2FF"
BORDER        = "#DDE4EC"
BORDER_STRONG = "#B8C4D2"

TEXT_PRIMARY   = "#111827"
TEXT_SECONDARY = "#4B5563"
TEXT_MUTED     = "#8793A3"

BRAND          = "#1F5FBF"
BRAND_LIGHT    = "#2F6FD4"
BRAND_HOVER    = "#1A4FA3"
BRAND_PRESSED  = "#153F82"
BRAND_DISABLED = "#9BBBEA"
BRAND_SUBTLE   = "#EAF2FF"

SUCCESS    = "#187044"
SUCCESS_BG = "#E2F6EA"
WARNING    = "#9A5B00"
WARNING_BG = "#FFF4D9"
DANGER     = "#A83131"
DANGER_BG  = "#FCE7E7"
INFO       = "#1F5FBF"
INFO_BG    = "#EAF2FF"

FONT_FAMILY = "'Segoe UI Variable Display', 'Segoe UI', system-ui, sans-serif"

# ── QSS global ────────────────────────────────────────────────────────────
STYLESHEET = f"""
* {{ font-family: {FONT_FAMILY}; }}

QMainWindow, QDialog {{ background-color: {BG_APP}; }}

QMenuBar {{
    background-color: {BG_SURFACE};
    border-bottom: 1px solid {BORDER};
    padding: 2px 4px;
    color: {TEXT_PRIMARY};
}}
QMenuBar::item {{ padding: 6px 12px; border-radius: 5px; background: transparent; }}
QMenuBar::item:selected {{ background-color: {BG_SUBTLE}; }}
QMenu {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
    color: {TEXT_PRIMARY};
}}
QMenu::item {{ padding: 7px 18px; border-radius: 4px; font-size: 13px; }}
QMenu::item:selected {{ background-color: {BG_HOVER}; color: {TEXT_PRIMARY}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 6px; }}

QFrame#Card {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

QLabel {{ color: {TEXT_PRIMARY}; font-size: 13px; }}
QLabel#PageTitle    {{ color: {TEXT_PRIMARY};   font-size: 22px; font-weight: 700;
                       letter-spacing: 0; }}
QLabel#PageSubtitle {{ color: {TEXT_SECONDARY}; font-size: 13px; }}
QLabel#CardTitle    {{ color: {TEXT_PRIMARY};   font-size: 13px; font-weight: 600; }}
QLabel#CardHint     {{ color: {TEXT_MUTED};     font-size: 10px; font-weight: 600;
                       letter-spacing: 0; }}
QLabel#Muted        {{ color: {TEXT_MUTED};     font-size: 13px; }}
QLabel#Filename     {{ color: {TEXT_PRIMARY};   font-size: 13px; font-weight: 500; }}
QLabel#KpiNumber    {{ color: {TEXT_PRIMARY};   font-size: 26px; font-weight: 700;
                       letter-spacing: 0; line-height: 1; }}
QLabel#KpiLabel     {{ color: {TEXT_MUTED};     font-size: 10px; font-weight: 600;
                       letter-spacing: 0; }}

QComboBox {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 7px 10px;
    color: {TEXT_PRIMARY};
    min-height: 22px;
    selection-background-color: {BRAND};
}}
QComboBox:hover   {{ border-color: {TEXT_MUTED}; }}
QComboBox:focus   {{ border: 2px solid {BRAND}; padding: 5px 9px; }}
QComboBox:disabled {{ background-color: {BG_SUBTLE}; color: {TEXT_MUTED}; border-color: {BORDER}; }}
QComboBox::drop-down {{
    border: none;
    width: 24px;
    subcontrol-origin: padding;
    subcontrol-position: top right;
}}
QComboBox::down-arrow {{
    image: url({_ICO_CH_DOWN});
    width: 12px;
    height: 8px;
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    selection-background-color: {BG_HOVER};
    selection-color: {TEXT_PRIMARY};
    color: {TEXT_PRIMARY};
    padding: 4px;
    outline: none;
}}
QComboBox QAbstractItemView::item {{
    padding: 7px 12px;
    border-radius: 4px;
    min-height: 28px;
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {BG_HOVER};
    color: {TEXT_PRIMARY};
}}

QLineEdit {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 7px 10px;
    color: {TEXT_PRIMARY};
    selection-background-color: {BRAND};
    selection-color: {BG_SURFACE};
    min-height: 22px;
}}
QLineEdit:hover    {{ border-color: {TEXT_MUTED}; }}
QLineEdit:focus    {{ border: 2px solid {BRAND}; padding: 5px 9px; }}
QLineEdit:disabled {{ background-color: {BG_SUBTLE}; color: {TEXT_MUTED};
                      border-color: {BORDER}; }}

QPushButton {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
    min-height: 22px;
}}
QPushButton:hover {{
    background: {BG_SUBTLE};
    border-color: {TEXT_MUTED};
}}
QPushButton:pressed {{
    background: {BORDER};
    border-color: {BORDER_STRONG};
    padding: 8px 16px;
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    background: {BG_SUBTLE};
    border: 1px solid {BORDER};
}}
QPushButton:focus {{ outline: none; }}

QPushButton#Primary {{
    background: {BRAND};
    color: {BG_SURFACE};
    border: 1px solid {BRAND};
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {BRAND_HOVER};
    border-color: {BRAND_HOVER};
}}
QPushButton#Primary:pressed {{
    background: {BRAND_PRESSED};
    border-color: {BRAND_PRESSED};
    padding: 8px 16px;
}}
QPushButton#Primary:disabled {{
    background: {BRAND_DISABLED};
    border: 1px solid {BRAND_DISABLED};
    color: {BG_SURFACE};
}}

QTableWidget {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: transparent;
    alternate-background-color: #F7F9FC;
    selection-background-color: {BG_HOVER};
    selection-color: {TEXT_PRIMARY};
    color: {TEXT_PRIMARY};
    font-size: 13px;
    outline: none;
}}
QTableWidget::item        {{ padding: 7px 12px; border: none; }}
QTableWidget::item:hover  {{ background-color: {BG_SUBTLE}; }}
QTableWidget::item:selected {{ background-color: {BG_HOVER}; color: {TEXT_PRIMARY}; }}

QTreeWidget {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    alternate-background-color: {BG_SUBTLE};
    selection-background-color: {BG_HOVER};
    selection-color: {TEXT_PRIMARY};
    color: {TEXT_PRIMARY};
    font-size: 13px;
    outline: none;
    show-decoration-selected: 0;
}}
QTreeWidget::item {{
    padding: 5px 8px;
    border: none;
    min-height: 28px;
}}
QTreeWidget::item:selected {{ background-color: {BG_HOVER}; color: {TEXT_PRIMARY}; }}
QTreeWidget::item:hover    {{ background-color: {BG_SUBTLE}; }}
QTreeWidget::branch        {{ background-color: {BG_SURFACE}; }}
QTreeWidget::branch:selected {{ background-color: {BG_HOVER}; }}
QTreeWidget::branch:has-children:!has-siblings:closed,
QTreeWidget::branch:closed:has-children:has-siblings {{
    {_BRANCH_CLOSED}
}}
QTreeWidget::branch:open:has-children:!has-siblings,
QTreeWidget::branch:open:has-children:has-siblings {{
    {_BRANCH_OPEN}
}}

QHeaderView::section {{
    background-color: {BG_SUBTLE};
    color: {TEXT_SECONDARY};
    padding: 9px 12px;
    border: none;
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0;
}}
QTableCornerButton::section {{
    background-color: {BG_SUBTLE};
    border: none;
    border-bottom: 1px solid {BORDER};
}}

QProgressBar {{
    background-color: {BG_SUBTLE};
    border: none;
    border-radius: 3px;
    color: transparent;
    min-height: 6px;
    max-height: 6px;
}}
QProgressBar::chunk {{
    background: {BRAND};
    border-radius: 3px;
}}

QStatusBar {{
    background-color: {BG_SURFACE};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    padding: 3px 16px;
    font-size: 12px;
}}
QStatusBar::item {{ border: none; }}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 18px;
    padding: 16px 14px 14px;
    background-color: {BG_SURFACE};
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    background-color: {BG_APP};
    color: {TEXT_MUTED};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0;
}}

QScrollBar:vertical   {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG}; border-radius: 4px; min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG}; border-radius: 4px; min-width: 36px;
}}
QScrollBar::handle:horizontal:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}

QToolTip {{
    background-color: {TEXT_PRIMARY};
    color: {BG_SURFACE};
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

QMessageBox  {{ background-color: {BG_SURFACE}; }}
QMessageBox QLabel {{ color: {TEXT_PRIMARY}; font-size: 13px; }}

QDialogButtonBox QPushButton {{ min-width: 88px; }}
"""

# ── Popup del completer ───────────────────────────────────────────────────
POPUP_STYLESHEET = f"""
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    color: {TEXT_PRIMARY};
    font-size: 13px;
    outline: none;
    selection-background-color: {BG_HOVER};
    selection-color: {TEXT_PRIMARY};
"""


def style_combo_popup(combo) -> None:
    """Aplica estilo al popup del completer de un QComboBox editable."""
    c = combo.completer()
    if c is not None:
        popup = c.popup()
        popup.setStyleSheet(
            f"QListView {{ {POPUP_STYLESHEET} }}"
            f"QListView::item {{ padding: 7px 12px; border-radius: 4px; }}"
            f"QListView::item:selected {{ background-color: {BG_HOVER}; }}"
        )


# ── Animación de entrada ─────────────────────────────────────────────────
def show_animated(dialog, duration: int = 160) -> None:
    """Fade-in dialog on open. Call before exec() or show().
    Emil: occasional dialogs → standard animation, ease-out, ≤200ms."""
    from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
    dialog.setWindowOpacity(0.0)
    anim = QPropertyAnimation(dialog, b"windowOpacity", dialog)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start()
    dialog._show_anim = anim   # prevent GC


# ── Widgets ───────────────────────────────────────────────────────────────

class NoScrollComboBox(QComboBox):
    """QComboBox que ignora el scroll del mouse para evitar cambios accidentales."""
    def wheelEvent(self, event):          # noqa: N802
        event.ignore()


# ── Badges ────────────────────────────────────────────────────────────────
_BADGE_VARIANTS = {
    "success": (SUCCESS, SUCCESS_BG),
    "warning": (WARNING, WARNING_BG),
    "danger":  (DANGER,  DANGER_BG),
    "info":    (INFO,    INFO_BG),
    "neutral": (TEXT_SECONDARY, BG_SUBTLE),
}


def badge_qss(variant: str) -> str:
    fg, bg = _BADGE_VARIANTS.get(variant, _BADGE_VARIANTS["neutral"])
    return (
        f"background-color: {bg};"
        f"color: {fg};"
        f"border: 1px solid {BORDER};"
        f"border-radius: 6px;"
        f"padding: 3px 10px;"
        f"font-size: 11px;"
        f"font-weight: 600;"
    )


def make_badge(text: str, variant: str = "neutral") -> QWidget:
    """Pill widget centrado, listo para setCellWidget o layouts."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(6, 4, 6, 4)
    layout.setSpacing(0)
    label = QLabel(text)
    label.setStyleSheet(badge_qss(variant))
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
    layout.addWidget(label)
    layout.addStretch()
    return container
