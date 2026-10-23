"""Reglas de la bitácora: registro y liquidación de apuestas, saldo del fondo y métricas."""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from predictor.modelos import Apuesta, Estado, Movimiento, TipoMovimiento
from predictor.repositorio import Repositorio

logger = logging.getLogger(__name__)

FONDO_INICIAL_POR_DEFECTO = 10_000
_CLAVE_FONDO_INICIAL = "fondo_inicial"


@dataclass(frozen=True)
class Metricas:
    total: int = 0
    pendientes: int = 0
    ganadas: int = 0
    perdidas: int = 0
    nulas: int = 0
    apostado: int = 0  # Solo ganadas y perdidas: las nulas devuelven el monto.
    resultado: int = 0

    @property
    def roi(self) -> float | None:
        return self.resultado / self.apostado if self.apostado else None

    @property
    def acierto(self) -> float | None:
        decididas = self.ganadas + self.perdidas
        return self.ganadas / decididas if decididas else None


@dataclass(frozen=True)
class Resumen:
    fondo_inicial: int
    depositos: int
    retiros: int
    en_juego: int
    saldo: int
    colocadas: Metricas
    no_colocadas: Metricas
    por_deporte: dict[str, Metricas]
    por_liga: dict[str, Metricas]

    @property
    def ganancia(self) -> int:
        return self.colocadas.resultado


def calcular_resultado(apuesta: Apuesta, estado: Estado) -> int:
    if estado is Estado.GANADA:
        return apuesta.pago_bruto() - apuesta.monto
    if estado is Estado.PERDIDA:
        return -apuesta.monto
    if estado is Estado.NULA:
        return 0
    raise ValueError(f"No hay resultado para una apuesta en estado {estado}")


def calcular_metricas(apuestas: Iterable[Apuesta]) -> Metricas:
    apuestas = list(apuestas)
    conteo = Counter(a.estado for a in apuestas)
    decididas = [a for a in apuestas if a.estado in (Estado.GANADA, Estado.PERDIDA)]
    return Metricas(
        total=len(apuestas),
        pendientes=conteo[Estado.PENDIENTE],
        ganadas=conteo[Estado.GANADA],
        perdidas=conteo[Estado.PERDIDA],
        nulas=conteo[Estado.NULA],
        apostado=sum(a.monto for a in decididas),
        resultado=sum(a.resultado_neto for a in apuestas if a.liquidada),
    )


def _agrupar(apuestas: Iterable[Apuesta], clave: Callable[[Apuesta], str]) -> dict[str, Metricas]:
    grupos: dict[str, list[Apuesta]] = defaultdict(list)
    for apuesta in apuestas:
        grupos[clave(apuesta)].append(apuesta)
    return {nombre: calcular_metricas(grupo) for nombre, grupo in sorted(grupos.items())}


