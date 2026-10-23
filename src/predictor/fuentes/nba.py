"""Historial NBA desde stats.nba.com a través del paquete nba_api."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import date

from predictor.modelos import ResultadoHistorico

logger = logging.getLogger(__name__)

TIEMPO_ESPERA = 30  # segundos

# Estadística → columna de LeagueGameFinder (una fila por equipo y partido).
EXTRAS = {
    "rebotes": "REB",
    "asistencias": "AST",
    "triples": "FG3M",
    "pct_tiro": "FG_PCT",
    "perdidas": "TOV",
}


def _buscar(temporada: str) -> list[dict]:
    from nba_api.stats.endpoints import leaguegamefinder  # import diferido: es pesado

    consulta = leaguegamefinder.LeagueGameFinder(
        season_nullable=temporada,
        league_id_nullable="00",
        season_type_nullable="Regular Season",
        timeout=TIEMPO_ESPERA,
    )
    return consulta.get_normalized_dict()["LeagueGameFinderResults"]


def parsear(temporada: str, filas: list[dict]) -> list[ResultadoHistorico]:
    """Une las dos filas de cada partido (local "vs.", visita "@") en un resultado."""
    por_juego: dict[str, dict[str, dict]] = defaultdict(dict)
    for fila in filas:
        lado = "local" if " vs. " in fila["MATCHUP"] else "visita"
        por_juego[fila["GAME_ID"]][lado] = fila

    resultados = []
    for juego in por_juego.values():
        local, visita = juego.get("local"), juego.get("visita")
        if not local or not visita or local.get("WL") is None or local.get("PTS") is None:
            continue  # partido incompleto o en curso
        extras = {
            nombre: (float(local[columna]), float(visita[columna]))
            for nombre, columna in EXTRAS.items()
            if local.get(columna) is not None and visita.get(columna) is not None
        }
        resultados.append(
            ResultadoHistorico(
                liga="NBA",
                temporada=temporada,
                fecha=date.fromisoformat(local["GAME_DATE"]),
                local=local["TEAM_NAME"],
                visitante=visita["TEAM_NAME"],
                marcador_local=int(local["PTS"]),
                marcador_visitante=int(visita["PTS"]),
                extras=extras,
            )
        )
    return sorted(resultados, key=lambda r: r.fecha)


def descargar(
    temporada: str, buscar: Callable[[str], list[dict]] = _buscar
) -> list[ResultadoHistorico]:
    try:
        filas = buscar(temporada)
    except Exception as error:  # nba_api puede fallar por red, bloqueo o JSON inválido
        raise ValueError(
            f"No se pudo descargar el historial NBA {temporada} ({type(error).__name__})"
        ) from error
    resultados = parsear(temporada, filas)
    logger.info("Historial NBA %s: %s partidos", temporada, len(resultados))
    return resultados
