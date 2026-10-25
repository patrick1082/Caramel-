"""Cuánto apostar: % de la banca según el valor de la apuesta y monto en CLP (regla D1 del hito 5).

Con valor confirmado se usa ¼ de Kelly con la probabilidad más prudente (mercado o modelo), entre
un piso y un tope. "Solo modelo" perdió dinero en el backtest, así que va con un % fijo menor que
una apuesta sin valor. El tope por apuesta evita que una racha mala se lleve la banca.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from predictor.modelos import Valor

if TYPE_CHECKING:
    from predictor.valor import Valoracion

FRACCION_KELLY = 0.25
PISO = 0.01  # Mínimo con valor confirmado.
TOPE = 0.03  # Máximo de la banca en una sola apuesta.
SOLO_MODELO = 0.005
SIN_VALOR = 0.01
REDONDEO = 100  # CLP
MONTO_MINIMO = 100  # CLP; bajo esto, no apostar.


def kelly(prob: float, cuota: Decimal | float) -> float:
    """Fracción de Kelly completa; 0 si la apuesta no tiene EV positivo."""
    cuota = float(cuota)
    return max(0.0, (prob * cuota - 1) / (cuota - 1))


def fraccion(valoracion: Valoracion, cuota: Decimal | float) -> float:
    """Parte de la banca (0–1) a apostar."""
    if valoracion.valor is Valor.CONFIRMADO:
        probs = [p for p in (valoracion.prob_mercado, valoracion.prob_modelo) if p is not None]
        sugerida = FRACCION_KELLY * min(kelly(p, cuota) for p in probs)
        return min(TOPE, max(PISO, sugerida))
    if valoracion.valor is Valor.MODELO:
        return SOLO_MODELO
    return SIN_VALOR


def monto(saldo: int, parte: float) -> int:
    """Monto en CLP redondeado hacia abajo a la centena; 0 (no apostar) si queda bajo el mínimo."""
    redondeado = int(max(0, saldo) * parte // REDONDEO) * REDONDEO
    return redondeado if redondeado >= MONTO_MINIMO else 0
