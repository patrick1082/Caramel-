"""Página de partidos: filtros, lista del día, "Valor del día" y el detalle de cada partido."""

from __future__ import annotations

from datetime import UTC, datetime

from PySide6.QtCore import QDate, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from predictor import stake
from predictor.cartelera import Cartelera
from predictor.escritorio import tema
from predictor.escritorio.comun import AVISO_VALOR, Contexto, hora_chile, pct
from predictor.escritorio.iconos import icono
from predictor.escritorio.widgets import (
    Tabla,
    Tarjeta,
    aviso,
    lanzar,
    limpiar,
    panel,
    subtitulo,
    tenue,
    texto,
)
from predictor.exportar import (
    resumen_contraste,
    tabla_cara_a_cara,
    tabla_contraste,
    tabla_cuotas,
    tabla_estadisticas,
    tabla_jugadores,
    tabla_sugeridas,
    tabla_valor_del_dia,
)
from predictor.fuentes.odds_api import costo_creditos
from predictor.ligas import ZONA_CHILE
from predictor.modelos import LIGAS, Deporte, Ganador, Partido, Prediccion, Valor
from predictor.valor import PROB_SUGERIDA

TODAS = "Todas las ligas"
FUTBOL = "Fútbol (todas)"
_FILTROS: dict[str, tuple[str, ...]] = {
    TODAS: tuple(liga for d in Deporte for liga in LIGAS[d]),
    FUTBOL: LIGAS[Deporte.FUTBOL],
    **{liga: (liga,) for d in Deporte for liga in LIGAS[d]},
}
_MARCA = {Valor.CONFIRMADO: tema.VERDE, Valor.MODELO: tema.AMBAR}
SIN_CLAVE = (
    "Falta la clave de The Odds API, que es la única fuente de partidos y cuotas: sin ella no "
    "aparece ningún partido. Crea una clave gratuita en the-odds-api.com, ejecuta "
    'setx ODDS_API_KEY "tu-clave" en una terminal y vuelve a abrir la app. Mientras tanto, '
    "Actualizar solo descarga el historial, los jugadores y el ESPN BPI."
)


def hoy_chile():
    return datetime.now(ZONA_CHILE).date()


def actualizar(cartelera: Cartelera, ligas: list[str]) -> dict[str, dict[str, str]]:
    """Descarga cuotas (si hay clave), historial, jugadores y ESPN BPI; devuelve los errores."""
    if cartelera.tiene_clave:
        cartelera.actualizar_cuotas(ligas)
    cartelera.actualizar_historial(ligas)
    _, errores = cartelera.actualizar_jugadores(ligas)
    _, errores_bpi = cartelera.actualizar_bpi() if "NBA" in ligas else ([], {})
    return {"jugadores": errores, "bpi": {str(d): e for d, e in errores_bpi.items()}}


