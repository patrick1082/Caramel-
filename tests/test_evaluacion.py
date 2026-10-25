import random
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from predictor.evaluacion import (
    BASE,
    PROPIA,
    TOTAL,
    Evaluada,
    LineaBase,
    MetricasFuente,
    ResultadoValor,
    backtest,
    backtest_valor,
    cruzar,
    por_fuente,
    por_liga,
)
from predictor.ligas import ZONA_CHILE
from predictor.modelos import (
    Fuente,
    Ganador,
    Mercado,
    Prediccion,
    PrediccionPropia,
    ProbabilidadLinea,
    Pronostico3,
    ResultadoHistorico,
)
from predictor.valor import Umbrales


def _resultado(dia, local, visitante, goles_local, goles_visita, liga="Premier League"):
    return ResultadoHistorico(liga, "2627", dia, local, visitante, goles_local, goles_visita)


def _prediccion(dia, local, visitante, probs, esperados=(1.5, 1.0), linea=None, over=None):
    lineas = []
    if linea is not None:
        lineas = [
            ProbabilidadLinea(Mercado.TOTALES, "Over", linea, over),
            ProbabilidadLinea(Mercado.TOTALES, "Under", linea, 1 - over),
        ]
    inicio = datetime.combine(dia, datetime.min.time(), ZONA_CHILE).replace(hour=21)
    return Prediccion(
        partido_id=f"{local}-{visitante}",
        liga="Premier League",
        local=local,
        visitante=visitante,
        inicio=inicio,
        modelo="poisson-1",
        creada=inicio,
        esperado_local=esperados[0],
        esperado_visitante=esperados[1],
        prob_local=probs[0],
        prob_empate=probs[1],
        prob_visitante=probs[2],
        lineas=lineas,
        linea_total=linea,
    )


DIA = date(2026, 10, 20)
HISTORIAL = [
    _resultado(DIA - timedelta(days=7), "Arsenal", "Chelsea", 2, 0),
    _resultado(DIA - timedelta(days=7), "Everton", "Fulham", 1, 1),
    _resultado(DIA - timedelta(days=7), "Brentford", "Burnley", 0, 1),
    _resultado(DIA - timedelta(days=7), "Leeds", "Wolves", 3, 1),
    # Estos partidos se jugaron el día siguiente (hora de Europa) al inicio en Chile.
    _resultado(DIA + timedelta(days=1), "Man City", "Aston Villa", 3, 1),
    _resultado(DIA + timedelta(days=1), "Liverpool", "Tottenham", 1, 1),
]


def test_cruza_por_fecha_cercana_y_nombres():
    predicciones = [
        _prediccion(DIA, "Manchester City", "Aston Villa", (0.6, 0.25, 0.15)),
        _prediccion(DIA, "Liverpool", "Tottenham Hotspur", (0.5, 0.3, 0.2)),
        _prediccion(DIA, "Arsenal", "Chelsea", (0.5, 0.3, 0.2)),  # se jugó hace una semana
    ]

    evaluadas = cruzar(predicciones, HISTORIAL)

    assert [(e.resultado.local, e.resultado.visitante) for e in evaluadas] == [
        ("Man City", "Aston Villa"),
        ("Liverpool", "Tottenham"),
    ]
    # La línea base solo usa los 4 partidos anteriores: 2 locales, 1 empate, 1 visita.
    assert evaluadas[0].base == pytest.approx((0.5, 0.25, 0.25))
    assert evaluadas[1].base == pytest.approx((0.5, 0.25, 0.25))


def test_metricas_acierto_brier_error_y_linea():
    evaluadas = cruzar(
        [
            _prediccion(DIA, "Man City", "Aston Villa", (0.6, 0.25, 0.15), (2.5, 1.0), 2.5, 0.7),
            _prediccion(DIA, "Liverpool", "Tottenham", (0.5, 0.3, 0.2), (2.0, 1.0), 2.5, 0.6),
        ],
        HISTORIAL,
    )

    metricas = por_liga(evaluadas)

    assert list(metricas) == ["Premier League", TOTAL]
    total = metricas[TOTAL]
    assert total.partidos == 2
    assert total.acierto == 0.5  # gana el City (acierto); empate en Anfield (fallo)
    brier_city = 0.4**2 + 0.25**2 + 0.15**2
    brier_liverpool = 0.5**2 + 0.7**2 + 0.2**2
    assert total.brier == pytest.approx((brier_city + brier_liverpool) / 2)
    assert total.error_medio == pytest.approx(((0.5 + 0) / 2 + (1 + 0) / 2) / 2)
    assert total.lineas == 2 and total.acierto_over_under == 0.5  # 4 goles: Over; 2: Under
    assert total.acierto_base == 0.5  # la base siempre elige al local
    gana_local = 0.5**2 + 0.25**2 + 0.25**2
    empate = 0.5**2 + 0.75**2 + 0.25**2
    assert total.brier_base == pytest.approx((gana_local + empate) / 2)


