"""Tema oscuro: paleta de Qt y hoja de estilos (QSS)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

FONDO = "#0f1117"
SUPERFICIE = "#171a23"
TARJETA = "#1e2230"
BORDE = "#2a2f3d"
TEXTO = "#e6e8ee"
TENUE = "#8b93a7"
ACENTO = "#6d8bff"
VERDE = "#22c55e"
ROJO = "#ef4444"
AMBAR = "#f59e0b"

ESTILO = f"""
* {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 10pt; color: {TEXTO}; }}
QMainWindow, QWidget#pagina, QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {FONDO};
}}
QWidget#lateral {{ background: {SUPERFICIE}; border-right: 1px solid {BORDE}; }}
QLabel#marca {{ font-size: 14pt; font-weight: 700; }}
QLabel#seccion {{
    color: #5d6579; font-size: 8pt; font-weight: 700; padding: 10px 6px 4px 6px;
}}
QLabel#titulo {{ font-size: 18pt; font-weight: 700; }}
QLabel#subtitulo {{ font-size: 12pt; font-weight: 600; padding-top: 10px; }}
QLabel#tenue {{ color: {TENUE}; }}
QLabel#aviso {{
    background: #2a2210; border: 1px solid #5c4813; border-radius: 8px; padding: 8px 10px;
    color: #fcd581;
}}
QLabel#banner {{ border-radius: 8px; padding: 8px 12px; font-weight: 600; }}
QLabel#banner[error="true"] {{ background: #3a1518; border: 1px solid #7f1d1d; color: #fca5a5; }}
QLabel#banner[error="false"] {{ background: #0f2e1d; border: 1px solid #166534; color: #86efac; }}

QFrame#tarjeta, QFrame#panel {{
    background: {TARJETA}; border: 1px solid {BORDE}; border-radius: 10px;
}}
QFrame#tarjeta QLabel, QFrame#panel QLabel {{ background: transparent; border: none; }}
QLabel#tarjeta_titulo {{ color: {TENUE}; font-size: 9pt; }}
QLabel#tarjeta_valor {{ font-size: 17pt; font-weight: 700; }}
QLabel#tarjeta_detalle {{ font-size: 9pt; color: {TENUE}; }}
QLabel#tarjeta_detalle[tono="positivo"] {{ color: {VERDE}; }}
QLabel#tarjeta_detalle[tono="negativo"] {{ color: {ROJO}; }}

QListWidget#navegacion {{ background: transparent; border: none; outline: none; }}
QListWidget#navegacion::item {{
    padding: 8px 10px; border-radius: 8px; margin: 1px 0; color: {TENUE};
    border-left: 3px solid transparent;
}}
QListWidget#navegacion::item:hover {{ background: {TARJETA}; color: {TEXTO}; }}
QListWidget#navegacion::item:selected {{
    background: #262c40; color: {TEXTO}; border-left: 3px solid {ACENTO}; font-weight: 600;
}}

QListWidget#partidos {{
    background: {SUPERFICIE}; border: 1px solid {BORDE}; border-radius: 10px; outline: none;
    padding: 4px;
}}
QListWidget#partidos::item {{ padding: 8px; border-radius: 6px; border-bottom: 1px solid {BORDE}; }}
QListWidget#partidos::item:hover {{ background: {TARJETA}; }}
QListWidget#partidos::item:selected {{ background: #262c40; color: {TEXTO}; }}

QPushButton {{
    background: {TARJETA}; border: 1px solid {BORDE}; border-radius: 8px; padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {ACENTO}; }}
QPushButton:pressed {{ background: #262c40; }}
QPushButton:disabled {{ color: #555c6e; border-color: #23273300; }}
QPushButton#primario {{ background: {ACENTO}; border: none; color: white; font-weight: 600; }}
QPushButton#primario:hover {{ background: #849cff; }}
QPushButton#primario:disabled {{ background: #2f3a66; color: #8b93a7; }}
QPushButton#peligro {{ background: #3a1518; border: 1px solid #7f1d1d; color: #fca5a5; }}
QPushButton#peligro:disabled {{ background: {TARJETA}; border-color: {BORDE}; color: #555c6e; }}

QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
    background: {SUPERFICIE}; border: 1px solid {BORDE}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {ACENTO};
}}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QComboBox:focus {{ border-color: {ACENTO}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled, QDoubleSpinBox:disabled {{
    color: #555c6e;
}}
QComboBox QAbstractItemView {{
    background: {TARJETA}; border: 1px solid {BORDE}; selection-background-color: #262c40;
}}
QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px; border: 1px solid #4a5163; background: {SUPERFICIE};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACENTO}; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {ACENTO}; border-color: {ACENTO};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ border-color: {BORDE}; }}

QTableView {{
    background: {SUPERFICIE}; alternate-background-color: #1a1e29; border: 1px solid {BORDE};
    border-radius: 8px; gridline-color: transparent; selection-background-color: #262c40;
}}
QHeaderView {{ background: {TARJETA}; border: none; border-bottom: 1px solid {BORDE}; }}
QHeaderView::section {{
    background: {TARJETA}; color: {TENUE}; border: none; border-bottom: 1px solid {BORDE};
    padding: 6px 8px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {TARJETA}; border: none; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: {BORDE}; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: #3b4254; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; border: none; width: 0; height: 0;
}}
QSplitter::handle {{ background: transparent; }}
QStatusBar {{ background: {SUPERFICIE}; color: {TENUE}; border-top: 1px solid {BORDE}; }}
QToolTip {{ background: {TARJETA}; color: {TEXTO}; border: 1px solid {BORDE}; padding: 4px; }}
"""


def aplicar(app: QApplication) -> None:
    app.setStyle("Fusion")
    paleta = QPalette()
    colores = {
        QPalette.ColorRole.Window: FONDO,
        QPalette.ColorRole.WindowText: TEXTO,
        QPalette.ColorRole.Base: SUPERFICIE,
        QPalette.ColorRole.AlternateBase: TARJETA,
        QPalette.ColorRole.Text: TEXTO,
        QPalette.ColorRole.Button: TARJETA,
        QPalette.ColorRole.ButtonText: TEXTO,
        QPalette.ColorRole.Highlight: ACENTO,
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: TARJETA,
        QPalette.ColorRole.ToolTipText: TEXTO,
        QPalette.ColorRole.PlaceholderText: TENUE,
    }
    for rol, color in colores.items():
        paleta.setColor(rol, QColor(color))
    app.setPalette(paleta)
    app.setStyleSheet(ESTILO)
