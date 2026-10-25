"""Páginas del modelo (acierto, opiniones y backtest) y de configuración."""

from __future__ import annotations

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QPushButton, QSpinBox

from predictor.escritorio.comun import Contexto
from predictor.escritorio.widgets import Pagina, Tabla, fila, lanzar, panel, subtitulo, tenue
from predictor.exportar import (
    tabla_backtest_valor,
    tabla_evaluacion,
    tabla_fuentes,
    tabla_predicciones,
)
from predictor.modelos import LIGAS, Deporte
from predictor.valor import Umbrales


class PaginaModelo(Pagina):
    def __init__(self, contexto: Contexto) -> None:
        super().__init__(
            "Modelo",
            "El modelo es estadístico (Poisson en fútbol, ratings en la NBA). Cada predicción se "
            "guarda antes del inicio y se mide contra el resultado real. La línea base predice "
            "según cuánto gana el local, empata o gana la visita en la liga. "
            "Brier: menor es mejor.",
        )
        self._contexto = contexto
        self._tarea = None
        self.contenido.addWidget(subtitulo("Predicciones guardadas"))
        self.sin_evaluadas = tenue(
            "Aún no hay predicciones con resultado. Se miden tras actualizar el historial."
        )
        self.evaluacion, self.predicciones = Tabla(), Tabla(compacta=False)
        self.predicciones.setMinimumHeight(300)
        for widget in (self.sin_evaluadas, self.evaluacion, self.predicciones):
            self.contenido.addWidget(widget)

        self.contenido.addWidget(subtitulo("Por opinión"))
        self.nota_fuentes = tenue(
            "Acierto del favorito de cada opinión en los partidos jugados. La mía no tiene "
            "Brier porque solo elige ganador."
        )
        self.fuentes = Tabla()
        self.contenido.addWidget(self.nota_fuentes)
        self.contenido.addWidget(self.fuentes)

        self.contenido.addWidget(subtitulo("Backtest"))
        self.calcular = QPushButton("Calcular backtest sobre el historial guardado")
        self.calcular.clicked.connect(self.calcular_backtest)
        self.estado_backtest = tenue("Cada fecha se predice solo con los partidos anteriores.")
        self.contenido.addLayout(fila(self.calcular, self.estado_backtest, estirar=True))
        self.backtest = Tabla()
        self.titulo_valor = subtitulo("Estrategia de valor (fútbol)")
        self.nota_valor = tenue(
            "1 unidad a la cuota promedio previa cada vez que el modelo ve valor con los "
            "umbrales de Configuración, frente a apostar siempre al favorito. Aproximación: "
            "no usa la cuota de Betano ni la confirmación del mercado."
        )
        self.backtest_valor = Tabla()
        for widget in (self.backtest, self.titulo_valor, self.nota_valor, self.backtest_valor):
            widget.hide()
            self.contenido.addWidget(widget)
        self.contenido.addStretch(1)

    def refrescar(self) -> None:
        self.sucia = False
        cartelera = self._contexto.cartelera
        evaluadas = cartelera.evaluadas()
        self.sin_evaluadas.setVisible(not evaluadas)
        self.evaluacion.setVisible(bool(evaluadas))
        self.predicciones.setVisible(bool(evaluadas))
        if evaluadas:
            self.evaluacion.fijar(tabla_evaluacion(cartelera.evaluacion()))
            self.predicciones.fijar(
                tabla_predicciones([e.prediccion for e in reversed(evaluadas)], evaluadas)
            )
        fuentes = cartelera.evaluacion_por_fuente()
        self.fuentes.setVisible(bool(fuentes))
        if fuentes:
            self.nota_fuentes.setText(
                "Acierto del favorito de cada opinión en los partidos jugados. La mía no tiene "
                "Brier porque solo elige ganador."
            )
            self.fuentes.fijar(tabla_fuentes(fuentes))
        else:
            self.nota_fuentes.setText("Aún no hay opiniones guardadas con resultado.")

    def calcular_backtest(self) -> None:
        cartelera = self._contexto.cartelera

        def calcular():
            return (
                cartelera.backtest([liga for d in Deporte for liga in LIGAS[d]]),
                cartelera.backtest_valor(LIGAS[Deporte.FUTBOL]),
            )

        self.calcular.setEnabled(False)
        self.estado_backtest.setText("Recorriendo el historial…")
        self._tarea = lanzar(calcular, self._mostrar_backtest, self._fallo)

    def _mostrar_backtest(self, resultado) -> None:
        backtest, valor = resultado
        self._tarea = None
        self.calcular.setEnabled(True)
        self.estado_backtest.setText("Cada fecha se predice solo con los partidos anteriores.")
        self.backtest.fijar(tabla_evaluacion(backtest))
        self.backtest.show()
        self.titulo_valor.show()
        self.nota_valor.show()
        if valor:
            self.backtest_valor.fijar(tabla_backtest_valor(valor))
            self.backtest_valor.show()
        else:
            self.nota_valor.setText(
                "El historial guardado no tiene cuotas. Actualiza el historial de fútbol."
            )

    def _fallo(self, error: str) -> None:
        self._tarea = None
        self.calcular.setEnabled(True)
        self.estado_backtest.setText("")
        self._contexto.mensaje.emit(f"No se pudo calcular el backtest: {error}", True)


