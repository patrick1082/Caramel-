"""Correspondencia de cada liga con sus fuentes externas, casas de apuestas y temporadas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from predictor.modelos import LIGAS, Deporte

ZONA_CHILE = ZoneInfo("America/Santiago")


@dataclass(frozen=True)
class FuenteLiga:
    deporte: Deporte
    clave_odds: str  # sport_key de The Odds API
    codigo_historial: str | None = None  # Archivo de football-data.co.uk (solo fútbol)
    codigo_espn: str | None = None  # Liga en la API de ESPN (solo fútbol)


FUENTES: dict[str, FuenteLiga] = {
    "NBA": FuenteLiga(Deporte.NBA, "basketball_nba"),
    "Premier League": FuenteLiga(Deporte.FUTBOL, "soccer_epl", "E0", "eng.1"),
    "Serie A": FuenteLiga(Deporte.FUTBOL, "soccer_italy_serie_a", "I1", "ita.1"),
    "Bundesliga": FuenteLiga(Deporte.FUTBOL, "soccer_germany_bundesliga", "D1", "ger.1"),
    "LaLiga": FuenteLiga(Deporte.FUTBOL, "soccer_spain_la_liga", "SP1", "esp.1"),
    "Ligue 1": FuenteLiga(Deporte.FUTBOL, "soccer_france_ligue_one", "F1", "fra.1"),
}
assert set(FUENTES) == {liga for ligas in LIGAS.values() for liga in ligas}

CASA_BASE = "betano_uk"
CASA_REFERENCIA = "pinnacle"

# Casas consultadas (≤ 10 cuentan como una sola región en The Odds API) y su nombre visible.
CASAS: dict[str, str] = {
    CASA_BASE: "Betano (UK)",
    CASA_REFERENCIA: "Pinnacle",
    "betfair_ex_eu": "Betfair",
    "williamhill": "William Hill",
    "marathonbet": "Marathon Bet",
    "onexbet": "1xBet",
    "sport888": "888sport",
    "betsson": "Betsson",
    "nordicbet": "NordicBet",
}


def anio_temporada(deporte: Deporte, hoy: date) -> int:
    """Año en que empezó la temporada en curso (julio en fútbol, octubre en la NBA)."""
    return hoy.year if hoy.month >= (7 if deporte is Deporte.FUTBOL else 10) else hoy.year - 1


def temporadas(deporte: Deporte, hoy: date) -> tuple[str, str]:
    """Temporada en curso y la anterior, en el formato de la fuente de historial.

    Fútbol (football-data.co.uk): "2627". NBA (nba_api): "2026-27".
    """
    inicio = anio_temporada(deporte, hoy)
    if deporte is Deporte.FUTBOL:
        return tuple(f"{a % 100:02d}{(a + 1) % 100:02d}" for a in (inicio, inicio - 1))
    return tuple(f"{a}-{(a + 1) % 100:02d}" for a in (inicio, inicio - 1))
