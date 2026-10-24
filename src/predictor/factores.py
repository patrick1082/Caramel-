"""Factores clave de un partido en frases cortas, ordenados por relevancia."""

from __future__ import annotations

from collections.abc import Sequence

from predictor.estadisticas import Estadisticas
from predictor.modelos import Deporte, Jugador, ResultadoHistorico, Rol
from predictor.nombres import emparejar
from predictor.prediccion import Pronostico

MAXIMO = 6
MUESTRA_MINIMA = 10  # partidos por debajo de los cuales se advierte poca fiabilidad
RACHA = 4  # victorias o derrotas en los últimos 5
LESIONADOS_VISIBLES = 3
UMBRAL_XG = 0.5  # goles por partido sobre o bajo el xG
DESCANSO_EXTRA = 3  # días de diferencia de descanso que se destacan (fútbol)

# Diferencia (goles o puntos por partido) entre jugar de local/visita y el promedio general.
UMBRAL_LOCALIA = {Deporte.FUTBOL: 1.0, Deporte.NBA: 8.0}


def _diferencia(promedios) -> float:
    return promedios.a_favor - promedios.en_contra


def _muestra(nombres: dict[str, str], pronostico: Pronostico | None) -> list[tuple[int, str]]:
    if pronostico is None:
        return [(0, "Sin historial suficiente para predecir este partido.")]
    factores = []
    for equipo, jugados in (
        (nombres["local"], pronostico.partidos_local),
        (nombres["visitante"], pronostico.partidos_visitante),
    ):
        if jugados < MUESTRA_MINIMA:
            factores.append(
                (0, f"Pocos datos: {equipo} tiene solo {jugados} partidos en el historial.")
            )
    return factores


def _lesiones(equipo: str, jugadores: Sequence[Jugador]) -> list[tuple[int, str]]:
    lesionados = [j for j in jugadores if j.rol is Rol.LESIONADO]
    destacados = {j.nombre: j for j in jugadores if j.rol is Rol.DESTACADO}
    factores = []
    for lesionado in lesionados:
        figura = destacados.get(emparejar(lesionado.nombre, destacados) or "")
        if figura is not None:
            texto = f"Baja clave en {equipo}: {figura.nombre} ({figura.detalle})"
            factores.append((1, f"{texto} — {lesionado.detalle}."))
    resto = [j for j in lesionados if emparejar(j.nombre, destacados) is None]
    if resto:
        nombres = ", ".join(f"{j.nombre} ({j.detalle})" for j in resto[:LESIONADOS_VISIBLES])
        extra = len(resto) - LESIONADOS_VISIBLES
        cola = f" y {extra} más" if extra > 0 else ""
        factores.append((4, f"Lesionados en {equipo}: {nombres}{cola}."))
    return factores


def _descanso(deporte: Deporte, nombres: dict[str, str], pronostico: Pronostico | None):
    if pronostico is None:
        return []
    dias = {"local": pronostico.descanso_local, "visitante": pronostico.descanso_visitante}
    factores = []
    for lado, descanso in dias.items():
        if descanso == 1:
            factores.append((2, f"{nombres[lado]} juega back-to-back (jugó ayer)."))
    local, visita = dias["local"], dias["visitante"]
    if deporte is Deporte.FUTBOL and local is not None and visita is not None:
        if abs(local - visita) >= DESCANSO_EXTRA and min(local, visita) <= 4:
            lado = "local" if local > visita else "visitante"
            mas, menos = max(local, visita), min(local, visita)
            factores.append(
                (5, f"{nombres[lado]} llega con {mas} días de descanso frente a {menos} del rival.")
            )
    return factores


def _racha(equipo: str, stats: Estadisticas | None) -> list[tuple[int, str]]:
    if stats is None or len(stats.forma) < 5:
        return []
    if stats.forma.count("G") >= RACHA:
        return [(3, f"{equipo} viene en racha: {stats.forma} en los últimos 5.")]
    if stats.forma.count("P") >= RACHA:
        return [(3, f"{equipo} viene en mala racha: {stats.forma} en los últimos 5.")]
    return []


