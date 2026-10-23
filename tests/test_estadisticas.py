from datetime import date, timedelta

from predictor.estadisticas import Promedios, calcular, cara_a_cara
from predictor.modelos import ResultadoHistorico

INICIO = date(2026, 8, 1)


def _historial(*partidos):
    """Cada partido: (local, visitante, goles local, goles visita[, extras])."""
    return [
        ResultadoHistorico("Premier League", "2627", INICIO + timedelta(days=7 * i), *p)
        for i, p in enumerate(partidos)
    ]


def test_sin_partidos_devuelve_none():
    assert calcular("Arsenal", _historial(("Chelsea", "Everton", 1, 0))) is None


def test_forma_y_balance_desde_la_perspectiva_del_equipo():
    historial = _historial(
        ("Arsenal", "Chelsea", 2, 0),  # G
        ("Everton", "Arsenal", 1, 1),  # E
        ("Liverpool", "Arsenal", 3, 1),  # P
        ("Arsenal", "Fulham", 0, 1),  # P
        ("Chelsea", "Everton", 5, 5),  # ajeno
        ("Leeds", "Arsenal", 0, 4),  # G
    )

    stats = calcular("Arsenal", historial)

    assert stats.jugados == 5
    assert (stats.ganados, stats.empatados, stats.perdidos) == (2, 1, 2)
    assert stats.forma == "GPPEG"  # el más reciente primero
    assert stats.ultimos == Promedios(jugados=5, a_favor=1.6, en_contra=1.0)
    assert stats.de_local == Promedios(jugados=2, a_favor=1.0, en_contra=0.5)
    assert stats.de_visita == Promedios(jugados=3, a_favor=2.0, en_contra=1.33)


def test_forma_y_promedios_usan_solo_los_ultimos():
    historial = _historial(
        *[("Arsenal", "Chelsea", 0, 3)] * 5, *[("Arsenal", "Chelsea", 2, 0)] * 10
    )

    stats = calcular("Arsenal", historial)

    assert stats.forma == "GGGGG"
    assert stats.ultimos.a_favor == 2.0 and stats.ultimos.jugados == 10
    assert stats.de_visita is None
    assert stats.perdidos == 5


def test_extras_se_orientan_al_equipo():
    historial = _historial(
        ("Arsenal", "Chelsea", 1, 0, {"tiros": (10.0, 4.0)}),
        ("Chelsea", "Arsenal", 0, 0, {"tiros": (6.0, 14.0), "xg": (0.5, 1.5)}),
    )

    stats = calcular("Arsenal", historial)

    assert stats.extras == {"tiros": (12.0, 5.0), "xg": (1.5, 0.5)}


def test_cara_a_cara_en_ambas_canchas_mas_reciente_primero():
    historial = _historial(
        ("Arsenal", "Chelsea", 1, 0),
        ("Arsenal", "Everton", 2, 2),
        ("Chelsea", "Arsenal", 3, 1),
        ("Arsenal", "Chelsea", 0, 0),
    )

    directos = cara_a_cara("Chelsea", "Arsenal", historial, ultimos=2)

    assert [(r.local, r.marcador_local, r.marcador_visitante) for r in directos] == [
        ("Arsenal", 0, 0),
        ("Chelsea", 3, 1),
    ]
