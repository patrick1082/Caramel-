"""Lesiones NBA y goleadores de fútbol desde la API pública (sin clave) de ESPN."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

import requests

from predictor.ligas import FUENTES
from predictor.modelos import Jugador, Rol

logger = logging.getLogger(__name__)

URL_LESIONES_NBA = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
URL_FUTBOL = "https://sports.core.api.espn.com/v2/sports/soccer/leagues/{codigo}/seasons/{anio}"
URL_EQUIPOS = "https://site.api.espn.com/apis/site/v2/sports/soccer/{codigo}/teams"
TIEMPO_ESPERA = 30  # segundos
POR_CATEGORIA = 8  # líderes que se leen de goles y de asistencias

# Categoría de ESPN → estadística propia.
CATEGORIAS = {"goalsLeaders": "goles", "assistsLeaders": "asistencias"}

Obtener = Callable[..., requests.Response]


def _json(url: str, que: str, obtener: Obtener) -> dict:
    try:
        respuesta = obtener(url, timeout=TIEMPO_ESPERA)
    except requests.RequestException as error:
        raise ValueError(f"No se pudo consultar ESPN ({que}): {type(error).__name__}") from None
    if respuesta.status_code != 200:
        raise ValueError(f"ESPN respondió con error {respuesta.status_code} ({que})")
    try:
        return respuesta.json()
    except ValueError:
        raise ValueError(f"ESPN devolvió datos inválidos ({que})") from None


def _id(referencia: dict | None, recurso: str) -> str | None:
    """Id numérico dentro de un `$ref` de ESPN (no se sigue el enlace: viene de afuera)."""
    coincidencia = re.search(rf"/{recurso}/(\d+)", (referencia or {}).get("$ref", ""))
    return coincidencia.group(1) if coincidencia else None


def lesiones_nba(obtener: Obtener = requests.get) -> list[Jugador]:
    datos = _json(URL_LESIONES_NBA, "lesiones NBA", obtener)
    jugadores = []
    for bloque in datos.get("injuries", []):
        equipo = bloque.get("displayName") or ""
        for lesion in bloque.get("injuries", []):
            nombre = (lesion.get("athlete") or {}).get("displayName") or ""
            if not equipo.strip() or not nombre.strip():
                continue
            partes = [lesion.get("status"), (lesion.get("details") or {}).get("type")]
            detalle = " · ".join(p for p in partes if p) or "Lesionado"
            jugadores.append(Jugador("NBA", equipo, nombre, Rol.LESIONADO, detalle))
    logger.info("Lesiones NBA: %s jugadores", len(jugadores))
    return jugadores


def _detalle(stats: dict) -> str:
    partes = []
    for clave, singular in (("goles", "gol"), ("asistencias", "asistencia")):
        if n := stats.get(clave, 0):
            partes.append(f"{n} {singular if n == 1 else clave}")
    if stats.get("pj"):
        partes.append(f"{stats['pj']} PJ")
    return " · ".join(partes)


def goleadores(liga: str, anio: int, obtener: Obtener = requests.get) -> list[Jugador]:
    """Máximos goleadores y asistidores de la temporada que empezó en `anio`."""
    codigo = FUENTES[liga].codigo_espn
    if codigo is None:
        raise ValueError(f"{liga} no tiene goleadores en ESPN")
    base = URL_FUTBOL.format(codigo=codigo, anio=anio)
    lideres = _json(f"{base}/types/1/leaders", f"goleadores de {liga}", obtener)

    por_atleta: dict[str, dict] = {}
    for categoria in lideres.get("categories", []):
        estadistica = CATEGORIAS.get(categoria.get("name"))
        if estadistica is None:
            continue
        for lider in categoria.get("leaders", [])[:POR_CATEGORIA]:
            atleta, equipo = _id(lider.get("athlete"), "athletes"), _id(lider.get("team"), "teams")
            if atleta is None or equipo is None:
                continue
            stats = por_atleta.setdefault(atleta, {"equipo": equipo})
            stats[estadistica] = int(lider.get("value") or 0)
            if pj := re.search(r"Matches: (\d+)", lider.get("displayValue", "")):
                stats["pj"] = max(stats.get("pj", 0), int(pj.group(1)))
    if not por_atleta:
        return []

    datos = _json(URL_EQUIPOS.format(codigo=codigo), f"equipos de {liga}", obtener)
    equipos = {
        e["team"]["id"]: e["team"]["displayName"]
        for deporte in datos.get("sports", [])
        for torneo in deporte.get("leagues", [])
        for e in torneo.get("teams", [])
    }

    jugadores = []
    for atleta, stats in por_atleta.items():
        equipo = equipos.get(stats["equipo"])
        if equipo is None:
            continue  # equipo que ya no está en la liga
        nombre = _json(f"{base}/athletes/{atleta}", f"jugador de {liga}", obtener).get(
            "displayName", ""
        )
        if nombre.strip():
            valor = float(stats.get("goles", 0))
            jugadores.append(Jugador(liga, equipo, nombre, Rol.DESTACADO, _detalle(stats), valor))
    jugadores.sort(key=lambda j: (-j.valor, j.nombre))
    logger.info("Goleadores %s %s: %s jugadores", liga, anio, len(jugadores))
    return jugadores
