import random
from datetime import date, timedelta

import pytest

from predictor import prediccion
from predictor.modelos import Deporte, ResultadoHistorico
from predictor.prediccion import Discreta, Normal, ajustar, prob_linea

HOY = date(2026, 10, 23)


def _historial(*partidos, liga="Premier League", hasta=HOY):
    """Cada partido: (local, visitante, marcador local, marcador visita). El último es el más
    reciente y se jugó dos días antes de `hasta`."""
    n = len(partidos)
    return [
        ResultadoHistorico(liga, "2627", hasta - timedelta(days=2 + 3 * (n - 1 - i)), *p)
        for i, p in enumerate(partidos)
    ]


def _liga_pareja(equipos="ABCD", vueltas=3, goles=(1, 1)):
    """Todos contra todos con el mismo marcador: ningún equipo es mejor que otro."""
    return _historial(
        *[(a, b, *goles) for _ in range(vueltas) for a in equipos for b in equipos if a != b]
    )


def test_probabilidades_suman_uno_y_marcador_probable():
    historial = _liga_pareja() + _liga_pareja(goles=(2, 2))  # λ = 1.5 por equipo
    pronostico = ajustar(Deporte.FUTBOL, historial, HOY).pronosticar("A", "B")

    suma = pronostico.prob_local + pronostico.prob_empate + pronostico.prob_visitante
    assert suma == pytest.approx(1)
    assert sum(pronostico.total.probs.values()) == pytest.approx(1)
    assert pronostico.esperado_local == pytest.approx(1.5, abs=0.01)
    assert pronostico.marcador_probable == "1-1"
    assert pronostico.prob_over(2.5) + pronostico.prob_under(2.5) == pytest.approx(1)


def test_localia_favorece_al_local_entre_equipos_iguales():
    pronostico = ajustar(Deporte.FUTBOL, _liga_pareja(goles=(2, 1)), HOY).pronosticar("A", "B")

    assert pronostico.esperado_local > pronostico.esperado_visitante
    assert pronostico.prob_local > pronostico.prob_visitante


def test_mas_goles_a_favor_da_mas_lambda():
    historial = _liga_pareja() + _historial(*[("A", "C", 4, 0)] * 3, *[("D", "A", 0, 3)] * 3)

    ajuste = ajustar(Deporte.FUTBOL, historial, HOY)

    assert ajuste.ataque["A"] > ajuste.ataque["B"]
    assert ajuste.pronosticar("A", "B").esperado_local > ajuste.pronosticar("B", "A").esperado_local
    assert ajuste.pronosticar("A", "B").prob_local > 0.5


def test_encogimiento_y_equipo_sin_partidos():
    ajuste = ajustar(Deporte.FUTBOL, [*_liga_pareja(vueltas=1), *_historial(("A", "B", 6, 0))], HOY)

    assert 1 < ajuste.ataque["A"] < 2  # sin encogimiento la fuerza sería extrema
    assert ajuste.pronosticar("A", "Z") is None
    assert ajustar(Deporte.FUTBOL, [], HOY).pronosticar("A", "B") is None


def test_solo_usa_partidos_anteriores_a_la_fecha():
    historial = _liga_pareja()
    futuro = [*historial, ResultadoHistorico("Premier League", "2627", HOY, "A", "B", 9, 0)]

    assert ajustar(Deporte.FUTBOL, futuro, HOY).ataque == (
        ajustar(Deporte.FUTBOL, historial, HOY).ataque
    )


def test_lineas_enteras_y_asiaticas():
    goles = Discreta({0: 0.2, 1: 0.3, 2: 0.3, 3: 0.2})

    assert prob_linea(goles, 1.5) == pytest.approx(0.5)
    assert prob_linea(goles, 2) == pytest.approx(0.2 / 0.7)  # sin contar la devolución
    assert prob_linea(goles, 1.75) == pytest.approx((0.5 + 0.2 / 0.7) / 2)
    assert prob_linea(goles, 2.25) == pytest.approx((0.2 / 0.7 + 0.2) / 2)
    assert prob_linea(goles.negada(), -1.5) == pytest.approx(0.5)


def test_handicap_del_local_y_del_visitante():
    pronostico = ajustar(Deporte.FUTBOL, _liga_pareja(), HOY).pronosticar("A", "B")

    # +0.5 del local gana si no pierde; −0.5 del visitante gana solo si gana.
    assert pronostico.prob_handicap(True, 0.5) == pytest.approx(
        pronostico.prob_local + pronostico.prob_empate
    )
    assert pronostico.prob_handicap(False, -0.5) == pytest.approx(pronostico.prob_visitante)


def test_normal_discretizada():
    puntos = Normal(220.0, 18.0)

    assert puntos.mayor(219.5) == pytest.approx(1 - puntos.acumulada(219.5))
    assert puntos.mayor(219.5) > 0.5 > puntos.mayor(220.5)
    assert prob_linea(puntos, 220) == pytest.approx(0.5)  # simétrica sin la devolución


def _temporada_nba(partidos=120, semilla=1):
    """El equipo "Fuerte" anota ~10 más que el resto y el local suma ~3 puntos."""
    azar = random.Random(semilla)
    equipos = ["Fuerte", "B", "C", "D", "E", "F"]
    filas = []
    for _ in range(partidos):
        local, visita = azar.sample(equipos, 2)
        filas.append(
            (
                local,
                visita,
                round(azar.gauss(113 + (10 if local == "Fuerte" else 0), 9)),
                round(azar.gauss(110 + (10 if visita == "Fuerte" else 0), 9)),
            )
        )
    return _historial(*filas, liga="NBA")


def test_nba_ratings_localia_y_sigma_de_residuos():
    ajuste = ajustar(Deporte.NBA, _temporada_nba(), HOY)

    fuerte = ajuste.pronosticar("Fuerte", "B")
    assert fuerte.prob_local > 0.7
    assert fuerte.prob_empate is None and fuerte.marcador_probable is None
    assert fuerte.prob_local + fuerte.prob_visitante == pytest.approx(1)
    assert 0 < ajuste.localia < 7
    assert 8 < ajuste.sigma_margen < 16 and ajuste.sigma_margen != prediccion.SIGMA_MARGEN
    assert 200 < ajuste.pronosticar("B", "C").total.media < 245


def test_nba_pocos_partidos_sigma_por_defecto_y_back_to_back():
    historial = _historial(("A", "B", 110, 100), ("B", "A", 100, 110), liga="NBA")
    ayer = ResultadoHistorico("NBA", "2627", HOY - timedelta(days=1), "A", "C", 100, 90)

    ajuste = ajustar(Deporte.NBA, [*historial, ayer], HOY)

    assert ajuste.sigma_margen == prediccion.SIGMA_MARGEN
    pronostico = ajuste.pronosticar("A", "B")
    assert pronostico.descanso_local == 1 and pronostico.descanso_visitante == 2
    assert pronostico.esperado_local == pytest.approx(
        ajuste._esperados_nba("A", "B")[0] - prediccion.FATIGA_B2B
    )
