"""Modelos estadísticos locales: Poisson para el fútbol y ratings ofensivos/defensivos en la NBA.

Ambos se ajustan con el historial anterior a la fecha del partido, dando más peso a lo
reciente (vida media de `MEDIA_VIDA` días) y encogiendo a cada equipo hacia la media de la
liga con `PRIOR` partidos ficticios, para que pocos partidos no den fuerzas extremas.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from statistics import fmean

from predictor.modelos import Deporte, Prediccion, ProbabilidadLinea, ResultadoHistorico

MEDIA_VIDA = 180  # días
PRIOR = 3.0  # partidos de un equipo promedio que se suman a cada equipo
ITERACIONES = 40
MAX_GOLES = 10  # tamaño de la matriz de marcadores (0..10 goles por equipo)

# NBA: desviaciones por defecto si hay pocos partidos para estimarlas de los residuos.
SIGMA_MARGEN = 12.0
SIGMA_TOTAL = 18.0
MINIMO_SIGMA = 30
FATIGA_B2B = 1.5  # puntos que pierde un equipo que jugó el día anterior

MODELO_FUTBOL = "poisson-1"
MODELO_NBA = "nba-ratings-1"


class Discreta:
    """Distribución de un entero (goles totales o diferencia de goles)."""

    def __init__(self, probs: dict[int, float]):
        self.probs = probs

    def mayor(self, umbral: float) -> float:
        return sum(p for k, p in self.probs.items() if k > umbral)

    def igual(self, umbral: float) -> float:
        return self.probs.get(int(umbral), 0.0) if umbral == int(umbral) else 0.0

    def negada(self) -> Discreta:
        return Discreta({-k: p for k, p in self.probs.items()})


class Normal:
    """Normal discretizada en enteros (puntos NBA), con corrección de continuidad."""

    def __init__(self, media: float, sigma: float):
        self.media, self.sigma = media, sigma

    def acumulada(self, x: float) -> float:
        return 0.5 * (1 + math.erf((x - self.media) / (self.sigma * math.sqrt(2))))

    def mayor(self, umbral: float) -> float:
        return 1 - self.acumulada(math.floor(umbral) + 0.5)

    def igual(self, umbral: float) -> float:
        if umbral != int(umbral):
            return 0.0
        return self.acumulada(umbral + 0.5) - self.acumulada(umbral - 0.5)

    def negada(self) -> Normal:
        return Normal(-self.media, self.sigma)


Distribucion = Discreta | Normal


def prob_linea(distribucion: Distribucion, linea: float) -> float:
    """Probabilidad de superar `linea`, sin contar la devolución en líneas enteras.

    Las líneas asiáticas (.25 / .75) reparten la apuesta en las dos líneas vecinas.
    """
    if (linea * 4) % 2 == 1:
        return (prob_linea(distribucion, linea - 0.25) + prob_linea(distribucion, linea + 0.25)) / 2
    devolucion = distribucion.igual(linea)
    if devolucion >= 1:
        return 0.5
    return distribucion.mayor(linea) / (1 - devolucion)


@dataclass(frozen=True)
class Pronostico:
    modelo: str
    esperado_local: float
    esperado_visitante: float
    prob_local: float
    prob_empate: float | None  # None en la NBA
    prob_visitante: float
    marcador_probable: str | None
    total: Distribucion
    margen: Distribucion  # marcador local − visitante
    partidos_local: int
    partidos_visitante: int
    descanso_local: int | None  # días desde su último partido
    descanso_visitante: int | None

    def prob_over(self, linea: float) -> float:
        return prob_linea(self.total, linea)

    def prob_under(self, linea: float) -> float:
        return 1 - self.prob_over(linea)

    def prob_handicap(self, es_local: bool, linea: float) -> float:
        """Probabilidad de cubrir el hándicap `linea` (p. ej. +0.75) del equipo elegido."""
        margen = self.margen if es_local else self.margen.negada()
        return prob_linea(margen, -linea)

    def a_prediccion(
        self,
        partido_id: str,
        liga: str,
        local: str,
        visitante: str,
        inicio: datetime,
        creada: datetime,
        factores: Sequence[str] = (),
        lineas: Sequence[ProbabilidadLinea] = (),
        linea_total: float | None = None,
    ) -> Prediccion:
        return Prediccion(
            partido_id=partido_id,
            liga=liga,
            local=local,
            visitante=visitante,
            inicio=inicio,
            modelo=self.modelo,
            creada=creada,
            esperado_local=round(self.esperado_local, 2),
            esperado_visitante=round(self.esperado_visitante, 2),
            prob_local=self.prob_local,
            prob_empate=self.prob_empate,
            prob_visitante=self.prob_visitante,
            marcador_probable=self.marcador_probable,
            factores=list(factores),
            lineas=list(lineas),
            linea_total=linea_total,
        )


def _poisson(media: float) -> list[float]:
    return [math.exp(-media) * media**k / math.factorial(k) for k in range(MAX_GOLES + 1)]


class Ajuste:
    """Fuerzas de todos los equipos de una liga a una fecha; `pronosticar` cruza dos de ellos."""

    def __init__(self, deporte: Deporte, historial: Sequence[ResultadoHistorico], fecha: date):
        self.deporte, self.fecha = deporte, fecha
        self.partidos = [
            (r, 0.5 ** ((fecha - r.fecha).days / MEDIA_VIDA)) for r in historial if r.fecha < fecha
        ]
        self.jugados: dict[str, int] = defaultdict(int)
        self.ultimo: dict[str, date] = {}
        for r, _ in self.partidos:
            for equipo in (r.local, r.visitante):
                self.jugados[equipo] += 1
                self.ultimo[equipo] = max(self.ultimo.get(equipo, r.fecha), r.fecha)
        if self.partidos:
            (self._ajustar_futbol if deporte is Deporte.FUTBOL else self._ajustar_nba)()

    @property
    def equipos(self) -> list[str]:
        return list(self.jugados)

    def _ajustar_futbol(self) -> None:
        """Modelo de Maher: λ = media de la liga × ataque propio × defensa rival."""
        total = sum(w for _, w in self.partidos)
        self.media_local = sum(w * r.marcador_local for r, w in self.partidos) / total
        self.media_visita = sum(w * r.marcador_visitante for r, w in self.partidos) / total
        media = (self.media_local + self.media_visita) / 2 or 1.0
        ataque = dict.fromkeys(self.jugados, 1.0)
        defensa = dict.fromkeys(self.jugados, 1.0)
        for _ in range(ITERACIONES):
            goles, esperados = defaultdict(float), defaultdict(float)
            for r, w in self.partidos:
                goles[r.local] += w * r.marcador_local
                goles[r.visitante] += w * r.marcador_visitante
                esperados[r.local] += w * self.media_local * defensa[r.visitante]
                esperados[r.visitante] += w * self.media_visita * defensa[r.local]
            ataque = {
                e: (goles[e] + PRIOR * media) / (esperados[e] + PRIOR * media) for e in ataque
            }
            recibidos, esperados = defaultdict(float), defaultdict(float)
            for r, w in self.partidos:
                recibidos[r.local] += w * r.marcador_visitante
                recibidos[r.visitante] += w * r.marcador_local
                esperados[r.local] += w * self.media_visita * ataque[r.visitante]
                esperados[r.visitante] += w * self.media_local * ataque[r.local]
            defensa = {
                e: (recibidos[e] + PRIOR * media) / (esperados[e] + PRIOR * media) for e in defensa
            }
        self.ataque, self.defensa = ataque, defensa

    def _esperados_nba(self, local: str, visitante: str) -> tuple[float, float]:
        return (
            self.base + self.localia + self.ofensiva[local] - self.defensiva[visitante],
            self.base + self.ofensiva[visitante] - self.defensiva[local],
        )

    def _ajustar_nba(self) -> None:
        """Puntos = base (+ localía) + ofensiva propia − defensiva rival, todo aditivo."""
        self.ofensiva = dict.fromkeys(self.jugados, 0.0)
        self.defensiva = dict.fromkeys(self.jugados, 0.0)  # puntos que evita bajo la media
        total = sum(w for _, w in self.partidos)
        self.base = sum(w * r.marcador_visitante for r, w in self.partidos) / total
        self.localia = sum(w * r.marcador_local for r, w in self.partidos) / total - self.base
        for _ in range(ITERACIONES):
            anotado, evitado, peso = defaultdict(float), defaultdict(float), defaultdict(float)
            for r, w in self.partidos:
                local, visita = self._esperados_nba(r.local, r.visitante)
                anotado[r.local] += w * (r.marcador_local - local + self.ofensiva[r.local])
                anotado[r.visitante] += w * (
                    r.marcador_visitante - visita + self.ofensiva[r.visitante]
                )
                evitado[r.local] += w * (visita + self.defensiva[r.local] - r.marcador_visitante)
                evitado[r.visitante] += w * (local + self.defensiva[r.visitante] - r.marcador_local)
                peso[r.local] += w
                peso[r.visitante] += w
            self.ofensiva = {e: anotado[e] / (peso[e] + PRIOR) for e in self.ofensiva}
            self.defensiva = {e: evitado[e] / (peso[e] + PRIOR) for e in self.defensiva}
            # Base y localía con las fuerzas nuevas.
            residuo_local = residuo_visita = 0.0
            for r, w in self.partidos:
                local, visita = self._esperados_nba(r.local, r.visitante)
                residuo_local += w * (r.marcador_local - local)
                residuo_visita += w * (r.marcador_visitante - visita)
            self.base += residuo_visita / total
            self.localia += (residuo_local - residuo_visita) / total

        if len(self.partidos) < MINIMO_SIGMA:
            self.sigma_margen, self.sigma_total = SIGMA_MARGEN, SIGMA_TOTAL
            return
        margenes, totales = [], []
        for r, _ in self.partidos:
            local, visita = self._esperados_nba(r.local, r.visitante)
            margenes.append((r.marcador_local - r.marcador_visitante) - (local - visita))
            totales.append((r.marcador_local + r.marcador_visitante) - (local + visita))
        self.sigma_margen = math.sqrt(fmean(m * m for m in margenes))
        self.sigma_total = math.sqrt(fmean(t * t for t in totales))

    def descanso(self, equipo: str) -> int | None:
        return (self.fecha - self.ultimo[equipo]).days if equipo in self.ultimo else None

    def pronosticar(self, local: str, visitante: str) -> Pronostico | None:
        """None si alguno de los dos equipos (nombres del historial) no tiene partidos."""
        if local not in self.jugados or visitante not in self.jugados or local == visitante:
            return None
        if self.deporte is Deporte.FUTBOL:
            return self._futbol(local, visitante)
        return self._nba(local, visitante)

    def _comunes(self, local: str, visitante: str) -> dict:
        return {
            "partidos_local": self.jugados[local],
            "partidos_visitante": self.jugados[visitante],
            "descanso_local": self.descanso(local),
            "descanso_visitante": self.descanso(visitante),
        }

    def _futbol(self, local: str, visitante: str) -> Pronostico:
        lam_local = self.media_local * self.ataque[local] * self.defensa[visitante]
        lam_visita = self.media_visita * self.ataque[visitante] * self.defensa[local]
        goles_local, goles_visita = _poisson(lam_local), _poisson(lam_visita)
        suma = sum(goles_local) * sum(goles_visita)
        totales, margenes = defaultdict(float), defaultdict(float)
        mejor, prob_mejor = (0, 0), -1.0
        for i, p_i in enumerate(goles_local):
            for j, p_j in enumerate(goles_visita):
                p = p_i * p_j / suma
                totales[i + j] += p
                margenes[i - j] += p
                if p > prob_mejor:
                    mejor, prob_mejor = (i, j), p
        margen = Discreta(dict(margenes))
        empate, prob_local = margen.igual(0), margen.mayor(0)
        return Pronostico(
            modelo=MODELO_FUTBOL,
            esperado_local=lam_local,
            esperado_visitante=lam_visita,
            prob_local=prob_local,
            prob_empate=empate,
            prob_visitante=max(1 - prob_local - empate, 0.0),
            marcador_probable=f"{mejor[0]}-{mejor[1]}",
            total=Discreta(dict(totales)),
            margen=margen,
            **self._comunes(local, visitante),
        )

    def _nba(self, local: str, visitante: str) -> Pronostico:
        pts_local, pts_visita = self._esperados_nba(local, visitante)
        if self.descanso(local) == 1:
            pts_local -= FATIGA_B2B
        if self.descanso(visitante) == 1:
            pts_visita -= FATIGA_B2B
        margen = Normal(pts_local - pts_visita, self.sigma_margen)
        prob_local = 1 - margen.acumulada(0)  # en la NBA no hay empate
        return Pronostico(
            modelo=MODELO_NBA,
            esperado_local=max(pts_local, 0.0),
            esperado_visitante=max(pts_visita, 0.0),
            prob_local=prob_local,
            prob_empate=None,
            prob_visitante=1 - prob_local,
            marcador_probable=None,
            total=Normal(pts_local + pts_visita, self.sigma_total),
            margen=margen,
            **self._comunes(local, visitante),
        )


def ajustar(deporte: Deporte, historial: Sequence[ResultadoHistorico], fecha: date) -> Ajuste:
    return Ajuste(deporte, historial, fecha)