def test_metricas_vacias_y_linea_empatada():
    vacias = por_liga([])[TOTAL]
    assert vacias.partidos == 0 and vacias.acierto is None and vacias.brier is None
    assert vacias.acierto_over_under is None and vacias.brier_base is None

    [evaluada] = cruzar(
        [_prediccion(DIA, "Liverpool", "Tottenham Hotspur", (0.5, 0.3, 0.2), linea=2.0, over=0.6)],
        HISTORIAL,
    )
    assert evaluada.acierto_linea is None  # 2 goles en línea 2: devolución


def test_linea_base_nba_sin_empate():
    historial = [
        _resultado(DIA, "Lakers", "Celtics", 110, 100, liga="NBA"),
        _resultado(DIA + timedelta(days=1), "Celtics", "Lakers", 100, 105, liga="NBA"),
    ]
    base = LineaBase(historial)

    assert base.probabilidades("NBA", DIA) == (0.5, None, 0.5)
    assert base.probabilidades("NBA", DIA + timedelta(days=5)) == (0.5, None, 0.5)
    assert base.probabilidades("Premier League", DIA) == pytest.approx((1 / 3,) * 3)


def _temporada(equipos=8, jornadas=30, semilla=3):
    """El primer equipo es muy superior; cada jornada tiene su propia fecha."""
    azar = random.Random(semilla)
    nombres = [f"E{i}" for i in range(equipos)]
    filas = []
    for jornada in range(jornadas):
        orden = azar.sample(nombres, equipos)
        dia = date(2025, 8, 1) + timedelta(days=7 * jornada)
        for local, visita in zip(orden[::2], orden[1::2], strict=True):
            goles_local = azar.choices(range(5), weights=(3, 4, 3, 2, 1))[0]
            goles_visita = azar.choices(range(5), weights=(4, 4, 2, 1, 1))[0]
            goles_local += 2 if local == "E0" else 0
            goles_visita += 2 if visita == "E0" else 0
            filas.append(_resultado(dia, local, visita, goles_local, goles_visita))
    return filas


def test_backtest_solo_usa_el_pasado_y_supera_a_la_base():
    historial = _temporada()
    desde = date(2025, 8, 1) + timedelta(days=7 * 10)

    evaluadas = backtest("Premier League", historial, desde=desde, minimo=20)

    assert evaluadas and all(e.resultado.fecha >= desde for e in evaluadas)
    assert len(evaluadas) == 4 * 20
    # Agregar un resultado futuro absurdo no cambia la predicción de la primera jornada.
    primera = [e for e in evaluadas if e.resultado.fecha == desde]
    alterado = backtest(
        "Premier League",
        [*historial, _resultado(date(2026, 6, 1), "E1", "E2", 9, 0)],
        desde=desde,
        minimo=20,
    )
    assert [e.prediccion for e in alterado[: len(primera)]] == [e.prediccion for e in primera]
    metricas = por_liga(evaluadas)[TOTAL]
    assert metricas.brier < metricas.brier_base


def test_backtest_espera_el_minimo_de_partidos():
    historial = _temporada(jornadas=3)

    assert backtest("Premier League", historial, minimo=100) == []
    assert {e.resultado.fecha for e in backtest("Premier League", historial, minimo=8)} == {
        date(2025, 8, 15)
    }


