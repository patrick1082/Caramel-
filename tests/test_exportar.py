from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from openpyxl import load_workbook

from predictor.cartelera import Analisis, FilaComparacion
from predictor.estadisticas import calcular
from predictor.evaluacion import TOTAL, cruzar, por_liga
from predictor.exportar import (
    COLUMNAS_APUESTAS,
    COLUMNAS_MOVIMIENTOS,
    COLUMNAS_PREDICCIONES,
    exportar_excel,
    tabla_cara_a_cara,
    tabla_cuotas,
    tabla_estadisticas,
    tabla_evaluacion,
    tabla_jugadores,
    tabla_predicciones,
)
from predictor.ligas import ZONA_CHILE
from predictor.modelos import (
    Estado,
    Jugador,
    Mercado,
    Movimiento,
    Prediccion,
    ProbabilidadLinea,
    ResultadoHistorico,
    Rol,
    TipoMovimiento,
)


def _abrir(bitacora):
    contenido = exportar_excel(bitacora.apuestas(), bitacora.movimientos(), bitacora.resumen())
    return load_workbook(BytesIO(contenido))


def _filas(hoja):
    return list(hoja.iter_rows(values_only=True))


def test_exporta_cuatro_hojas(bitacora):
    libro = _abrir(bitacora)

    assert libro.sheetnames == ["Apuestas", "Movimientos", "Resumen", "Predicciones"]
    assert _filas(libro["Predicciones"]) == [COLUMNAS_PREDICCIONES]


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


INICIO = datetime(2026, 10, 20, 16, 0, tzinfo=ZONA_CHILE)


def _prediccion(partido_id="p1", local="Arsenal", visitante="Everton"):
    return Prediccion(
        partido_id=partido_id,
        liga="Premier League",
        local=local,
        visitante=visitante,
        inicio=INICIO,
        modelo="poisson-1",
        creada=INICIO,
        esperado_local=1.8,
        esperado_visitante=0.9,
        prob_local=0.5,
        prob_empate=0.25,
        prob_visitante=0.25,
        marcador_probable="1-0",
        lineas=[
            ProbabilidadLinea(Mercado.TOTALES, "Over", 2.5, 0.48),
            ProbabilidadLinea(Mercado.TOTALES, "Under", 2.5, 0.52),
        ],
        linea_total=2.5,
    )


def test_tabla_cuotas_con_probabilidad_del_modelo_y_cuota_justa():
    tabla = tabla_cuotas(
        [
            _fila(Mercado.GANADOR, "Arsenal"),
            _fila(Mercado.GANADOR, "Draw"),
            _fila(Mercado.TOTALES, "Under", "2.5"),
            _fila(Mercado.HANDICAP, "Arsenal", "-1.5"),  # el modelo no la calculó
        ],
        _prediccion(),
    )

    assert tabla["Modelo (%)"].tolist()[:3] == [50.0, 25.0, 52.0]
    assert tabla["Cuota justa"].tolist()[:3] == [2.0, 4.0, 1.92]
    assert tabla[["Modelo (%)", "Cuota justa"]].iloc[3].isna().all()
    assert "Modelo (%)" not in tabla_cuotas([_fila(Mercado.GANADOR, "Arsenal")]).columns


def test_tabla_jugadores_de_ambos_equipos():
    tabla = tabla_jugadores(
        "Arsenal",
        [Jugador("Premier League", "Arsenal", "Saka", Rol.DESTACADO, "5 goles · 8 PJ", 5)],
        "Everton",
        [Jugador("Premier League", "Everton", "Pickford", Rol.LESIONADO, "Out · Knee")],
    )

    assert tabla.values.tolist() == [
        ["Arsenal", "Destacado", "Saka", "5 goles · 8 PJ"],
        ["Everton", "Lesionado", "Pickford", "Out · Knee"],
    ]


def test_tabla_evaluacion_y_predicciones():
    historial = [
        ResultadoHistorico("Premier League", "2627", INICIO.date(), "Arsenal", "Everton", 2, 1)
    ]
    pendiente = _prediccion("p2", "Chelsea", "Fulham")
    evaluadas = cruzar([_prediccion(), pendiente], historial)

    evaluacion = tabla_evaluacion(por_liga(evaluadas))
    predicciones = tabla_predicciones([_prediccion(), pendiente], evaluadas)

    assert evaluacion["Liga"].tolist() == ["Premier League", TOTAL]
    liga = evaluacion.iloc[0]
    assert liga["Partidos"] == 1 and liga["Acierto modelo (%)"] == 100.0
    assert liga["Brier modelo"] == round(0.5**2 + 0.25**2 + 0.25**2, 3)
    assert liga["Acierto over/under (%)"] == 0.0  # 3 goles, pero el modelo daba Under 52 %
    assert evaluacion["Error medio"].isna().tolist() == [False, True]
    primera = dict(zip(COLUMNAS_PREDICCIONES, predicciones.iloc[0], strict=True))
    assert primera["Inicio"] == "2026-10-20 16:00"
    assert primera["Esperado"] == "1.8 - 0.9" and primera["Over (%)"] == 48.0
    assert primera["Resultado"] == "2 - 1" and primera["Acierto"] == "Sí"
    assert predicciones.iloc[1]["Resultado"] == "" and predicciones.iloc[1]["Acierto"] == ""
