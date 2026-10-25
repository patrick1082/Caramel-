"""Piezas reutilizables: tabla sobre un DataFrame, tarjetas, textos y tareas en segundo plano.

Los textos que vienen de fuentes externas (nombres, lesiones, factores) se muestran siempre como
texto plano: un QLabel por defecto interpreta HTML si el texto lo parece.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from numbers import Integral, Real

import pandas as pd
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QRunnable,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from predictor.escritorio import tema

_COLUMNAS_CON_SIGNO = ("Resultado", "ROI", "EV")
_COLORES_TEXTO = {
    "Confirmado": tema.VERDE,
    "Solo modelo": tema.AMBAR,
    "ganada": tema.VERDE,
    "perdida": tema.ROJO,
}


def formatear(columna: str, valor) -> str:
    """Texto de una celda: montos en CLP con punto de miles, porcentajes y cuotas legibles."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "—"
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, Integral):
        texto = f"{abs(int(valor)):,}".replace(",", ".")
        signo = "-" if valor < 0 else ""
        return f"{signo}${texto}" if "(CLP)" in columna else f"{signo}{texto}"
    if isinstance(valor, Real):
        if columna.endswith("(%)"):
            return f"{valor:.1f} %"
        if "Brier" in columna:
            return f"{valor:.3f}"
        return f"{valor:.2f}"
    return str(valor)


def color_celda(columna: str, valor) -> str | None:
    if isinstance(valor, str):
        return _COLORES_TEXTO.get(valor)
    if isinstance(valor, bool) or not isinstance(valor, Real) or math.isnan(valor):
        return None
    if any(clave in columna for clave in _COLUMNAS_CON_SIGNO) and valor != 0:
        return tema.VERDE if valor > 0 else tema.ROJO
    return None


