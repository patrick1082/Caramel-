from dataclasses import replace
from datetime import date

from predictor.estadisticas import Estadisticas, Promedios
from predictor.factores import MAXIMO, generar
from predictor.modelos import Deporte, Jugador, ResultadoHistorico, Rol
from predictor.prediccion import Discreta, Pronostico

PRONOSTICO = Pronostico(
    modelo="poisson-1",
    esperado_local=1.5,
    esperado_visitante=1.1,
    prob_local=0.45,
    prob_empate=0.27,
    prob_visitante=0.28,
    marcador_probable="1-1",
    total=Discreta({2: 1.0}),
    margen=Discreta({0: 1.0}),
    partidos_local=30,
    partidos_visitante=30,
    descanso_local=6,
    descanso_visitante=6,
)


def _stats(equipo, forma="GEPGE", ultimos=(1.5, 1.0), de_local=None, de_visita=None, extras=None):
    return Estadisticas(
        equipo=equipo,
        jugados=30,
        ganados=10,
        empatados=10,
        perdidos=10,
        forma=forma,
        ultimos=Promedios(10, *ultimos),
        de_local=Promedios(5, *de_local) if de_local else None,
        de_visita=Promedios(5, *de_visita) if de_visita else None,
        extras=extras or {},
    )


def _generar(
    deporte=Deporte.FUTBOL,
    local=None,
    visitante=None,
    directos=(),
    pronostico=PRONOSTICO,
    **jugadores,
):
    return generar(
        deporte,
        "Manchester City",
        "Aston Villa",
        local or _stats("Man City"),
        visitante or _stats("Aston Villa"),
        list(directos),
        pronostico,
        **jugadores,
    )


def test_sin_factores_destacables():
    assert _generar() == []


def test_sin_pronostico_o_con_pocos_partidos():
    assert _generar(pronostico=None) == ["Sin historial suficiente para predecir este partido."]
    [factor] = _generar(pronostico=replace(PRONOSTICO, partidos_visitante=4))
    assert factor == "Pocos datos: Aston Villa tiene solo 4 partidos en el historial."


def test_rachas():
    factores = _generar(
        local=_stats("Man City", forma="GGGPG"), visitante=_stats("Aston Villa", forma="PPEPP")
    )

    assert factores == [
        "Manchester City viene en racha: GGGPG en los últimos 5.",
        "Aston Villa viene en mala racha: PPEPP en los últimos 5.",
    ]
    assert _generar(local=_stats("Man City", forma="GGGPP")) == []


def test_localia_con_umbral():
    local = _stats("Man City", ultimos=(1.5, 1.0), de_local=(2.5, 0.8))  # +1.7 vs +0.5
    visitante = _stats("Aston Villa", ultimos=(1.5, 1.0), de_visita=(0.8, 1.4))  # −0.6 vs +0.5
    apenas = _stats("Man City", ultimos=(1.5, 1.0), de_local=(1.9, 0.8))  # +1.1 vs +0.5

    assert _generar(local=local, visitante=visitante) == [
        "Manchester City se hace fuerte en casa: +1.7 goles por partido de local.",
        "Aston Villa rinde peor de visita: -0.6 goles por partido fuera.",
    ]
    assert _generar(local=apenas) == []


def test_back_to_back_y_descanso():
    nba = _generar(Deporte.NBA, pronostico=replace(PRONOSTICO, descanso_local=1))
    futbol = _generar(pronostico=replace(PRONOSTICO, descanso_local=3, descanso_visitante=7))

    assert nba == ["Manchester City juega back-to-back (jugó ayer)."]
    assert futbol == ["Aston Villa llega con 7 días de descanso frente a 3 del rival."]


def _directo(local, visitante, goles_local, goles_visita):
    return ResultadoHistorico(
        "Premier League", "2627", date(2026, 1, 1), local, visitante, goles_local, goles_visita
    )


def test_dominio_en_enfrentamientos_directos():
    dominio = [
        _directo("Man City", "Aston Villa", 2, 0),
        _directo("Aston Villa", "Man City", 1, 3),
        _directo("Aston Villa", "Man City", 1, 1),
        _directo("Man City", "Aston Villa", 1, 0),
    ]

    assert _generar(directos=dominio) == [
        "Manchester City ganó 3 de los últimos 4 enfrentamientos directos."
    ]
    assert _generar(directos=[*dominio[:3], _directo("Man City", "Aston Villa", 0, 1)]) == []


def test_xg_frente_a_goles():
    suerte = _stats("Man City", ultimos=(2.4, 1.0), extras={"xg": (1.6, 1.0)})
    falta = _stats("Aston Villa", ultimos=(0.9, 1.0), extras={"xg": (1.3, 1.0)})

    assert _generar(local=suerte, visitante=falta) == [
        "Manchester City marca más de lo que genera (2.4 goles vs 1.6 xG)."
    ]


def test_lesiones_bajas_clave_y_goleador():
    haaland = Jugador(
        "Premier League", "Manchester City", "Erling Haaland", Rol.DESTACADO, "8 goles · 7 PJ", 8
    )
    foden = Jugador("Premier League", "Manchester City", "Phil Foden", Rol.DESTACADO, "3 goles", 3)
    lesionados = [
        Jugador("Premier League", "Manchester City", "Erling Haaland", Rol.LESIONADO, "Out · Knee"),
        *[
            Jugador("Premier League", "Aston Villa", f"Jugador {i}", Rol.LESIONADO, "Out")
            for i in range(5)
        ],
    ]

    factores = _generar(
        jugadores_local=[haaland, foden, lesionados[0]],
        jugadores_visitante=lesionados[1:],
    )

    assert factores == [
        "Baja clave en Manchester City: Erling Haaland (8 goles · 7 PJ) — Out · Knee.",
        "Lesionados en Aston Villa: Jugador 0 (Out), Jugador 1 (Out), Jugador 2 (Out) y 2 más.",
        "Goleador de Manchester City: Erling Haaland (8 goles · 7 PJ).",
    ]


def test_maximo_de_factores():
    factores = _generar(
        local=_stats(
            "Man City",
            forma="GGGGG",
            ultimos=(2.4, 1.0),
            de_local=(3.5, 0.5),
            extras={"xg": (1.0, 1.0)},
        ),
        visitante=_stats(
            "Aston Villa",
            forma="PPPPP",
            ultimos=(1.5, 1.0),
            de_visita=(0.5, 2.0),
            extras={"xg": (2.5, 1.0)},
        ),
        pronostico=replace(PRONOSTICO, partidos_local=5, descanso_visitante=1),
        jugadores_local=[
            Jugador(
                "Premier League", "Manchester City", "Erling Haaland", Rol.DESTACADO, "8 goles", 8
            )
        ],
    )

    assert len(factores) == MAXIMO
    assert factores[0].startswith("Pocos datos")