class PaginaConfiguracion(Pagina):
    def __init__(self, contexto: Contexto) -> None:
        super().__init__("Configuración")
        self._contexto = contexto

        marco, caja = panel()
        caja.addWidget(subtitulo("Fondo"))
        self.fondo = QSpinBox()
        self.fondo.setRange(0, 1_000_000_000)
        self.fondo.setSingleStep(1000)
        self.fondo.setPrefix("$ ")
        self.fondo.setGroupSeparatorShown(True)
        self.guardar_fondo = QPushButton("Guardar")
        self.guardar_fondo.clicked.connect(
            lambda: contexto.ejecutar(
                "Fondo inicial actualizado",
                contexto.bitacora.fijar_fondo_inicial,
                self.fondo.value(),
            )
        )
        formulario = QFormLayout()
        formulario.addRow("Fondo inicial (CLP)", fila(self.fondo, self.guardar_fondo, estirar=True))
        caja.addLayout(formulario)
        self.contenido.addWidget(marco)

        marco, caja = panel()
        caja.addWidget(subtitulo("Apuestas de valor"))
        self.ev_modelo, self.cuota_maxima, self.ev_mercado = (
            QDoubleSpinBox(),
            QDoubleSpinBox(),
            QDoubleSpinBox(),
        )
        for caja_ev in (self.ev_modelo, self.ev_mercado):
            caja_ev.setRange(0.0, 100.0)
            caja_ev.setSingleStep(1.0)
            caja_ev.setSuffix(" %")
        self.cuota_maxima.setRange(1.01, 1000.0)
        self.cuota_maxima.setSingleStep(0.5)
        self.guardar_umbrales = QPushButton("Guardar umbrales")
        self.guardar_umbrales.setObjectName("primario")
        self.guardar_umbrales.clicked.connect(self._guardar_umbrales)
        formulario = QFormLayout()
        formulario.addRow("EV mínimo del modelo", self.ev_modelo)
        formulario.addRow("Cuota máxima", self.cuota_maxima)
        formulario.addRow("EV mínimo según el mercado para confirmar", self.ev_mercado)
        caja.addLayout(formulario)
        caja.addLayout(fila(self.guardar_umbrales, estirar=True))
        self.contenido.addWidget(marco)

        self.info_bd = tenue()
        self.info_clave = tenue()
        self.contenido.addWidget(self.info_bd)
        self.contenido.addWidget(self.info_clave)
        self.contenido.addStretch(1)

    def refrescar(self) -> None:
        self.sucia = False
        self.fondo.setValue(self._contexto.bitacora.fondo_inicial)
        umbrales = self._contexto.cartelera.umbrales
        self.ev_modelo.setValue(umbrales.modelo * 100)
        self.cuota_maxima.setValue(umbrales.cuota_maxima)
        self.ev_mercado.setValue(umbrales.mercado * 100)
        self.info_bd.setText(
            f"Base de datos: {self._contexto.ruta.resolve()} "
            "(cámbiala con la variable PREDICTOR_DB)"
        )
        estado = "configurada" if self._contexto.cartelera.tiene_clave else "no configurada"
        self.info_clave.setText(f"Clave de The Odds API (variable ODDS_API_KEY): {estado}")

    def _guardar_umbrales(self) -> None:
        self._contexto.ejecutar(
            "Umbrales actualizados",
            lambda: self._contexto.cartelera.fijar_umbrales(
                Umbrales(
                    round(self.ev_modelo.value() / 100, 4),
                    self.cuota_maxima.value(),
                    round(self.ev_mercado.value() / 100, 4),
                )
            ),
        )
