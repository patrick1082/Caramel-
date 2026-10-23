"""Tablas de la bitácora y exportación a Excel."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from predictor.bitacora import Metricas, Resumen
from predictor.modelos import Apuesta, Movimiento

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
