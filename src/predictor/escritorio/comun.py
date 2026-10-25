"""Contexto compartido por las páginas y formato de montos, porcentajes y filas de cuotas."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from predictor.bitacora import Bitacora
from predictor.cartelera import Cartelera
from predictor.fuentes.odds_api import ClienteOddsApi
from predictor.ligas import ZONA_CHILE
from predictor.modelos import Apuesta, Mercado
from predictor.repositorio import Repositorio
from predictor.valor import Umbrales, Valoracion, clasificar

AVISO_VALOR = (
    "Confirmado (punto verde): el modelo ve valor en la cuota de Betano y el mercado (Pinnacle "
    "sin margen) no lo contradice. Solo modelo (punto ámbar): el mercado no está de acuerdo; en "
    "el backtest de fútbol 2025-26 esa estrategia perdió dinero. Las cuotas son de Betano UK: "
    "confirma la de Betano Chile antes de apostar. El valor no es una garantía."
)


def ruta_bd() -> Path:
    return Path(os.environ.get("PREDICTOR_DB", "data/bitacora.db"))


def clp(monto: int) -> str:
    signo = "-" if monto < 0 else ""
    return f"{signo}${abs(monto):,}".replace(",", ".")


def pct(valor: float | None) -> str:
    return "—" if valor is None else f"{valor:.1%}"


def hora_chile(momento: datetime) -> str:
    return f"{momento.astimezone(ZONA_CHILE):%H:%M}"


def registrar(
    bitacora: Bitacora, valoracion: Valoracion | None, umbrales: Umbrales, **datos
) -> None:
    """Registra la apuesta; si viene de la cartelera, recalcula el valor con la cuota escrita."""
    if valoracion is not None:
        datos["prob_modelo"] = valoracion.prob_modelo
        datos["valor"] = clasificar(
            datos["cuota"], valoracion.prob_modelo, valoracion.prob_mercado, umbrales
        )
    bitacora.registrar_apuesta(Apuesta(**datos))


def describir_fila(valoracion: Valoracion) -> tuple[str, str]:
    """Mercado y selección de una fila de cuotas, como se escriben en la bitácora."""
    fila = valoracion.fila
    mercado = fila.mercado.etiqueta
    if fila.linea is not None:
        linea = f"{fila.linea:+g}" if fila.mercado is Mercado.HANDICAP else f"{fila.linea:g}"
        mercado += f" {linea}"
    return mercado, "Empate" if fila.seleccion == "Draw" else fila.seleccion


class Contexto(QObject):
    """Dominio compartido por la ventana. `cambiado` avisa a las páginas que deben refrescarse."""

    cambiado = Signal()
    mensaje = Signal(str, bool)  # texto, es_error

    def __init__(self, repo: Repositorio, cartelera: Cartelera, ruta: Path) -> None:
        super().__init__()
        self.repo = repo
        self.bitacora = Bitacora(repo)
        self.cartelera = cartelera
        self.ruta = ruta

    @classmethod
    def desde_entorno(cls) -> Contexto:
        ruta = ruta_bd()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        repo = Repositorio(ruta)
        clave = os.environ.get("ODDS_API_KEY", "").strip()
        return cls(repo, Cartelera(repo, ClienteOddsApi(clave) if clave else None), ruta)

    def ejecutar(self, mensaje: str, accion: Callable, *args, **kwargs) -> bool:
        """Ejecuta una acción del dominio; avisa el error de validación o refresca las páginas."""
        try:
            accion(*args, **kwargs)
        except ValueError as error:
            self.mensaje.emit(str(error), True)
            return False
        self.mensaje.emit(mensaje, False)
        self.cambiado.emit()
        return True
