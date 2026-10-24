"""Historial y jugadores NBA desde stats.nba.com a través del paquete nba_api."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import date

from predictor.modelos import Jugador, ResultadoHistorico, Rol

logger = logging.getLogger(__name__)

TIEMPO_ESPERA = 30  # segundos
POR_EQUIPO = 3  # jugadores destacados por equipo

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


def _buscar_jugadores(temporada: str) -> list[dict]:
    from nba_api.stats.endpoints import leaguedashplayerstats

    consulta = leaguedashplayerstats.LeagueDashPlayerStats(
        season=temporada,
        season_type_all_star="Regular Season",
        per_mode_detailed="PerGame",
        timeout=TIEMPO_ESPERA,
    )
    return consulta.get_normalized_dict()["LeagueDashPlayerStats"]


def _nombres_equipos() -> dict[int, str]:
    from nba_api.stats.static import teams  # datos incluidos en el paquete, sin red

    return {equipo["id"]: equipo["full_name"] for equipo in teams.get_teams()}


def _cifra(valor: float) -> str:
    return f"{valor:.1f}".removesuffix(".0")


def jugadores(
    temporada: str, buscar: Callable[[str], list[dict]] = _buscar_jugadores
) -> list[Jugador]:
    """Los máximos anotadores (promedio por partido) de cada equipo."""
    try:
        filas = buscar(temporada)
    except Exception as error:  # mismo motivo que en `descargar`
        raise ValueError(
            f"No se pudieron descargar los jugadores NBA {temporada} ({type(error).__name__})"
        ) from error
    nombres = _nombres_equipos()
    por_equipo: dict[str, list[dict]] = defaultdict(list)
    for fila in filas:
        if fila.get("TEAM_ID") in nombres and fila.get("PTS") is not None:
            por_equipo[nombres[fila["TEAM_ID"]]].append(fila)

    resultado = []
    for equipo, filas_equipo in por_equipo.items():
        for fila in sorted(filas_equipo, key=lambda f: -f["PTS"])[:POR_EQUIPO]:
            detalle = (
                f"{_cifra(fila['PTS'])} pts, {_cifra(fila.get('REB') or 0)} reb, "
                f"{_cifra(fila.get('AST') or 0)} ast en {_cifra(fila.get('MIN') or 0)} min "
                f"({fila.get('GP') or 0} PJ)"
            )
            resultado.append(
                Jugador("NBA", equipo, fila["PLAYER_NAME"], Rol.DESTACADO, detalle, fila["PTS"])
            )
    logger.info("Jugadores NBA %s: %s destacados", temporada, len(resultado))
    return resultado