def _localia(deporte: Deporte, nombres: dict[str, str], local, visitante) -> list:
    umbral = UMBRAL_LOCALIA[deporte]
    unidad = "goles" if deporte is Deporte.FUTBOL else "puntos"
    factores = []
    if local is not None and local.de_local is not None and local.de_local.jugados >= 3:
        cambio = _diferencia(local.de_local) - _diferencia(local.ultimos)
        if cambio >= umbral:
            diferencia = _diferencia(local.de_local)
            texto = f"{nombres['local']} se hace fuerte en casa: {diferencia:+.1f} {unidad}"
            factores.append((6, f"{texto} por partido de local."))
    if (
        visitante is not None
        and visitante.de_visita is not None
        and visitante.de_visita.jugados >= 3
    ):
        cambio = _diferencia(visitante.de_visita) - _diferencia(visitante.ultimos)
        if cambio <= -umbral:
            diferencia = _diferencia(visitante.de_visita)
            texto = f"{nombres['visitante']} rinde peor de visita: {diferencia:+.1f} {unidad}"
            factores.append((6, f"{texto} por partido fuera."))
    return factores


def _cara_a_cara(nombres: dict[str, str], historiales: dict[str, str], directos) -> list:
    if len(directos) < 3:
        return []
    victorias = dict.fromkeys(historiales, 0)
    for r in directos:
        if r.marcador_local == r.marcador_visitante:
            continue
        ganador = r.local if r.marcador_local > r.marcador_visitante else r.visitante
        for lado, nombre in historiales.items():
            if nombre == ganador:
                victorias[lado] += 1
    for lado, otro in (("local", "visitante"), ("visitante", "local")):
        if victorias[lado] >= 3 and victorias[otro] == 0:
            texto = f"{nombres[lado]} ganó {victorias[lado]} de los últimos {len(directos)}"
            return [(7, f"{texto} enfrentamientos directos.")]
    return []


def _xg(equipo: str, stats: Estadisticas | None) -> list[tuple[int, str]]:
    if stats is None or "xg" not in stats.extras:
        return []
    xg, goles = stats.extras["xg"][0], stats.ultimos.a_favor
    if goles - xg >= UMBRAL_XG:
        return [(8, f"{equipo} marca más de lo que genera ({goles:.1f} goles vs {xg:.1f} xG).")]
    if xg - goles >= UMBRAL_XG:
        return [(8, f"{equipo} genera más de lo que convierte ({xg:.1f} xG vs {goles:.1f} goles).")]
    return []


def _figura(deporte: Deporte, equipo: str, jugadores: Sequence[Jugador]) -> list:
    destacados = [j for j in jugadores if j.rol is Rol.DESTACADO]
    if not destacados:
        return []
    figura = max(destacados, key=lambda j: j.valor)
    titulo = "Goleador" if deporte is Deporte.FUTBOL else "Figura"
    return [(9, f"{titulo} de {equipo}: {figura.nombre} ({figura.detalle}).")]


def generar(
    deporte: Deporte,
    local: str,
    visitante: str,
    estadisticas_local: Estadisticas | None,
    estadisticas_visitante: Estadisticas | None,
    cara_a_cara: Sequence[ResultadoHistorico],
    pronostico: Pronostico | None,
    jugadores_local: Sequence[Jugador] = (),
    jugadores_visitante: Sequence[Jugador] = (),
) -> list[str]:
    """Hasta `MAXIMO` frases; `local`/`visitante` son los nombres visibles del partido."""
    nombres = {"local": local, "visitante": visitante}
    historiales = {
        lado: stats.equipo
        for lado, stats in (("local", estadisticas_local), ("visitante", estadisticas_visitante))
        if stats is not None
    }
    factores = [
        *_muestra(nombres, pronostico),
        *_lesiones(local, jugadores_local),
        *_lesiones(visitante, jugadores_visitante),
        *_descanso(deporte, nombres, pronostico),
        *_racha(local, estadisticas_local),
        *_racha(visitante, estadisticas_visitante),
        *_localia(deporte, nombres, estadisticas_local, estadisticas_visitante),
        *_cara_a_cara(nombres, historiales, cara_a_cara),
        *_xg(local, estadisticas_local),
        *_xg(visitante, estadisticas_visitante),
        *_figura(deporte, local, jugadores_local),
        *_figura(deporte, visitante, jugadores_visitante),
    ]
    return [texto for _, texto in sorted(factores, key=lambda f: f[0])][:MAXIMO]
