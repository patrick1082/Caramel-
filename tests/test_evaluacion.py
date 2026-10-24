import random
from datetime import date, datetime, timedelta

import pytest

from predictor.evaluacion import TOTAL, LineaBase, backtest, cruzar, por_liga
from predictor.ligas import ZONA_CHILE
from predictor.modelos import Mercado, Prediccion, ProbabilidadLinea, ResultadoHistorico


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
