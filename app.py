"""Predictor de apuestas: interfaz Streamlit. Ejecutar con `streamlit run app.py`."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import streamlit as st

from predictor.bitacora import Bitacora
from predictor.cartelera import Cartelera
from predictor.exportar import (
    exportar_excel,
    resumen_contraste,
    tabla_apuestas,
    tabla_backtest_valor,
    tabla_cara_a_cara,
    tabla_contraste,
    tabla_cuotas,
    tabla_estadisticas,
    tabla_evaluacion,
    tabla_fuentes,
    tabla_jugadores,
    tabla_metricas,
    tabla_movimientos,
    tabla_predicciones,
    tabla_valor_del_dia,
)
from predictor.fuentes.odds_api import ClienteOddsApi, costo_creditos
from predictor.ligas import ZONA_CHILE
from predictor.modelos import (
    LIGAS,
    Apuesta,
    Deporte,
    Estado,
    Ganador,
    Mercado,
    Movimiento,
    Partido,
    Prediccion,
    TipoMovimiento,
    Valor,
)
from predictor.repositorio import Repositorio
from predictor.valor import Umbrales, Valoracion, clasificar

AVISO_VALOR = (
    "✅ Confirmado: el modelo ve valor en la cuota de Betano y el mercado (Pinnacle sin margen) "
    "no lo contradice. ⚠️ Solo modelo: el mercado no está de acuerdo; en el backtest de fútbol "
    "2025-26 esa estrategia perdió dinero. Las cuotas son de Betano UK: confirma la de Betano "
    "Chile antes de apostar. El valor no es una garantía."
)

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


def registrar(
    bitacora: Bitacora, valoracion: Valoracion | None, umbrales: Umbrales, **datos
) -> None:
    """Registra la apuesta; si viene de la cartelera, recalcula el valor con la cuota escrita."""
    if valoracion is not None:
        datos["prob_modelo"] = valoracion.prob_modelo
        datos["valor"] = clasificar(
            datos["cuota"], valoracion.prob_modelo, valoracion.prob_mercado, umbrales
        )
    bitacora.registrar_apuesta(Apuesta(**datos))


def describir_fila(valoracion: Valoracion) -> tuple[str, str]:
    """Mercado y selección de una fila de cuotas, como se escriben en la bitácora."""
    fila = valoracion.fila
    mercado = fila.mercado.etiqueta
    if fila.linea is not None:
        linea = f"{fila.linea:+g}" if fila.mercado is Mercado.HANDICAP else f"{fila.linea:g}"
        mercado += f" {linea}"
    return mercado, "Empate" if fila.seleccion == "Draw" else fila.seleccion


def actualizar(cartelera: Cartelera, ligas: list[str]) -> None:
    with st.spinner("Descargando cuotas, historial y jugadores…"):
        if cartelera.tiene_clave:
            cartelera.actualizar_cuotas(ligas)
        cartelera.actualizar_historial(ligas)
        _, errores = cartelera.actualizar_jugadores(ligas)
        _, errores_bpi = cartelera.actualizar_bpi() if "NBA" in ligas else ([], {})
    st.session_state["errores_jugadores"] = errores
    st.session_state["errores_bpi"] = errores_bpi


def sin_markdown(texto: str) -> str:
    """Escapa el markdown de textos de fuentes externas (nombres y lesiones)."""
    return re.sub(r"([\\`*_{}\[\]()<>#+\-.!|~$])", r"\\\1", texto)


def hora_chile(momento: datetime) -> str:
    return f"{momento.astimezone(ZONA_CHILE):%H:%M}"


def mostrar_prediccion(prediccion: Prediccion, empezado: bool) -> None:
    st.markdown(
        "**Predicción del modelo**"
        + (" (congelada al inicio)" if empezado else "")
        + f" · {prediccion.modelo}"
    )
    columnas = st.columns(5 if prediccion.prob_empate is not None else 4)
    columnas[0].metric(prediccion.local, pct(prediccion.prob_local))
    if prediccion.prob_empate is not None:
        columnas[1].metric("Empate", pct(prediccion.prob_empate))
    columnas[-3].metric(prediccion.visitante, pct(prediccion.prob_visitante))
    formato = ".2g" if prediccion.prob_empate is not None else ".1f"  # goles o puntos
    columnas[-2].metric(
        "Marcador esperado",
        f"{prediccion.esperado_local:{formato}} - {prediccion.esperado_visitante:{formato}}",
        help=(
            f"Marcador más probable: {prediccion.marcador_probable}"
            if prediccion.marcador_probable
            else None
        ),
    )
    total = f"{prediccion.total_esperado:.1f}"
    if prediccion.linea_total is not None and prediccion.prob_over is not None:
        columnas[-1].metric(
            f"Total (línea {prediccion.linea_total:g})",
            total,
            delta=f"Over {pct(prediccion.prob_over)}",
            delta_color="off",
        )
    else:
        columnas[-1].metric("Total esperado", total)
    if prediccion.factores:
        st.markdown("\n".join(f"- {sin_markdown(factor)}" for factor in prediccion.factores))


def mostrar_contraste(
    cartelera: Cartelera, partido: Partido, prediccion: Prediccion | None, empezado: bool
) -> None:
    """Mi predicción, el modelo, ESPN BPI y el mercado lado a lado, y el formulario de la mía."""
    propia = cartelera.prediccion_propia(partido)
    pronosticos = cartelera.pronosticos(partido, prediccion)
    st.markdown("**Contraste**" + (" (congelado al inicio)" if empezado else ""))
    if propia is not None or pronosticos:
        st.dataframe(
            tabla_contraste(partido.local, partido.visitante, propia, pronosticos, prediccion),
            hide_index=True,
            width="stretch",
        )
        if linea := resumen_contraste(partido.local, partido.visitante, propia, pronosticos):
            st.caption(sin_markdown(linea))
    with st.form(f"propia_{partido.id}"):
        opciones = [Ganador.LOCAL, Ganador.VISITANTE]
        if partido.deporte is not Deporte.NBA:
            opciones.insert(1, Ganador.EMPATE)
        nombres = {
            Ganador.LOCAL: partido.local,
            Ganador.EMPATE: "Empate",
            Ganador.VISITANTE: partido.visitante,
        }
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        ganador = col1.radio(
            "Mi predicción",
            opciones,
            index=opciones.index(propia.ganador) if propia else 0,
            format_func=nombres.__getitem__,
            horizontal=True,
            disabled=empezado,
        )
        con_marcador = col2.checkbox(
            "Con marcador",
            value=propia is not None and propia.marcador_local is not None,
            disabled=empezado,
        )
        goles_local = col3.number_input(
            partido.local,
            min_value=0,
            value=(propia.marcador_local or 0) if propia else 0,
            disabled=empezado,
        )
        goles_visitante = col4.number_input(
            partido.visitante,
            min_value=0,
            value=(propia.marcador_visitante or 0) if propia else 0,
            disabled=empezado,
        )
        nota = st.text_input("Nota", value=propia.nota if propia else "", disabled=empezado)
        if st.form_submit_button("Guardar mi predicción", disabled=empezado):
            ejecutar(
                "Predicción guardada",
                cartelera.guardar_prediccion_propia,
                partido,
                ganador,
                int(goles_local) if con_marcador else None,
                int(goles_visitante) if con_marcador else None,
                nota,
            )


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
        data=exportar_excel(
            apuestas,
            movimientos,
            resumen,
            obtener_repositorio().listar_predicciones(),
            cartelera.evaluadas(),
            cartelera.evaluacion_por_fuente(),
        ),
        file_name=f"bitacora_{date.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

st.title("📒 Predictor de apuestas")
(
    tab_partidos,
    tab_modelo,
    tab_resumen,
    tab_nueva,
    tab_pendientes,
    tab_historial,
    tab_movimientos,
    tab_config,
) = st.tabs(
    [
        "Partidos",
        "Modelo",
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
    for liga, error in st.session_state.get("errores_jugadores", {}).items():
        st.warning(f"No se pudieron actualizar los jugadores de {liga}: {error}")
    for dia, error in st.session_state.get("errores_bpi", {}).items():
        st.warning(f"No se pudo actualizar el ESPN BPI del {dia}: {error}")

    partidos = cartelera.partidos(dia, desde_hora, hasta_hora, ligas) if ligas else []
    if not partidos:
        st.info("No hay partidos guardados para este filtro. Prueba con Actualizar.")
    else:
        st.subheader("Valor del día")
        oportunidades = cartelera.valor_del_dia(partidos)
        if oportunidades:
            st.dataframe(tabla_valor_del_dia(oportunidades), hide_index=True, width="stretch")
        else:
            st.caption("Ninguna cuota de Betano con valor en los partidos por empezar.")
        st.caption(AVISO_VALOR)
    ahora = datetime.now(UTC)
    for partido in partidos:
        etiqueta = f"{hora_chile(partido.inicio)} · {partido.liga} · {partido.nombre}"
        empezado = partido.inicio <= ahora
        if empezado:
            etiqueta += " · en curso"
        with st.expander(etiqueta):
            prediccion = cartelera.predecir(partido)
            if prediccion is not None:
                mostrar_prediccion(prediccion, empezado)
            else:
                st.caption("Sin historial suficiente para que el modelo prediga este partido.")
            mostrar_contraste(cartelera, partido, prediccion, empezado)
            filas = cartelera.comparar(partido)
            if filas:
                st.markdown("**Cuotas**")
                st.dataframe(
                    tabla_cuotas(filas, prediccion, cartelera.valorar(partido, prediccion)),
                    hide_index=True,
                    width="stretch",
                )
            else:
                st.caption("Sin cuotas para este partido.")
            jugadores_local, jugadores_visitante = cartelera.jugadores(partido)
            if jugadores_local or jugadores_visitante:
                st.markdown("**Figuras y bajas**")
                st.dataframe(
                    tabla_jugadores(
                        partido.local, jugadores_local, partido.visitante, jugadores_visitante
                    ),
                    hide_index=True,
                    width="stretch",
                )
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

with tab_modelo:
    st.caption(
        "El modelo es estadístico (Poisson en fútbol, ratings en la NBA). Cada predicción se "
        "guarda antes del inicio y se mide contra el resultado real. La línea base predice "
        "según cuánto gana el local, empata o gana la visita en la liga. Brier: menor es mejor."
    )
    evaluadas = cartelera.evaluadas()
    st.subheader("Predicciones guardadas")
    if evaluadas:
        st.dataframe(tabla_evaluacion(cartelera.evaluacion()), hide_index=True, width="stretch")
        st.dataframe(
            tabla_predicciones([e.prediccion for e in reversed(evaluadas)], evaluadas),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("Aún no hay predicciones con resultado. Se miden tras actualizar el historial.")
    st.subheader("Por opinión")
    fuentes = cartelera.evaluacion_por_fuente()
    if fuentes:
        st.caption(
            "Acierto del favorito de cada opinión en los partidos jugados. La mía no tiene "
            "Brier porque solo elige ganador."
        )
        st.dataframe(tabla_fuentes(fuentes), hide_index=True, width="stretch")
    else:
        st.info("Aún no hay opiniones guardadas con resultado.")
    st.subheader("Backtest")
    if st.checkbox("Calcular backtest sobre el historial guardado (tarda unos segundos)"):
        with st.spinner("Recorriendo el historial…"):
            backtest = cartelera.backtest([liga for d in Deporte for liga in LIGAS[d]])
            backtest_valor = cartelera.backtest_valor(LIGAS[Deporte.FUTBOL])
        st.caption("Cada fecha se predice solo con los partidos anteriores.")
        st.dataframe(tabla_evaluacion(backtest), hide_index=True, width="stretch")
        st.markdown("**Estrategia de valor (fútbol)**")
        st.caption(
            "1 unidad a la cuota promedio previa cada vez que el modelo ve valor con los "
            "umbrales de Configuración, frente a apostar siempre al favorito. Aproximación: "
            "no usa la cuota de Betano ni la confirmación del mercado."
        )
        if backtest_valor:
            st.dataframe(tabla_backtest_valor(backtest_valor), hide_index=True, width="stretch")
        else:
            st.info("El historial guardado no tiene cuotas. Actualiza el historial de fútbol.")

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
    st.subheader("Con valor vs. sin valor")
    st.caption(
        "La hipótesis del proyecto: ¿rinden más las apuestas que la app marcó con valor? "
        "Incluye las no colocadas y solo cuenta las registradas desde la cartelera."
    )
    st.dataframe(
        tabla_metricas({Valor(v).etiqueta: m for v, m in resumen.por_valor.items()}),
        hide_index=True,
        width="stretch",
    )

    st.subheader("Apuestas no colocadas (hipotético)")
    nc = resumen.no_colocadas
    col1, col2, col3 = st.columns(3)
    col1.metric("Registradas", nc.total)
    col2.metric("Resultado si las hubieras hecho", clp(nc.resultado))
    col3.metric("ROI hipotético", pct(nc.roi))

with tab_nueva:
    hoy = datetime.now(ZONA_CHILE).date()
    proximos = [p for p in cartelera.partidos(hoy) if p.inicio > datetime.now(UTC)]
    origen = st.selectbox(
        "Desde la cartelera (opcional)",
        [None, *proximos],
        format_func=lambda p: (
            "— Escribir a mano —"
            if p is None
            else f"{hora_chile(p.inicio)} · {p.liga} · {p.nombre}"
        ),
        help="Partidos de hoy que aún no empiezan. Guarda la probabilidad del modelo y la "
        "marca de valor para comparar el ROI con y sin valor.",
    )
    valoracion = None
    if origen is not None:
        valoraciones = [
            v for v in cartelera.valorar(origen, cartelera.predecir(origen)) if v.fila.betano
        ]
        if valoraciones:
            valoracion = st.selectbox(
                "Cuota de Betano",
                valoraciones,
                format_func=lambda v: " · ".join(
                    [*describir_fila(v), f"{v.fila.betano}", v.valor.etiqueta]
                ),
            )
        else:
            st.caption("Este partido no tiene cuotas de Betano guardadas.")
    deporte = st.selectbox(
        "Deporte",
        list(Deporte),
        index=list(Deporte).index(origen.deporte) if origen else 0,
        format_func=str,
        disabled=origen is not None,
    )
    mercado_origen, seleccion_origen = describir_fila(valoracion) if valoracion else ("", "")
    with st.form("nueva_apuesta", clear_on_submit=True):
        col1, col2 = st.columns(2)
        liga = col1.selectbox(
            "Liga", LIGAS[deporte], index=LIGAS[deporte].index(origen.liga) if origen else 0
        )
        fecha_evento = col2.date_input(
            "Fecha del partido",
            value=origen.inicio.astimezone(ZONA_CHILE).date() if origen else date.today(),
        )
        partido = st.text_input(
            "Partido", value=origen.nombre if origen else "", placeholder="Lakers vs Celtics"
        )
        col1, col2 = st.columns(2)
        mercado = col1.text_input(
            "Mercado", value=mercado_origen, placeholder="Ganador, Over/Under 2.5, Hándicap…"
        )
        seleccion = col2.text_input("Selección", value=seleccion_origen, placeholder="Lakers")
        col1, col2, col3 = st.columns(3)
        cuota = col1.number_input(
            "Cuota",
            min_value=1.01,
            value=float(valoracion.fila.betano) if valoracion else 1.80,
            step=0.01,
            format="%.2f",
            help="Escribe la cuota real de Betano Chile: el valor se recalcula con ella.",
        )
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
                valoracion,
                cartelera.umbrales,
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
    umbrales = cartelera.umbrales
    with st.form("umbrales"):
        st.markdown("**Apuestas de valor**")
        col1, col2, col3 = st.columns(3)
        ev_modelo = col1.number_input(
            "EV mínimo del modelo (%)",
            min_value=0.0,
            max_value=100.0,
            value=umbrales.modelo * 100,
            step=1.0,
        )
        cuota_maxima = col2.number_input(
            "Cuota máxima", min_value=1.01, value=umbrales.cuota_maxima, step=0.5
        )
        ev_mercado = col3.number_input(
            "EV mínimo según el mercado para confirmar (%)",
            min_value=0.0,
            max_value=100.0,
            value=umbrales.mercado * 100,
            step=1.0,
        )
        if st.form_submit_button("Guardar umbrales"):
            ejecutar(
                "Umbrales actualizados",
                lambda: cartelera.fijar_umbrales(
                    Umbrales(ev_modelo / 100, cuota_maxima, ev_mercado / 100)
                ),
            )
    st.caption(f"Base de datos: `{RUTA_BD.resolve()}` (cámbiala con la variable PREDICTOR_DB)")
    estado_clave = "configurada" if cartelera.tiene_clave else "no configurada"
    st.caption(f"Clave de The Odds API (variable ODDS_API_KEY): {estado_clave}")
