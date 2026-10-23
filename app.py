"""Predictor de apuestas: interfaz Streamlit. Ejecutar con `streamlit run app.py`."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import streamlit as st

from predictor.bitacora import Bitacora
from predictor.cartelera import Cartelera
from predictor.exportar import (
    exportar_excel,
    tabla_apuestas,
    tabla_cara_a_cara,
    tabla_cuotas,
    tabla_estadisticas,
    tabla_metricas,
    tabla_movimientos,
)
from predictor.fuentes.odds_api import ClienteOddsApi, costo_creditos
from predictor.ligas import ZONA_CHILE
from predictor.modelos import LIGAS, Apuesta, Deporte, Estado, Movimiento, TipoMovimiento
from predictor.repositorio import Repositorio

RUTA_BD = Path(os.environ.get("PREDICTOR_DB", "data/bitacora.db"))


@st.cache_resource
def obtener_repositorio() -> Repositorio:
    RUTA_BD.parent.mkdir(parents=True, exist_ok=True)
    return Repositorio(RUTA_BD)


@st.cache_resource
def obtener_bitacora() -> Bitacora:
    return Bitacora(obtener_repositorio())


@st.cache_resource
def obtener_cartelera() -> Cartelera:
    clave = os.environ.get("ODDS_API_KEY", "").strip()
    return Cartelera(obtener_repositorio(), ClienteOddsApi(clave) if clave else None)


def clp(monto: int) -> str:
    signo = "-" if monto < 0 else ""
    return f"{signo}${abs(monto):,}".replace(",", ".")


def pct(valor: float | None) -> str:
    return "—" if valor is None else f"{valor:.1%}"


def ejecutar(mensaje: str, accion: Callable, *args, **kwargs) -> None:
    """Ejecuta una acción del dominio; muestra el error de validación o recarga la página."""
    try:
        accion(*args, **kwargs)
    except ValueError as error:
        st.error(str(error))
    else:
        st.toast(mensaje)
        st.rerun()


def registrar(bitacora: Bitacora, **datos) -> None:
    bitacora.registrar_apuesta(Apuesta(**datos))


def actualizar(cartelera: Cartelera, ligas: list[str]) -> None:
    with st.spinner("Descargando cuotas e historial…"):
        if cartelera.tiene_clave:
            cartelera.actualizar_cuotas(ligas)
        cartelera.actualizar_historial(ligas)


def hora_chile(momento: datetime) -> str:
    return f"{momento.astimezone(ZONA_CHILE):%H:%M}"


st.set_page_config(page_title="Predictor de apuestas", page_icon="📒", layout="wide")
bitacora = obtener_bitacora()
cartelera = obtener_cartelera()
apuestas = bitacora.apuestas()
movimientos = bitacora.movimientos()
resumen = bitacora.resumen()

with st.sidebar:
    st.metric("Saldo disponible", clp(resumen.saldo))
    st.metric("En juego", clp(resumen.en_juego))
    st.download_button(
        "Descargar Excel",
        data=exportar_excel(apuestas, movimientos, resumen),
        file_name=f"bitacora_{date.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

st.title("📒 Predictor de apuestas")
(
    tab_partidos,
    tab_resumen,
    tab_nueva,
    tab_pendientes,
    tab_historial,
    tab_movimientos,
    tab_config,
) = st.tabs(
    [
        "Partidos",
        "Resumen",
        "Nueva apuesta",
        "Pendientes",
        "Historial",
        "Movimientos",
        "Configuración",
    ]
)

with tab_partidos:
    col1, col2, col3, col4 = st.columns([1, 2, 1, 2])
    dia = col1.date_input("Día", value=datetime.now(ZONA_CHILE).date(), key="dia_partidos")
    desde_hora, hasta_hora = col2.slider("Hora de inicio (Chile)", 0, 24, (0, 24))
    deportes_partidos = col3.multiselect(
        "Deporte", list(Deporte), default=list(Deporte), format_func=str
    )
    opciones_ligas = [liga for d in deportes_partidos for liga in LIGAS[d]]
    ligas = col4.multiselect("Ligas", opciones_ligas, default=opciones_ligas)

    vencidas = cartelera.ligas_por_actualizar(ligas)
    col1, col2, col3 = st.columns([1, 1, 2])
    creditos = cartelera.creditos_restantes
    col1.metric("Créditos The Odds API", "—" if creditos is None else creditos)
    costo = costo_creditos(len(vencidas)) if cartelera.tiene_clave else 0
    if col2.button(f"Actualizar ({costo} créditos)", disabled=not ligas, type="primary"):
        ejecutar("Partidos actualizados", actualizar, cartelera, ligas)
    actualizadas = [m for liga in ligas if (m := cartelera.cuotas_actualizadas(liga))]
    if actualizadas:
        col3.caption(
            f"Cuotas consultadas por última vez a las {hora_chile(min(actualizadas))} "
            f"({len(vencidas)} de {len(ligas)} ligas con más de 1 hora)"
        )
    if not cartelera.tiene_clave:
        st.warning(
            "Falta la clave de The Odds API: define la variable de entorno ODDS_API_KEY y "
            "reinicia la app. Mientras tanto se muestran las cuotas ya guardadas y el "
            "botón solo descarga el historial."
        )

    partidos = cartelera.partidos(dia, desde_hora, hasta_hora, ligas) if ligas else []
    if not partidos:
        st.info("No hay partidos guardados para este filtro. Prueba con Actualizar.")
    ahora = datetime.now(UTC)
    for partido in partidos:
        etiqueta = f"{hora_chile(partido.inicio)} · {partido.liga} · {partido.nombre}"
        if partido.inicio <= ahora:
            etiqueta += " · en curso"
        with st.expander(etiqueta):
            filas = cartelera.comparar(partido)
            if filas:
                st.dataframe(tabla_cuotas(filas), hide_index=True, width="stretch")
            else:
                st.caption("Sin cuotas para este partido.")
            analisis = cartelera.analizar(partido)
            st.markdown("**Forma reciente** (propio / rival, promedio de los últimos 10)")
            st.dataframe(
                tabla_estadisticas(analisis, partido.local, partido.visitante),
                hide_index=True,
                width="stretch",
            )
            if analisis.cara_a_cara:
                st.markdown("**Enfrentamientos directos**")
                st.dataframe(
                    tabla_cara_a_cara(analisis.cara_a_cara), hide_index=True, width="stretch"
                )

with tab_resumen:
    capital = resumen.fondo_inicial + resumen.depositos - resumen.retiros
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Saldo", clp(resumen.saldo), delta=clp(resumen.saldo - capital))
    col2.metric("Ganancia / pérdida", clp(resumen.ganancia))
    col3.metric("ROI", pct(resumen.colocadas.roi))
    col4.metric("Acierto", pct(resumen.colocadas.acierto))
    c = resumen.colocadas
    st.caption(
        f"Capital aportado {clp(capital)} · {c.total} apuestas colocadas: "
        f"{c.ganadas} ganadas, {c.perdidas} perdidas, {c.nulas} nulas, {c.pendientes} pendientes"
    )

    st.subheader("Por deporte")
    st.dataframe(tabla_metricas(resumen.por_deporte), hide_index=True, width="stretch")
    st.subheader("Por liga")
    st.dataframe(tabla_metricas(resumen.por_liga), hide_index=True, width="stretch")

    st.subheader("Apuestas no colocadas (hipotético)")
    nc = resumen.no_colocadas
    col1, col2, col3 = st.columns(3)
    col1.metric("Registradas", nc.total)
    col2.metric("Resultado si las hubieras hecho", clp(nc.resultado))
    col3.metric("ROI hipotético", pct(nc.roi))

with tab_nueva:
    deporte = st.selectbox("Deporte", list(Deporte), format_func=str)
    with st.form("nueva_apuesta", clear_on_submit=True):
        col1, col2 = st.columns(2)
        liga = col1.selectbox("Liga", LIGAS[deporte])
        fecha_evento = col2.date_input("Fecha del partido", value=date.today())
        partido = st.text_input("Partido", placeholder="Lakers vs Celtics")
        col1, col2 = st.columns(2)
        mercado = col1.text_input("Mercado", placeholder="Ganador, Over/Under 2.5, Hándicap…")
        seleccion = col2.text_input("Selección", placeholder="Lakers")
        col1, col2, col3 = st.columns(3)
        cuota = col1.number_input("Cuota", min_value=1.01, value=1.80, step=0.01, format="%.2f")
        monto = col2.number_input("Monto (CLP)", min_value=1, value=500, step=100)
        casa = col3.text_input("Casa", value="Betano")
        colocada = st.checkbox(
            "Apuesta colocada",
            value=True,
            help="Desmárcala para registrar una apuesta que analizaste pero no hiciste.",
        )
        prediccion = st.text_area("Mi predicción", placeholder="Lakers ganan por 5-8 puntos")
        nota = st.text_input("Nota")
        if st.form_submit_button("Registrar apuesta", type="primary"):
            ejecutar(
                "Apuesta registrada",
                registrar,
                bitacora,
                deporte=deporte,
                liga=liga,
                partido=partido,
                mercado=mercado,
                seleccion=seleccion,
                cuota=Decimal(f"{cuota:.2f}"),
                monto=int(monto),
                fecha_evento=fecha_evento,
                casa=casa,
                colocada=colocada,
                prediccion_propia=prediccion,
                nota=nota,
            )

with tab_pendientes:
    pendientes = [a for a in apuestas if not a.liquidada]
    if not pendientes:
        st.info("No hay apuestas pendientes.")
    for apuesta in pendientes:
        etiqueta = (
            f"#{apuesta.id} · {apuesta.fecha_evento:%d-%m} · {apuesta.partido} — "
            f"{apuesta.seleccion} @ {apuesta.cuota} · {clp(apuesta.monto)}"
        )
        if not apuesta.colocada:
            etiqueta += " · no colocada"
        with st.expander(etiqueta), st.form(f"liquidar_{apuesta.id}"):
            estado = st.radio(
                "Resultado",
                [Estado.GANADA, Estado.PERDIDA, Estado.NULA],
                format_func=lambda e: e.value.capitalize(),
                horizontal=True,
            )
            ganancia = clp(apuesta.pago_bruto() - apuesta.monto)
            st.caption(f"Si gana, el resultado neto será {ganancia}")
            ajustar = st.checkbox("Ajustar resultado neto manualmente (redondeo de la casa)")
            neto = st.number_input("Resultado neto (CLP)", value=0, step=1)
            if st.form_submit_button("Liquidar"):
                ejecutar(
                    "Apuesta liquidada",
                    bitacora.liquidar,
                    apuesta.id,
                    estado,
                    int(neto) if ajustar else None,
                )

with tab_historial:
    col1, col2, col3 = st.columns(3)
    deportes = col1.multiselect("Deporte", list(Deporte), format_func=str)
    estados = col2.multiselect("Estado", list(Estado), format_func=str)
    tipo = col3.selectbox("Mostrar", ["Todas", "Colocadas", "No colocadas"])
    filtradas = [
        a
        for a in apuestas
        if (not deportes or a.deporte in deportes)
        and (not estados or a.estado in estados)
        and (tipo == "Todas" or a.colocada == (tipo == "Colocadas"))
    ]
    st.dataframe(tabla_apuestas(filtradas), hide_index=True, width="stretch")

    if apuestas:
        st.subheader("Corregir una apuesta")
        por_id = {a.id: a for a in apuestas}
        elegida = por_id[
            st.selectbox(
                "Apuesta",
                list(reversed(por_id)),
                format_func=lambda i: f"#{i} · {por_id[i].partido} · {por_id[i].estado}",
            )
        ]
        col1, col2 = st.columns(2)
        if col1.button("Volver a pendiente", disabled=not elegida.liquidada):
            ejecutar("Apuesta revertida a pendiente", bitacora.revertir, elegida.id)
        confirmar = col2.checkbox("Confirmo que quiero eliminarla")
        if col2.button("Eliminar", disabled=not confirmar):
            ejecutar("Apuesta eliminada", bitacora.eliminar_apuesta, elegida.id)

with tab_movimientos:
    with st.form("nuevo_movimiento", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        tipo_mov = col1.radio("Tipo", list(TipoMovimiento), format_func=str.capitalize)
        monto_mov = col2.number_input("Monto (CLP)", min_value=1, value=1000, step=500)
        fecha_mov = col3.date_input("Fecha", value=date.today())
        nota_mov = st.text_input("Nota")
        if st.form_submit_button("Registrar movimiento"):
            ejecutar(
                "Movimiento registrado",
                lambda: bitacora.registrar_movimiento(
                    Movimiento(tipo=tipo_mov, monto=int(monto_mov), fecha=fecha_mov, nota=nota_mov)
                ),
            )
    st.dataframe(tabla_movimientos(movimientos), hide_index=True, width="stretch")

with tab_config:
    with st.form("config"):
        fondo = st.number_input(
            "Fondo inicial (CLP)", min_value=0, value=bitacora.fondo_inicial, step=1000
        )
        if st.form_submit_button("Guardar"):
            ejecutar("Fondo inicial actualizado", bitacora.fijar_fondo_inicial, int(fondo))
    st.caption(f"Base de datos: `{RUTA_BD.resolve()}` (cámbiala con la variable PREDICTOR_DB)")
    estado_clave = "configurada" if cartelera.tiene_clave else "no configurada"
    st.caption(f"Clave de The Odds API (variable ODDS_API_KEY): {estado_clave}")
