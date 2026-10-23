"""Servicio de partidos: actualiza cuotas e historial, filtra la cartelera y arma comparaciones."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from statistics import fmean

from predictor import estadisticas
from predictor.estadisticas import Estadisticas
from predictor.fuentes import football_data, nba
from predictor.fuentes.odds_api import ClienteOddsApi, costo_creditos
from predictor.ligas import CASA_BASE, CASA_REFERENCIA, CASAS, FUENTES, ZONA_CHILE, temporadas
from predictor.modelos import Cuota, Deporte, Mercado, Partido, ResultadoHistorico
from predictor.nombres import emparejar
from predictor.repositorio import Repositorio

logger = logging.getLogger(__name__)

VIGENCIA_CUOTAS = timedelta(minutes=60)
VIGENCIA_HISTORIAL = timedelta(days=1)

_CREDITOS = "odds_creditos_restantes"
_ORDEN_MERCADOS = list(Mercado)


@dataclass(frozen=True)
class FilaComparacion:
    mercado: Mercado
    seleccion: str
    linea: Decimal | None
    betano: Decimal | None
    pinnacle: Decimal | None
    mejor: Decimal
    casa_mejor: str  # nombre visible
    promedio: Decimal
    casas: int


@dataclass(frozen=True)
class Analisis:
    local: Estadisticas | None
    visitante: Estadisticas | None
    cara_a_cara: list[ResultadoHistorico]


class Cartelera:
    def __init__(
        self,
        repo: Repositorio,
        cliente: ClienteOddsApi | None,
        descargar_futbol: Callable[[str, str], list[ResultadoHistorico]] = football_data.descargar,
        descargar_nba: Callable[[str], list[ResultadoHistorico]] = nba.descargar,
        reloj: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repo = repo
        self._cliente = cliente
        self._descargar_futbol = descargar_futbol
        self._descargar_nba = descargar_nba
        self._reloj = reloj
        self._historiales: dict[str, list[ResultadoHistorico]] = {}

    # --- Estado de las actualizaciones ---

    @property
    def tiene_clave(self) -> bool:
        return self._cliente is not None

    @property
    def creditos_restantes(self) -> int | None:
        valor = self._repo.obtener_config(_CREDITOS)
        return int(valor) if valor is not None else None

    def _momento(self, clave: str) -> datetime | None:
        valor = self._repo.obtener_config(clave)
        return datetime.fromisoformat(valor) if valor else None

    def _marcar(self, clave: str) -> None:
        self._repo.fijar_config(clave, self._reloj().isoformat(timespec="seconds"))

    def cuotas_actualizadas(self, liga: str) -> datetime | None:
        return self._momento(f"cuotas_actualizadas:{liga}")

    def ligas_por_actualizar(self, ligas: Iterable[str]) -> list[str]:
        """Ligas sin cuotas o con cuotas de más de `VIGENCIA_CUOTAS`."""
        limite = self._reloj() - VIGENCIA_CUOTAS
        return [
            liga
            for liga in ligas
            if (momento := self.cuotas_actualizadas(liga)) is None or momento < limite
        ]

    # --- Actualizaciones ---

    def actualizar_cuotas(self, ligas: Iterable[str], forzar: bool = False) -> list[str]:
        """Consulta The Odds API para las ligas vencidas (o todas si `forzar`)."""
        if self._cliente is None:
            raise ValueError("Falta la clave de The Odds API (variable ODDS_API_KEY)")
        ligas = list(ligas)
        pendientes = ligas if forzar else self.ligas_por_actualizar(ligas)
        costo = costo_creditos(len(pendientes))
        restantes = self.creditos_restantes
        if restantes is not None and costo > restantes:
            raise ValueError(f"Actualizar cuesta {costo} créditos y quedan {restantes} este mes")

        for liga in pendientes:
            respuesta = self._cliente.cuotas(liga)
            self._repo.reemplazar_cartelera(liga, respuesta.partidos, respuesta.cuotas)
            self._marcar(f"cuotas_actualizadas:{liga}")
            if respuesta.creditos_restantes is not None:
                self._repo.fijar_config(_CREDITOS, str(respuesta.creditos_restantes))
        return pendientes

    def actualizar_historial(self, ligas: Iterable[str], forzar: bool = False) -> list[str]:
        """Descarga la temporada actual y la anterior, como mucho una vez al día por liga."""
        limite = self._reloj() - VIGENCIA_HISTORIAL
        hoy = self._reloj().astimezone(ZONA_CHILE).date()
        actualizadas = []
        for liga in ligas:
            clave = f"historial_actualizado:{liga}"
            momento = self._momento(clave)
            if not forzar and momento is not None and momento >= limite:
                continue
            deporte = FUENTES[liga].deporte
            for temporada in temporadas(deporte, hoy):
                if deporte is Deporte.NBA:
                    resultados = self._descargar_nba(temporada)
                else:
                    resultados = self._descargar_futbol(liga, temporada)
                self._repo.guardar_historial(liga, temporada, resultados)
            self._marcar(clave)
            self._historiales.pop(liga, None)
            actualizadas.append(liga)
        return actualizadas

    # --- Consultas ---

    def partidos(
        self,
        dia: date,
        desde_hora: int = 0,
        hasta_hora: int = 24,
        ligas: Iterable[str] | None = None,
    ) -> list[Partido]:
        """Partidos del día `dia` (hora de Chile) que empiezan entre las horas indicadas."""
        if not 0 <= desde_hora < hasta_hora <= 24:
            raise ValueError("El rango de horas no es válido")
        medianoche = datetime(dia.year, dia.month, dia.day, tzinfo=ZONA_CHILE)
        desde = medianoche + timedelta(hours=desde_hora)
        hasta = medianoche + timedelta(hours=hasta_hora)
        return self._repo.listar_partidos(desde, hasta, ligas)

    def comparar(self, partido: Partido) -> list[FilaComparacion]:
        """Una fila por mercado/selección/línea con Betano, Pinnacle y la mejor cuota."""
        grupos: dict[tuple, list[Cuota]] = {}
        for cuota in self._repo.cuotas_de(partido.id):
            grupos.setdefault((cuota.mercado, cuota.seleccion, cuota.linea), []).append(cuota)

        filas = []
        for (mercado, seleccion, linea), cuotas in grupos.items():
            por_casa = {c.casa: c.cuota for c in cuotas}
            if len(por_casa) < 2 and not {CASA_BASE, CASA_REFERENCIA} & por_casa.keys():
                continue  # línea alternativa de una sola casa: ruido
            casa_mejor = max(por_casa, key=por_casa.get)
            filas.append(
                FilaComparacion(
                    mercado=mercado,
                    seleccion=seleccion,
                    linea=linea,
                    betano=por_casa.get(CASA_BASE),
                    pinnacle=por_casa.get(CASA_REFERENCIA),
                    mejor=por_casa[casa_mejor],
                    casa_mejor=CASAS.get(casa_mejor, casa_mejor),
                    promedio=Decimal(str(round(fmean(por_casa.values()), 2))),
                    casas=len(por_casa),
                )
            )

        orden = {partido.local: 0, "Draw": 1, partido.visitante: 2, "Over": 0, "Under": 1}

        def clave(fila: FilaComparacion) -> tuple:
            linea = fila.linea if fila.linea is not None else Decimal(0)
            return (_ORDEN_MERCADOS.index(fila.mercado), abs(linea), orden.get(fila.seleccion, 3))

        return sorted(filas, key=clave)

    def _historial(self, liga: str) -> Sequence[ResultadoHistorico]:
        if liga not in self._historiales:
            self._historiales[liga] = self._repo.historial_de(liga)
        return self._historiales[liga]

    def analizar(self, partido: Partido) -> Analisis:
        """Forma de ambos equipos y enfrentamientos directos, cruzando nombres entre fuentes."""
        historial = self._historial(partido.liga)
        equipos = {r.local for r in historial} | {r.visitante for r in historial}
        local = emparejar(partido.local, equipos) if equipos else None
        visitante = emparejar(partido.visitante, equipos) if equipos else None
        return Analisis(
            local=estadisticas.calcular(local, historial) if local else None,
            visitante=estadisticas.calcular(visitante, historial) if visitante else None,
            cara_a_cara=(
                estadisticas.cara_a_cara(local, visitante, historial) if local and visitante else []
            ),
        )
