"""Medición del modelo: cruce de predicciones con resultados, métricas, línea base y backtest."""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from predictor.ligas import FUENTES, ZONA_CHILE
from predictor.modelos import Deporte, Prediccion, ResultadoHistorico
from predictor.nombres import emparejar
from predictor.prediccion import ajustar

TOTAL = "Total"
MINIMO_BACKTEST = 50  # partidos previos de la liga antes de empezar a predecir

Probabilidades = tuple[float, float | None, float]  # local, empate (None en la NBA), visita


def _desenlace(resultado: ResultadoHistorico) -> int:
    """0 local, 1 empate, 2 visita."""
    if resultado.marcador_local > resultado.marcador_visitante:
        return 0
    return 1 if resultado.marcador_local == resultado.marcador_visitante else 2


def _favorito(probs: Probabilidades) -> int:
    local, empate, visita = probs
    return max((0, 1, 2), key=lambda i: (local, -1.0 if empate is None else empate, visita)[i])


def _brier(probs: Probabilidades, desenlace: int) -> float:
    return sum((p - (i == desenlace)) ** 2 for i, p in enumerate(probs) if p is not None)


class LineaBase:
    """Modelo ingenuo: tasas de local, empate y visita de la liga antes de cada fecha."""

    def __init__(self, historial: Iterable[ResultadoHistorico]):
        por_liga: dict[str, list[ResultadoHistorico]] = defaultdict(list)
        for r in historial:
            por_liga[r.liga].append(r)
        self._fechas: dict[str, list[date]] = {}
        self._acumulados: dict[str, list[tuple[int, int, int]]] = {}
        for liga, resultados in por_liga.items():
            resultados.sort(key=lambda r: r.fecha)
            conteo, acumulados = [0, 0, 0], [(0, 0, 0)]
            for r in resultados:
                conteo[_desenlace(r)] += 1
                acumulados.append(tuple(conteo))
            self._fechas[liga] = [r.fecha for r in resultados]
            self._acumulados[liga] = acumulados

    def probabilidades(self, liga: str, fecha: date) -> Probabilidades:
        hasta = bisect.bisect_left(self._fechas.get(liga, []), fecha)
        local, empate, visita = self._acumulados[liga][hasta] if hasta else (0, 0, 0)
        if FUENTES[liga].deporte is Deporte.NBA:
            jugados = local + visita
            return (local / jugados, None, visita / jugados) if jugados else (0.5, None, 0.5)
        jugados = local + empate + visita
        if not jugados:
            return (1 / 3, 1 / 3, 1 / 3)
        return (local / jugados, empate / jugados, visita / jugados)


@dataclass(frozen=True)
class Evaluada:
    prediccion: Prediccion
    resultado: ResultadoHistorico
    base: Probabilidades

    @property
    def probabilidades(self) -> Probabilidades:
        p = self.prediccion
        return (p.prob_local, p.prob_empate, p.prob_visitante)

    @property
    def desenlace(self) -> int:
        return _desenlace(self.resultado)

    @property
    def acierto(self) -> bool:
        return _favorito(self.probabilidades) == self.desenlace

    @property
    def error(self) -> float:
        """Error absoluto medio por equipo en goles o puntos."""
        p, r = self.prediccion, self.resultado
        return (
            abs(p.esperado_local - r.marcador_local)
            + abs(p.esperado_visitante - r.marcador_visitante)
        ) / 2

    @property
    def acierto_linea(self) -> bool | None:
        """Over/under en la línea de Betano; None sin línea o si el total la iguala."""
        p, total = (
            self.prediccion,
            self.resultado.marcador_local + self.resultado.marcador_visitante,
        )
        if p.linea_total is None or p.prob_over is None or total == p.linea_total:
            return None
        return (p.prob_over > 0.5) == (total > p.linea_total)


@dataclass
class MetricasModelo:
    partidos: int = 0
    aciertos: int = 0
    brier_suma: float = 0.0
    error_suma: float = 0.0
    lineas: int = 0
    aciertos_linea: int = 0
    aciertos_base: int = 0
    brier_base_suma: float = 0.0

    @property
    def acierto(self) -> float | None:
        return self.aciertos / self.partidos if self.partidos else None

    @property
    def brier(self) -> float | None:
        return self.brier_suma / self.partidos if self.partidos else None

    @property
    def error_medio(self) -> float | None:
        return self.error_suma / self.partidos if self.partidos else None

    @property
    def acierto_over_under(self) -> float | None:
        return self.aciertos_linea / self.lineas if self.lineas else None

    @property
    def acierto_base(self) -> float | None:
        return self.aciertos_base / self.partidos if self.partidos else None

    @property
    def brier_base(self) -> float | None:
        return self.brier_base_suma / self.partidos if self.partidos else None