def test_por_fuente_mide_cada_opinion_sobre_los_partidos_jugados():
    evaluadas = cruzar(
        [
            _prediccion(DIA, "Man City", "Aston Villa", (0.6, 0.25, 0.15)),  # gana el local
            _prediccion(DIA, "Liverpool", "Tottenham", (0.5, 0.3, 0.2)),  # empate
        ],
        HISTORIAL,
    )
    momento = datetime(2026, 10, 1, tzinfo=ZONA_CHILE)
    pronosticos = [
        Pronostico3("Man City-Aston Villa", Fuente.ESPN, 0.3, 0.4, 0.3, momento),
        Pronostico3("Liverpool-Tottenham", Fuente.MERCADO, 0.4, 0.35, 0.25, momento),
        Pronostico3("Liverpool-Tottenham", Fuente.MODELO, 0.1, 0.1, 0.8, momento),  # ignorado
        Pronostico3("Sin-Resultado", Fuente.ESPN, 0.5, 0.2, 0.3, momento),
    ]

    def propia(partido_id, dia, local, visitante, ganador):
        inicio = datetime.combine(dia, datetime.min.time(), ZONA_CHILE).replace(hour=12)
        return PrediccionPropia(
            partido_id, "Premier League", local, visitante, inicio, ganador, momento
        )

    propias = [
        propia("Liverpool-Tottenham", DIA, "Liverpool", "Tottenham", Ganador.EMPATE),
        # Sin predicción del modelo: se cruza por equipos y fecha.
        propia("x", DIA - timedelta(days=7), "Everton", "Fulham", Ganador.LOCAL),
        propia("y", DIA, "Arsenal", "Chelsea", Ganador.LOCAL),  # sin resultado ese día
        propia("z", DIA, "Man City", "Fulham", Ganador.LOCAL),  # otro visitante
    ]

    metricas = por_fuente(evaluadas, pronosticos, propias, HISTORIAL)

    assert list(metricas) == [PROPIA, "Modelo", "ESPN BPI", "Mercado", BASE]
    assert (metricas[PROPIA].partidos, metricas[PROPIA].acierto) == (2, 0.5)
    assert metricas[PROPIA].brier is None
    assert (metricas["Modelo"].acierto, metricas["Modelo"].brier) == (0.5, pytest.approx(0.5125))
    assert (metricas["ESPN BPI"].partidos, metricas["ESPN BPI"].acierto) == (1, 0)
    assert metricas["ESPN BPI"].brier == pytest.approx(0.74)
    assert (metricas["Mercado"].acierto, metricas["Mercado"].brier) == (0, pytest.approx(0.645))
    assert (metricas[BASE].partidos, metricas[BASE].acierto) == (2, 0.5)
    assert por_fuente([], [], [], []) == {}
    assert MetricasFuente().acierto is None and MetricasFuente().brier is None


def _evaluada(local, visitante, goles, probs, cuotas, liga="Premier League"):
    resultado = replace(_resultado(DIA, local, visitante, *goles, liga=liga), cuotas=cuotas)
    prediccion = replace(_prediccion(DIA, local, visitante, probs), liga=liga)
    return Evaluada(prediccion, resultado, (0.45, 0.25, 0.3))


EVALUADAS_CON_CUOTAS = [
    # EV máximo 0 (empate): no se apuesta. El favorito (local, 1.5) gana.
    _evaluada("Man City", "Aston Villa", (3, 1), (0.6, 0.25, 0.15), (1.5, 4.0, 6.0)),
    # Empate con EV 0.225: se apuesta y gana 2.5. El favorito pierde.
    _evaluada("Liverpool", "Tottenham", (1, 1), (0.45, 0.35, 0.2), (2.0, 3.5, 4.0)),
    # Local con EV 0.5 a cuota 3.0: gana 2. El favorito (visita, 2.5) pierde.
    _evaluada("Arsenal", "Chelsea", (2, 0), (0.5, 0.3, 0.2), (3.0, 3.4, 2.5)),
    _evaluada("Everton", "Fulham", (1, 0), (0.9, 0.05, 0.05), None),  # sin cuotas: no cuenta
    # Local con EV 0.26: pierde. El favorito también.
    _evaluada("Inter", "Milan", (0, 1), (0.7, 0.2, 0.1), (1.8, 3.6, 4.5), liga="Serie A"),
]


def test_backtest_valor_apuesta_al_mayor_ev_y_compara_con_el_favorito():
    resultados = backtest_valor(EVALUADAS_CON_CUOTAS)

    assert list(resultados) == ["Premier League", "Serie A", TOTAL]
    total = resultados[TOTAL]
    assert (total.partidos, total.apuestas, total.aciertos) == (4, 3, 2)
    assert total.ganancia == pytest.approx(3.5) and total.roi == pytest.approx(3.5 / 3)
    assert total.acierto == pytest.approx(2 / 3)
    assert total.ganancia_favorito == pytest.approx(-2.5)
    assert total.roi_favorito == pytest.approx(-2.5 / 4)
    premier, serie_a = resultados["Premier League"], resultados["Serie A"]
    assert (premier.partidos, premier.apuestas, premier.ganancia) == (3, 2, pytest.approx(4.5))
    assert (serie_a.apuestas, serie_a.aciertos, serie_a.ganancia) == (1, 0, -1)


def test_backtest_valor_respeta_los_umbrales():
    # Con cuota máxima 2.9 se descartan el empate a 3.5 y el local a 3.0 (lo que queda no llega).
    resultados = backtest_valor(EVALUADAS_CON_CUOTAS, Umbrales(cuota_maxima=2.9))

    assert (resultados[TOTAL].apuestas, resultados[TOTAL].ganancia) == (1, -1)
    assert resultados["Premier League"].roi is None
    assert resultados["Premier League"].acierto is None
    assert backtest_valor([]) == {} and ResultadoValor().roi_favorito is None
