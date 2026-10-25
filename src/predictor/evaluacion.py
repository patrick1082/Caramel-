"""Medición del modelo: cruce de predicciones con resultados, métricas, línea base y backtest."""

from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from predictor.ligas import FUENTES, ZONA_CHILE
from predictor.modelos import (
    Deporte,
    Fuente,
    Ganador,
    Prediccion,
    PrediccionPropia,
    Pronostico3,
    ResultadoHistorico,
)
from predictor.nombres import emparejar
from predictor.prediccion import ajustar
from predictor.valor import POR_DEFECTO, Umbrales, ev

TOTAL = "Total"
PROPIA = "Mía"
BASE = "Línea base"
_INDICE = {Ganador.LOCAL: 0, Ganador.EMPATE: 1, Ganador.VISITANTE: 2}
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


class _Buscador:
    """Encuentra el resultado de un partido: misma liga, fecha ±1 día (Chile) y nombres."""

    def __init__(self, historial: Iterable[ResultadoHistorico]):
        self._por_fecha: dict[tuple[str, date], list[ResultadoHistorico]] = defaultdict(list)
        for r in historial:
            self._por_fecha[(r.liga, r.fecha)].append(r)

    def resultado(
        self, liga: str, local: str, visitante: str, inicio: datetime
    ) -> ResultadoHistorico | None:
        dia = inicio.astimezone(ZONA_CHILE).date()
        candidatos = [
            r for d in (-1, 0, 1) for r in self._por_fecha.get((liga, dia + timedelta(days=d)), [])
        ]
        for r in candidatos:
            if emparejar(local, [c.local for c in candidatos]) != r.local:
                continue
            if emparejar(visitante, [c.visitante for c in candidatos]) != r.visitante:
                continue
            return r
        return None


def cruzar(
    predicciones: Iterable[Prediccion], historial: Sequence[ResultadoHistorico]
) -> list[Evaluada]:
    """Une cada predicción con su resultado: misma liga, fecha ±1 día (Chile) y nombres."""
    buscador, base = _Buscador(historial), LineaBase(historial)
    evaluadas = []
    for p in predicciones:
        if r := buscador.resultado(p.liga, p.local, p.visitante, p.inicio):
            evaluadas.append(Evaluada(p, r, base.probabilidades(p.liga, r.fecha)))
    return evaluadas


@dataclass
class MetricasFuente:
    partidos: int = 0
    aciertos: int = 0
    brier_suma: float | None = 0.0  # None si la fuente solo elige ganador (la propia)

    @property
    def acierto(self) -> float | None:
        return self.aciertos / self.partidos if self.partidos else None

    @property
    def brier(self) -> float | None:
        if self.brier_suma is None or not self.partidos:
            return None
        return self.brier_suma / self.partidos

    def sumar(self, probs: Probabilidades | None, acierto: bool, desenlace: int) -> None:
        self.partidos += 1
        self.aciertos += acierto
        if self.brier_suma is not None and probs is not None:
            self.brier_suma += _brier(probs, desenlace)


def por_fuente(
    evaluadas: Iterable[Evaluada],
    pronosticos: Iterable[Pronostico3],
    propias: Iterable[PrediccionPropia],
    historial: Sequence[ResultadoHistorico],
) -> dict[str, MetricasFuente]:
    """Acierto y Brier de cada opinión del 1X2 sobre los partidos ya jugados.

    El modelo, el mercado y ESPN se miden en los partidos que el modelo predijo; la propia
    se cruza con el historial por su cuenta. Solo se incluyen las fuentes con partidos.
    """
    evaluadas = list(evaluadas)
    resultados = {e.prediccion.partido_id: e.resultado for e in evaluadas}
    metricas = {
        PROPIA: MetricasFuente(brier_suma=None),
        **{f.etiqueta: MetricasFuente() for f in (Fuente.MODELO, Fuente.ESPN, Fuente.MERCADO)},
        BASE: MetricasFuente(),
    }

    buscador = _Buscador(historial)
    for propia in propias:
        r = resultados.get(propia.partido_id) or buscador.resultado(
            propia.liga, propia.local, propia.visitante, propia.inicio
        )
        if r is not None:
            desenlace = _desenlace(r)
            metricas[PROPIA].sumar(None, _INDICE[propia.ganador] == desenlace, desenlace)
    for e in evaluadas:
        metricas[Fuente.MODELO.etiqueta].sumar(e.probabilidades, e.acierto, e.desenlace)
        metricas[BASE].sumar(e.base, _favorito(e.base) == e.desenlace, e.desenlace)
    for p in pronosticos:
        if p.fuente is Fuente.MODELO or (r := resultados.get(p.partido_id)) is None:
            continue  # el modelo ya se midió con su predicción completa
        probs, desenlace = (p.prob_local, p.prob_empate, p.prob_visitante), _desenlace(r)
        metricas[p.fuente.etiqueta].sumar(probs, _favorito(probs) == desenlace, desenlace)
    return {fuente: m for fuente, m in metricas.items() if m.partidos}


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


@dataclass
class ResultadoValor:
    """Apostar 1 unidad a la cuota previa (promedio de casas) cuando el modelo ve valor."""

    partidos: int = 0  # partidos con predicción y cuotas
    apuestas: int = 0
    aciertos: int = 0
    ganancia: float = 0.0
    ganancia_favorito: float = 0.0  # comparación: apostar siempre a la cuota más baja

    @property
    def roi(self) -> float | None:
        return self.ganancia / self.apuestas if self.apuestas else None

    @property
    def acierto(self) -> float | None:
        return self.aciertos / self.apuestas if self.apuestas else None

    @property
    def roi_favorito(self) -> float | None:
        return self.ganancia_favorito / self.partidos if self.partidos else None


def backtest_valor(
    evaluadas: Iterable[Evaluada], umbrales: Umbrales = POR_DEFECTO
) -> dict[str, ResultadoValor]:
    """Estrategia de valor sobre un backtest: por partido, la selección de mayor EV del modelo.

    Solo cuentan los partidos con cuotas históricas (fútbol). Devuelve cada liga y `TOTAL`.
    """
    resultados: dict[str, ResultadoValor] = defaultdict(ResultadoValor)
    for e in evaluadas:
        if e.resultado.cuotas is None:
            continue
        cuotas, desenlace = e.resultado.cuotas, e.desenlace
        for clave in (e.prediccion.liga, TOTAL):
            resultado = resultados[clave]
            resultado.partidos += 1
            favorito = min(range(3), key=lambda i: cuotas[i])
            resultado.ganancia_favorito += cuotas[favorito] - 1 if favorito == desenlace else -1
            candidatas = [
                (ev(p, cuotas[i]), i)
                for i, p in enumerate(e.probabilidades)
                if p is not None and cuotas[i] <= umbrales.cuota_maxima
            ]
            mejor = max(candidatas, default=None)
            if mejor is None or mejor[0] < umbrales.modelo:
                continue
            resultado.apuestas += 1
            if mejor[1] == desenlace:
                resultado.aciertos += 1
                resultado.ganancia += cuotas[mejor[1]] - 1
            else:
                resultado.ganancia -= 1
    return {clave: resultados[clave] for clave in sorted(resultados, key=lambda c: (c == TOTAL, c))}
