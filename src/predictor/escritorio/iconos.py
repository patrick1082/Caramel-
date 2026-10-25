"""Íconos de la app: máscaras PNG del set propio teñidas por estado, más el logo y unos trazos."""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap, QPolygonF

from predictor.escritorio import tema

ESCALA = 2  # Se dibuja al doble para que se vea nítido en pantallas con escalado.
RECURSOS = Path(__file__).parent / "recursos"

# Nombre en la app -> máscara blanca con alfa en recursos/iconos (recortada de la hoja de íconos).
_IMAGENES = {
    "partidos": "diana",
    "modelo": "analisis",
    "resumen": "torta",
    "nueva": "monedas",
    "pendientes": "reloj",
    "historial": "documento",
    "movimientos": "billetera",
    "configuracion": "ajustes",
    "actualizar": "actualizar",
    "estrella": "estrella",
    "saldo": "banco",
    "en_juego": "crecimiento",
}


def _linea(p: QPainter, *puntos: tuple[float, float]) -> None:
    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in puntos]))


def _descarga(p: QPainter) -> None:
    _linea(p, (12, 4), (12, 15))
    _linea(p, (7, 10), (12, 15), (17, 10))
    _linea(p, (5, 20), (19, 20))


def _punto(p: QPainter) -> None:
    p.setBrush(p.pen().color())
    p.drawEllipse(QPointF(12, 12), 4.5, 4.5)


def _vacio(p: QPainter) -> None:
    """Reserva el espacio del ícono para que los textos de una lista queden alineados."""


# Trazos sobre una grilla de 24×24 para lo que el set de íconos no trae.
_DIBUJOS: dict[str, Callable[[QPainter], None]] = {
    "exportar": _descarga,
    "punto": _punto,
    "vacio": _vacio,
}
NOMBRES = sorted({*_IMAGENES, *_DIBUJOS, "marca"})


def _pluma(color: QColor, ancho: float = 1.8) -> QPen:
    pluma = QPen(color, ancho)
    pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
    pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pluma


@cache
def _imagen(ruta: Path) -> QImage:
    imagen = QImage(str(ruta))
    if imagen.isNull():
        raise FileNotFoundError(f"Falta el recurso {ruta}")
    return imagen


def _lienzo(tam: int) -> QPixmap:
    lienzo = QPixmap(tam * ESCALA, tam * ESCALA)
    lienzo.fill(Qt.GlobalColor.transparent)
    return lienzo


def _escalada(imagen: QImage, lado: int) -> QImage:
    return imagen.scaled(
        lado, lado, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


def pixmap(nombre: str, color: str = tema.TENUE, tam: int = 18) -> QPixmap:
    lienzo = _lienzo(tam)
    lado = tam * ESCALA
    p = QPainter(lienzo)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if nombre == "marca":
        logo = _escalada(_imagen(RECURSOS / "logo.png"), lado)
        p.drawImage((lado - logo.width()) // 2, (lado - logo.height()) // 2, logo)
    elif nombre in _IMAGENES:
        mascara = _escalada(_imagen(RECURSOS / "iconos" / f"{_IMAGENES[nombre]}.png"), lado)
        p.drawImage((lado - mascara.width()) // 2, (lado - mascara.height()) // 2, mascara)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p.fillRect(lienzo.rect(), QColor(color))
    else:
        p.scale(lado / 24, lado / 24)
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


def logo() -> QIcon:
    """Logo en varios tamaños, para la ventana y la barra de tareas."""
    resultado = QIcon()
    for tam in (16, 24, 32, 48, 64, 128, 256):
        resultado.addPixmap(QPixmap.fromImage(_escalada(_imagen(RECURSOS / "logo.png"), tam)))
    return resultado
