"""Páginas de la bitácora: resumen, nueva apuesta, pendientes, historial y movimientos."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from predictor.escritorio.comun import Contexto, clp, describir_fila, hora_chile, pct, registrar
from predictor.escritorio.partidos import hoy_chile
from predictor.escritorio.widgets import (
    Pagina,
    Tabla,
    Tarjeta,
    fila,
    limpiar,
    panel,
    subtitulo,
    tenue,
    texto,
    tono,
)
from predictor.exportar import tabla_apuestas, tabla_metricas, tabla_movimientos
from predictor.ligas import ZONA_CHILE
from predictor.modelos import LIGAS, Deporte, Estado, Movimiento, Partido, TipoMovimiento, Valor

MAXIMO_CLP = 1_000_000_000


def _qdate(dia: date) -> QDate:
    return QDate(dia.year, dia.month, dia.day)


def _boton(texto_boton: str, nombre: str = "") -> QPushButton:
    boton = QPushButton(texto_boton)
    if nombre:
        boton.setObjectName(nombre)
    return boton


def _monto(valor: int, paso: int, minimo: int = 1) -> QSpinBox:
    caja = QSpinBox()
    caja.setRange(minimo, MAXIMO_CLP)
    caja.setSingleStep(paso)
    caja.setValue(valor)
    caja.setPrefix("$ ")
    caja.setGroupSeparatorShown(True)
    return caja


class PaginaResumen(Pagina):
    def __init__(self, contexto: Contexto) -> None:
        super().__init__("Resumen")
        self._contexto = contexto
        self.saldo, self.ganancia = Tarjeta("Saldo"), Tarjeta("Ganancia / pérdida")
        self.roi, self.acierto = Tarjeta("ROI"), Tarjeta("Acierto")
        self.contenido.addLayout(fila(self.saldo, self.ganancia, self.roi, self.acierto))
        self.detalle = tenue()
        self.contenido.addWidget(self.detalle)
        self.por_deporte, self.por_liga, self.por_valor = Tabla(), Tabla(), Tabla()
        self.contenido.addWidget(subtitulo("Por deporte"))
        self.contenido.addWidget(self.por_deporte)
        self.contenido.addWidget(subtitulo("Por liga"))
        self.contenido.addWidget(self.por_liga)
        self.contenido.addWidget(subtitulo("Con valor vs. sin valor"))
        self.contenido.addWidget(
            tenue(
                "La hipótesis del proyecto: ¿rinden más las apuestas que la app marcó con valor? "
                "Incluye las no colocadas y solo cuenta las registradas desde la cartelera."
            )
        )
        self.contenido.addWidget(self.por_valor)
        self.contenido.addWidget(subtitulo("Apuestas no colocadas (hipotético)"))
        self.registradas = Tarjeta("Registradas")
        self.hipotetico = Tarjeta("Resultado si las hubieras hecho")
        self.roi_hipotetico = Tarjeta("ROI hipotético")
        self.contenido.addLayout(fila(self.registradas, self.hipotetico, self.roi_hipotetico))
        self.contenido.addStretch(1)

    def refrescar(self) -> None:
        self.sucia = False
        resumen = self._contexto.bitacora.resumen()
        capital = resumen.fondo_inicial + resumen.depositos - resumen.retiros
        diferencia = resumen.saldo - capital
        self.saldo.fijar(
            clp(resumen.saldo), f"{clp(diferencia)} sobre lo aportado", tono(diferencia)
        )
        self.ganancia.fijar(clp(resumen.ganancia), "", tono(resumen.ganancia))
        c = resumen.colocadas
        self.roi.fijar(pct(c.roi), "", tono(c.roi))
        self.acierto.fijar(pct(c.acierto))
        self.detalle.setText(
            f"Capital aportado {clp(capital)} · {c.total} apuestas colocadas: "
            f"{c.ganadas} ganadas, {c.perdidas} perdidas, {c.nulas} nulas, "
            f"{c.pendientes} pendientes"
        )
        self.por_deporte.fijar(tabla_metricas(resumen.por_deporte))
        self.por_liga.fijar(tabla_metricas(resumen.por_liga))
        self.por_valor.fijar(
            tabla_metricas({Valor(v).etiqueta: m for v, m in resumen.por_valor.items()})
        )
        nc = resumen.no_colocadas
        self.registradas.fijar(str(nc.total))
        self.hipotetico.fijar(clp(nc.resultado), "", tono(nc.resultado))
        self.roi_hipotetico.fijar(pct(nc.roi), "", tono(nc.roi))


class PaginaNuevaApuesta(Pagina):
    def __init__(self, contexto: Contexto) -> None:
        super().__init__(
            "Nueva apuesta",
            "Desde la cartelera se guarda la probabilidad del modelo y la marca de valor, "
            "recalculada con la cuota que escribas (la de Betano Chile).",
        )
        self._contexto = contexto
        marco, caja = panel()
        formulario = QFormLayout()
        formulario.setSpacing(10)
        formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.origen = QComboBox()
        self.valoracion = QComboBox()
        self.sin_cuotas = tenue("Este partido no tiene cuotas de Betano guardadas.")
        self.deporte = QComboBox()
        for deporte in Deporte:
            self.deporte.addItem(str(deporte), deporte)
        self.liga = QComboBox()
        self.fecha = QDateEdit()
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat("dd-MM-yyyy")
        self.partido = QLineEdit()
        self.partido.setPlaceholderText("Lakers vs Celtics")
        self.mercado = QLineEdit()
        self.mercado.setPlaceholderText("Ganador, Over/Under 2.5, Hándicap…")
        self.seleccion = QLineEdit()
        self.seleccion.setPlaceholderText("Lakers")
        self.cuota = QDoubleSpinBox()
        self.cuota.setRange(1.01, 1000.0)
        self.cuota.setDecimals(2)
        self.cuota.setSingleStep(0.01)
        self.cuota.setToolTip(
            "Escribe la cuota real de Betano Chile: el valor se recalcula con ella."
        )
        self.monto = _monto(500, 100)
        self.casa = QLineEdit()
        self.colocada = QCheckBox("Apuesta colocada")
        self.colocada.setToolTip(
            "Desmárcala para registrar una apuesta que analizaste pero no hiciste."
        )
        self.prediccion = QPlainTextEdit()
        self.prediccion.setPlaceholderText("Lakers ganan por 5-8 puntos")
        self.prediccion.setFixedHeight(70)
        self.nota = QLineEdit()
        self.registrar = _boton("Registrar apuesta", "primario")
        self.registrar.clicked.connect(self._registrar)

        formulario.addRow("Desde la cartelera", self.origen)
        formulario.addRow("Cuota de Betano", self.valoracion)
        formulario.addRow("", self.sin_cuotas)
        formulario.addRow("Deporte", self.deporte)
        formulario.addRow("Liga", self.liga)
        formulario.addRow("Fecha del partido", self.fecha)
        formulario.addRow("Partido", self.partido)
        formulario.addRow("Mercado", self.mercado)
        formulario.addRow("Selección", self.seleccion)
        formulario.addRow("Cuota", self.cuota)
        formulario.addRow("Monto (CLP)", self.monto)
        formulario.addRow("Casa", self.casa)
        formulario.addRow("", self.colocada)
        formulario.addRow("Mi predicción", self.prediccion)
        formulario.addRow("Nota", self.nota)
        caja.addLayout(formulario)
        botones = QHBoxLayout()
        botones.addStretch(1)
        botones.addWidget(self.registrar)
        caja.addLayout(botones)
        marco.setMaximumWidth(760)
        self.contenido.addWidget(marco)
        self.contenido.addStretch(1)

        self.deporte.currentIndexChanged.connect(self._llenar_ligas)
        self.origen.currentIndexChanged.connect(self._elegir_origen)
        self.valoracion.currentIndexChanged.connect(self._elegir_valoracion)
        self._limpiar()

    def _llenar_ligas(self) -> None:
        self.liga.clear()
        self.liga.addItems(list(LIGAS[self.deporte.currentData()]))

    def _limpiar(self) -> None:
        self.fecha.setDate(_qdate(date.today()))
        for campo in (self.partido, self.mercado, self.seleccion, self.nota):
            campo.clear()
        self.prediccion.clear()
        self.cuota.setValue(1.80)
        self.monto.setValue(500)
        self.casa.setText("Betano")
        self.colocada.setChecked(True)

    def refrescar(self, preferido: Partido | None = None) -> None:
        self.sucia = False
        actual = preferido or self.origen.currentData()
        ahora = datetime.now(UTC)
        proximos = [p for p in self._contexto.cartelera.partidos(hoy_chile()) if p.inicio > ahora]
        if preferido is not None and all(p.id != preferido.id for p in proximos):
            proximos.append(preferido)
        self.origen.blockSignals(True)
        self.origen.clear()
        self.origen.addItem("— Escribir a mano —", None)
        for partido in proximos:
            self.origen.addItem(
                f"{hora_chile(partido.inicio)} · {partido.liga} · {partido.nombre}", partido
            )
        indice = next(
            (i for i, p in enumerate(proximos, start=1) if actual and p.id == actual.id), 0
        )
        self.origen.setCurrentIndex(indice)
        self.origen.blockSignals(False)
        self._elegir_origen()

    def preparar(self, partido: Partido) -> None:
        """Abre el formulario con el partido elegido en la cartelera."""
        self.refrescar(partido)

    def _elegir_origen(self) -> None:
        partido: Partido | None = self.origen.currentData()
        self.valoracion.blockSignals(True)
        self.valoracion.clear()
        if partido is not None:
            cartelera = self._contexto.cartelera
            for v in cartelera.valorar(partido, cartelera.predecir(partido)):
                if v.fila.betano:
                    etiqueta = " · ".join(
                        [*describir_fila(v), f"{v.fila.betano}", v.valor.etiqueta]
                    )
                    self.valoracion.addItem(etiqueta, v)
        self.valoracion.blockSignals(False)
        tiene = self.valoracion.count() > 0
        self.valoracion.setEnabled(tiene)
        self.sin_cuotas.setVisible(partido is not None and not tiene)
        self.deporte.setEnabled(partido is None)
        if partido is not None:
            self.deporte.setCurrentIndex(list(Deporte).index(partido.deporte))
            self._llenar_ligas()
            self.liga.setCurrentText(partido.liga)
            self.fecha.setDate(_qdate(partido.inicio.astimezone(ZONA_CHILE).date()))
            self.partido.setText(partido.nombre)
        elif self.liga.count() == 0:
            self._llenar_ligas()
        self._elegir_valoracion()

    def _elegir_valoracion(self) -> None:
        valoracion = self.valoracion.currentData()
        if valoracion is None:
            return
        mercado, seleccion = describir_fila(valoracion)
        self.mercado.setText(mercado)
        self.seleccion.setText(seleccion)
        self.cuota.setValue(float(valoracion.fila.betano))

    def _registrar(self) -> None:
        bitacora, cartelera = self._contexto.bitacora, self._contexto.cartelera
        valoracion = self.valoracion.currentData() if self.origen.currentData() else None
        if self._contexto.ejecutar(
            "Apuesta registrada",
            registrar,
            bitacora,
            valoracion,
            cartelera.umbrales,
            deporte=self.deporte.currentData(),
            liga=self.liga.currentText(),
            partido=self.partido.text(),
            mercado=self.mercado.text(),
            seleccion=self.seleccion.text(),
            cuota=Decimal(f"{self.cuota.value():.2f}"),
            monto=self.monto.value(),
            fecha_evento=self.fecha.date().toPython(),
            casa=self.casa.text(),
            colocada=self.colocada.isChecked(),
            prediccion_propia=self.prediccion.toPlainText(),
            nota=self.nota.text(),
        ):
            self._limpiar()
            self.origen.setCurrentIndex(0)


class PaginaPendientes(Pagina):
    def __init__(self, contexto: Contexto) -> None:
        super().__init__("Pendientes", "Liquida cada apuesta cuando termine el partido.")
        self._contexto = contexto
        self.lista = QVBoxLayout()
        self.lista.setSpacing(10)
        self.contenido.addLayout(self.lista)
        self.contenido.addStretch(1)

    def refrescar(self) -> None:
        self.sucia = False
        limpiar(self.lista)
        pendientes = [a for a in self._contexto.bitacora.apuestas() if not a.liquidada]
        if not pendientes:
            self.lista.addWidget(tenue("No hay apuestas pendientes."))
        for apuesta in pendientes:
            self.lista.addWidget(self._tarjeta(apuesta))

    def _tarjeta(self, apuesta):
        marco, caja = panel()
        no_colocada = " · no colocada" if not apuesta.colocada else ""
        caja.addWidget(texto(f"#{apuesta.id} · {apuesta.partido}", "subtitulo"))
        caja.addWidget(
            tenue(
                f"{apuesta.fecha_evento:%d-%m} · {apuesta.liga} · {apuesta.mercado} — "
                f"{apuesta.seleccion} @ {apuesta.cuota} · {clp(apuesta.monto)}{no_colocada}"
            )
        )
        estado = QComboBox()
        for opcion in (Estado.GANADA, Estado.PERDIDA, Estado.NULA):
            estado.addItem(opcion.value.capitalize(), opcion)
        ajustar = QCheckBox("Ajustar resultado neto (redondeo de la casa)")
        neto = QSpinBox()
        neto.setRange(-MAXIMO_CLP, MAXIMO_CLP)
        neto.setPrefix("$ ")
        neto.setEnabled(False)
        ajustar.toggled.connect(neto.setEnabled)
        liquidar = _boton("Liquidar", "primario")
        liquidar.clicked.connect(
            lambda: self._contexto.ejecutar(
                "Apuesta liquidada",
                self._contexto.bitacora.liquidar,
                apuesta.id,
                estado.currentData(),
                neto.value() if ajustar.isChecked() else None,
            )
        )
        controles = QHBoxLayout()
        controles.addWidget(estado)
        controles.addWidget(ajustar)
        controles.addWidget(neto)
        controles.addStretch(1)
        controles.addWidget(liquidar)
        caja.addLayout(controles)
        caja.addWidget(
            tenue(f"Si gana, el resultado neto será {clp(apuesta.pago_bruto() - apuesta.monto)}")
        )
        marco.setProperty("apuesta", apuesta.id)
        marco.estado, marco.ajustar, marco.neto, marco.liquidar = estado, ajustar, neto, liquidar
        return marco


class PaginaHistorial(Pagina):
    def __init__(self, contexto: Contexto) -> None:
        super().__init__("Historial")
        self._contexto = contexto
        self.deporte, self.estado, self.tipo = QComboBox(), QComboBox(), QComboBox()
        self.deporte.addItem("Todos los deportes", None)
        for deporte in Deporte:
            self.deporte.addItem(str(deporte), deporte)
        self.estado.addItem("Todos los estados", None)
        for estado in Estado:
            self.estado.addItem(estado.value.capitalize(), estado)
        self.tipo.addItems(["Todas", "Colocadas", "No colocadas"])
        for combo in (self.deporte, self.estado, self.tipo):
            combo.currentIndexChanged.connect(lambda *_: self.refrescar())
        self.contenido.addLayout(fila(self.deporte, self.estado, self.tipo, estirar=True))
        self.tabla = Tabla(compacta=False)
        self.tabla.setMinimumHeight(360)
        self.contenido.addWidget(self.tabla, 1)

        self.contenido.addWidget(subtitulo("Corregir una apuesta"))
        self.elegida = QComboBox()
        self.elegida.setMinimumWidth(360)
        self.elegida.currentIndexChanged.connect(lambda *_: self._habilitar())
        self.revertir = _boton("Volver a pendiente")
        self.revertir.clicked.connect(
            lambda: self._contexto.ejecutar(
                "Apuesta revertida a pendiente",
                self._contexto.bitacora.revertir,
                self.elegida.currentData().id,
            )
        )
        self.confirmar = QCheckBox("Confirmo que quiero eliminarla")
        self.eliminar = _boton("Eliminar", "peligro")
        self.confirmar.toggled.connect(lambda *_: self._habilitar())
        self.eliminar.clicked.connect(
            lambda: self._contexto.ejecutar(
                "Apuesta eliminada",
                self._contexto.bitacora.eliminar_apuesta,
                self.elegida.currentData().id,
            )
        )
        self.contenido.addLayout(
            fila(self.elegida, self.revertir, self.confirmar, self.eliminar, estirar=True)
        )

    def refrescar(self) -> None:
        self.sucia = False
        apuestas = self._contexto.bitacora.apuestas()
        deporte, estado, tipo = (
            self.deporte.currentData(),
            self.estado.currentData(),
            self.tipo.currentText(),
        )
        filtradas = [
            a
            for a in apuestas
            if (deporte is None or a.deporte is deporte)
            and (estado is None or a.estado is estado)
            and (tipo == "Todas" or a.colocada == (tipo == "Colocadas"))
        ]
        self.tabla.fijar(tabla_apuestas(filtradas))
        self.elegida.blockSignals(True)
        self.elegida.clear()
        for apuesta in reversed(apuestas):
            self.elegida.addItem(f"#{apuesta.id} · {apuesta.partido} · {apuesta.estado}", apuesta)
        self.elegida.blockSignals(False)
        self.confirmar.setChecked(False)
        self._habilitar()

    def _habilitar(self) -> None:
        apuesta = self.elegida.currentData()
        self.revertir.setEnabled(apuesta is not None and apuesta.liquidada)
        self.confirmar.setEnabled(apuesta is not None)
        self.eliminar.setEnabled(apuesta is not None and self.confirmar.isChecked())


class PaginaMovimientos(Pagina):
    def __init__(self, contexto: Contexto) -> None:
        super().__init__("Movimientos", "Depósitos y retiros del fondo.")
        self._contexto = contexto
        marco, caja = panel()
        self.tipo = QComboBox()
        for tipo in TipoMovimiento:
            self.tipo.addItem(tipo.value.capitalize(), tipo)
        self.monto = _monto(1000, 500)
        self.fecha = QDateEdit(_qdate(date.today()))
        self.fecha.setCalendarPopup(True)
        self.fecha.setDisplayFormat("dd-MM-yyyy")
        self.nota = QLineEdit()
        self.nota.setPlaceholderText("Nota (opcional)")
        self.registrar = _boton("Registrar movimiento", "primario")
        self.registrar.clicked.connect(self._registrar)
        caja.addLayout(fila(self.tipo, self.monto, self.fecha, self.nota, self.registrar))
        self.contenido.addWidget(marco)
        self.tabla = Tabla(compacta=False)
        self.tabla.setMinimumHeight(320)
        self.contenido.addWidget(self.tabla, 1)

    def refrescar(self) -> None:
        self.sucia = False
        self.tabla.fijar(tabla_movimientos(self._contexto.bitacora.movimientos()))

    def _registrar(self) -> None:
        if self._contexto.ejecutar(
            "Movimiento registrado",
            lambda: self._contexto.bitacora.registrar_movimiento(
                Movimiento(
                    tipo=self.tipo.currentData(),
                    monto=self.monto.value(),
                    fecha=self.fecha.date().toPython(),
                    nota=self.nota.text(),
                )
            ),
        ):
            self.nota.clear()
