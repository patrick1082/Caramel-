"""Tablas de la bitácora y de la cartelera, y exportación a Excel."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from predictor import stake
from predictor.bitacora import Metricas, Resumen
from predictor.cartelera import Analisis, FilaComparacion, Oportunidad, Sugerencia
from predictor.estadisticas import Estadisticas, Promedios
from predictor.evaluacion import TOTAL, Evaluada, MetricasFuente, MetricasModelo, ResultadoValor
from predictor.ligas import ZONA_CHILE
from predictor.modelos import (
    Apuesta,
    Deporte,
    Fuente,
    Ganador,
    Jugador,
    Mercado,
    Movimiento,
    Partido,
    Prediccion,
    PrediccionPropia,
    Pronostico3,
    ResultadoHistorico,
    Valor,
)
from predictor.valor import Valoracion, prob_modelo

COLUMNAS_APUESTAS = {
    "id": "N°",
    "fecha_registro": "Registrada",
    "fecha_evento": "Fecha partido",
    "deporte": "Deporte",
    "liga": "Liga",
    "partido": "Partido",
    "mercado": "Mercado",
    "seleccion": "Selección",
    "cuota": "Cuota",
    "monto": "Monto (CLP)",
    "casa": "Casa",
    "colocada": "Colocada",
    "estado": "Estado",
    "resultado_neto": "Resultado neto (CLP)",
    "prediccion_propia": "Mi predicción",
    "prob_modelo": "Modelo (%)",
    "valor": "Valor",
    "nota": "Nota",
}

COLUMNAS_MOVIMIENTOS = {
    "id": "N°",
    "fecha": "Fecha",
    "tipo": "Tipo",
    "monto": "Monto (CLP)",
    "nota": "Nota",
}

COLUMNAS_METRICAS = (
    "Grupo",
    "Apuestas",
    "Pendientes",
    "Ganadas",
    "Perdidas",
    "Nulas",
    "Apostado (CLP)",
    "Resultado (CLP)",
    "ROI (%)",
    "Acierto (%)",
)

COLUMNAS_CUOTAS = (
    "Mercado",
    "Selección",
    "Línea",
    "Betano",
    "Pinnacle",
    "Mejor",
    "Casa mejor",
    "Promedio",
    "Casas",
)

COLUMNAS_EVALUACION = (
    "Liga",
    "Partidos",
    "Acierto modelo (%)",
    "Acierto base (%)",
    "Brier modelo",
    "Brier base",
    "Error medio",
    "Over/under medidos",
    "Acierto over/under (%)",
)

COLUMNAS_VALOR_DEL_DIA = (
    "Hora",
    "Liga",
    "Partido",
    "Mercado",
    "Selección",
    "Línea",
    "Betano",
    "Modelo (%)",
    "Mercado (%)",
    "EV (%)",
    "Valor",
)

COLUMNAS_SUGERIDAS = (
    "Hora",
    "Liga",
    "Partido",
    "Apuesta",
    "Cuota",
    "Casa",
    "Acierto estimado (%)",
    "Modelo (%)",
    "Mercado (%)",
    "EV estimado (%)",
    "Banca (%)",
    "Monto (CLP)",
)

COLUMNAS_CONTRASTE = ("Opinión", "Local (%)", "Empate (%)", "Visita (%)", "Favorito", "Marcador")

COLUMNAS_FUENTES = ("Fuente", "Partidos", "Acierto (%)", "Brier")

COLUMNAS_BACKTEST_VALOR = (
    "Liga",
    "Partidos",
    "Apuestas",
    "Acierto (%)",
    "ROI valor (%)",
    "ROI favorito (%)",
)

COLUMNAS_PREDICCIONES = (
    "Inicio",
    "Liga",
    "Partido",
    "Local (%)",
    "Empate (%)",
    "Visita (%)",
    "Esperado",
    "Marcador probable",
    "Línea total",
    "Over (%)",
    "Resultado",
    "Acierto",
    "Acierto over/under",
)

ETIQUETAS_EXTRAS = {
    "tiros": "Tiros",
    "tiros_al_arco": "Tiros al arco",
    "xg": "xG",
    "corners": "Córners",
    "amarillas": "Amarillas",
    "rebotes": "Rebotes",
    "asistencias": "Asistencias",
    "triples": "Triples",
    "pct_tiro": "% de tiro",
    "perdidas": "Pérdidas",
}


def _porcentaje(valor: float | None) -> float | None:
    return None if valor is None else round(valor * 100, 2)


def tabla_apuestas(apuestas: list[Apuesta]) -> pd.DataFrame:
    filas = [
        {
            "id": a.id,
            "fecha_registro": a.fecha_registro.strftime("%Y-%m-%d %H:%M"),
            "fecha_evento": a.fecha_evento.isoformat(),
            "deporte": a.deporte.value,
            "liga": a.liga,
            "partido": a.partido,
            "mercado": a.mercado,
            "seleccion": a.seleccion,
            "cuota": float(a.cuota),
            "monto": a.monto,
            "casa": a.casa,
            "colocada": "Sí" if a.colocada else "No",
            "estado": a.estado.value,
            "resultado_neto": a.resultado_neto,
            "prediccion_propia": a.prediccion_propia,
            "prob_modelo": _porcentaje(a.prob_modelo),
            "valor": a.valor.etiqueta,
            "nota": a.nota,
        }
        for a in apuestas
    ]
    return pd.DataFrame(filas, columns=list(COLUMNAS_APUESTAS)).rename(columns=COLUMNAS_APUESTAS)


def tabla_movimientos(movimientos: list[Movimiento]) -> pd.DataFrame:
    filas = [
        {
            "id": m.id,
            "fecha": m.fecha.isoformat(),
            "tipo": m.tipo.value,
            "monto": m.monto,
            "nota": m.nota,
        }
        for m in movimientos
    ]
    return pd.DataFrame(filas, columns=list(COLUMNAS_MOVIMIENTOS)).rename(
        columns=COLUMNAS_MOVIMIENTOS
    )


def tabla_metricas(grupos: dict[str, Metricas]) -> pd.DataFrame:
    filas = [
        (
            nombre,
            m.total,
            m.pendientes,
            m.ganadas,
            m.perdidas,
            m.nulas,
            m.apostado,
            m.resultado,
            _porcentaje(m.roi),
            _porcentaje(m.acierto),
        )
        for nombre, m in grupos.items()
    ]
    return pd.DataFrame(filas, columns=COLUMNAS_METRICAS)


def tabla_resumen(resumen: Resumen) -> pd.DataFrame:
    colocadas, no_colocadas = resumen.colocadas, resumen.no_colocadas
    filas = [
        ("Fondo inicial (CLP)", resumen.fondo_inicial),
        ("Depósitos (CLP)", resumen.depositos),
        ("Retiros (CLP)", resumen.retiros),
        ("En juego (CLP)", resumen.en_juego),
        ("Saldo actual (CLP)", resumen.saldo),
        ("Ganancia / pérdida (CLP)", resumen.ganancia),
        ("Apostado liquidado (CLP)", colocadas.apostado),
        ("ROI (%)", _porcentaje(colocadas.roi)),
        ("Acierto (%)", _porcentaje(colocadas.acierto)),
        ("Apuestas colocadas", colocadas.total),
        ("Ganadas", colocadas.ganadas),
        ("Perdidas", colocadas.perdidas),
        ("Nulas", colocadas.nulas),
        ("Pendientes", colocadas.pendientes),
        ("Apuestas no colocadas", no_colocadas.total),
        ("Resultado hipotético no colocadas (CLP)", no_colocadas.resultado),
        ("ROI hipotético no colocadas (%)", _porcentaje(no_colocadas.roi)),
    ]
    return pd.DataFrame(filas, columns=["Concepto", "Valor"])


def _seleccion(seleccion: str) -> str:
    return "Empate" if seleccion == "Draw" else seleccion


def _cuota(valor) -> float | None:
    return None if valor is None else float(valor)


def _linea(fila: FilaComparacion) -> str:
    if fila.linea is None:
        return ""
    return f"{fila.linea:+g}" if fila.mercado is Mercado.HANDICAP else f"{fila.linea:g}"


def tabla_cuotas(
    filas: list[FilaComparacion],
    prediccion: Prediccion | None = None,
    valoraciones: list[Valoracion] = (),
) -> pd.DataFrame:
    """Cuotas por casa; con predicción suma la probabilidad del modelo y su cuota justa, y con
    valoraciones (en el orden de `filas`) el mercado sin margen, el EV de Betano y la marca."""
    datos = [
        (
            f.mercado.etiqueta,
            _seleccion(f.seleccion),
            _linea(f),
            _cuota(f.betano),
            _cuota(f.pinnacle),
            float(f.mejor),
            f.casa_mejor,
            float(f.promedio),
            f.casas,
        )
        for f in filas
    ]
    tabla = pd.DataFrame(datos, columns=COLUMNAS_CUOTAS)
    if prediccion is not None:
        probs = [prob_modelo(f, prediccion) for f in filas]
        tabla["Modelo (%)"] = [_porcentaje(p) for p in probs]
        tabla["Cuota justa"] = [round(1 / p, 2) if p else None for p in probs]
    if valoraciones:
        tabla["Mercado (%)"] = [_porcentaje(v.prob_mercado) for v in valoraciones]
        tabla["EV (%)"] = [_porcentaje(v.ev) for v in valoraciones]
        tabla["Valor"] = [v.valor.etiqueta for v in valoraciones]
    return tabla


def tabla_valor_del_dia(oportunidades: list[Oportunidad]) -> pd.DataFrame:
    filas = [
        (
            o.partido.inicio.astimezone(ZONA_CHILE).strftime("%H:%M"),
            o.partido.liga,
            o.partido.nombre,
            o.valoracion.fila.mercado.etiqueta,
            _seleccion(o.valoracion.fila.seleccion),
            _linea(o.valoracion.fila),
            _cuota(o.valoracion.fila.betano),
            _porcentaje(o.valoracion.prob_modelo),
            _porcentaje(o.valoracion.prob_mercado),
            _porcentaje(o.valoracion.ev),
            o.valoracion.valor.etiqueta,
        )
        for o in oportunidades
    ]
    return pd.DataFrame(filas, columns=COLUMNAS_VALOR_DEL_DIA)


def describir_apuesta(partido: Partido, fila: FilaComparacion) -> str:
    """La apuesta en palabras: "Gana Arsenal", "Más de 2.5 goles", "Lakers -4.5"."""
    if fila.mercado is Mercado.GANADOR:
        return "Empate" if fila.seleccion == "Draw" else f"Gana {fila.seleccion}"
    if fila.mercado is Mercado.TOTALES:
        unidad = "puntos" if partido.deporte is Deporte.NBA else "goles"
        sentido = "Más" if fila.seleccion == "Over" else "Menos"
        return f"{sentido} de {fila.linea:g} {unidad}"
    return f"{fila.seleccion} {_linea(fila)}"


def tabla_sugeridas(sugerencias: list[Sugerencia], saldo: int) -> pd.DataFrame:
    """Una fila por sugerencia; el monto sale del saldo disponible (vacío si no alcanza)."""
    filas = [
        (
            s.partido.inicio.astimezone(ZONA_CHILE).strftime("%H:%M"),
            s.partido.liga,
            s.partido.nombre,
            describir_apuesta(s.partido, s.valoracion.fila),
            _cuota(s.cuota),
            "Betano" if s.de_betano else "Promedio",
            _porcentaje(s.prob),
            _porcentaje(s.valoracion.prob_modelo),
            _porcentaje(s.valoracion.prob_mercado),
            _porcentaje(s.ev),
            _porcentaje(s.stake),
            stake.monto(saldo, s.stake) or None,
        )
        for s in sugerencias
    ]
    # object: con algún monto vacío, pandas pasaría los CLP a float.
    return pd.DataFrame(filas, columns=COLUMNAS_SUGERIDAS, dtype=object)


_FUENTES_CONTRASTE = {
    Fuente.MODELO: "el modelo",
    Fuente.ESPN: "ESPN BPI",
    Fuente.MERCADO: "el mercado",
}


def _ganador(ganador: Ganador, local: str, visitante: str) -> str:
    return {Ganador.LOCAL: local, Ganador.EMPATE: "Empate", Ganador.VISITANTE: visitante}[ganador]


def tabla_contraste(
    local: str,
    visitante: str,
    propia: PrediccionPropia | None,
    pronosticos: dict[Fuente, Pronostico3],
    prediccion: Prediccion | None = None,
) -> pd.DataFrame:
    """Las opiniones del 1X2 lado a lado: la mía, el modelo, ESPN BPI y el mercado.

    Solo aparecen las que existen; la columna de empate, solo si alguna fuente lo tiene.
    """
    filas = []
    if propia is not None:
        marcador = ""
        if propia.marcador_local is not None:
            marcador = f"{propia.marcador_local} - {propia.marcador_visitante}"
        filas.append(
            ("Mía", None, None, None, _ganador(propia.ganador, local, visitante), marcador)
        )
    for fuente in _FUENTES_CONTRASTE:
        if (p := pronosticos.get(fuente)) is None:
            continue
        marcador = ""
        if fuente is Fuente.MODELO and prediccion is not None:
            marcador = prediccion.marcador_probable or ""
        filas.append(
            (
                fuente.etiqueta,
                _porcentaje(p.prob_local),
                _porcentaje(p.prob_empate),
                _porcentaje(p.prob_visitante),
                _ganador(p.favorito, local, visitante),
                marcador,
            )
        )
    tabla = pd.DataFrame(filas, columns=COLUMNAS_CONTRASTE)
    if tabla["Empate (%)"].isna().all():
        tabla = tabla.drop(columns="Empate (%)")
    return tabla


def resumen_contraste(
    local: str,
    visitante: str,
    propia: PrediccionPropia | None,
    pronosticos: dict[Fuente, Pronostico3],
) -> str:
    """Una línea: "Coinciden tú y el mercado: gana X" o "Gana X según tú · Empate según…"."""
    opiniones: dict[str, list[str]] = {}
    if propia is not None:
        opiniones.setdefault(_ganador(propia.ganador, local, visitante), []).append("tú")
    for fuente, nombre in _FUENTES_CONTRASTE.items():
        if (p := pronosticos.get(fuente)) is not None:
            opiniones.setdefault(_ganador(p.favorito, local, visitante), []).append(nombre)
    if sum(map(len, opiniones.values())) < 2:
        return ""

    def _lista(quienes: list[str]) -> str:
        return quienes[0] if len(quienes) == 1 else ", ".join(quienes[:-1]) + " y " + quienes[-1]

    def _resultado(ganador: str) -> str:
        return "empate" if ganador == "Empate" else f"gana {ganador}"

    if len(opiniones) == 1:
        ganador, quienes = next(iter(opiniones.items()))
        return f"Coinciden {_lista(quienes)}: {_resultado(ganador)}"
    return " · ".join(
        f"{_resultado(ganador)[0].upper()}{_resultado(ganador)[1:]} según {_lista(quienes)}"
        for ganador, quienes in opiniones.items()
    )


def tabla_jugadores(
    local: str, jugadores_local: list[Jugador], visitante: str, jugadores_visitante: list[Jugador]
) -> pd.DataFrame:
    filas = [
        (equipo, j.rol.value.capitalize(), j.nombre, j.detalle)
        for equipo, jugadores in ((local, jugadores_local), (visitante, jugadores_visitante))
        for j in jugadores
    ]
    return pd.DataFrame(filas, columns=["Equipo", "Rol", "Jugador", "Detalle"])


def _redondear(valor: float | None, decimales: int = 3) -> float | None:
    return None if valor is None else round(valor, decimales)


def tabla_evaluacion(metricas: dict[str, MetricasModelo]) -> pd.DataFrame:
    """Modelo frente a la línea base por liga. El total no tiene error medio: mezcla goles y
    puntos."""
    filas = [
        (
            liga,
            m.partidos,
            _porcentaje(m.acierto),
            _porcentaje(m.acierto_base),
            _redondear(m.brier),
            _redondear(m.brier_base),
            None if liga == TOTAL else _redondear(m.error_medio, 2),
            m.lineas,
            _porcentaje(m.acierto_over_under),
        )
        for liga, m in metricas.items()
    ]
    return pd.DataFrame(filas, columns=COLUMNAS_EVALUACION)


def tabla_fuentes(metricas: dict[str, MetricasFuente]) -> pd.DataFrame:
    """Acierto y Brier de cada opinión; la mía no tiene Brier porque solo elige ganador."""
    filas = [
        (fuente, m.partidos, _porcentaje(m.acierto), _redondear(m.brier))
        for fuente, m in metricas.items()
    ]
    return pd.DataFrame(filas, columns=COLUMNAS_FUENTES)


def tabla_backtest_valor(resultados: dict[str, ResultadoValor]) -> pd.DataFrame:
    filas = [
        (
            liga,
            r.partidos,
            r.apuestas,
            _porcentaje(r.acierto),
            _porcentaje(r.roi),
            _porcentaje(r.roi_favorito),
        )
        for liga, r in resultados.items()
    ]
    return pd.DataFrame(filas, columns=COLUMNAS_BACKTEST_VALOR)


def _si_no(valor: bool | None) -> str:
    return "" if valor is None else ("Sí" if valor else "No")


def tabla_predicciones(
    predicciones: list[Prediccion], evaluadas: list[Evaluada] = ()
) -> pd.DataFrame:
    """Una fila por predicción guardada; las columnas de resultado se llenan si ya se evaluó."""
    por_partido = {e.prediccion.partido_id: e for e in evaluadas}
    filas = []
    for p in predicciones:
        e = por_partido.get(p.partido_id)
        filas.append(
            (
                p.inicio.astimezone(ZONA_CHILE).strftime("%Y-%m-%d %H:%M"),
                p.liga,
                f"{p.local} vs {p.visitante}",
                _porcentaje(p.prob_local),
                _porcentaje(p.prob_empate),
                _porcentaje(p.prob_visitante),
                f"{p.esperado_local:g} - {p.esperado_visitante:g}",
                p.marcador_probable or "",
                p.linea_total,
                _porcentaje(p.prob_over),
                f"{e.resultado.marcador_local} - {e.resultado.marcador_visitante}" if e else "",
                _si_no(e.acierto) if e else "",
                _si_no(e.acierto_linea) if e else "",
            )
        )
    return pd.DataFrame(filas, columns=COLUMNAS_PREDICCIONES)


def _par(promedios: Promedios | None) -> str:
    if promedios is None:
        return "—"
    return f"{promedios.a_favor:g} / {promedios.en_contra:g} ({promedios.jugados} PJ)"


def _columna(stats: Estadisticas | None, extras: list[str]) -> list[str]:
    if stats is None:
        return ["Sin datos"] + [""] * (4 + len(extras))
    return [
        str(stats.jugados),
        f"{stats.ganados}-{stats.empatados}-{stats.perdidos}",
        stats.forma,
        _par(stats.ultimos),
        f"{_par(stats.de_local)} · {_par(stats.de_visita)}",
    ] + [
        "{:g} / {:g}".format(*stats.extras[nombre]) if nombre in stats.extras else "—"
        for nombre in extras
    ]


def tabla_estadisticas(analisis: Analisis, local: str, visitante: str) -> pd.DataFrame:
    """Forma de ambos equipos lado a lado. Pares "propio / rival", promedios de 10 partidos."""
    equipos = [s for s in (analisis.local, analisis.visitante) if s is not None]
    extras = [n for n in ETIQUETAS_EXTRAS if any(n in s.extras for s in equipos)]
    conceptos = [
        "Partidos",
        "G-E-P",
        "Racha (reciente primero)",
        "Anota / recibe",
        "Como local · como visita",
    ] + [ETIQUETAS_EXTRAS[n] for n in extras]
    return pd.DataFrame(
        {
            "Concepto": conceptos,
            local: _columna(analisis.local, extras),
            visitante: _columna(analisis.visitante, extras),
        }
    )


def tabla_cara_a_cara(resultados: list[ResultadoHistorico]) -> pd.DataFrame:
    filas = [
        (
            r.fecha.isoformat(),
            r.local,
            f"{r.marcador_local} - {r.marcador_visitante}",
            r.visitante,
            r.temporada,
        )
        for r in resultados
    ]
    return pd.DataFrame(filas, columns=["Fecha", "Local", "Resultado", "Visita", "Temporada"])


def exportar_excel(
    apuestas: list[Apuesta],
    movimientos: list[Movimiento],
    resumen: Resumen,
    predicciones: list[Prediccion] = (),
    evaluadas: list[Evaluada] = (),
    fuentes: dict[str, MetricasFuente] | None = None,
) -> bytes:
    totales = tabla_resumen(resumen)
    por_valor = {f"Valor: {Valor(v).etiqueta}": m for v, m in resumen.por_valor.items()}
    desglose = tabla_metricas({**resumen.por_deporte, **resumen.por_liga, **por_valor})

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        tabla_apuestas(apuestas).to_excel(writer, sheet_name="Apuestas", index=False)
        tabla_movimientos(movimientos).to_excel(writer, sheet_name="Movimientos", index=False)
        totales.to_excel(writer, sheet_name="Resumen", index=False)
        desglose.to_excel(writer, sheet_name="Resumen", index=False, startrow=len(totales) + 2)
        tabla_predicciones(list(predicciones), list(evaluadas)).to_excel(
            writer, sheet_name="Predicciones", index=False
        )
        tabla_fuentes(fuentes or {}).to_excel(writer, sheet_name="Contraste", index=False)
        for hoja in writer.sheets.values():
            for fila in hoja.iter_rows():
                for celda in fila:
                    # Nombres y notas vienen de fuentes externas o del usuario: un texto que
                    # empieza con "=" se guarda como texto, nunca como fórmula.
                    if celda.data_type == "f":
                        celda.data_type = "s"
            for columna in hoja.columns:
                ancho = max(len(str(celda.value or "")) for celda in columna)
                hoja.column_dimensions[columna[0].column_letter].width = min(ancho + 2, 50)
    return buffer.getvalue()
