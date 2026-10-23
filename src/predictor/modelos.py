"""Entidades del dominio: apuestas, movimientos del fondo y sus validaciones."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum


class Deporte(StrEnum):
    NBA = "NBA"
    FUTBOL = "Futbol"


class Estado(StrEnum):
    PENDIENTE = "pendiente"
    GANADA = "ganada"
    PERDIDA = "perdida"
    NULA = "nula"


class TipoMovimiento(StrEnum):
    DEPOSITO = "deposito"
    RETIRO = "retiro"


LIGAS: dict[Deporte, tuple[str, ...]] = {
    Deporte.NBA: ("NBA",),
    Deporte.FUTBOL: ("Premier League", "Serie A", "Bundesliga", "LaLiga", "Ligue 1"),
}


def _validar_monto(monto: int) -> None:
    if not isinstance(monto, int) or isinstance(monto, bool):
        raise ValueError("El monto debe ser un número entero de CLP")
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a 0")


@dataclass
class Apuesta:
    deporte: Deporte
    liga: str
    partido: str
    mercado: str
    seleccion: str
    cuota: Decimal
    monto: int
    fecha_evento: date
    colocada: bool = True
    casa: str = "Betano"
    prediccion_propia: str = ""
    nota: str = ""
    estado: Estado = Estado.PENDIENTE
    resultado_neto: int | None = None
    fecha_registro: datetime = field(default_factory=lambda: datetime.now().replace(microsecond=0))
    id: int | None = None

    def __post_init__(self) -> None:
        self.deporte = Deporte(self.deporte)
        self.estado = Estado(self.estado)
        self.cuota = Decimal(str(self.cuota))

        if self.liga not in LIGAS[self.deporte]:
            raise ValueError(f"La liga '{self.liga}' no corresponde a {self.deporte}")
        for nombre in ("partido", "mercado", "seleccion"):
            if not getattr(self, nombre).strip():
                raise ValueError(f"El campo '{nombre}' es obligatorio")
        if self.cuota <= 1:
            raise ValueError("La cuota debe ser mayor a 1.00")
        _validar_monto(self.monto)

        if self.estado is Estado.PENDIENTE and self.resultado_neto is not None:
            raise ValueError("Una apuesta pendiente no puede tener resultado")
        if self.estado is not Estado.PENDIENTE and self.resultado_neto is None:
            raise ValueError("Una apuesta liquidada debe tener resultado")

    @property
    def liquidada(self) -> bool:
        return self.estado is not Estado.PENDIENTE

    def pago_bruto(self) -> int:
        """Pago total si la apuesta gana, redondeado al peso."""
        return int((self.cuota * self.monto).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass
class Movimiento:
    tipo: TipoMovimiento
    monto: int
    fecha: date = field(default_factory=date.today)
    nota: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        self.tipo = TipoMovimiento(self.tipo)
        _validar_monto(self.monto)
