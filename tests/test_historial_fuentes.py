import json
from datetime import date

import pytest
import requests
from fakes import DATOS, ObtenerFalso, RespuestaFalsa

from predictor.fuentes import football_data, nba


def test_football_data_url_y_parseo():
    obtener = ObtenerFalso(RespuestaFalsa((DATOS / "E0.csv").read_bytes()))

    resultados = football_data.descargar("Premier League", "2627", obtener)

    assert obtener.llamadas[0][0] == "https://football-data.co.uk/mmz4281/2627/E0.csv"
    assert len(resultados) == 30
    primero = resultados[0]
    assert primero.fecha == date(2026, 8, 21)
    assert (primero.local, primero.visitante) == ("Arsenal", "Coventry")
    assert (primero.marcador_local, primero.marcador_visitante) == (3, 0)
    assert primero.extras["tiros"] == (20, 4)
    assert primero.extras["xg"] == (1.88, 0.2)
    assert primero.temporada == "2627"


def test_football_data_omite_filas_sin_resultado_y_columnas_faltantes():
    texto = (
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HS,AS\n"
        "E0,21/08/26,Arsenal,Coventry,1,1,10,\n"
        "E0,28/08/26,Hull,Leeds,,,,\n"
        ",,,,,,,\n"
    )

    resultados = football_data.parsear("Premier League", "2627", texto)

    assert len(resultados) == 1
    assert resultados[0].fecha == date(2026, 8, 21)
    assert resultados[0].extras == {}


def test_football_data_temporada_inexistente_devuelve_vacio():
    obtener = ObtenerFalso(RespuestaFalsa(status_code=404))

    assert football_data.descargar("LaLiga", "2728", obtener) == []


@pytest.mark.parametrize(
    "respuesta", [RespuestaFalsa(status_code=500), requests.ConnectionError("caída")]
)
def test_football_data_errores(respuesta):
    with pytest.raises(ValueError, match="historial|error 500"):
        football_data.descargar("Serie A", "2627", ObtenerFalso(respuesta))


def test_nba_une_local_y_visita():
    filas = json.loads((DATOS / "nba_juegos.json").read_text())

    resultados = nba.descargar("2025-26", buscar=lambda temporada: filas)

    assert len(resultados) == 6  # la fila suelta del último juego se descarta
    dallas = next(r for r in resultados if r.local == "Dallas Mavericks")
    assert dallas.visitante == "Chicago Bulls"
    assert (dallas.marcador_local, dallas.marcador_visitante) == (149, 128)
    assert dallas.fecha == date(2026, 4, 12)
    assert dallas.extras["rebotes"][0] == 57
    lakers = next(r for r in resultados if r.local == "Los Angeles Lakers")
    assert lakers.visitante == "Utah Jazz"  # la fila de la visita venía primero


def test_nba_omite_partido_en_curso():
    filas = json.loads((DATOS / "nba_juegos.json").read_text())[:2]
    for fila in filas:
        fila["WL"] = None

    assert nba.parsear("2026-27", filas) == []


def test_nba_error_de_descarga():
    def falla(temporada):
        raise requests.ReadTimeout("lento")

    with pytest.raises(ValueError, match="historial NBA 2026-27"):
        nba.descargar("2026-27", buscar=falla)
