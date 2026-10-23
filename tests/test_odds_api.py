import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import requests
from fakes import ObtenerFalso, RespuestaFalsa, respuesta_odds

from predictor.fuentes.odds_api import ClienteOddsApi, costo_creditos
from predictor.modelos import Deporte, Mercado


def test_costo_es_tres_creditos_por_liga():
    assert costo_creditos(6) == 18


def test_sin_clave_falla():
    with pytest.raises(ValueError, match="ODDS_API_KEY"):
        ClienteOddsApi("  ")


def test_parametros_de_la_consulta():
    obtener = ObtenerFalso(respuesta_odds("odds_soccer_epl.json"))

    ClienteOddsApi("clave", obtener).cuotas("Premier League")

    url, params = obtener.llamadas[0]
    assert url.endswith("/sports/soccer_epl/odds")
    assert params["markets"] == "h2h,totals,spreads"
    assert params["oddsFormat"] == "decimal"
    assert "betano_uk" in params["bookmakers"] and "pinnacle" in params["bookmakers"]
    assert len(params["bookmakers"].split(",")) <= 10
    assert "regions" not in params


def test_parsea_partidos_y_creditos():
    respuesta = ClienteOddsApi(
        "clave", ObtenerFalso(respuesta_odds("odds_soccer_epl.json"))
    ).cuotas("Premier League")

    assert respuesta.creditos_restantes == 494
    assert respuesta.creditos_usados == 6
    partido = respuesta.partidos[0]
    assert (partido.local, partido.visitante) == ("Aston Villa", "Manchester City")
    assert partido.deporte is Deporte.FUTBOL
    assert partido.inicio == datetime(2026, 10, 24, 11, 30, tzinfo=UTC)


def test_parsea_los_tres_mercados_con_empate_y_lineas():
    cuotas = (
        ClienteOddsApi("clave", ObtenerFalso(respuesta_odds("odds_soccer_epl.json")))
        .cuotas("Premier League")
        .cuotas
    )
    pinnacle = {
        (c.mercado, c.seleccion, c.linea): c.cuota
        for c in cuotas
        if c.partido_id == "aca5dd297dbee71f576f7641569fe578" and c.casa == "pinnacle"
    }

    assert pinnacle[(Mercado.GANADOR, "Draw", None)] == Decimal("4.46")
    assert pinnacle[(Mercado.HANDICAP, "Manchester City", Decimal("-0.75"))] == Decimal("1.78")
    assert pinnacle[(Mercado.TOTALES, "Over", Decimal("3.0"))] == Decimal("1.81")


def test_descarta_mercados_y_casas_no_configurados():
    cuotas = (
        ClienteOddsApi("clave", ObtenerFalso(respuesta_odds("odds_basketball_nba.json")))
        .cuotas("NBA")
        .cuotas
    )

    assert {c.mercado for c in cuotas} == set(Mercado)  # sin "h2h_lay"
    betano = {c.mercado for c in cuotas if c.casa == "betano_uk"}
    assert betano == {Mercado.GANADOR, Mercado.TOTALES}  # Betano UK no ofrece hándicap NBA


def test_cuota_invalida_se_descarta(caplog):
    evento = {
        "id": "x",
        "commence_time": "2026-10-24T11:30:00Z",
        "home_team": "Arsenal",
        "away_team": "Everton",
        "bookmakers": [
            {
                "key": "pinnacle",
                "last_update": "2026-10-23T22:27:05Z",
                "markets": [{"key": "h2h", "outcomes": [{"name": "Arsenal", "price": 1.0}]}],
            }
        ],
    }
    obtener = ObtenerFalso(RespuestaFalsa(json.dumps([evento]).encode()))

    respuesta = ClienteOddsApi("clave", obtener).cuotas("Premier League")

    assert respuesta.cuotas == []
    assert respuesta.creditos_restantes is None
    assert "Cuota descartada" in caplog.text


@pytest.mark.parametrize(
    ("status", "mensaje"),
    [(401, "rechazó la clave"), (429, "créditos"), (500, "error 500")],
)
def test_errores_http(status, mensaje):
    cliente = ClienteOddsApi("clave", ObtenerFalso(RespuestaFalsa(b"{}", status_code=status)))

    with pytest.raises(ValueError, match=mensaje):
        cliente.cuotas("NBA")


def test_error_de_red_no_expone_la_clave():
    error = requests.ConnectionError("https://api.the-odds-api.com/v4?apiKey=secreta")
    cliente = ClienteOddsApi("secreta", ObtenerFalso(error))

    with pytest.raises(ValueError, match="No se pudo conectar") as excinfo:
        cliente.cuotas("NBA")
    assert "secreta" not in str(excinfo.value)
