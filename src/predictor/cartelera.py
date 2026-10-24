"""Servicio de partidos: actualiza cuotas, historial y jugadores, compara cuotas y predice."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from statistics import fmean
from zoneinfo import ZoneInfo

from predictor import estadisticas, evaluacion, factores
from predictor.estadisticas import Estadisticas
from predictor.evaluacion import MINIMO_BACKTEST, Evaluada, MetricasModelo
from predictor.fuentes import espn, football_data, nba
from predictor.fuentes.odds_api import ClienteOddsApi, costo_creditos
from predictor.ligas import (
    CASA_BASE,
    CASA_REFERENCIA,
    CASAS,
    FUENTES,
    ZONA_CHILE,
    anio_temporada,
    temporadas,
)
from predictor.modelos import (
    Cuota,
    Deporte,
    Jugador,
    Mercado,
    Partido,
    Prediccion,
    ProbabilidadLinea,
    ResultadoHistorico,
)
from predictor.nombres import emparejar
from predictor.prediccion import Ajuste, Pronostico, ajustar
from predictor.repositorio import Repositorio

logger = logging.getLogger(__name__)

VIGENCIA_CUOTAS = timedelta(minutes=60)
VIGENCIA_HISTORIAL = timedelta(days=1)
VIGENCIA_JUGADORES = timedelta(days=1)

# Las fechas del historial son locales de cada liga: así el descanso se cuenta bien.
ZONA_HISTORIAL = {
    Deporte.FUTBOL: ZoneInfo("Europe/Paris"),
    Deporte.NBA: ZoneInfo("America/New_York"),
}

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


def descargar_jugadores(liga: str, hoy: date) -> list[Jugador]:
    """Figuras de la temporada en curso: nba_api + lesiones de ESPN, o goleadores de ESPN."""
    deporte = FUENTES[liga].deporte
    if deporte is Deporte.NBA:
        return nba.jugadores(temporadas(deporte, hoy)[0]) + espn.lesiones_nba()
    return espn.goleadores(liga, anio_temporada(deporte, hoy))


def _linea_principal(cuotas: Sequence[Cuota]) -> float | None:
    """Línea de totales con Over y Under más parejos, de Betano o, si no, de Pinnacle."""
    for casa in (CASA_BASE, CASA_REFERENCIA):
        precios: dict[Decimal, dict[str, Decimal]] = {}
        for c in cuotas:
            if c.casa == casa and c.mercado is Mercado.TOTALES and c.linea is not None:
                precios.setdefault(c.linea, {})[c.seleccion] = c.cuota
        parejas = {
            linea: abs(p["Over"] - p["Under"])
            for linea, p in precios.items()
            if {"Over", "Under"} <= p.keys()
        }
        if parejas:
            return float(min(parejas, key=lambda linea: (parejas[linea], linea)))
    return None


def _lineas(
    partido: Partido, pronostico: Pronostico, cuotas: Sequence[Cuota]
) -> list[ProbabilidadLinea]:
    """Probabilidad del modelo en cada línea de totales y hándicap que ofrecen las casas."""
    lineas = {}
    for c in cuotas:
        if c.linea is None:
            continue
        linea = float(c.linea)
        if c.mercado is Mercado.TOTALES and c.seleccion in ("Over", "Under"):
            over = pronostico.prob_over(linea)
            prob = over if c.seleccion == "Over" else 1 - over
        elif c.mercado is Mercado.HANDICAP and c.seleccion in (partido.local, partido.visitante):
            prob = pronostico.prob_handicap(c.seleccion == partido.local, linea)
        else:
            continue
        lineas[(c.mercado, c.seleccion, linea)] = ProbabilidadLinea(
            c.mercado, c.seleccion, linea, round(prob, 4)
        )
    orden = list(Mercado)
    return [lineas[k] for k in sorted(lineas, key=lambda k: (orden.index(k[0]), k[2], k[1]))]


class Cartelera:
    def __init__(
        self,
        repo: Repositorio,
        cliente: ClienteOddsApi | None,
        descargar_futbol: Callable[[str, str], list[ResultadoHistorico]] = football_data.descargar,
        descargar_nba: Callable[[str], list[ResultadoHistorico]] = nba.descargar,
        reloj: Callable[[], datetime] = lambda: datetime.now(UTC),
        descargar_jugadores: Callable[[str, date], list[Jugador]] = descargar_jugadores,
    ) -> None:
        self._repo = repo
        self._cliente = cliente
        self._descargar_futbol = descargar_futbol
        self._descargar_nba = descargar_nba
        self._descargar_jugadores = descargar_jugadores
        self._reloj = reloj
        self._historiales: dict[str, list[ResultadoHistorico]] = {}
        self._ajustes: dict[tuple[str, date], Ajuste] = {}
        self._backtests: dict[str, list[Evaluada]] = {}

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
            self._olvidar(liga)
            actualizadas.append(liga)
        return actualizadas

    def actualizar_jugadores(
        self, ligas: Iterable[str], forzar: bool = False
    ) -> tuple[list[str], dict[str, str]]:
        """Figuras y lesiones una vez al día por liga; si una fuente falla, sigue con el resto.

        Devuelve las ligas actualizadas y el error de cada liga que falló.
        """
        limite = self._reloj() - VIGENCIA_JUGADORES
        hoy = self._reloj().astimezone(ZONA_CHILE).date()
        actualizadas, errores = [], {}
        for liga in ligas:
            clave = f"jugadores_actualizados:{liga}"
            momento = self._momento(clave)
            if not forzar and momento is not None and momento >= limite:
                continue
            try:
                jugadores = self._descargar_jugadores(liga, hoy)
            except ValueError as error:
                logger.warning("Jugadores de %s sin actualizar: %s", liga, error)
                errores[liga] = str(error)
                continue
            self._repo.reemplazar_jugadores(liga, jugadores)
            self._marcar(clave)
            actualizadas.append(liga)
        return actualizadas, errores

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

    def _olvidar(self, liga: str) -> None:
        """Descarta lo calculado con el historial anterior de la liga."""
        self._historiales.pop(liga, None)
        self._backtests.pop(liga, None)
        for clave in [k for k in self._ajustes if k[0] == liga]:
            del self._ajustes[clave]

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

    def jugadores(self, partido: Partido) -> tuple[list[Jugador], list[Jugador]]:
        """Figuras y lesionados del local y del visitante, cruzando nombres de equipos."""
        por_equipo: dict[str, list[Jugador]] = {}
        for jugador in self._repo.jugadores_de(partido.liga):
            por_equipo.setdefault(jugador.equipo, []).append(jugador)
        local = emparejar(partido.local, por_equipo) if por_equipo else None
        visitante = emparejar(partido.visitante, por_equipo) if por_equipo else None
        return por_equipo.get(local, []), por_equipo.get(visitante, [])

    def _ajuste(self, liga: str, fecha: date) -> Ajuste:
        if (liga, fecha) not in self._ajustes:
            deporte = FUENTES[liga].deporte
            self._ajustes[(liga, fecha)] = ajustar(deporte, self._historial(liga), fecha)
        return self._ajustes[(liga, fecha)]

    def predecir(self, partido: Partido) -> Prediccion | None:
        """Predicción del modelo, guardada para medirla después.

        Antes del inicio se recalcula con los datos más nuevos; desde el inicio queda congelada
        y se devuelve la guardada. None si el historial no alcanza para predecir.
        """
        if self._reloj() >= partido.inicio:
            return self._repo.prediccion_de(partido.id)
        analisis = self.analizar(partido)
        if analisis.local is None or analisis.visitante is None:
            return None
        fecha = partido.inicio.astimezone(ZONA_HISTORIAL[partido.deporte]).date()
        ajuste = self._ajuste(partido.liga, fecha)
        pronostico = ajuste.pronosticar(analisis.local.equipo, analisis.visitante.equipo)
        if pronostico is None:
            return None
        cuotas = self._repo.cuotas_de(partido.id)
        jugadores_local, jugadores_visitante = self.jugadores(partido)
        prediccion = pronostico.a_prediccion(
            partido.id,
            partido.liga,
            partido.local,
            partido.visitante,
            partido.inicio,
            self._reloj(),
            factores=factores.generar(
                partido.deporte,
                partido.local,
                partido.visitante,
                analisis.local,
                analisis.visitante,
                analisis.cara_a_cara,
                pronostico,
                jugadores_local,
                jugadores_visitante,
            ),
            lineas=_lineas(partido, pronostico, cuotas),
            linea_total=_linea_principal(cuotas),
        )
        self._repo.guardar_prediccion(prediccion)
        return prediccion

    # --- Evaluación del modelo ---

    def evaluadas(self) -> list[Evaluada]:
        """Predicciones de partidos ya empezados que tienen resultado en el historial."""
        predicciones = self._repo.listar_predicciones(hasta=self._reloj())
        ligas = sorted({p.liga for p in predicciones})
        historial = [r for liga in ligas for r in self._historial(liga)]
        return evaluacion.cruzar(predicciones, historial)

    def evaluacion(self) -> dict[str, MetricasModelo]:
        return evaluacion.por_liga(self.evaluadas())

    def backtest(
        self, ligas: Iterable[str], minimo: int = MINIMO_BACKTEST
    ) -> dict[str, MetricasModelo]:
        """Walk-forward sobre todo el historial guardado (temporada actual y anterior)."""
        evaluadas = []
        for liga in ligas:
            if liga not in self._backtests:
                self._backtests[liga] = evaluacion.backtest(
                    liga, self._historial(liga), minimo=minimo
                )
            evaluadas += self._backtests[liga]
        return evaluacion.por_liga(evaluadas)