def calcular_metricas(evaluadas: Iterable[Evaluada]) -> MetricasModelo:
    metricas = MetricasModelo()
    for e in evaluadas:
        metricas.partidos += 1
        metricas.aciertos += e.acierto
        metricas.brier_suma += _brier(e.probabilidades, e.desenlace)
        metricas.error_suma += e.error
        if e.acierto_linea is not None:
            metricas.lineas += 1
            metricas.aciertos_linea += e.acierto_linea
        metricas.aciertos_base += _favorito(e.base) == e.desenlace
        metricas.brier_base_suma += _brier(e.base, e.desenlace)
    return metricas


def por_liga(evaluadas: Iterable[Evaluada]) -> dict[str, MetricasModelo]:
    """Métricas de cada liga, en orden alfabético, más `TOTAL` al final."""
    evaluadas = list(evaluadas)
    grupos: dict[str, list[Evaluada]] = defaultdict(list)
    for e in evaluadas:
        grupos[e.prediccion.liga].append(e)
    metricas = {liga: calcular_metricas(grupo) for liga, grupo in sorted(grupos.items())}
    metricas[TOTAL] = calcular_metricas(evaluadas)
    return metricas


def cruzar(
    predicciones: Iterable[Prediccion], historial: Sequence[ResultadoHistorico]
) -> list[Evaluada]:
    """Une cada predicción con su resultado: misma liga, fecha ±1 día (Chile) y nombres."""
    por_fecha: dict[tuple[str, date], list[ResultadoHistorico]] = defaultdict(list)
    for r in historial:
        por_fecha[(r.liga, r.fecha)].append(r)
    base = LineaBase(historial)
    evaluadas = []
    for p in predicciones:
        dia = p.inicio.astimezone(ZONA_CHILE).date()
        candidatos = [
            r for d in (-1, 0, 1) for r in por_fecha.get((p.liga, dia + timedelta(days=d)), [])
        ]
        for r in candidatos:
            if emparejar(p.local, [c.local for c in candidatos]) != r.local:
                continue
            if emparejar(p.visitante, [c.visitante for c in candidatos]) != r.visitante:
                continue
            evaluadas.append(Evaluada(p, r, base.probabilidades(p.liga, r.fecha)))
            break
    return evaluadas


def backtest(
    liga: str,
    historial: Sequence[ResultadoHistorico],
    desde: date | None = None,
    minimo: int = MINIMO_BACKTEST,
) -> list[Evaluada]:
    """Walk-forward: cada fecha se predice solo con los partidos anteriores de la liga.

    Empieza en `desde` (o al principio) y cuando la liga ya tiene `minimo` partidos previos.
    """
    deporte = FUENTES[liga].deporte
    partidos = sorted((r for r in historial if r.liga == liga), key=lambda r: r.fecha)
    base = LineaBase(partidos)
    por_fecha: dict[date, list[ResultadoHistorico]] = defaultdict(list)
    for r in partidos:
        por_fecha[r.fecha].append(r)
    evaluadas, previos = [], 0
    for fecha in sorted(por_fecha):
        del_dia = por_fecha[fecha]
        if previos >= minimo and (desde is None or fecha >= desde):
            ajuste = ajustar(deporte, partidos, fecha)
            momento = datetime.combine(fecha, time(12), ZONA_CHILE)
            for r in del_dia:
                pronostico = ajuste.pronosticar(r.local, r.visitante)
                if pronostico is None:
                    continue
                prediccion = pronostico.a_prediccion(
                    f"backtest:{liga}:{fecha}:{r.local}:{r.visitante}",
                    liga,
                    r.local,
                    r.visitante,
                    momento,
                    momento,
                )
                evaluadas.append(Evaluada(prediccion, r, base.probabilidades(liga, fecha)))
        previos += len(del_dia)
    return evaluadas
