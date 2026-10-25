"""Entidades del dominio: apuestas, fondo, partidos, cuotas, historial y predicciones."""

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


class Valor(StrEnum):
    """Marca de valor de una cuota según el modelo y el mercado."""

    NINGUNO = "ninguno"
    MODELO = "modelo"  # Solo el modelo ve valor.
    CONFIRMADO = "confirmado"  # El modelo ve valor y el mercado no lo contradice.

    @property
    def etiqueta(self) -> str:
        return {"ninguno": "—", "modelo": "Solo modelo", "confirmado": "Confirmado"}[self.value]


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
    prob_modelo: float | None = None  # Probabilidad del modelo al registrarla desde la cartelera.
    valor: Valor = Valor.NINGUNO
    estado: Estado = Estado.PENDIENTE
    resultado_neto: int | None = None
    fecha_registro: datetime = field(default_factory=lambda: datetime.now().replace(microsecond=0))
    id: int | None = None

    def __post_init__(self) -> None:
        self.deporte = Deporte(self.deporte)
        self.estado = Estado(self.estado)
        self.valor = Valor(self.valor)
        self.cuota = Decimal(str(self.cuota))

        _validar_liga(self.deporte, self.liga)
        if self.prob_modelo is not None and not 0 <= self.prob_modelo <= 1:
            raise ValueError("La probabilidad del modelo debe estar entre 0 y 1")
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
    # Cuotas promedio previas al partido (local, empate, visitante); solo fútbol.
    cuotas: tuple[float, float, float] | None = None

    def __post_init__(self) -> None:
        if self.marcador_local < 0 or self.marcador_visitante < 0:
            raise ValueError("El marcador no puede ser negativo")
        if self.cuotas is not None and any(c <= 1 for c in self.cuotas):
            raise ValueError("Las cuotas históricas deben ser mayores a 1.00")


class Rol(StrEnum):
    DESTACADO = "destacado"
    LESIONADO = "lesionado"


@dataclass
class Jugador:
    liga: str
    equipo: str  # Nombre en la fuente del jugador; se cruza con `emparejar`.
    nombre: str
    rol: Rol
    detalle: str  # "8 goles · 7 PJ", "Out · Foot"
    valor: float = 0.0  # Puntos o goles por los que se ordena.

    def __post_init__(self) -> None:
        self.rol = Rol(self.rol)
        for nombre in ("equipo", "nombre"):
            if not getattr(self, nombre).strip():
                raise ValueError(f"El campo '{nombre}' es obligatorio")


@dataclass(frozen=True)
class ProbabilidadLinea:
    mercado: Mercado
    seleccion: str
    linea: float | None
    prob: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "mercado", Mercado(self.mercado))
        if not 0 <= self.prob <= 1:
            raise ValueError("La probabilidad debe estar entre 0 y 1")


_TOLERANCIA = 0.01


def _validar_probabilidades(local: float, empate: float | None, visitante: float) -> None:
    probs = [local, visitante] + ([empate] if empate is not None else [])
    if any(not 0 <= p <= 1 for p in probs) or abs(sum(probs) - 1) > _TOLERANCIA:
        raise ValueError("Las probabilidades deben estar entre 0 y 1 y sumar 1")


@dataclass
class Prediccion:
    partido_id: str
    liga: str
    local: str
    visitante: str
    inicio: datetime
    modelo: str  # Versión, p. ej. "poisson-1"
    creada: datetime
    esperado_local: float
    esperado_visitante: float
    prob_local: float
    prob_empate: float | None  # None en la NBA
    prob_visitante: float
    marcador_probable: str | None = None
    factores: list[str] = field(default_factory=list)
    lineas: list[ProbabilidadLinea] = field(default_factory=list)
    linea_total: float | None = None  # Línea principal de over/under de Betano

    def __post_init__(self) -> None:
        if self.inicio.tzinfo is None or self.creada.tzinfo is None:
            raise ValueError("Las fechas de la predicción deben tener zona horaria")
        if self.esperado_local < 0 or self.esperado_visitante < 0:
            raise ValueError("Los goles o puntos esperados no pueden ser negativos")
        _validar_probabilidades(self.prob_local, self.prob_empate, self.prob_visitante)

    @property
    def total_esperado(self) -> float:
        return self.esperado_local + self.esperado_visitante

    @property
    def prob_over(self) -> float | None:
        """Probabilidad del over en la línea principal, si se calculó."""
        for p in self.lineas:
            principal = p.linea == self.linea_total
            if p.mercado is Mercado.TOTALES and p.seleccion == "Over" and principal:
                return p.prob
        return None


class Ganador(StrEnum):
    LOCAL = "local"
    EMPATE = "empate"
    VISITANTE = "visitante"


@dataclass
class PrediccionPropia:
    """Lo que piensa el usuario de un partido; se congela al inicio."""

    partido_id: str
    liga: str
    local: str
    visitante: str
    inicio: datetime
    ganador: Ganador
    creada: datetime
    marcador_local: int | None = None
    marcador_visitante: int | None = None
    nota: str = ""

    def __post_init__(self) -> None:
        self.ganador = Ganador(self.ganador)
        if self.inicio.tzinfo is None or self.creada.tzinfo is None:
            raise ValueError("Las fechas de la predicción deben tener zona horaria")
        if self.liga in LIGAS[Deporte.NBA] and self.ganador is Ganador.EMPATE:
            raise ValueError("En la NBA no hay empate")
        marcador = (self.marcador_local, self.marcador_visitante)
        if marcador.count(None) == 1:
            raise ValueError("El marcador necesita los dos valores o ninguno")
        if None not in marcador:
            local, visitante = marcador
            if local < 0 or visitante < 0:
                raise ValueError("El marcador no puede ser negativo")
            if self.ganador is not _ganador_de(local, visitante):
                raise ValueError("El marcador no coincide con el ganador elegido")


def _ganador_de(local: int, visitante: int) -> Ganador:
    if local > visitante:
        return Ganador.LOCAL
    return Ganador.VISITANTE if visitante > local else Ganador.EMPATE


class Fuente(StrEnum):
    """Origen de un pronóstico 1X2 externo o del modelo."""

    MODELO = "modelo"
    MERCADO = "mercado"  # Pinnacle sin margen (o el promedio de las casas).
    ESPN = "espn"  # ESPN BPI, solo NBA.

    @property
    def etiqueta(self) -> str:
        return {"modelo": "Modelo", "mercado": "Mercado", "espn": "ESPN BPI"}[self.value]


@dataclass
class Pronostico3:
    """Probabilidades de local, empate y visitante según una fuente."""

    partido_id: str
    fuente: Fuente
    prob_local: float
    prob_empate: float | None  # None en la NBA
    prob_visitante: float
    actualizada: datetime

    def __post_init__(self) -> None:
        self.fuente = Fuente(self.fuente)
        if self.actualizada.tzinfo is None:
            raise ValueError("La fecha del pronóstico debe tener zona horaria")
        _validar_probabilidades(self.prob_local, self.prob_empate, self.prob_visitante)

    @property
    def favorito(self) -> Ganador:
        probs = {Ganador.LOCAL: self.prob_local, Ganador.VISITANTE: self.prob_visitante}
        if self.prob_empate is not None:
            probs[Ganador.EMPATE] = self.prob_empate
        return max(probs, key=probs.__getitem__)
