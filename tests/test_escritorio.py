"""Pruebas de la aplicación de escritorio: se maneja la ventana real, sin red ni clave."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # antes de importar PySide6

from datetime import UTC, date, datetime, timedelta  # noqa: E402
from decimal import Decimal  # noqa: E402

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QPushButton  # noqa: E402

from predictor.cartelera import Cartelera  # noqa: E402
from predictor.escritorio import iconos, tema  # noqa: E402
from predictor.escritorio.comun import Contexto, clp, pct, ruta_bd  # noqa: E402
from predictor.escritorio.ventana import Ventana  # noqa: E402
from predictor.escritorio.widgets import Tabla, color_celda, formatear  # noqa: E402
from predictor.ligas import CASA_BASE, CASA_REFERENCIA, ZONA_CHILE  # noqa: E402
from predictor.modelos import (  # noqa: E402
    Apuesta,
    Cuota,
    Deporte,
    Estado,
    Ganador,
    Mercado,
    Partido,
    Prediccion,
    TipoMovimiento,
    Valor,
)
from predictor.repositorio import Repositorio  # noqa: E402
from predictor.valor import Umbrales  # noqa: E402

AHORA = datetime.now(UTC).replace(microsecond=0)
PARTIDO = Partido(
    "p1", Deporte.FUTBOL, "Premier League", "Arsenal", "Chelsea", AHORA + timedelta(minutes=30)
)


def _sin_jugadores(liga, dia):
    raise ValueError("sin red")


@pytest.fixture
def contexto(tmp_path):
    ruta = tmp_path / "bitacora.db"
    repo = Repositorio(ruta)
    precios = {CASA_BASE: ("2.40", "3.40", "3.20"), CASA_REFERENCIA: ("2.10", "3.50", "3.80")}
    cuotas = [
        Cuota("p1", casa, Mercado.GANADOR, seleccion, cuota, AHORA)
        for casa, valores in precios.items()
        for seleccion, cuota in zip(("Arsenal", "Draw", "Chelsea"), valores, strict=True)
    ]
    repo.reemplazar_cartelera("Premier League", [PARTIDO], cuotas)
    cartelera = Cartelera(
        repo,
        None,
        descargar_futbol=lambda liga, temporada: [],
        descargar_nba=lambda temporada: [],
        descargar_jugadores=_sin_jugadores,
        descargar_bpi=lambda dia: [],
    )
    yield Contexto(repo, cartelera, ruta)
    repo.cerrar()


@pytest.fixture
def ventana(qtbot, contexto):
    tema.aplicar(QApplication.instance())
    ventana = Ventana(contexto)
    qtbot.addWidget(ventana)
    dia = PARTIDO.inicio.astimezone(ZONA_CHILE).date()  # cerca de medianoche puede ser mañana
    ventana.partidos.dia.setDate(QDate(dia.year, dia.month, dia.day))
    return ventana


def _apuesta(**cambios) -> Apuesta:
    datos = {
        "deporte": Deporte.NBA,
        "liga": "NBA",
        "partido": "Lakers vs Celtics",
        "mercado": "Ganador",
        "seleccion": "Lakers",
        "cuota": Decimal("1.85"),
        "monto": 1000,
        "fecha_evento": date.today(),
    }
    datos.update(cambios)
    return Apuesta(**datos)


def _prediccion() -> Prediccion:
    return Prediccion(
        "p1",
        "Premier League",
        "Arsenal",
        "Chelsea",
        PARTIDO.inicio,
        "poisson-1",
        AHORA,
        1.6,
        1.1,
        0.48,
        0.27,
        0.25,
        marcador_probable="1-1",
        factores=["Arsenal gana el 70 % en casa"],
    )


def _textos(widget) -> list[str]:
    return [etiqueta.text() for etiqueta in widget.findChildren(QLabel)]


def test_todas_las_paginas_cargan(ventana):
    for fila in range(ventana.navegacion.count()):
        ventana.navegacion.setCurrentRow(fila)
        assert ventana.pila.currentIndex() == fila
        assert not ventana.pagina_actual.sucia
        assert not ventana.navegacion.item(fila).icon().isNull()
    assert ventana.navegacion.item(0).text() == "Partidos"  # sin emojis: el ícono va aparte
    assert ventana.saldo.valor.text() == "$10.000"


@pytest.mark.parametrize("nombre", [n for n in iconos.NOMBRES if n != "vacio"])
def test_cada_icono_dibuja_algo(qtbot, nombre):
    imagen = iconos.pixmap(nombre, tema.TEXTO).toImage()
    assert imagen.width() == 18 * iconos.ESCALA
    assert any(
        imagen.pixelColor(x, y).alpha() > 0
        for x in range(imagen.width())
        for y in range(imagen.height())
    )


def test_el_logo_es_el_icono_de_la_ventana(ventana):
    assert not ventana.windowIcon().isNull()
    assert {t.width() for t in iconos.logo().availableSizes()} >= {16, 32, 256}


def test_un_icono_se_tine_con_el_color_pedido(qtbot):
    imagen = iconos.pixmap("partidos", tema.ACENTO).toImage()
    pintados = [
        imagen.pixelColor(x, y)
        for x in range(imagen.width())
        for y in range(imagen.height())
        if imagen.pixelColor(x, y).alpha() == 255
    ]
    assert pintados and all(c.name() == tema.ACENTO for c in pintados)


def test_falta_un_recurso(qtbot, tmp_path):
    with pytest.raises(FileNotFoundError, match="Falta el recurso"):
        iconos._imagen(tmp_path / "no_existe.png")


def test_lista_partidos_y_muestra_el_detalle(ventana):
    partidos = ventana.partidos
    assert partidos.lista.count() == 2
    assert partidos.lista.item(0).text().startswith("Valor del día")
    assert partidos.detalle.partido is None  # arranca en "Valor del día"

    assert not partidos.lista.item(0).icon().isNull()  # estrella dibujada, no un emoji
    partidos.lista.setCurrentRow(1)
    assert partidos.detalle.partido.id == "p1"
    assert len(partidos.detalle.grupo_ganador.buttons()) == 3
    assert "Falta la clave" in partidos.avisos.itemAt(0).widget().text()


def test_el_detalle_muestra_la_prediccion_del_modelo(ventana, monkeypatch):
    monkeypatch.setattr(ventana.contexto.cartelera, "predecir", lambda partido: _prediccion())
    ventana.partidos.lista.setCurrentRow(1)

    textos = _textos(ventana.partidos.detalle)
    assert "48.0%" in textos
    assert "•  Arsenal gana el 70 % en casa" in textos
    assert "Más probable: 1-1" in textos


def test_el_filtro_sin_partidos_lo_avisa(ventana):
    ventana.partidos.ligas.setCurrentText("NBA")
    assert ventana.partidos.lista.count() == 0
    assert ventana.partidos.detalle.partido is None
    assert any("falta la clave de The Odds API" in t for t in _textos(ventana.partidos.detalle))


def test_las_horas_se_mantienen_validas(ventana):
    partidos = ventana.partidos
    partidos.desde.setValue(23)
    assert partidos.hasta.value() == 24
    partidos.hasta.setValue(5)
    assert partidos.desde.value() < partidos.hasta.value()


def test_registra_una_apuesta_desde_la_cartelera(ventana, contexto):
    ventana.partidos.lista.setCurrentRow(1)
    [apostar] = [
        b
        for b in ventana.partidos.detalle.findChildren(QPushButton)
        if b.text() == "Apostar en este partido"
    ]
    apostar.click()
    nueva = ventana.nueva
    assert ventana.pagina_actual is nueva
    assert nueva.partido.text() == "Arsenal vs Chelsea"
    assert nueva.cuota.value() == pytest.approx(2.40)
    assert not nueva.deporte.isEnabled()

    nueva.registrar.click()

    [apuesta] = contexto.bitacora.apuestas()
    assert apuesta.liga == "Premier League"
    assert apuesta.cuota == Decimal("2.40")
    assert isinstance(apuesta.valor, Valor)
    assert ventana.banner.text() == "Apuesta registrada"
    assert nueva.partido.text() == ""


def test_registra_una_apuesta_a_mano(ventana, contexto):
    ventana.ir_a("Nueva apuesta")
    nueva = ventana.nueva
    nueva.deporte.setCurrentIndex(list(Deporte).index(Deporte.FUTBOL))
    nueva.liga.setCurrentText("LaLiga")
    nueva.partido.setText("Betis vs Sevilla")
    nueva.mercado.setText("Ganador")
    nueva.seleccion.setText("Betis")
    nueva.colocada.setChecked(False)
    nueva.registrar.click()

    [apuesta] = contexto.bitacora.apuestas()
    assert (apuesta.liga, apuesta.prob_modelo, apuesta.colocada) == ("LaLiga", None, False)


def test_un_error_de_validacion_se_muestra_en_el_aviso(ventana, contexto):
    ventana.ir_a("Nueva apuesta")
    ventana.nueva.registrar.click()  # sin partido ni mercado

    assert contexto.bitacora.apuestas() == []
    assert ventana.banner.isVisibleTo(ventana)
    assert ventana.banner.property("error") == "true"


def test_liquida_revierte_y_elimina(ventana, contexto):
    contexto.bitacora.registrar_apuesta(_apuesta())
    contexto.cambiado.emit()
    ventana.ir_a("Pendientes")
    marco = ventana.pagina_actual.lista.itemAt(0).widget()
    marco.estado.setCurrentIndex(marco.estado.findData(Estado.GANADA))
    marco.ajustar.setChecked(True)
    marco.neto.setValue(840)
    marco.liquidar.click()
    [apuesta] = contexto.bitacora.apuestas()
    assert apuesta.estado is Estado.GANADA
    assert ventana.saldo.valor.text() == clp(10_840)

    ventana.ir_a("Historial")
    historial = ventana.pagina_actual
    assert historial.tabla.modelo.rowCount() == 1
    historial.estado.setCurrentIndex(historial.estado.findData(Estado.PERDIDA))
    assert historial.tabla.modelo.rowCount() == 0
    historial.estado.setCurrentIndex(0)
    assert not historial.eliminar.isEnabled()
    historial.revertir.click()
    assert contexto.bitacora.apuestas()[0].estado is Estado.PENDIENTE

    historial.confirmar.setChecked(True)
    historial.eliminar.click()
    assert contexto.bitacora.apuestas() == []


def test_registra_movimientos_y_el_fondo_inicial(ventana, contexto):
    ventana.ir_a("Movimientos")
    movimientos = ventana.pagina_actual
    movimientos.tipo.setCurrentIndex(movimientos.tipo.findData(TipoMovimiento.DEPOSITO))
    movimientos.monto.setValue(5000)
    movimientos.registrar.click()
    assert movimientos.tabla.modelo.rowCount() == 1
    assert ventana.saldo.valor.text() == "$15.000"

    ventana.ir_a("Configuración")
    configuracion = ventana.pagina_actual
    configuracion.fondo.setValue(20_000)
    configuracion.guardar_fondo.click()
    assert contexto.bitacora.fondo_inicial == 20_000
    assert "no configurada" in configuracion.info_clave.text()


def test_guarda_los_umbrales(ventana, contexto):
    ventana.ir_a("Configuración")
    configuracion = ventana.pagina_actual
    configuracion.ev_modelo.setValue(5.0)
    configuracion.cuota_maxima.setValue(3.0)
    configuracion.ev_mercado.setValue(0.0)
    configuracion.guardar_umbrales.click()

    assert contexto.cartelera.umbrales == Umbrales(0.05, 3.0, 0.0)


def test_guarda_mi_prediccion(ventana, contexto):
    ventana.partidos.lista.setCurrentRow(1)
    detalle = ventana.partidos.detalle
    visita = next(
        b for b in detalle.grupo_ganador.buttons() if b.property("ganador") == "visitante"
    )
    visita.setChecked(True)
    detalle.con_marcador.setChecked(True)
    detalle.goles_local.setValue(0)
    detalle.goles_visitante.setValue(2)
    detalle.nota.setText("Chelsea llega mejor")
    detalle.guardar.click()

    propia = contexto.cartelera.prediccion_propia(PARTIDO)
    assert propia.ganador is Ganador.VISITANTE
    assert (propia.marcador_local, propia.marcador_visitante) == (0, 2)
    assert detalle.nota.text() == "Chelsea llega mejor"  # se volvió a dibujar con lo guardado


def test_un_marcador_incoherente_no_se_guarda(ventana, contexto):
    ventana.partidos.lista.setCurrentRow(1)
    detalle = ventana.partidos.detalle
    detalle.con_marcador.setChecked(True)
    detalle.goles_local.setValue(0)
    detalle.goles_visitante.setValue(2)  # gana la visita, pero está marcado el local
    detalle.guardar.click()

    assert contexto.cartelera.prediccion_propia(PARTIDO) is None
    assert ventana.banner.property("error") == "true"


def test_actualizar_descarga_en_segundo_plano(ventana, qtbot):
    partidos = ventana.partidos
    with qtbot.waitSignal(partidos.ocupada, timeout=10_000):
        partidos.boton_actualizar.click()
    qtbot.waitUntil(lambda: partidos.boton_actualizar.isEnabled(), timeout=10_000)

    assert ventana.navegacion.isEnabled()
    assert ventana.banner.text() == "Partidos actualizados"
    textos = [partidos.avisos.itemAt(i).widget().text() for i in range(partidos.avisos.count())]
    assert "No se pudieron actualizar los jugadores de Premier League: sin red" in textos


def test_mientras_descarga_se_bloquea_la_navegacion(ventana):
    ventana._ocupada(True)
    assert not ventana.navegacion.isEnabled()
    assert not ventana.exportar.isEnabled()
    ventana._ocupada(False)
    assert ventana.navegacion.isEnabled()


def test_un_fallo_al_actualizar_se_avisa(ventana, qtbot, monkeypatch):
    def fallar(ligas, forzar=False):
        raise RuntimeError("caída")

    monkeypatch.setattr(ventana.contexto.cartelera, "actualizar_historial", fallar)
    ventana.partidos.boton_actualizar.click()
    qtbot.waitUntil(lambda: ventana.partidos.boton_actualizar.isEnabled(), timeout=10_000)

    assert ventana.banner.text() == "No se pudo actualizar: caída"


def test_calcula_el_backtest(ventana, qtbot):
    ventana.ir_a("Modelo")
    modelo = ventana.pagina_actual
    assert modelo.sin_evaluadas.isVisibleTo(modelo)
    modelo.calcular.click()
    qtbot.waitUntil(lambda: modelo.calcular.isEnabled(), timeout=10_000)

    assert modelo.backtest.isVisibleTo(modelo)
    assert "no tiene cuotas" in modelo.nota_valor.text()


def test_un_fallo_del_backtest_se_avisa(ventana, qtbot, monkeypatch):
    def fallar(ligas):
        raise RuntimeError("sin historial")

    monkeypatch.setattr(ventana.contexto.cartelera, "backtest", fallar)
    ventana.ir_a("Modelo")
    ventana.pagina_actual.calcular.click()
    qtbot.waitUntil(lambda: ventana.pagina_actual.calcular.isEnabled(), timeout=10_000)

    assert ventana.banner.text() == "No se pudo calcular el backtest: sin historial"


def test_exporta_a_excel(ventana, contexto, tmp_path, monkeypatch):
    contexto.bitacora.registrar_apuesta(_apuesta())
    destino = tmp_path / "bitacora.xlsx"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), ""))
    ventana.exportar.click()

    assert destino.read_bytes()[:2] == b"PK"  # un .xlsx es un zip
    assert ventana.banner.text() == f"Excel guardado en {destino}"


def test_exportar_cancelado_o_fallido(ventana, tmp_path, monkeypatch):
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    ventana.exportar.click()
    assert not ventana.banner.isVisibleTo(ventana)

    carpeta = tmp_path / "carpeta"
    carpeta.mkdir()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(carpeta), ""))
    ventana.exportar.click()
    assert ventana.banner.text().startswith("No se pudo guardar el Excel")


def test_el_contexto_se_arma_desde_el_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("PREDICTOR_DB", str(tmp_path / "datos" / "bitacora.db"))
    monkeypatch.setenv("ODDS_API_KEY", "clave-de-prueba")
    contexto = Contexto.desde_entorno()
    try:
        assert contexto.ruta == ruta_bd()
        assert contexto.cartelera.tiene_clave
    finally:
        contexto.repo.cerrar()


@pytest.mark.parametrize(
    ("columna", "valor", "esperado"),
    [
        ("Monto (CLP)", 12500, "$12.500"),
        ("Apuestas", 1200, "1.200"),
        ("ROI (%)", 12.345, "12.3 %"),
        ("Brier", 0.21234, "0.212"),
        ("Cuota", 2.4, "2.40"),
        ("Colocada", True, "Sí"),
        ("Colocada", False, "No"),
        ("EV (%)", None, "—"),
        ("EV (%)", float("nan"), "—"),
        ("Partido", "Arsenal vs Chelsea", "Arsenal vs Chelsea"),
    ],
)
def test_formatear(columna, valor, esperado):
    assert formatear(columna, valor) == esperado


def test_color_celda():
    assert color_celda("Valor", "Confirmado") == tema.VERDE
    assert color_celda("Estado", "perdida") == tema.ROJO
    assert color_celda("Resultado (CLP)", 500) == tema.VERDE
    assert color_celda("ROI (%)", -3.0) == tema.ROJO
    assert color_celda("ROI (%)", 0) is None
    assert color_celda("Cuota", 2.4) is None
    assert color_celda("Colocada", True) is None
    assert color_celda("EV (%)", float("nan")) is None


def test_la_tabla_formatea_y_colorea(qtbot):
    tabla = Tabla()
    qtbot.addWidget(tabla)
    tabla.fijar(pd.DataFrame({"Partido": ["A vs B"], "Resultado (CLP)": [-500]}))
    modelo = tabla.modelo
    celda = modelo.index(0, 1)
    assert modelo.data(celda) == "-$500"
    assert modelo.data(celda, Qt.ItemDataRole.ForegroundRole).name() == tema.ROJO
    assert modelo.data(celda, Qt.ItemDataRole.TextAlignmentRole) is not None
    assert modelo.data(modelo.index(0, 0), Qt.ItemDataRole.TextAlignmentRole) is None
    assert modelo.data(modelo.index(5, 5)) is None
    assert modelo.headerData(1, Qt.Orientation.Horizontal) == "Resultado (CLP)"
    assert modelo.headerData(0, Qt.Orientation.Vertical) is None


def test_formatos_comunes():
    assert clp(-1500) == "-$1.500"
    assert pct(None) == "—"
    assert pct(0.5) == "50.0%"


def test_valor_del_dia_muestra_las_apuestas_sugeridas(ventana):
    from predictor.cartelera import FilaComparacion, Sugerencia
    from predictor.valor import Valoracion

    detalle = ventana.partidos.detalle
    assert any(t.startswith("Apuestas sugeridas") for t in _textos(detalle))

    detalle.mostrar_valor_del_dia([], [])
    assert "Ningún partido por empezar tiene una apuesta de 55% o más." in _textos(detalle)
    assert not detalle.findChildren(Tabla)

    fila = FilaComparacion(
        Mercado.GANADOR, "Arsenal", None, Decimal("1.80"), Decimal("1.75"),
        Decimal("1.80"), CASA_BASE, Decimal("1.78"), 2,
    )  # fmt: skip
    sugerencia = Sugerencia(PARTIDO, Valoracion(fila, 0.6, 0.56, None, Valor.NINGUNO), 0.58)
    detalle.mostrar_valor_del_dia([], [sugerencia])
    assert "Apuestas sugeridas  (1)" in _textos(detalle)
    assert "Si apuestas todas, arriesgas 1.0% de la banca hoy." in _textos(detalle)
    tabla = detalle.findChildren(Tabla)[0]
    assert tabla.model().rowCount() == 1