class ModeloDataFrame(QAbstractTableModel):
    def __init__(self, df: pd.DataFrame | None = None) -> None:
        super().__init__()
        self._df = df if df is not None else pd.DataFrame()

    def fijar(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df
        self.endResetModel()

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    def rowCount(self, padre: QModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if padre.isValid() else len(self._df)

    def columnCount(self, padre: QModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if padre.isValid() else len(self._df.columns)

    def _valor(self, indice: QModelIndex):
        valor = self._df.iat[indice.row(), indice.column()]
        return valor.item() if hasattr(valor, "item") else valor

    def data(self, indice: QModelIndex, rol: int = Qt.ItemDataRole.DisplayRole):
        if not indice.isValid():
            return None
        columna = str(self._df.columns[indice.column()])
        valor = self._valor(indice)
        if rol == Qt.ItemDataRole.DisplayRole:
            return formatear(columna, valor)
        if rol == Qt.ItemDataRole.ForegroundRole:
            color = color_celda(columna, valor)
            return QColor(color) if color else None
        if rol == Qt.ItemDataRole.TextAlignmentRole and isinstance(valor, Real):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, seccion: int, orientacion, rol: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if rol == Qt.ItemDataRole.DisplayRole and orientacion == Qt.Orientation.Horizontal:
            return str(self._df.columns[seccion])
        return None


class Tabla(QTableView):
    """Tabla de solo lectura. Con `compacta`, su alto se ajusta a las filas (sin scroll propio)."""

    def __init__(self, compacta: bool = True) -> None:
        super().__init__()
        self._compacta = compacta
        self.modelo = ModeloDataFrame()
        self.setModel(self.modelo)
        self.setAlternatingRowColors(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(30)
        cabecera = self.horizontalHeader()
        cabecera.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if compacta:
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def fijar(self, df: pd.DataFrame) -> None:
        self.modelo.fijar(df.reset_index(drop=True))
        if self._compacta:
            alto = self.horizontalHeader().sizeHint().height()
            alto += self.verticalHeader().defaultSectionSize() * len(df)
            barra = self.horizontalScrollBar().sizeHint().height()
            self.setFixedHeight(alto + barra + 2 * self.frameWidth())


def texto(contenido: str = "", nombre: str | None = None, ajustar: bool = True) -> QLabel:
    """QLabel en texto plano (nunca HTML), con ajuste de línea."""
    etiqueta = QLabel(contenido)
    etiqueta.setTextFormat(Qt.TextFormat.PlainText)
    etiqueta.setWordWrap(ajustar)
    if nombre:
        etiqueta.setObjectName(nombre)
    return etiqueta


def subtitulo(contenido: str) -> QLabel:
    return texto(contenido, "subtitulo")


def tenue(contenido: str = "") -> QLabel:
    return texto(contenido, "tenue")


def aviso(contenido: str = "") -> QLabel:
    return texto(contenido, "aviso")


class Tarjeta(QFrame):
    """Métrica: título pequeño, valor grande y un detalle opcional coloreado."""

    def __init__(self, titulo: str, valor: str = "—") -> None:
        super().__init__()
        self.setObjectName("tarjeta")
        # En una fila, todas las tarjetas toman el alto de la más alta.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        disposicion = QVBoxLayout(self)
        disposicion.setContentsMargins(14, 10, 14, 10)
        disposicion.setSpacing(2)
        self.titulo = texto(titulo, "tarjeta_titulo")
        self.valor = texto(valor, "tarjeta_valor", ajustar=False)
        self.detalle = texto("", "tarjeta_detalle")
        self.detalle.hide()
        for widget in (self.titulo, self.valor, self.detalle):
            disposicion.addWidget(widget)

    def fijar(self, valor: str, detalle: str = "", tono: str = "") -> None:
        self.valor.setText(valor)
        self.detalle.setText(detalle)
        self.detalle.setVisible(bool(detalle))
        self.detalle.setProperty("tono", tono)
        self.detalle.style().unpolish(self.detalle)
        self.detalle.style().polish(self.detalle)


def tono(monto: float | None) -> str:
    if not monto:
        return ""
    return "positivo" if monto > 0 else "negativo"


def fila(*widgets: QWidget, espaciado: int = 10, estirar: bool = False) -> QHBoxLayout:
    disposicion = QHBoxLayout()
    disposicion.setSpacing(espaciado)
    for widget in widgets:
        disposicion.addWidget(widget)
    if estirar:
        disposicion.addStretch(1)
    return disposicion


def panel() -> tuple[QFrame, QVBoxLayout]:
    marco = QFrame()
    marco.setObjectName("panel")
    disposicion = QVBoxLayout(marco)
    disposicion.setContentsMargins(16, 14, 16, 14)
    disposicion.setSpacing(8)
    return marco, disposicion


def limpiar(disposicion) -> None:
    """Quita y destruye todo lo que contiene un layout, incluidos los layouts anidados."""
    while disposicion.count():
        item = disposicion.takeAt(0)
        if widget := item.widget():
            widget.setParent(None)
            widget.deleteLater()
        elif hijo := item.layout():
            limpiar(hijo)


class Pagina(QScrollArea):
    """Página con título y contenido desplazable. Se refresca solo cuando está a la vista."""

    def __init__(self, titulo: str, descripcion: str = "") -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        interior = QWidget()
        interior.setObjectName("pagina")
        self.contenido = QVBoxLayout(interior)
        self.contenido.setContentsMargins(28, 22, 28, 28)
        self.contenido.setSpacing(10)
        self.contenido.addWidget(texto(titulo, "titulo"))
        if descripcion:
            self.contenido.addWidget(tenue(descripcion))
        self.setWidget(interior)
        self.sucia = True

    def refrescar(self) -> None:  # pragma: no cover - cada página lo implementa
        raise NotImplementedError


class _Senales(QObject):
    terminado = Signal(object)
    fallo = Signal(str)


class Tarea(QRunnable):
    """Ejecuta `funcion` en el pool de hilos y avisa el resultado (o el error) al hilo de la UI."""

    def __init__(self, funcion: Callable[[], object]) -> None:
        super().__init__()
        self._funcion = funcion
        self.senales = _Senales()

    def run(self) -> None:
        try:
            resultado = self._funcion()
        except Exception as error:  # noqa: BLE001 - errores de red o de datos se muestran en la UI
            self.senales.fallo.emit(str(error) or type(error).__name__)
        else:
            self.senales.terminado.emit(resultado)


def lanzar(
    funcion: Callable[[], object],
    al_terminar: Callable[[object], None],
    al_fallar: Callable[[str], None],
) -> Tarea:
    tarea = Tarea(funcion)
    tarea.senales.terminado.connect(al_terminar)
    tarea.senales.fallo.connect(al_fallar)
    QThreadPool.globalInstance().start(tarea)
    return tarea
