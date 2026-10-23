"""Tablas de la bitácora y de la cartelera, y exportación a Excel."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from predictor.bitacora import Metricas, Resumen
from predictor.cartelera import Analisis, FilaComparacion
from predictor.estadisticas import Estadisticas, Promedios
from predictor.modelos import Apuesta, Mercado, Movimiento, ResultadoHistorico

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


def _cuota(valor) -> float | None:
    return None if valor is None else float(valor)


def _linea(fila: FilaComparacion) -> str:
    if fila.linea is None:
        return ""
    return f"{fila.linea:+g}" if fila.mercado is Mercado.HANDICAP else f"{fila.linea:g}"


def tabla_cuotas(filas: list[FilaComparacion]) -> pd.DataFrame:
    datos = [
        (
            f.mercado.etiqueta,
            "Empate" if f.seleccion == "Draw" else f.seleccion,
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
    return pd.DataFrame(datos, columns=COLUMNAS_CUOTAS)


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
    apuestas: list[Apuesta], movimientos: list[Movimiento], resumen: Resumen
) -> bytes:
    totales = tabla_resumen(resumen)
    desglose = tabla_metricas({**resumen.por_deporte, **resumen.por_liga})

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        tabla_apuestas(apuestas).to_excel(writer, sheet_name="Apuestas", index=False)
        tabla_movimientos(movimientos).to_excel(writer, sheet_name="Movimientos", index=False)
        totales.to_excel(writer, sheet_name="Resumen", index=False)
        desglose.to_excel(writer, sheet_name="Resumen", index=False, startrow=len(totales) + 2)
        for hoja in writer.sheets.values():
            for columna in hoja.columns:
                ancho = max(len(str(celda.value or "")) for celda in columna)
                hoja.column_dimensions[columna[0].column_letter].width = min(ancho + 2, 50)
    return buffer.getvalue()
