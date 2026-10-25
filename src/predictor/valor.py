"""Apuestas de valor: probabilidades sin margen, valor esperado y marca de cada cuota."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from predictor.modelos import Mercado, Prediccion, Valor

if TYPE_CHECKING:  # cartelera importa este módulo
    from predictor.cartelera import FilaComparacion

UMBRAL_MODELO = 0.05  # EV mínimo según el modelo
CUOTA_MAXIMA = 5.0  # sobre esta cuota el modelo está poco calibrado
UMBRAL_MERCADO = 0.0  # EV mínimo según el mercado para confirmar

Clave = tuple[Mercado, str, Decimal | None]


@dataclass(frozen=True)
class Umbrales:
    modelo: float = UMBRAL_MODELO
    cuota_maxima: float = CUOTA_MAXIMA
    mercado: float = UMBRAL_MERCADO

    def __post_init__(self) -> None:
        if not 0 <= self.modelo <= 1 or not 0 <= self.mercado <= 1:
            raise ValueError("Los umbrales de valor deben estar entre 0 % y 100 %")
        if self.cuota_maxima <= 1:
            raise ValueError("La cuota máxima debe ser mayor a 1.00")


POR_DEFECTO = Umbrales()


@dataclass(frozen=True)
class Valoracion:
    fila: FilaComparacion
    prob_modelo: float | None
    prob_mercado: float | None
    ev: float | None  # EV de la cuota de Betano según el modelo
    valor: Valor


def sin_margen(cuotas: Sequence[Decimal | float]) -> list[float]:
    """Probabilidades implícitas normalizadas para que sumen 1 (método proporcional)."""
    if len(cuotas) < 2 or any(c <= 1 for c in cuotas):
        raise ValueError("Se necesitan al menos dos cuotas mayores a 1.00")
    implicitas = [1 / float(c) for c in cuotas]
    total = sum(implicitas)
    return [p / total for p in implicitas]


def ev(prob: float, cuota: Decimal | float) -> float:
    """Ganancia esperada por peso apostado."""
    return prob * float(cuota) - 1


def prob_modelo(fila: FilaComparacion, prediccion: Prediccion) -> float | None:
    if fila.mercado is Mercado.GANADOR:
        return {
            prediccion.local: prediccion.prob_local,
            "Draw": prediccion.prob_empate,
            prediccion.visitante: prediccion.prob_visitante,
        }.get(fila.seleccion)
    linea = None if fila.linea is None else float(fila.linea)
    for p in prediccion.lineas:
        if (p.mercado, p.seleccion, p.linea) == (fila.mercado, fila.seleccion, linea):
            return p.prob
    return None


def _clave(fila: FilaComparacion) -> Clave:
    return (fila.mercado, fila.seleccion, fila.linea)


def probabilidades_mercado(filas: Sequence[FilaComparacion], local: str) -> dict[Clave, float]:
    """Probabilidad sin margen de cada selección: Pinnacle o, si le falta, el promedio.

    Se agrupan las selecciones complementarias: el 1X2 completo, Over/Under de la misma
    línea y el hándicap del local con el opuesto del visitante (-5.5 con +5.5).
    """
    grupos: dict[tuple, list[FilaComparacion]] = {}
    for fila in filas:
        if fila.mercado is Mercado.GANADOR:
            grupo = (fila.mercado,)
        elif fila.linea is None:
            continue
        elif fila.mercado is Mercado.HANDICAP:
            grupo = (fila.mercado, fila.linea if fila.seleccion == local else -fila.linea)
        else:
            grupo = (fila.mercado, fila.linea)
        grupos.setdefault(grupo, []).append(fila)

    probs = {}
    for grupo in grupos.values():
        if len(grupo) < 2:
            continue
        pinnacle = [f.pinnacle for f in grupo]
        cuotas = pinnacle if None not in pinnacle else [f.promedio for f in grupo]
        for fila, prob in zip(grupo, sin_margen(cuotas), strict=True):
            probs[_clave(fila)] = prob
    return probs


def clasificar(
    cuota: Decimal | None,
    prob_modelo: float | None,
    prob_mercado: float | None,
    umbrales: Umbrales = POR_DEFECTO,
) -> Valor:
    """Valor del modelo si su EV supera el umbral; confirmado si el mercado tampoco lo niega."""
    if cuota is None or prob_modelo is None or float(cuota) > umbrales.cuota_maxima:
        return Valor.NINGUNO
    if ev(prob_modelo, cuota) < umbrales.modelo:
        return Valor.NINGUNO
    if prob_mercado is not None and ev(prob_mercado, cuota) >= umbrales.mercado:
        return Valor.CONFIRMADO
    return Valor.MODELO


def valorar(
    filas: Sequence[FilaComparacion],
    prediccion: Prediccion | None,
    local: str,
    umbrales: Umbrales = POR_DEFECTO,
) -> list[Valoracion]:
    """Una valoración por fila de cuotas, en el mismo orden."""
    mercado = probabilidades_mercado(filas, local)
    valoraciones = []
    for fila in filas:
        p_modelo = prob_modelo(fila, prediccion) if prediccion is not None else None
        p_mercado = mercado.get(_clave(fila))
        valoraciones.append(
            Valoracion(
                fila=fila,
                prob_modelo=p_modelo,
                prob_mercado=p_mercado,
                ev=ev(p_modelo, fila.betano) if p_modelo and fila.betano else None,
                valor=clasificar(fila.betano, p_modelo, p_mercado, umbrales),
            )
        )
    return valoraciones


PROB_SUGERIDA = 0.55  # Acierto estimado mínimo de una apuesta sugerida.


def prob_estimada(valoracion: Valoracion) -> float | None:
    """Promedio del modelo y del mercado (Pinnacle sin margen); si falta uno, el otro."""
    probs = [p for p in (valoracion.prob_modelo, valoracion.prob_mercado) if p is not None]
    return sum(probs) / len(probs) if probs else None


def sugerir(
    valoraciones: Sequence[Valoracion], minimo: float = PROB_SUGERIDA
) -> tuple[Valoracion, float] | None:
    """Entre las apuestas con acierto estimado ≥ `minimo`, la de mayor EV estimado."""
    candidatas = []
    for valoracion in valoraciones:
        prob = prob_estimada(valoracion)
        if prob is not None and prob >= minimo:
            cuota = valoracion.fila.betano or valoracion.fila.promedio
            candidatas.append((ev(prob, cuota), prob, valoracion))
    if not candidatas:
        return None
    _, prob, valoracion = max(candidatas, key=lambda c: (c[0], c[1]))
    return valoracion, prob
