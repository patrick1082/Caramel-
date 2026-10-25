"""Ventana principal: barra lateral con navegación y saldo, páginas y avisos."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from predictor.escritorio import tema
from predictor.escritorio.bitacora import (
    PaginaHistorial,
    PaginaMovimientos,
    PaginaNuevaApuesta,
    PaginaPendientes,
    PaginaResumen,
)
from predictor.escritorio.comun import Contexto, clp
from predictor.escritorio.iconos import icono, pixmap
from predictor.escritorio.modelo import PaginaConfiguracion, PaginaModelo
from predictor.escritorio.partidos import PaginaPartidos
from predictor.escritorio.widgets import Tarjeta, texto
from predictor.exportar import exportar_excel

DURACION_AVISO_MS = 6000
_ICONOS = (
    "partidos",
    "modelo",
    "resumen",
    "nueva",
    "pendientes",
    "historial",
    "movimientos",
    "configuracion",
)


def _marca() -> QHBoxLayout:
    logo = QLabel()
    logo.setPixmap(pixmap("marca", tam=30))
    nombres = QVBoxLayout()
    nombres.setSpacing(0)
    nombres.addWidget(texto("Predictor", "marca"))
    nombres.addWidget(texto("NBA y fútbol europeo", "tenue"))
    fila = QHBoxLayout()
    fila.setContentsMargins(4, 0, 0, 14)
    fila.setSpacing(10)
    fila.addWidget(logo)
    fila.addLayout(nombres, 1)
    return fila


class Ventana(QMainWindow):
    def __init__(self, contexto: Contexto) -> None:
        super().__init__()
        self.contexto = contexto
        self.setWindowTitle("Predictor de apuestas")
        self.resize(1440, 900)

        self.partidos = PaginaPartidos(contexto)
        self.nueva = PaginaNuevaApuesta(contexto)
        self.paginas = {
            "Partidos": self.partidos,
            "Modelo": PaginaModelo(contexto),
            "Resumen": PaginaResumen(contexto),
            "Nueva apuesta": self.nueva,
            "Pendientes": PaginaPendientes(contexto),
            "Historial": PaginaHistorial(contexto),
            "Movimientos": PaginaMovimientos(contexto),
            "Configuración": PaginaConfiguracion(contexto),
        }

        lateral = QWidget()
        lateral.setObjectName("lateral")
        lateral.setFixedWidth(230)
        columna = QVBoxLayout(lateral)
        columna.setContentsMargins(14, 18, 14, 16)
        columna.addLayout(_marca())
        columna.addWidget(texto("NAVEGACIÓN", "seccion"))
        self.navegacion = QListWidget()
        self.navegacion.setObjectName("navegacion")
        self.navegacion.setIconSize(QSize(18, 18))
        for nombre, clave_icono in zip(self.paginas, _ICONOS, strict=True):
            self.navegacion.addItem(
                QListWidgetItem(icono(clave_icono, tema.TENUE, tema.ACENTO), nombre)
            )
        self.navegacion.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        columna.addWidget(self.navegacion, 1)
        columna.addWidget(texto("FONDO", "seccion"))
        self.saldo, self.en_juego = Tarjeta("Saldo disponible"), Tarjeta("En juego")
        columna.addWidget(self.saldo)
        columna.addWidget(self.en_juego)
        self.exportar = QPushButton(icono("exportar", tema.TEXTO), "  Exportar a Excel")
        self.exportar.clicked.connect(self.exportar_excel)
        columna.addWidget(self.exportar)

        self.banner = texto("", "banner")
        self.banner.hide()
        self._ocultar = QTimer(self)
        self._ocultar.setSingleShot(True)
        self._ocultar.timeout.connect(self.banner.hide)
        self.pila = QStackedWidget()
        for pagina in self.paginas.values():
            self.pila.addWidget(pagina)
        derecha = QVBoxLayout()
        derecha.setContentsMargins(0, 0, 0, 0)
        derecha.addWidget(self.banner)
        derecha.addWidget(self.pila, 1)

        central = QWidget()
        raiz = QHBoxLayout(central)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(lateral)
        raiz.addLayout(derecha, 1)
        self.setCentralWidget(central)
        self.statusBar().showMessage(f"Base de datos: {contexto.ruta}")

        self.navegacion.currentRowChanged.connect(self._ir)
        contexto.cambiado.connect(self._cambiado)
        contexto.mensaje.connect(self.avisar)
        self.partidos.apostar.connect(self.apostar)
        self.partidos.ocupada.connect(self._ocupada)
        self._actualizar_saldo()
        self.navegacion.setCurrentRow(0)

    @property
    def pagina_actual(self):
        return self.pila.currentWidget()

    def ir_a(self, nombre: str) -> None:
        self.navegacion.setCurrentRow(list(self.paginas).index(nombre))

    def _ir(self, fila: int) -> None:
        self.pila.setCurrentIndex(fila)
        if self.pagina_actual.sucia:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self.pagina_actual.refrescar()
            finally:
                QApplication.restoreOverrideCursor()

    def _cambiado(self) -> None:
        self._actualizar_saldo()
        for pagina in self.paginas.values():
            pagina.sucia = True
        self._ir(self.pila.currentIndex())

    def _actualizar_saldo(self) -> None:
        resumen = self.contexto.bitacora.resumen()
        self.saldo.fijar(clp(resumen.saldo))
        self.en_juego.fijar(clp(resumen.en_juego))

    def _ocupada(self, ocupada: bool) -> None:
        """Mientras se descarga en segundo plano, las demás páginas no tocan la base."""
        self.navegacion.setEnabled(not ocupada)
        self.exportar.setEnabled(not ocupada)
        if ocupada:
            self.statusBar().showMessage("Descargando cuotas, historial y jugadores…")
        else:
            self.statusBar().clearMessage()

    def avisar(self, mensaje: str, error: bool) -> None:
        self.banner.setText(mensaje)
        self.banner.setProperty("error", "true" if error else "false")
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner.show()
        self._ocultar.start(DURACION_AVISO_MS * (2 if error else 1))

    def apostar(self, partido) -> None:
        self.ir_a("Nueva apuesta")
        self.nueva.preparar(partido)

    def exportar_excel(self) -> None:
        sugerido = Path.home() / f"bitacora_{date.today():%Y%m%d}.xlsx"
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar bitácora", str(sugerido), "Excel (*.xlsx)"
        )
        if not ruta:
            return
        bitacora, cartelera = self.contexto.bitacora, self.contexto.cartelera
        contenido = exportar_excel(
            bitacora.apuestas(),
            bitacora.movimientos(),
            bitacora.resumen(),
            self.contexto.repo.listar_predicciones(),
            cartelera.evaluadas(),
            cartelera.evaluacion_por_fuente(),
        )
        try:
            Path(ruta).write_bytes(contenido)
        except OSError as error:
            self.avisar(f"No se pudo guardar el Excel: {error}", True)
        else:
            self.avisar(f"Excel guardado en {ruta}", False)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Predictor de apuestas")
    tema.aplicar(app)
    contexto = Contexto.desde_entorno()
    ventana = Ventana(contexto)
    ventana.show()
    try:
        return app.exec()
    finally:
        contexto.repo.cerrar()
