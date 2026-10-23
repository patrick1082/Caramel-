from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fakes import DATOS, ObtenerFalso, respuesta_odds

from predictor.cartelera import Cartelera
from predictor.fuentes import football_data
from predictor.fuentes.odds_api import ClienteOddsApi
from predictor.modelos import Mercado

VILLA_CITY = "aca5dd297dbee71f576f7641569fe578"


class Reloj:
    def __init__(self, momento=datetime(2026, 10, 23, 15, 0, tzinfo=UTC)):
        self.momento = momento

    def __call__(self):
        return self.momento


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def obtener():
    return ObtenerFalso(
        respuesta_odds("odds_soccer_epl.json", restantes=491),
        respuesta_odds("odds_basketball_nba.json", restantes=488),
    )


@pytest.fixture
def cartelera(repo, obtener, reloj):
    return Cartelera(repo, ClienteOddsApi("clave", obtener), reloj=reloj)


def test_actualizar_cuotas_guarda_partidos_y_creditos(cartelera, obtener):
    actualizadas = cartelera.actualizar_cuotas(["Premier League", "NBA"])

    assert actualizadas == ["Premier League", "NBA"]
    assert len(obtener.llamadas) == 2
    assert cartelera.creditos_restantes == 488
    assert len(cartelera.partidos(date(2026, 10, 24), ligas=["Premier League"])) == 3


def test_no_repite_consulta_mientras_las_cuotas_estan_vigentes(cartelera, obtener, reloj):
    cartelera.actualizar_cuotas(["Premier League"])
    reloj.momento += timedelta(minutes=59)

    assert cartelera.actualizar_cuotas(["Premier League"]) == []
    assert cartelera.actualizar_cuotas(["Premier League"], forzar=True) == ["Premier League"]
    reloj.momento += timedelta(minutes=61)
    assert cartelera.ligas_por_actualizar(["Premier League", "NBA"]) == ["Premier League", "NBA"]
    assert len(obtener.llamadas) == 2


def test_sin_creditos_suficientes_no_consulta(repo, cartelera, obtener):
    repo.fijar_config("odds_creditos_restantes", "5")

    with pytest.raises(ValueError, match="cuesta 6 créditos y quedan 5"):
        cartelera.actualizar_cuotas(["Premier League", "NBA"])
    assert obtener.llamadas == []


def test_sin_clave_no_actualiza_pero_muestra_lo_guardado(repo, cartelera):
    cartelera.actualizar_cuotas(["Premier League"])
    sin_clave = Cartelera(repo, None)

    assert not sin_clave.tiene_clave
    with pytest.raises(ValueError, match="ODDS_API_KEY"):
        sin_clave.actualizar_cuotas(["Premier League"])
    assert len(sin_clave.partidos(date(2026, 10, 24))) == 3


def test_partidos_filtra_por_dia_y_hora_de_chile(cartelera):
    cartelera.actualizar_cuotas(["Premier League", "NBA"])

    # NBA: 17:16 y 20:10 del 23 en Chile. Premier: 08:30 y 11:00 del 24.
    noche = cartelera.partidos(date(2026, 10, 23), desde_hora=18)
    manana = cartelera.partidos(date(2026, 10, 24), 8, 9)

    assert [p.liga for p in noche] == ["NBA", "NBA"]
    assert [p.id for p in manana] == [VILLA_CITY]
    assert cartelera.partidos(date(2026, 10, 24), ligas=["NBA"]) == []


def test_rango_de_horas_invalido(cartelera):
    with pytest.raises(ValueError, match="rango de horas"):
        cartelera.partidos(date(2026, 10, 24), 12, 12)


def test_comparar_ordena_y_resume_las_cuotas(cartelera):
    cartelera.actualizar_cuotas(["Premier League"])
    [villa_city] = cartelera.partidos(date(2026, 10, 24), 8, 9)

    filas = cartelera.comparar(villa_city)

    assert [(f.mercado, f.seleccion, f.linea) for f in filas] == [
        (Mercado.GANADOR, "Aston Villa", None),
        (Mercado.GANADOR, "Draw", None),
        (Mercado.GANADOR, "Manchester City", None),
        (Mercado.TOTALES, "Over", Decimal("2.5")),
        (Mercado.TOTALES, "Under", Decimal("2.5")),
        (Mercado.TOTALES, "Over", Decimal("3.0")),
        (Mercado.TOTALES, "Under", Decimal("3.0")),
        (Mercado.TOTALES, "Over", Decimal("3.5")),
        (Mercado.TOTALES, "Under", Decimal("3.5")),
        (Mercado.HANDICAP, "Aston Villa", Decimal("0.75")),
        (Mercado.HANDICAP, "Manchester City", Decimal("-0.75")),
    ]  # las líneas ±1 y ±1.5 de una sola casa se omiten
    villa = filas[0]
    assert (villa.betano, villa.pinnacle) == (Decimal("4.75"), Decimal("5.08"))
    assert (villa.mejor, villa.casa_mejor) == (Decimal("5.3"), "Betfair")
    assert villa.promedio == Decimal("4.92")
    assert villa.casas == 9
    assert filas[3].betano is None


def _descargar_e0(liga, temporada):
    if temporada == "2627":
        return football_data.parsear(liga, temporada, (DATOS / "E0.csv").read_text("utf-8-sig"))
    return []


def test_actualizar_historial_una_vez_al_dia(repo, reloj):
    pedidas = []

    def futbol(liga, temporada):
        pedidas.append(temporada)
        return _descargar_e0(liga, temporada)

    def baloncesto(temporada):
        pedidas.append(temporada)
        return []

    cartelera = Cartelera(repo, None, futbol, baloncesto, reloj)

    assert cartelera.actualizar_historial(["Premier League", "NBA"]) == ["Premier League", "NBA"]
    assert pedidas == ["2627", "2526", "2026-27", "2025-26"]
    assert len(repo.historial_de("Premier League")) == 30

    reloj.momento += timedelta(hours=23)
    assert cartelera.actualizar_historial(["Premier League"]) == []
    assert cartelera.actualizar_historial(["Premier League"], forzar=True) == ["Premier League"]


def test_analizar_cruza_nombres_entre_fuentes(repo, obtener, reloj):
    cartelera = Cartelera(repo, ClienteOddsApi("clave", obtener), _descargar_e0, reloj=reloj)
    cartelera.actualizar_cuotas(["Premier League"])
    [villa_city] = cartelera.partidos(date(2026, 10, 24), 8, 9)
    sin_historial = cartelera.analizar(villa_city)

    cartelera.actualizar_historial(["Premier League"])
    analisis = cartelera.analizar(villa_city)

    assert sin_historial.local is None and sin_historial.cara_a_cara == []
    assert analisis.local.equipo == "Aston Villa"
    assert analisis.visitante.equipo == "Man City"  # nombre de football-data.co.uk
    assert analisis.local.jugados >= 1
