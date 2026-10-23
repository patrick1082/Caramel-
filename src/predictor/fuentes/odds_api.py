"""Cliente de The Odds API v4: partidos próximos y cuotas por liga."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import requests

from predictor.ligas import CASAS, FUENTES
from predictor.modelos import Cuota, Mercado, Partido

logger = logging.getLogger(__name__)

URL_BASE = "https://api.the-odds-api.com/v4"
TIEMPO_ESPERA = 15  # segundos


def costo_creditos(cantidad_ligas: int) -> int:
    """Créditos que cobra la API: mercados × regiones (≤ 10 casas = 1 región) por liga."""
    return cantidad_ligas * len(Mercado)


@dataclass(frozen=True)
class RespuestaOdds:
    partidos: list[Partido]
    cuotas: list[Cuota]
    creditos_restantes: int | None
    creditos_usados: int | None


def _entero(valor: str | None) -> int | None:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return None


def parsear(liga: str, eventos: list[dict]) -> tuple[list[Partido], list[Cuota]]:
    """Convierte la respuesta JSON de /odds en partidos y cuotas de las casas configuradas."""
    deporte = FUENTES[liga].deporte
    partidos, cuotas = [], []
    for evento in eventos:
        partidos.append(
            Partido(
                id=evento["id"],
                deporte=deporte,
                liga=liga,
                local=evento["home_team"],
                visitante=evento["away_team"],
                inicio=datetime.fromisoformat(evento["commence_time"]),
            )
        )
        for casa in evento.get("bookmakers", []):
            if casa["key"] not in CASAS:
                continue
            for mercado in casa.get("markets", []):
                if mercado["key"] not in Mercado:
                    continue  # p. ej. "h2h_lay" de Betfair
                actualizada = datetime.fromisoformat(
                    mercado.get("last_update", casa["last_update"])
                )
                for opcion in mercado["outcomes"]:
                    try:
                        cuotas.append(
                            Cuota(
                                partido_id=evento["id"],
                                casa=casa["key"],
                                mercado=mercado["key"],
                                seleccion=opcion["name"],
                                cuota=opcion["price"],
                                linea=opcion.get("point"),
                                actualizada=actualizada,
                            )
                        )
                    except ValueError as error:
                        logger.warning(
                            "Cuota descartada (%s, %s): %s", casa["key"], evento["id"], error
                        )
    return partidos, cuotas


class ClienteOddsApi:
    def __init__(self, api_key: str, obtener: Callable[..., requests.Response] = requests.get):
        if not api_key or not api_key.strip():
            raise ValueError("Falta la clave de The Odds API (variable ODDS_API_KEY)")
        self._api_key = api_key.strip()
        self._obtener = obtener

    def cuotas(self, liga: str) -> RespuestaOdds:
        parametros = {
            "apiKey": self._api_key,
            "bookmakers": ",".join(CASAS),
            "markets": ",".join(m.value for m in Mercado),
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }
        url = f"{URL_BASE}/sports/{FUENTES[liga].clave_odds}/odds"
        try:
            respuesta = self._obtener(url, params=parametros, timeout=TIEMPO_ESPERA)
        except requests.RequestException as error:
            # El mensaje de requests incluye la URL con la clave: no se muestra.
            raise ValueError(
                f"No se pudo conectar con The Odds API ({type(error).__name__})"
            ) from None

        if respuesta.status_code == 401:
            raise ValueError("The Odds API rechazó la clave: revisa ODDS_API_KEY")
        if respuesta.status_code == 429:
            raise ValueError("The Odds API: se agotaron los créditos o hay demasiadas consultas")
        if respuesta.status_code != 200:
            raise ValueError(f"The Odds API respondió con error {respuesta.status_code}")

        partidos, cuotas = parsear(liga, respuesta.json())
        restantes = _entero(respuesta.headers.get("x-requests-remaining"))
        usados = _entero(respuesta.headers.get("x-requests-used"))
        logger.info(
            "Cuotas %s: %s partidos, %s cuotas, %s créditos restantes",
            liga,
            len(partidos),
            len(cuotas),
            restantes,
        )
        return RespuestaOdds(partidos, cuotas, restantes, usados)
