"""Íconos de línea dibujados con QPainter sobre una grilla de 24×24, sin emojis ni archivos."""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

from predictor.escritorio import tema

ESCALA = 2  # Se dibuja al doble para que se vea nítido en pantallas con escalado.


def _linea(p: QPainter, *puntos: tuple[float, float]) -> None:
    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in puntos]))


def _calendario(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(3.5, 5, 17, 15.5), 2.5, 2.5)
    _linea(p, (3.5, 10), (20.5, 10))
    _linea(p, (8, 3), (8, 7))
    _linea(p, (16, 3), (16, 7))


def _tendencia(p: QPainter) -> None:
    _linea(p, (3, 17), (9, 11), (13, 15), (21, 7))
    _linea(p, (15.5, 7), (21, 7), (21, 12.5))


def _barras(p: QPainter) -> None:
    for x, alto in ((6, 13), (12, 6), (18, 10)):
        _linea(p, (x, 20), (x, alto))


def _mas(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    _linea(p, (12, 8), (12, 16))
    _linea(p, (8, 12), (16, 12))


def _reloj(p: QPainter) -> None:
    p.drawEllipse(QPointF(12, 12), 9, 9)
    _linea(p, (12, 7), (12, 12), (15.5, 14))


def _lista(p: QPainter) -> None:
    for y in (7, 12, 17):
        _linea(p, (9, y), (20, y))
        p.drawPoint(QPointF(4.5, y))


def _flechas(p: QPainter) -> None:
    _linea(p, (8, 20), (8, 5))
    _linea(p, (4, 9), (8, 5), (12, 9))
    _linea(p, (16, 4), (16, 19))
    _linea(p, (12, 15), (16, 19), (20, 15))


def _ajustes(p: QPainter) -> None:
    _linea(p, (4, 7), (6.5, 7))
    _linea(p, (11.5, 7), (20, 7))
    p.drawEllipse(QPointF(9, 7), 2.5, 2.5)
    _linea(p, (4, 17), (12.5, 17))
    _linea(p, (17.5, 17), (20, 17))
    p.drawEllipse(QPointF(15, 17), 2.5, 2.5)


def _descarga(p: QPainter) -> None:
    _linea(p, (12, 4), (12, 15))
    _linea(p, (7, 10), (12, 15), (17, 10))
    _linea(p, (5, 20), (19, 20))


def _recargar(p: QPainter) -> None:
    p.drawArc(QRectF(4, 4, 16, 16), 60 * 16, 290 * 16)
    _linea(p, (11.5, 2.5), (16, 5), (13.5, 9))


def _estrella(p: QPainter) -> None:
    puntas = []
    for i in range(10):
        radio = 9.5 if i % 2 == 0 else 4
        angulo = math.radians(-90 + 36 * i)
        puntas.append(QPointF(12 + radio * math.cos(angulo), 12.5 + radio * math.sin(angulo)))
    p.setBrush(p.pen().color())
    p.drawPolygon(QPolygonF(puntas))


def _punto(p: QPainter) -> None:
    p.setBrush(p.pen().color())
    p.drawEllipse(QPointF(12, 12), 4.5, 4.5)


def _vacio(p: QPainter) -> None:
    """Reserva el espacio del ícono para que los textos de una lista queden alineados."""


def _marca(p: QPainter) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(tema.ACENTO))
    p.drawRoundedRect(QRectF(0, 0, 24, 24), 6, 6)
    p.setPen(_pluma(QColor("white"), 2.2))
    _linea(p, (5.5, 16.5), (10, 12), (13, 14.5), (18.5, 8))


_DIBUJOS: dict[str, Callable[[QPainter], None]] = {
    "partidos": _calendario,
    "modelo": _tendencia,
    "resumen": _barras,
    "nueva": _mas,
    "pendientes": _reloj,
    "historial": _lista,
    "movimientos": _flechas,
    "configuracion": _ajustes,
    "exportar": _descarga,
    "actualizar": _recargar,
    "estrella": _estrella,
    "punto": _punto,
    "vacio": _vacio,
    "marca": _marca,
}


def _pluma(color: QColor, ancho: float = 1.8) -> QPen:
    pluma = QPen(color, ancho)
    pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
    pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pluma


def pixmap(nombre: str, color: str = tema.TENUE, tam: int = 18) -> QPixmap:
    lienzo = QPixmap(tam * ESCALA, tam * ESCALA)
    lienzo.fill(Qt.GlobalColor.transparent)
    p = QPainter(lienzo)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(tam * ESCALA / 24, tam * ESCALA / 24)
    p.setPen(_pluma(QColor(color)))
    _DIBUJOS[nombre](p)
    p.end()
    lienzo.setDevicePixelRatio(ESCALA)
    return lienzo


def icono(nombre: str, color: str = tema.TENUE, activo: str | None = None) -> QIcon:
    """Ícono con su color normal y, si se indica, otro para el elemento seleccionado."""
    resultado = QIcon(pixmap(nombre, color))
    if activo is not None:
        resultado.addPixmap(pixmap(nombre, activo), QIcon.Mode.Selected)
    return resultado
