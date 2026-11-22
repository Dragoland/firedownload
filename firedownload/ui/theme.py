"""Tema oscuro con acento azul Arch Linux."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#1793d1"
ACCENT_HOVER = "#37a9e4"
ACCENT_PRESSED = "#117bb0"

_QSS = """
QWidget { background-color: #0c1118; color: #d9e2ec; }
QLabel, QCheckBox, QRadioButton { background: transparent; }
QDialog { background-color: #0c1118; }
QToolTip { background-color: #16202c; color: #d9e2ec; border: 1px solid #2a3a50; padding: 4px; }

QFrame#header { background-color: #0a0f15; border-bottom: 1px solid #1b2636; }
QMenuBar { background-color: #0a0f15; color: #b4c2d3; }
QMenuBar::item { padding: 6px 12px; background: transparent; border-radius: 4px; }
QMenuBar::item:selected { background-color: #1d2c40; color: #d9e2ec; }
QPushButton#link { background: transparent; border: none; color: #37a9e4; padding: 4px 10px; }
QPushButton#link:hover { color: #6cc3ee; }
QLabel#aboutTitle { font-size: 26px; font-weight: 700; color: #1793d1; }
QLabel#brand { font-size: 18px; font-weight: 700; color: #1793d1; }

QTabWidget::pane { border: none; }
QTabBar::tab { background: transparent; color: #7b8a9d; padding: 10px 22px; border: none;
               border-bottom: 2px solid transparent; font-weight: 600; }
QTabBar::tab:selected { color: #d9e2ec; border-bottom: 2px solid #1793d1; }
QTabBar::tab:hover:!selected { color: #b4c2d3; }
QTabBar::tab:disabled { color: #3d4a5c; }

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit { background-color: #121a24; border: 1px solid #223044;
    border-radius: 6px; padding: 7px 10px; selection-background-color: #1793d1; selection-color: #06121b; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: #1793d1; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: #4a586b; }
QComboBox QAbstractItemView { background-color: #121a24; border: 1px solid #223044;
    selection-background-color: #1d2c40; outline: none; }

QPushButton { background-color: #1a2432; border: 1px solid #2a3a50; border-radius: 6px;
              padding: 7px 14px; font-weight: 600; }
QPushButton:hover { background-color: #223146; border-color: #36506f; }
QPushButton:pressed { background-color: #141c28; }
QPushButton:disabled { color: #4a586b; background-color: #121a24; border-color: #1b2636; }
QPushButton#primary { background-color: #1793d1; border-color: #1793d1; color: #06121b; }
QPushButton#primary:hover { background-color: #37a9e4; border-color: #37a9e4; }
QPushButton#primary:pressed { background-color: #117bb0; border-color: #117bb0; }
QPushButton#primary:disabled { background-color: #17435c; border-color: #17435c; color: #4f7a94; }
QPushButton#danger:hover { background-color: #351f25; border-color: #e5534b; color: #e5534b; }

QFrame#card { background-color: #16202c; border: 1px solid #223044; border-radius: 10px; }
QLabel#title { font-size: 14px; font-weight: 600; }
QLabel#muted { color: #7b8a9d; }
QLabel#warning { color: #f0b429; }
QLabel#thumb { background-color: #0a0f15; border: 1px solid #1b2636; border-radius: 6px; }
QLabel#state[status="failed"] { color: #e5534b; }
QLabel#state[status="completed"] { color: #3fb68b; }
QLabel#state[status="paused"] { color: #f0b429; }
QLabel#state[status="downloading"] { color: #37a9e4; }

QGroupBox { border: 1px solid #223044; border-radius: 8px; margin-top: 14px; padding: 16px 12px 10px 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #1793d1; font-weight: 700; }

QProgressBar { background-color: #1f2b3b; border: none; border-radius: 4px; min-height: 8px; max-height: 8px; }
QProgressBar::chunk { background-color: #1793d1; border-radius: 4px; }

QSlider::groove:horizontal { height: 4px; background: #223044; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #1793d1; border-radius: 2px; }
QSlider::handle:horizontal { background: #37a9e4; width: 12px; margin: -5px 0; border-radius: 6px; }

QListWidget { background-color: #121a24; border: 1px solid #223044; border-radius: 8px;
              padding: 4px; outline: none; }
QListWidget::item { padding: 6px 8px; border-radius: 6px; }
QListWidget::item:selected { background-color: #1d2c40; color: #d9e2ec; }
QListWidget::item:hover:!selected { background-color: #172232; }

QScrollArea { border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #2a3a50; border-radius: 5px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #36506f; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QMenu { background-color: #121a24; border: 1px solid #223044; padding: 4px; }
QMenu::item { padding: 6px 22px; border-radius: 4px; }
QMenu::item:selected { background-color: #1d2c40; }
QMenu::separator { height: 1px; background: #223044; margin: 4px 8px; }

QStatusBar { background-color: #0a0f15; color: #7b8a9d; }
QStatusBar::item { border: none; }
"""


def _palette() -> QPalette:
    window, base = QColor("#0c1118"), QColor("#121a24")
    text, muted, accent = QColor("#d9e2ec"), QColor("#4a586b"), QColor(ACCENT)
    role, group = QPalette.ColorRole, QPalette.ColorGroup
    palette = QPalette()
    for r, color in (
        (role.Window, window),
        (role.WindowText, text),
        (role.Base, base),
        (role.AlternateBase, window),
        (role.ToolTipBase, QColor("#16202c")),
        (role.ToolTipText, text),
        (role.Text, text),
        (role.Button, QColor("#1a2432")),
        (role.ButtonText, text),
        (role.BrightText, QColor("#e5534b")),
        (role.Highlight, accent),
        (role.HighlightedText, QColor("#06121b")),
        (role.PlaceholderText, QColor("#5d6c80")),
        (role.Link, accent),
    ):
        palette.setColor(r, color)
    for r in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(group.Disabled, r, muted)
    return palette


def apply_theme(app: QApplication) -> None:
    """Aplica Fusion + paleta oscura + QSS."""
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(_QSS)