class DetallePartido(QWidget):
    """Predicción, contraste (con mi predicción), cuotas, jugadores y forma de un partido."""

    apostar = Signal(object)  # Partido

    def __init__(self, contexto: Contexto) -> None:
        super().__init__()
        self._contexto = contexto
        self.disposicion = QVBoxLayout(self)
        self.disposicion.setContentsMargins(4, 0, 4, 0)
        self.disposicion.setSpacing(10)
        self.partido: Partido | None = None

    def mostrar_valor_del_dia(self, oportunidades: list, sugeridas: list) -> None:
        self.partido = None
        limpiar(self.disposicion)
        self.disposicion.addWidget(texto("Valor del día", "titulo"))
        if oportunidades:
            tabla = Tabla()
            tabla.fijar(tabla_valor_del_dia(oportunidades))
            self.disposicion.addWidget(tabla)
        else:
            self.disposicion.addWidget(
                tenue("Ninguna cuota de Betano con valor en los partidos por empezar.")
            )
        self.disposicion.addWidget(aviso(AVISO_VALOR))

        self.disposicion.addWidget(subtitulo(f"Apuestas sugeridas  ({len(sugeridas)})"))
        self.disposicion.addWidget(
            tenue(
                f"Una apuesta por partido por empezar, si alguna tiene un acierto estimado de "
                f"{PROB_SUGERIDA:.0%} o más. El acierto estimado promedia el modelo y el mercado "
                "(Pinnacle sin margen); si falta uno, usa el otro. Entre las que pasan, se elige "
                "la de mayor EV estimado. Un EV negativo significa que la cuota paga menos de lo "
                "que vale el riesgo, aunque la apuesta sea probable."
            )
        )
        self.disposicion.addWidget(
            tenue(
                f"Banca: con valor confirmado, ¼ de Kelly con la probabilidad más prudente (entre "
                f"{stake.PISO:.0%} y {stake.TOPE:.0%}); solo modelo, {stake.SOLO_MODELO:.1%}; "
                f"sin valor, {stake.SIN_VALOR:.0%}. Nunca más de {stake.TOPE:.0%} en una apuesta: "
                "así una racha mala no se lleva la banca. El monto usa el saldo disponible, "
                f"redondeado hacia abajo a ${stake.REDONDEO}; vacío si no alcanza el mínimo."
            )
        )
        if sugeridas:
            total = sum(s.stake for s in sugeridas)
            self.disposicion.addWidget(
                tenue(f"Si apuestas todas, arriesgas {total:.1%} de la banca hoy.")
            )
        if sugeridas:
            tabla = Tabla()
            tabla.fijar(tabla_sugeridas(sugeridas, self._contexto.bitacora.resumen().saldo))
            self.disposicion.addWidget(tabla)
        else:
            self.disposicion.addWidget(
                tenue(f"Ningún partido por empezar tiene una apuesta de {PROB_SUGERIDA:.0%} o más.")
            )
        self.disposicion.addStretch(1)

    def mostrar(self, partido: Partido) -> None:
        self.partido = partido
        cartelera = self._contexto.cartelera
        limpiar(self.disposicion)
        empezado = partido.inicio <= datetime.now(UTC)

        cabecera = QHBoxLayout()
        titulos = QVBoxLayout()
        titulos.addWidget(texto(partido.nombre, "titulo"))
        estado = " · en curso" if empezado else ""
        titulos.addWidget(tenue(f"{partido.liga} · {hora_chile(partido.inicio)}{estado}"))
        cabecera.addLayout(titulos, 1)
        boton = QPushButton("Apostar en este partido")
        boton.setObjectName("primario")
        boton.setEnabled(not empezado)
        boton.clicked.connect(lambda: self.apostar.emit(partido))
        cabecera.addWidget(boton, 0, Qt.AlignmentFlag.AlignTop)
        self.disposicion.addLayout(cabecera)

        prediccion = cartelera.predecir(partido)
        if prediccion is not None:
            self._prediccion(prediccion, empezado)
        else:
            self.disposicion.addWidget(
                tenue("Sin historial suficiente para que el modelo prediga este partido.")
            )
        self._contraste(partido, prediccion, empezado)

        filas = cartelera.comparar(partido)
        self.disposicion.addWidget(subtitulo("Cuotas"))
        if filas:
            self._tabla(tabla_cuotas(filas, prediccion, cartelera.valorar(partido, prediccion)))
        else:
            self.disposicion.addWidget(tenue("Sin cuotas para este partido."))
        jugadores_local, jugadores_visitante = cartelera.jugadores(partido)
        if jugadores_local or jugadores_visitante:
            self.disposicion.addWidget(subtitulo("Figuras y bajas"))
            self._tabla(
                tabla_jugadores(
                    partido.local, jugadores_local, partido.visitante, jugadores_visitante
                )
            )
        analisis = cartelera.analizar(partido)
        self.disposicion.addWidget(subtitulo("Forma reciente"))
        self.disposicion.addWidget(tenue("Propio / rival, promedio de los últimos 10 partidos."))
        self._tabla(tabla_estadisticas(analisis, partido.local, partido.visitante))
        if analisis.cara_a_cara:
            self.disposicion.addWidget(subtitulo("Enfrentamientos directos"))
            self._tabla(tabla_cara_a_cara(analisis.cara_a_cara))
        self.disposicion.addStretch(1)

    def _tabla(self, df) -> None:
        tabla = Tabla()
        tabla.fijar(df)
        self.disposicion.addWidget(tabla)

    def _prediccion(self, prediccion: Prediccion, empezado: bool) -> None:
        congelada = " (congelada al inicio)" if empezado else ""
        self.disposicion.addWidget(subtitulo(f"Predicción del modelo{congelada}"))
        self.disposicion.addWidget(tenue(prediccion.modelo))
        tarjetas = [Tarjeta(prediccion.local, pct(prediccion.prob_local))]
        if prediccion.prob_empate is not None:
            tarjetas.append(Tarjeta("Empate", pct(prediccion.prob_empate)))
        tarjetas.append(Tarjeta(prediccion.visitante, pct(prediccion.prob_visitante)))
        formato = ".2g" if prediccion.prob_empate is not None else ".1f"  # goles o puntos
        esperado = Tarjeta("Marcador esperado")
        esperado.fijar(
            f"{prediccion.esperado_local:{formato}} - {prediccion.esperado_visitante:{formato}}",
            f"Más probable: {prediccion.marcador_probable}" if prediccion.marcador_probable else "",
        )
        tarjetas.append(esperado)
        if prediccion.linea_total is not None and prediccion.prob_over is not None:
            total = Tarjeta(f"Total (línea {prediccion.linea_total:g})")
            total.fijar(f"{prediccion.total_esperado:.1f}", f"Over {pct(prediccion.prob_over)}")
        else:
            total = Tarjeta("Total esperado", f"{prediccion.total_esperado:.1f}")
        tarjetas.append(total)
        rejilla = QHBoxLayout()
        rejilla.setSpacing(10)
        for tarjeta in tarjetas:
            rejilla.addWidget(tarjeta)
        self.disposicion.addLayout(rejilla)
        for factor in prediccion.factores:
            self.disposicion.addWidget(texto(f"•  {factor}"))

    def _contraste(self, partido: Partido, prediccion: Prediccion | None, empezado: bool) -> None:
        cartelera = self._contexto.cartelera
        propia = cartelera.prediccion_propia(partido)
        pronosticos = cartelera.pronosticos(partido, prediccion)
        congelado = " (congelado al inicio)" if empezado else ""
        self.disposicion.addWidget(subtitulo(f"Contraste{congelado}"))
        if propia is not None or pronosticos:
            self._tabla(
                tabla_contraste(partido.local, partido.visitante, propia, pronosticos, prediccion)
            )
            if linea := resumen_contraste(partido.local, partido.visitante, propia, pronosticos):
                self.disposicion.addWidget(tenue(linea))

        marco, caja = panel()
        caja.addWidget(subtitulo("Mi predicción"))
        opciones = [(Ganador.LOCAL, partido.local)]
        if partido.deporte is not Deporte.NBA:
            opciones.append((Ganador.EMPATE, "Empate"))
        opciones.append((Ganador.VISITANTE, partido.visitante))
        self.grupo_ganador = QButtonGroup(marco)
        botones = QHBoxLayout()
        for posicion, (ganador, nombre) in enumerate(opciones):
            radio = QRadioButton(nombre)
            radio.setProperty("ganador", ganador.value)
            radio.setChecked(propia.ganador is ganador if propia else posicion == 0)
            self.grupo_ganador.addButton(radio)
            botones.addWidget(radio)
        botones.addStretch(1)
        caja.addLayout(botones)

        rejilla = QGridLayout()
        self.con_marcador = QCheckBox("Con marcador")
        self.con_marcador.setChecked(propia is not None and propia.marcador_local is not None)
        self.goles_local, self.goles_visitante = QSpinBox(), QSpinBox()
        for caja_goles, valor in (
            (self.goles_local, propia.marcador_local if propia else None),
            (self.goles_visitante, propia.marcador_visitante if propia else None),
        ):
            caja_goles.setRange(0, 300)
            caja_goles.setValue(valor or 0)
        rejilla.addWidget(self.con_marcador, 0, 0)
        rejilla.addWidget(texto(partido.local, ajustar=False), 0, 1)
        rejilla.addWidget(self.goles_local, 0, 2)
        rejilla.addWidget(texto(partido.visitante, ajustar=False), 0, 3)
        rejilla.addWidget(self.goles_visitante, 0, 4)
        rejilla.setColumnStretch(5, 1)
        caja.addLayout(rejilla)
        self.nota = QLineEdit(propia.nota if propia else "")
        self.nota.setPlaceholderText("Nota (opcional)")
        caja.addWidget(self.nota)
        self.guardar = QPushButton("Guardar mi predicción")
        self.guardar.clicked.connect(self._guardar_propia)
        caja.addLayout(_a_la_derecha(self.guardar))
        marco.setEnabled(not empezado)
        self.disposicion.addWidget(marco)

    def _guardar_propia(self) -> None:
        partido = self.partido
        ganador = Ganador(self.grupo_ganador.checkedButton().property("ganador"))
        con_marcador = self.con_marcador.isChecked()
        if self._contexto.ejecutar(
            "Predicción guardada",
            self._contexto.cartelera.guardar_prediccion_propia,
            partido,
            ganador,
            self.goles_local.value() if con_marcador else None,
            self.goles_visitante.value() if con_marcador else None,
            self.nota.text(),
        ):
            self.mostrar(partido)


