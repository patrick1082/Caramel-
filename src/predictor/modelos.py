"""Entidades del dominio: apuestas, fondo, partidos, cuotas e historial, con sus validaciones."""

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


class Mercado(StrEnum):
    """Mercados de The Odds API; el valor es la clave que usa la API."""

    GANADOR = "h2h"
    TOTALES = "totals"
    HANDICAP = "spreads"

    @property
    def etiqueta(self) -> str:
        return {"h2h": "Ganador", "totals": "Over/Under", "spreads": "Hándicap"}[self.value]


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

        _validar_liga(self.deporte, self.liga)
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


def _validar_liga(deporte: Deporte, liga: str) -> None:
    if liga not in LIGAS[deporte]:
        raise ValueError(f"La liga '{liga}' no corresponde a {deporte}")


@dataclass
class Partido:
    id: str
    deporte: Deporte
    liga: str
    local: str
    visitante: str
    inicio: datetime  # Con zona horaria; se guarda en UTC.

    def __post_init__(self) -> None:
        self.deporte = Deporte(self.deporte)
        _validar_liga(self.deporte, self.liga)
        for nombre in ("id", "local", "visitante"):
            if not getattr(self, nombre).strip():
                raise ValueError(f"El campo '{nombre}' es obligatorio")
        if self.inicio.tzinfo is None:
            raise ValueError("La hora de inicio debe tener zona horaria")

    @property
    def nombre(self) -> str:
        return f"{self.local} vs {self.visitante}"


@dataclass
class Cuota:
    partido_id: str
    casa: str
    mercado: Mercado
    seleccion: str
    cuota: Decimal
    actualizada: datetime
    linea: Decimal | None = None  # Puntos/goles del hándicap o del over/under.

    def __post_init__(self) -> None:
        self.mercado = Mercado(self.mercado)
        self.cuota = Decimal(str(self.cuota))
        if self.linea is not None:
            self.linea = Decimal(str(self.linea))
        if self.cuota <= 1:
            raise ValueError("La cuota debe ser mayor a 1.00")


@dataclass
class ResultadoHistorico:
    liga: str
    temporada: str
    fecha: date
    local: str
    visitante: str
    marcador_local: int
    marcador_visitante: int
    # Estadística → (valor del local, valor del visitante), p. ej. {"tiros": (14, 9)}.
    extras: dict[str, tuple[float, float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.marcador_local < 0 or self.marcador_visitante < 0:
            raise ValueError("El marcador no puede ser negativo")
