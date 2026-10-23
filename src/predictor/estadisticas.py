"""Estadísticas de forma de un equipo y enfrentamientos directos a partir del historial."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import fmean

from predictor.modelos import ResultadoHistorico

FORMA = 5  # partidos que muestra la racha
VENTANA = 10  # partidos que se promedian


@dataclass(frozen=True)
class Promedios:
    jugados: int
    a_favor: float
    en_contra: float


@dataclass(frozen=True)
class Estadisticas:
    equipo: str
    jugados: int
    ganados: int
    empatados: int
    perdidos: int
    forma: str  # "G", "E" o "P" por partido, el más reciente primero.
    ultimos: Promedios
    de_local: Promedios | None
    de_visita: Promedios | None
    # Estadística → (promedio propio, promedio del rival) en los últimos partidos.
    extras: dict[str, tuple[float, float]] = field(default_factory=dict)


def _perspectiva(equipo: str, r: ResultadoHistorico) -> tuple[int, int, int]:
    """(goles a favor, en contra, índice 0/1 del equipo en las tuplas de extras)."""
    if r.local == equipo:
        return r.marcador_local, r.marcador_visitante, 0
    return r.marcador_visitante, r.marcador_local, 1


def _letra(a_favor: int, en_contra: int) -> str:
    if a_favor > en_contra:
        return "G"
    return "E" if a_favor == en_contra else "P"


def _promedios(equipo: str, partidos: Sequence[ResultadoHistorico]) -> Promedios | None:
    if not partidos:
        return None
    marcadores = [_perspectiva(equipo, r)[:2] for r in partidos]
    return Promedios(
        jugados=len(partidos),
        a_favor=round(fmean(f for f, _ in marcadores), 2),
        en_contra=round(fmean(c for _, c in marcadores), 2),
    )


def _extras(equipo: str, partidos: Sequence[ResultadoHistorico]) -> dict[str, tuple[float, float]]:
    valores: dict[str, list[tuple[float, float]]] = {}
    for r in partidos:
        lado = _perspectiva(equipo, r)[2]
        for nombre, par in r.extras.items():
            valores.setdefault(nombre, []).append((par[lado], par[1 - lado]))
    return {
        nombre: (round(fmean(p for p, _ in pares), 2), round(fmean(r for _, r in pares), 2))
        for nombre, pares in valores.items()
    }


def calcular(equipo: str, historial: Sequence[ResultadoHistorico]) -> Estadisticas | None:
    """Resume el historial de `equipo`. `historial` debe venir ordenado por fecha ascendente."""
    propios = [r for r in historial if equipo in (r.local, r.visitante)]
    if not propios:
        return None
    recientes = propios[::-1]
    letras = [_letra(*_perspectiva(equipo, r)[:2]) for r in recientes]
    ultimos = recientes[:VENTANA]
    return Estadisticas(
        equipo=equipo,
        jugados=len(propios),
        ganados=letras.count("G"),
        empatados=letras.count("E"),
        perdidos=letras.count("P"),
        forma="".join(letras[:FORMA]),
        ultimos=_promedios(equipo, ultimos),
        de_local=_promedios(equipo, [r for r in recientes if r.local == equipo][:VENTANA]),
        de_visita=_promedios(equipo, [r for r in recientes if r.visitante == equipo][:VENTANA]),
        extras=_extras(equipo, ultimos),
    )


def cara_a_cara(
    local: str, visitante: str, historial: Sequence[ResultadoHistorico], ultimos: int = FORMA
) -> list[ResultadoHistorico]:
    """Últimos enfrentamientos entre ambos equipos en cualquier cancha, el más reciente primero."""
    pareja = {local, visitante}
    directos = [r for r in historial if {r.local, r.visitante} == pareja]
    return directos[::-1][:ultimos]
