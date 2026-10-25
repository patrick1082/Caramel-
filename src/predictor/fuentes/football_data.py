"""Historial de fútbol desde los CSV gratuitos de football-data.co.uk."""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Callable
from datetime import date, datetime

import requests

from predictor.ligas import FUENTES
from predictor.modelos import ResultadoHistorico

logger = logging.getLogger(__name__)

URL = "https://football-data.co.uk/mmz4281/{temporada}/{codigo}.csv"
TIEMPO_ESPERA = 30  # segundos

# Estadística → (columna del local, columna del visitante).
EXTRAS = {
    "tiros": ("HS", "AS"),
    "tiros_al_arco": ("HST", "AST"),
    "xg": ("HxG", "AxG"),
    "corners": ("HC", "AC"),
    "amarillas": ("HY", "AY"),
}
# Cuotas promedio previas al partido (local, empate, visitante); BbAv en temporadas viejas.
CUOTAS = (("AvgH", "AvgD", "AvgA"), ("BbAvH", "BbAvD", "BbAvA"))


def _fecha(texto: str) -> date:
    formato = "%d/%m/%Y" if len(texto) == 10 else "%d/%m/%y"
    return datetime.strptime(texto, formato).date()


def _numero(texto: str | None) -> float | None:
    try:
        return float(texto)
    except (TypeError, ValueError):
        return None


def _cuotas(fila: dict) -> tuple[float, float, float] | None:
    for columnas in CUOTAS:
        cuotas = [_numero(fila.get(c)) for c in columnas]
        if all(c is not None and c > 1 for c in cuotas):
            return tuple(cuotas)
    return None


def parsear(liga: str, temporada: str, texto: str) -> list[ResultadoHistorico]:
    resultados = []
    for fila in csv.DictReader(io.StringIO(texto)):
        if not fila.get("HomeTeam") or not (fila.get("FTHG") or "").strip():
            continue  # filas vacías o partidos sin resultado
        extras = {}
        for nombre, (col_local, col_visita) in EXTRAS.items():
            local, visita = _numero(fila.get(col_local)), _numero(fila.get(col_visita))
            if local is not None and visita is not None:
                extras[nombre] = (local, visita)
        resultados.append(
            ResultadoHistorico(
                liga=liga,
                temporada=temporada,
                fecha=_fecha(fila["Date"]),
                local=fila["HomeTeam"],
                visitante=fila["AwayTeam"],
                marcador_local=int(fila["FTHG"]),
                marcador_visitante=int(fila["FTAG"]),
                extras=extras,
                cuotas=_cuotas(fila),
            )
        )
    return resultados


def descargar(
    liga: str, temporada: str, obtener: Callable[..., requests.Response] = requests.get
) -> list[ResultadoHistorico]:
    url = URL.format(temporada=temporada, codigo=FUENTES[liga].codigo_historial)
    try:
        respuesta = obtener(url, timeout=TIEMPO_ESPERA)
    except requests.RequestException as error:
        raise ValueError(f"No se pudo descargar el historial de {liga}: {error}") from None
    if respuesta.status_code == 404:
        logger.info("Sin historial %s %s todavía", liga, temporada)
        return []
    if respuesta.status_code != 200:
        raise ValueError(f"football-data.co.uk respondió con error {respuesta.status_code}")

    resultados = parsear(liga, temporada, respuesta.content.decode("utf-8-sig", "replace"))
    logger.info("Historial %s %s: %s partidos", liga, temporada, len(resultados))
    return resultados
