from datetime import date
from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook

from predictor.cartelera import Analisis, FilaComparacion
from predictor.estadisticas import calcular
from predictor.exportar import (
    COLUMNAS_APUESTAS,
    COLUMNAS_MOVIMIENTOS,
    exportar_excel,
    tabla_cara_a_cara,
    tabla_cuotas,
    tabla_estadisticas,
)
from predictor.modelos import Estado, Mercado, Movimiento, ResultadoHistorico, TipoMovimiento


def _abrir(bitacora):
    contenido = exportar_excel(bitacora.apuestas(), bitacora.movimientos(), bitacora.resumen())
    return load_workbook(BytesIO(contenido))


def _filas(hoja):
    return list(hoja.iter_rows(values_only=True))


def test_exporta_tres_hojas(bitacora):
    libro = _abrir(bitacora)

    assert libro.sheetnames == ["Apuestas", "Movimientos", "Resumen"]


def test_exporta_vacio_con_encabezados(bitacora):
    libro = _abrir(bitacora)

    assert _filas(libro["Apuestas"]) == [tuple(COLUMNAS_APUESTAS.values())]
    assert _filas(libro["Movimientos"]) == [tuple(COLUMNAS_MOVIMIENTOS.values())]


def test_exporta_apuestas_y_movimientos(bitacora, crear_apuesta):
    apuesta = bitacora.registrar_apuesta(crear_apuesta(monto=1000))
    bitacora.registrar_apuesta(crear_apuesta(monto=500, colocada=False))
    bitacora.liquidar(apuesta.id, Estado.GANADA)
    bitacora.registrar_movimiento(Movimiento(tipo=TipoMovimiento.DEPOSITO, monto=3_000))

    libro = _abrir(bitacora)
    apuestas = _filas(libro["Apuestas"])
    encabezados = apuestas[0]
    primera = dict(zip(encabezados, apuestas[1], strict=True))

    assert len(apuestas) == 3
    assert primera["Partido"] == "Lakers vs Celtics"
    assert primera["Cuota"] == 1.85
    assert primera["Monto (CLP)"] == 1000
    assert primera["Estado"] == "ganada"
    assert primera["Resultado neto (CLP)"] == 850
    assert primera["Colocada"] == "Sí"
    assert len(_filas(libro["Movimientos"])) == 2


def test_resumen_incluye_saldo_y_desglose(bitacora, crear_apuesta):
    apuesta = bitacora.registrar_apuesta(crear_apuesta(monto=1000))
    bitacora.liquidar(apuesta.id, Estado.PERDIDA)

    filas = _filas(_abrir(bitacora)["Resumen"])
    valores = {fila[0]: fila[1] for fila in filas if fila[0]}

    assert valores["Saldo actual (CLP)"] == 9_000
    assert valores["ROI (%)"] == -100
    assert any(fila[0] == "NBA" for fila in filas)


def _fila(mercado, seleccion, linea=None, betano="1.9"):
    return FilaComparacion(
        mercado=mercado,
        seleccion=seleccion,
        linea=Decimal(linea) if linea else None,
        betano=Decimal(betano) if betano else None,
        pinnacle=Decimal("2.0"),
        mejor=Decimal("2.1"),
        casa_mejor="Betfair",
        promedio=Decimal("1.95"),
        casas=5,
    )


def test_tabla_cuotas_traduce_empate_y_formatea_lineas():
    tabla = tabla_cuotas(
        [
            _fila(Mercado.GANADOR, "Draw"),
            _fila(Mercado.TOTALES, "Over", "2.5", betano=None),
            _fila(Mercado.HANDICAP, "Arsenal", "0.75"),
        ]
    )

    assert list(tabla["Mercado"]) == ["Ganador", "Over/Under", "Hándicap"]
    assert list(tabla["Selección"]) == ["Empate", "Over", "Arsenal"]
    assert list(tabla["Línea"]) == ["", "2.5", "+0.75"]
    assert tabla["Betano"].isna().tolist() == [False, True, False]
    assert tabla.loc[0, "Mejor"] == 2.1


def test_tabla_estadisticas_lado_a_lado():
    historial = [
        ResultadoHistorico(
            "Premier League",
            "2627",
            date(2026, 9, 1),
            "Arsenal",
            "Everton",
            2,
            1,
            {"tiros": (12.0, 5.0)},
        )
    ]
    analisis = Analisis(calcular("Arsenal", historial), None, historial)

    tabla = tabla_estadisticas(analisis, "Arsenal", "Leeds United")

    assert list(tabla.columns) == ["Concepto", "Arsenal", "Leeds United"]
    fila = dict(zip(tabla["Concepto"], tabla["Arsenal"], strict=True))
    assert fila["G-E-P"] == "1-0-0"
    assert fila["Anota / recibe"] == "2 / 1 (1 PJ)"
    assert fila["Como local · como visita"] == "2 / 1 (1 PJ) · —"
    assert fila["Tiros"] == "12 / 5"
    assert tabla["Leeds United"].iloc[0] == "Sin datos"
    assert list(tabla_cara_a_cara(historial).iloc[0]) == [
        "2026-09-01",
        "Arsenal",
        "2 - 1",
        "Everton",
        "2627",
    ]
