import json
from datetime import date

import pytest
import requests
from fakes import DATOS, ObtenerFalso, RespuestaFalsa

from predictor.fuentes import espn, nba
from predictor.ligas import anio_temporada
from predictor.modelos import Deporte, Rol


class ObtenerPorUrl:
    """Responde según la URL pedida (las fichas de jugador se piden de a una)."""

    def __init__(self):
        self.atletas = json.loads((DATOS / "espn_atletas.json").read_text("utf-8"))
        self.urls: list[str] = []

    def __call__(self, url, params=None, timeout=None):
        self.urls.append(url)
        if url.endswith("/leaders"):
            return RespuestaFalsa((DATOS / "espn_lideres_eng.json").read_bytes())
        if url.endswith("/teams"):
            return RespuestaFalsa((DATOS / "espn_equipos_eng.json").read_bytes())
        atleta = url.rsplit("/", 1)[1]
        return RespuestaFalsa(json.dumps(self.atletas[atleta]).encode())


def test_anio_temporada():
    assert anio_temporada(Deporte.FUTBOL, date(2026, 10, 23)) == 2026
    assert anio_temporada(Deporte.FUTBOL, date(2027, 3, 1)) == 2026
    assert anio_temporada(Deporte.NBA, date(2026, 9, 30)) == 2025


def test_goleadores_une_goles_y_asistencias():
    obtener = ObtenerPorUrl()

    jugadores = espn.goleadores("Premier League", 2026, obtener)

    assert obtener.urls[0] == (
        "https://sports.core.api.espn.com/v2/sports/soccer/leagues/eng.1/seasons/2026"
        "/types/1/leaders"
    )
    haaland = jugadores[0]
    assert (haaland.nombre, haaland.equipo, haaland.valor) == (
        "Erling Haaland",
        "Manchester City",
        8,
    )
    assert haaland.detalle.startswith("8 goles")
    assert haaland.rol is Rol.DESTACADO
    assert len(jugadores) == len(obtener.atletas)
    assert all(u.startswith("https://") for u in obtener.urls)
    assert any(j.nombre == "João Pedro" for j in jugadores)


def test_goleadores_liga_sin_codigo():
    with pytest.raises(ValueError, match="no tiene goleadores"):
        espn.goleadores("NBA", 2026, ObtenerFalso(RespuestaFalsa()))


@pytest.mark.parametrize(
    "respuesta, mensaje",
    [
        (RespuestaFalsa(status_code=503), "error 503"),
        (RespuestaFalsa(b"<html>"), "datos inválidos"),
        (requests.ConnectionError("caída"), "ConnectionError"),
    ],
)
def test_errores_de_espn(respuesta, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        espn.lesiones_nba(ObtenerFalso(respuesta))


def test_lesiones_nba():
    obtener = ObtenerFalso(RespuestaFalsa((DATOS / "espn_lesiones_nba.json").read_bytes()))

    lesionados = espn.lesiones_nba(obtener)

    assert [(j.equipo, j.nombre, j.detalle) for j in lesionados] == [
        ("Atlanta Hawks", "Mouhamed Gueye", "Out · Foot"),
        ("Atlanta Hawks", "Henri Veesaar", "Out · Knee"),
        ("Boston Celtics", "Devin Carter", "Out · Illness"),
    ]
    assert all(j.rol is Rol.LESIONADO for j in lesionados)


def test_nba_jugadores_top_por_equipo():
    filas = json.loads((DATOS / "nba_jugadores.json").read_text("utf-8"))

    jugadores = nba.jugadores("2026-27", buscar=lambda temporada: filas)

    celtics = [j for j in jugadores if j.equipo == "Boston Celtics"]
    assert len(celtics) == nba.POR_EQUIPO
    assert celtics[0].nombre == "Paul George" and celtics[0].valor == 38
    hawks = [j for j in jugadores if j.equipo == "Atlanta Hawks"]
    assert hawks[0].detalle == "31 pts, 4 reb, 3 ast en 29.7 min (1 PJ)"


def test_nba_jugadores_error():
    def falla(temporada):
        raise requests.ReadTimeout("lento")

    with pytest.raises(ValueError, match="jugadores NBA 2026-27"):
        nba.jugadores("2026-27", buscar=falla)


class ObtenerBpi:
    """Scoreboard del fixture; un summary real, uno 50/50, uno caído y el resto sin predictor."""

    def __init__(self):
        self.urls: list[str] = []

    def __call__(self, url, params=None, timeout=None):
        self.urls.append(url)
        if "/scoreboard" in url:
            return RespuestaFalsa((DATOS / "espn_scoreboard_nba.json").read_bytes())
        evento = url.rsplit("=", 1)[1]
        if evento == "401909854":
            return RespuestaFalsa((DATOS / "espn_predictor_nba.json").read_bytes())
        if evento == "401909853":
            parejo = {"homeTeam": {"id": "30", "gameProjection": "50.0"}}
            return RespuestaFalsa(json.dumps({"predictor": parejo}).encode())
        if evento == "401909855":
            return RespuestaFalsa(status_code=503)
        return RespuestaFalsa(b"{}")


def test_bpi_nba_lee_el_predictor_de_cada_partido(caplog):
    from datetime import UTC, datetime

    obtener = ObtenerBpi()

    pronosticos = espn.bpi_nba(date(2026, 10, 24), obtener)

    assert obtener.urls[0].endswith("/nba/scoreboard?dates=20261024")
    assert obtener.urls[2].endswith("/nba/summary?event=401909854")
    assert len(obtener.urls) == 9 and all(u.startswith("https://") for u in obtener.urls)
    assert pronosticos == [
        espn.BpiNba(
            "Cleveland Cavaliers",
            "Brooklyn Nets",
            datetime(2026, 10, 24, 23, 30, tzinfo=UTC),
            pytest.approx(0.805),
            pytest.approx(0.195),
        )
    ]
    assert "401909855" in caplog.text and "error 503" in caplog.text


@pytest.mark.parametrize(
    "predictor, esperado",
    [
        ({"homeTeam": {"id": "5", "gameProjection": "61.2"}}, 0.612),
        ({"homeTeam": {"id": "17"}, "awayTeam": {"id": "5", "gameProjection": "70"}}, 0.70),
        ({"homeTeam": {"id": "5", "gameProjection": "120"}}, None),
        ({"homeTeam": {"id": "5", "gameProjection": "n/a"}}, None),
        ({"homeTeam": {"id": "17", "gameProjection": "61.2"}}, None),
        (None, None),
    ],
)
def test_prob_local_del_predictor(predictor, esperado):
    prob = espn._prob_local({"predictor": predictor}, "5")

    assert prob == (None if esperado is None else pytest.approx(esperado))


def test_bpi_nba_omite_eventos_incompletos():
    eventos = {"events": [{"id": "1", "competitions": []}, {"id": "../x", "competitions": []}]}
    obtener = ObtenerFalso(RespuestaFalsa(json.dumps(eventos).encode()))

    assert espn.bpi_nba(date(2026, 10, 24), obtener) == []
    assert len(obtener.llamadas) == 1  # no se pide ningún summary


def test_bpi_nba_error_del_scoreboard_se_propaga():
    with pytest.raises(ValueError, match="partidos NBA"):
        espn.bpi_nba(date(2026, 10, 24), ObtenerFalso(RespuestaFalsa(status_code=500)))