class Bitacora:
    def __init__(self, repo: Repositorio) -> None:
        self._repo = repo

    # --- Fondo ---

    @property
    def fondo_inicial(self) -> int:
        valor = self._repo.obtener_config(_CLAVE_FONDO_INICIAL)
        return int(valor) if valor is not None else FONDO_INICIAL_POR_DEFECTO

    def fijar_fondo_inicial(self, monto: int) -> None:
        if monto < 0:
            raise ValueError("El fondo inicial no puede ser negativo")
        self._repo.fijar_config(_CLAVE_FONDO_INICIAL, str(monto))
        logger.info("Fondo inicial fijado en %s", monto)

    def saldo(self) -> int:
        return self.resumen().saldo

    # --- Consultas ---

    def apuestas(self) -> list[Apuesta]:
        return self._repo.listar_apuestas()

    def movimientos(self) -> list[Movimiento]:
        return self._repo.listar_movimientos()

    # --- Apuestas ---

    def registrar_apuesta(self, apuesta: Apuesta) -> Apuesta:
        if apuesta.id is not None:
            raise ValueError(f"La apuesta #{apuesta.id} ya está registrada")
        if apuesta.colocada:
            disponible = self.saldo()
            if apuesta.monto > disponible:
                raise ValueError(
                    f"Saldo insuficiente: disponible {disponible}, apuesta {apuesta.monto}"
                )
        guardada = self._repo.agregar_apuesta(apuesta)
        logger.info("Apuesta #%s registrada (%s)", guardada.id, guardada.partido)
        return guardada

    def liquidar(
        self, apuesta_id: int, estado: Estado, resultado_neto: int | None = None
    ) -> Apuesta:
        estado = Estado(estado)
        if estado is Estado.PENDIENTE:
            raise ValueError("Para volver una apuesta a pendiente usa revertir()")
        apuesta = self._obtener(apuesta_id)
        if apuesta.liquidada:
            raise ValueError(f"La apuesta #{apuesta_id} ya está liquidada")
        if resultado_neto is None:
            resultado_neto = calcular_resultado(apuesta, estado)
        liquidada = replace(apuesta, estado=estado, resultado_neto=resultado_neto)
        self._repo.actualizar_apuesta(liquidada)
        logger.info("Apuesta #%s liquidada: %s (%s)", apuesta_id, estado, resultado_neto)
        return liquidada

    def revertir(self, apuesta_id: int) -> Apuesta:
        apuesta = self._obtener(apuesta_id)
        if not apuesta.liquidada:
            raise ValueError(f"La apuesta #{apuesta_id} ya está pendiente")
        revertida = replace(apuesta, estado=Estado.PENDIENTE, resultado_neto=None)
        self._repo.actualizar_apuesta(revertida)
        logger.info("Apuesta #%s revertida a pendiente", apuesta_id)
        return revertida

    def eliminar_apuesta(self, apuesta_id: int) -> None:
        self._repo.eliminar_apuesta(apuesta_id)
        logger.info("Apuesta #%s eliminada", apuesta_id)

    def _obtener(self, apuesta_id: int) -> Apuesta:
        apuesta = self._repo.obtener_apuesta(apuesta_id)
        if apuesta is None:
            raise ValueError(f"La apuesta #{apuesta_id} no existe")
        return apuesta

    # --- Movimientos ---

    def registrar_movimiento(self, movimiento: Movimiento) -> Movimiento:
        if movimiento.tipo is TipoMovimiento.RETIRO:
            disponible = self.saldo()
            if movimiento.monto > disponible:
                raise ValueError(
                    f"Saldo insuficiente: disponible {disponible}, retiro {movimiento.monto}"
                )
        guardado = self._repo.agregar_movimiento(movimiento)
        logger.info("Movimiento #%s: %s %s", guardado.id, guardado.tipo, guardado.monto)
        return guardado

    # --- Resumen ---

    def resumen(self) -> Resumen:
        apuestas = self.apuestas()
        movimientos = self.movimientos()
        colocadas = [a for a in apuestas if a.colocada]

        depositos = sum(m.monto for m in movimientos if m.tipo is TipoMovimiento.DEPOSITO)
        retiros = sum(m.monto for m in movimientos if m.tipo is TipoMovimiento.RETIRO)
        en_juego = sum(a.monto for a in colocadas if not a.liquidada)
        metricas_colocadas = calcular_metricas(colocadas)
        fondo_inicial = self.fondo_inicial

        return Resumen(
            fondo_inicial=fondo_inicial,
            depositos=depositos,
            retiros=retiros,
            en_juego=en_juego,
            saldo=fondo_inicial + depositos - retiros + metricas_colocadas.resultado - en_juego,
            colocadas=metricas_colocadas,
            no_colocadas=calcular_metricas(a for a in apuestas if not a.colocada),
            por_deporte=_agrupar(colocadas, lambda a: a.deporte.value),
            por_liga=_agrupar(colocadas, lambda a: a.liga),
        )