def _a_la_derecha(widget: QWidget) -> QHBoxLayout:
    disposicion = QHBoxLayout()
    disposicion.addStretch(1)
    disposicion.addWidget(widget)
    return disposicion


class PaginaPartidos(QWidget):
    apostar = Signal(object)  # Partido
    ocupada = Signal(bool)

    def __init__(self, contexto: Contexto) -> None:
        super().__init__()
        self.setObjectName("pagina")
        self._contexto = contexto
        self._errores: dict[str, dict[str, str]] = {}
        self._oportunidades: list = []
        self._sugeridas: list = []
        self._tarea = None
        self.sucia = True

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(28, 22, 28, 16)
        raiz.setSpacing(10)
        raiz.addWidget(texto("Partidos", "titulo"))

        hoy = hoy_chile()
        self.dia = QDateEdit(QDate(hoy.year, hoy.month, hoy.day))
        self.dia.setCalendarPopup(True)
        self.dia.setDisplayFormat("ddd dd-MM-yyyy")
        self.desde, self.hasta = QSpinBox(), QSpinBox()
        self.desde.setRange(0, 23)
        self.hasta.setRange(1, 24)
        self.hasta.setValue(24)
        for caja in (self.desde, self.hasta):
            caja.setSuffix(" h")
        self.ligas = QComboBox()
        self.ligas.addItems(list(_FILTROS))
        self.boton_actualizar = QPushButton(icono("actualizar", "white"), "  Actualizar")
        self.boton_actualizar.setObjectName("primario")
        self.boton_actualizar.clicked.connect(self.actualizar)
        self.creditos = texto("", "tenue", ajustar=False)

        filtros = QHBoxLayout()
        filtros.setSpacing(8)
        for etiqueta, widget in (
            ("Día", self.dia),
            ("Desde", self.desde),
            ("Hasta", self.hasta),
            ("Ligas", self.ligas),
        ):
            filtros.addWidget(tenue(etiqueta))
            filtros.addWidget(widget)
        filtros.addStretch(1)
        filtros.addWidget(self.creditos)
        filtros.addWidget(self.boton_actualizar)
        raiz.addLayout(filtros)
        self.estado = tenue()
        raiz.addWidget(self.estado)
        self.avisos = QVBoxLayout()
        raiz.addLayout(self.avisos)

        self.lista = QListWidget()
        self.lista.setObjectName("partidos")
        self.lista.setMinimumWidth(300)
        self.lista.setIconSize(QSize(14, 14))
        self.lista.currentItemChanged.connect(self._seleccionar)
        self.detalle = DetallePartido(contexto)
        self.detalle.apostar.connect(self.apostar)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setWidget(self.detalle)
        divisor = QSplitter()
        divisor.addWidget(self.lista)
        divisor.addWidget(desplazable)
        divisor.setStretchFactor(1, 1)
        divisor.setSizes([340, 900])
        raiz.addWidget(divisor, 1)

        self.dia.dateChanged.connect(lambda *_: self.refrescar())
        self.desde.valueChanged.connect(self._ajustar_horas)
        self.hasta.valueChanged.connect(self._ajustar_horas)
        self.ligas.currentTextChanged.connect(lambda *_: self.refrescar())

    @property
    def ligas_elegidas(self) -> list[str]:
        return list(_FILTROS[self.ligas.currentText()])

    def _ajustar_horas(self) -> None:
        if self.desde.value() >= self.hasta.value():
            otra, valor = (
                (self.hasta, self.desde.value() + 1)
                if self.sender() is self.desde
                else (self.desde, self.hasta.value() - 1)
            )
            otra.blockSignals(True)
            otra.setValue(valor)
            otra.blockSignals(False)
        self.refrescar()

    def refrescar(self) -> None:
        self.sucia = False
        cartelera = self._contexto.cartelera
        ligas = self.ligas_elegidas
        vencidas = cartelera.ligas_por_actualizar(ligas)
        creditos = cartelera.creditos_restantes
        self.creditos.setText(f"Créditos The Odds API: {'—' if creditos is None else creditos}")
        costo = costo_creditos(len(vencidas)) if cartelera.tiene_clave else 0
        self.boton_actualizar.setText(f"  Actualizar ({costo} créditos)")
        actualizadas = [m for liga in ligas if (m := cartelera.cuotas_actualizadas(liga))]
        self.estado.setText(
            f"Cuotas consultadas por última vez a las {hora_chile(min(actualizadas))} "
            f"({len(vencidas)} de {len(ligas)} ligas con más de 1 hora)"
            if actualizadas
            else "Las cuotas de estas ligas aún no se han consultado."
        )
        self._mostrar_avisos()

        anterior = self.detalle.partido.id if self.detalle.partido else None
        dia = self.dia.date().toPython()
        partidos = cartelera.partidos(dia, self.desde.value(), self.hasta.value(), ligas)
        self._oportunidades, self._sugeridas = (
            cartelera.apuestas_del_dia(partidos) if partidos else ([], [])
        )
        marcas: dict[str, Valor] = {}
        for oportunidad in self._oportunidades:
            actual = marcas.get(oportunidad.partido.id)
            if actual is not Valor.CONFIRMADO:
                marcas[oportunidad.partido.id] = oportunidad.valoracion.valor

        self.lista.blockSignals(True)
        self.lista.clear()
        ahora = datetime.now(UTC)
        if partidos:
            cabecera = QListWidgetItem(
                icono("estrella", tema.AMBAR), f"Valor del día  ({len(self._oportunidades)})"
            )
            self.lista.addItem(cabecera)
        for partido in partidos:
            color = _MARCA.get(marcas.get(partido.id))
            en_curso = "  · en curso" if partido.inicio <= ahora else ""
            item = QListWidgetItem(
                icono("punto", color) if color else icono("vacio"),
                f"{hora_chile(partido.inicio)}   {partido.nombre}\n{partido.liga}{en_curso}",
            )
            item.setData(Qt.ItemDataRole.UserRole, partido)
            self.lista.addItem(item)
        self.lista.blockSignals(False)

        if not partidos:
            limpiar(self.detalle.disposicion)
            self.detalle.partido = None
            self.detalle.disposicion.addWidget(
                tenue(
                    "No hay partidos porque falta la clave de The Odds API (mira el aviso de "
                    "arriba)."
                    if not cartelera.tiene_clave
                    else "No hay partidos guardados para este filtro. Prueba con Actualizar."
                )
            )
            self.detalle.disposicion.addStretch(1)
            return
        fila = next(
            (
                i
                for i in range(self.lista.count())
                if (p := self.lista.item(i).data(Qt.ItemDataRole.UserRole)) and p.id == anterior
            ),
            0,
        )
        self.lista.setCurrentRow(fila)
        self._seleccionar(self.lista.item(fila))

    def _mostrar_avisos(self) -> None:
        limpiar(self.avisos)
        if not self._contexto.cartelera.tiene_clave:
            self.avisos.addWidget(aviso(SIN_CLAVE))
        for liga, error in self._errores.get("jugadores", {}).items():
            self.avisos.addWidget(
                aviso(f"No se pudieron actualizar los jugadores de {liga}: {error}")
            )
        for dia, error in self._errores.get("bpi", {}).items():
            self.avisos.addWidget(aviso(f"No se pudo actualizar el ESPN BPI del {dia}: {error}"))

    def _seleccionar(self, item: QListWidgetItem | None, _anterior=None) -> None:
        if item is None:
            return
        partido = item.data(Qt.ItemDataRole.UserRole)
        if partido is None:
            self.detalle.mostrar_valor_del_dia(self._oportunidades, self._sugeridas)
        else:
            self.detalle.mostrar(partido)

    def actualizar(self) -> None:
        cartelera, ligas = self._contexto.cartelera, self.ligas_elegidas
        self.boton_actualizar.setEnabled(False)
        self.boton_actualizar.setText("  Descargando…")
        self.ocupada.emit(True)
        self._tarea = lanzar(lambda: actualizar(cartelera, ligas), self._terminado, self._fallo)

    def _fin(self) -> None:
        self._tarea = None
        self.boton_actualizar.setEnabled(True)
        self.ocupada.emit(False)

    def _terminado(self, errores: dict) -> None:
        self._errores = errores
        self._fin()
        self._contexto.mensaje.emit("Partidos actualizados", False)
        self._contexto.cambiado.emit()

    def _fallo(self, error: str) -> None:
        self._fin()
        self._contexto.mensaje.emit(f"No se pudo actualizar: {error}", True)
        self.refrescar()
