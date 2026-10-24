"""Persistencia en SQLite. Única capa del proyecto que habla con la base de datos."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from predictor.modelos import (
    Apuesta,
    Cuota,
    Jugador,
    Movimiento,
    Partido,
    Prediccion,
    ProbabilidadLinea,
    ResultadoHistorico,
)

_ESQUEMA_V1 = """
CREATE TABLE apuestas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_registro TEXT NOT NULL,
    fecha_evento TEXT NOT NULL,
    deporte TEXT NOT NULL,
    liga TEXT NOT NULL,
    partido TEXT NOT NULL,
    mercado TEXT NOT NULL,
    seleccion TEXT NOT NULL,
    cuota TEXT NOT NULL,
    monto INTEGER NOT NULL,
    casa TEXT NOT NULL,
    colocada INTEGER NOT NULL,
    prediccion_propia TEXT NOT NULL,
    estado TEXT NOT NULL,
    resultado_neto INTEGER,
    nota TEXT NOT NULL
);
CREATE TABLE movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    tipo TEXT NOT NULL,
    monto INTEGER NOT NULL,
    nota TEXT NOT NULL
);
CREATE TABLE config (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
PRAGMA user_version = 1;
"""

_ESQUEMA_V2 = """
CREATE TABLE partidos (
    id TEXT PRIMARY KEY,
    deporte TEXT NOT NULL,
    liga TEXT NOT NULL,
    local TEXT NOT NULL,
    visitante TEXT NOT NULL,
    inicio TEXT NOT NULL
);
CREATE INDEX partidos_inicio ON partidos (inicio);
CREATE TABLE cuotas (
    partido_id TEXT NOT NULL REFERENCES partidos (id),
    casa TEXT NOT NULL,
    mercado TEXT NOT NULL,
    seleccion TEXT NOT NULL,
    linea TEXT,
    cuota TEXT NOT NULL,
    actualizada TEXT NOT NULL
);
CREATE INDEX cuotas_partido ON cuotas (partido_id);
CREATE TABLE historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    liga TEXT NOT NULL,
    temporada TEXT NOT NULL,
    fecha TEXT NOT NULL,
    local TEXT NOT NULL,
    visitante TEXT NOT NULL,
    marcador_local INTEGER NOT NULL,
    marcador_visitante INTEGER NOT NULL,
    extras TEXT NOT NULL,
    UNIQUE (liga, fecha, local, visitante)
);
PRAGMA user_version = 2;
"""

# Sin clave foránea a partidos: `reemplazar_cartelera` los borra y la predicción debe quedar
# para compararla con el resultado real.
_ESQUEMA_V3 = """
CREATE TABLE predicciones (
    partido_id TEXT PRIMARY KEY,
    liga TEXT NOT NULL,
    local TEXT NOT NULL,
    visitante TEXT NOT NULL,
    inicio TEXT NOT NULL,
    modelo TEXT NOT NULL,
    creada TEXT NOT NULL,
    esperado_local REAL NOT NULL,
    esperado_visitante REAL NOT NULL,
    prob_local REAL NOT NULL,
    prob_empate REAL,
    prob_visitante REAL NOT NULL,
    marcador_probable TEXT,
    factores TEXT NOT NULL,
    lineas TEXT NOT NULL,
    linea_total REAL
);
CREATE INDEX predicciones_inicio ON predicciones (inicio);
CREATE TABLE jugadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    liga TEXT NOT NULL,
    equipo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL,
    detalle TEXT NOT NULL,
    valor REAL NOT NULL
);
CREATE INDEX jugadores_liga ON jugadores (liga);
PRAGMA user_version = 3;
"""

_COLUMNAS_PREDICCION = (
    "partido_id",
    "liga",
    "local",
    "visitante",
    "inicio",
    "modelo",
    "creada",
    "esperado_local",
    "esperado_visitante",
    "prob_local",
    "prob_empate",
    "prob_visitante",
    "marcador_probable",
    "factores",
    "lineas",
    "linea_total",
)

_COLUMNAS_APUESTA = (
    "fecha_registro",
    "fecha_evento",
    "deporte",
    "liga",
    "partido",
    "mercado",
    "seleccion",
    "cuota",
    "monto",
    "casa",
    "colocada",
    "prediccion_propia",
    "estado",
    "resultado_neto",
    "nota",
)


def _apuesta_a_fila(apuesta: Apuesta) -> dict:
    return {
        "id": apuesta.id,
        "fecha_registro": apuesta.fecha_registro.isoformat(timespec="seconds"),
        "fecha_evento": apuesta.fecha_evento.isoformat(),
        "deporte": apuesta.deporte.value,
        "liga": apuesta.liga,
        "partido": apuesta.partido,
        "mercado": apuesta.mercado,
        "seleccion": apuesta.seleccion,
        "cuota": str(apuesta.cuota),
        "monto": apuesta.monto,
        "casa": apuesta.casa,
        "colocada": int(apuesta.colocada),
        "prediccion_propia": apuesta.prediccion_propia,
        "estado": apuesta.estado.value,
        "resultado_neto": apuesta.resultado_neto,
        "nota": apuesta.nota,
    }


def _fila_a_apuesta(fila: sqlite3.Row) -> Apuesta:
    return Apuesta(
        id=fila["id"],
        fecha_registro=datetime.fromisoformat(fila["fecha_registro"]),
        fecha_evento=date.fromisoformat(fila["fecha_evento"]),
        deporte=fila["deporte"],
        liga=fila["liga"],
        partido=fila["partido"],
        mercado=fila["mercado"],
        seleccion=fila["seleccion"],
        cuota=Decimal(fila["cuota"]),
        monto=fila["monto"],
        casa=fila["casa"],
        colocada=bool(fila["colocada"]),
        prediccion_propia=fila["prediccion_propia"],
        estado=fila["estado"],
        resultado_neto=fila["resultado_neto"],
        nota=fila["nota"],
    )


def _utc(momento: datetime) -> str:
    return momento.astimezone(UTC).isoformat(timespec="seconds")


def _fila_a_partido(fila: sqlite3.Row) -> Partido:
    return Partido(
        id=fila["id"],
        deporte=fila["deporte"],
        liga=fila["liga"],
        local=fila["local"],
        visitante=fila["visitante"],
        inicio=datetime.fromisoformat(fila["inicio"]),
    )


def _fila_a_cuota(fila: sqlite3.Row) -> Cuota:
    return Cuota(
        partido_id=fila["partido_id"],
        casa=fila["casa"],
        mercado=fila["mercado"],
        seleccion=fila["seleccion"],
        cuota=Decimal(fila["cuota"]),
        actualizada=datetime.fromisoformat(fila["actualizada"]),
        linea=Decimal(fila["linea"]) if fila["linea"] is not None else None,
    )


def _fila_a_resultado(fila: sqlite3.Row) -> ResultadoHistorico:
    return ResultadoHistorico(
        liga=fila["liga"],
        temporada=fila["temporada"],
        fecha=date.fromisoformat(fila["fecha"]),
        local=fila["local"],
        visitante=fila["visitante"],
        marcador_local=fila["marcador_local"],
        marcador_visitante=fila["marcador_visitante"],
        extras={nombre: tuple(par) for nombre, par in json.loads(fila["extras"]).items()},
    )


def _prediccion_a_fila(p: Prediccion) -> dict:
    return {
        "partido_id": p.partido_id,
        "liga": p.liga,
        "local": p.local,
        "visitante": p.visitante,
        "inicio": _utc(p.inicio),
        "modelo": p.modelo,
        "creada": _utc(p.creada),
        "esperado_local": p.esperado_local,
        "esperado_visitante": p.esperado_visitante,
        "prob_local": p.prob_local,
        "prob_empate": p.prob_empate,
        "prob_visitante": p.prob_visitante,
        "marcador_probable": p.marcador_probable,
        "factores": json.dumps(p.factores, ensure_ascii=False),
        "lineas": json.dumps([[x.mercado.value, x.seleccion, x.linea, x.prob] for x in p.lineas]),
        "linea_total": p.linea_total,
    }


def _fila_a_prediccion(fila: sqlite3.Row) -> Prediccion:
    return Prediccion(
        partido_id=fila["partido_id"],
        liga=fila["liga"],
        local=fila["local"],
        visitante=fila["visitante"],
        inicio=datetime.fromisoformat(fila["inicio"]),
        modelo=fila["modelo"],
        creada=datetime.fromisoformat(fila["creada"]),
        esperado_local=fila["esperado_local"],
        esperado_visitante=fila["esperado_visitante"],
        prob_local=fila["prob_local"],
        prob_empate=fila["prob_empate"],
        prob_visitante=fila["prob_visitante"],
        marcador_probable=fila["marcador_probable"],
        factores=json.loads(fila["factores"]),
        lineas=[ProbabilidadLinea(*x) for x in json.loads(fila["lineas"])],
        linea_total=fila["linea_total"],
    )


def _fila_a_jugador(fila: sqlite3.Row) -> Jugador:
    return Jugador(
        liga=fila["liga"],
        equipo=fila["equipo"],
        nombre=fila["nombre"],
        rol=fila["rol"],
        detalle=fila["detalle"],
        valor=fila["valor"],
    )


def _fila_a_movimiento(fila: sqlite3.Row) -> Movimiento:
    return Movimiento(
        id=fila["id"],
        fecha=date.fromisoformat(fila["fecha"]),
        tipo=fila["tipo"],
        monto=fila["monto"],
        nota=fila["nota"],
    )


class Repositorio:
    def __init__(self, ruta: str | Path) -> None:
        # Streamlit atiende cada sesión en su propio hilo y comparte este recurso.
        self._con = sqlite3.connect(ruta, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        self._migrar()

    def _migrar(self) -> None:
        version = self._con.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            self._con.executescript(_ESQUEMA_V1)
        if version < 2:
            self._con.executescript(_ESQUEMA_V2)
        if version < 3:
            self._con.executescript(_ESQUEMA_V3)

    def cerrar(self) -> None:
        self._con.close()

    # --- Apuestas ---

    def agregar_apuesta(self, apuesta: Apuesta) -> Apuesta:
        columnas = ", ".join(_COLUMNAS_APUESTA)
        valores = ", ".join(f":{c}" for c in _COLUMNAS_APUESTA)
        with self._con:
            cursor = self._con.execute(
                f"INSERT INTO apuestas ({columnas}) VALUES ({valores})", _apuesta_a_fila(apuesta)
            )
        return self.obtener_apuesta(cursor.lastrowid)

    def obtener_apuesta(self, apuesta_id: int) -> Apuesta | None:
        fila = self._con.execute("SELECT * FROM apuestas WHERE id = ?", (apuesta_id,)).fetchone()
        return _fila_a_apuesta(fila) if fila else None

    def listar_apuestas(self) -> list[Apuesta]:
        filas = self._con.execute("SELECT * FROM apuestas ORDER BY id").fetchall()
        return [_fila_a_apuesta(fila) for fila in filas]

    def actualizar_apuesta(self, apuesta: Apuesta) -> None:
        asignaciones = ", ".join(f"{c} = :{c}" for c in _COLUMNAS_APUESTA)
        with self._con:
            cursor = self._con.execute(
                f"UPDATE apuestas SET {asignaciones} WHERE id = :id", _apuesta_a_fila(apuesta)
            )
        if cursor.rowcount == 0:
            raise ValueError(f"La apuesta #{apuesta.id} no existe")

    def eliminar_apuesta(self, apuesta_id: int) -> None:
        with self._con:
            cursor = self._con.execute("DELETE FROM apuestas WHERE id = ?", (apuesta_id,))
        if cursor.rowcount == 0:
            raise ValueError(f"La apuesta #{apuesta_id} no existe")

    # --- Movimientos ---

    def agregar_movimiento(self, movimiento: Movimiento) -> Movimiento:
        with self._con:
            cursor = self._con.execute(
                "INSERT INTO movimientos (fecha, tipo, monto, nota) VALUES (?, ?, ?, ?)",
                (
                    movimiento.fecha.isoformat(),
                    movimiento.tipo.value,
                    movimiento.monto,
                    movimiento.nota,
                ),
            )
        fila = self._con.execute(
            "SELECT * FROM movimientos WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return _fila_a_movimiento(fila)

    def listar_movimientos(self) -> list[Movimiento]:
        filas = self._con.execute("SELECT * FROM movimientos ORDER BY id").fetchall()
        return [_fila_a_movimiento(fila) for fila in filas]

    # --- Partidos y cuotas ---

    def reemplazar_cartelera(
        self, liga: str, partidos: Iterable[Partido], cuotas: Iterable[Cuota]
    ) -> None:
        """Sustituye los partidos y cuotas de una liga por los de la última consulta."""
        with self._con:
            self._con.execute(
                "DELETE FROM cuotas WHERE partido_id IN (SELECT id FROM partidos WHERE liga = ?)",
                (liga,),
            )
            self._con.execute("DELETE FROM partidos WHERE liga = ?", (liga,))
            self._con.executemany(
                "INSERT INTO partidos (id, deporte, liga, local, visitante, inicio) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (p.id, p.deporte.value, p.liga, p.local, p.visitante, _utc(p.inicio))
                    for p in partidos
                ],
            )
            self._con.executemany(
                "INSERT INTO cuotas (partido_id, casa, mercado, seleccion, linea, cuota, "
                "actualizada) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        c.partido_id,
                        c.casa,
                        c.mercado.value,
                        c.seleccion,
                        str(c.linea) if c.linea is not None else None,
                        str(c.cuota),
                        _utc(c.actualizada),
                    )
                    for c in cuotas
                ],
            )

    def listar_partidos(
        self, desde: datetime, hasta: datetime, ligas: Iterable[str] | None = None
    ) -> list[Partido]:
        """Partidos que empiezan en [desde, hasta), ordenados por hora de inicio."""
        consulta = "SELECT * FROM partidos WHERE inicio >= ? AND inicio < ?"
        parametros: list = [_utc(desde), _utc(hasta)]
        if ligas is not None:
            ligas = list(ligas)
            consulta += f" AND liga IN ({', '.join('?' * len(ligas))})"
            parametros += ligas
        filas = self._con.execute(consulta + " ORDER BY inicio, liga, id", parametros).fetchall()
        return [_fila_a_partido(fila) for fila in filas]

    def cuotas_de(self, partido_id: str) -> list[Cuota]:
        filas = self._con.execute(
            "SELECT * FROM cuotas WHERE partido_id = ? ORDER BY mercado, casa, seleccion",
            (partido_id,),
        ).fetchall()
        return [_fila_a_cuota(fila) for fila in filas]

    # --- Historial ---

    def guardar_historial(
        self, liga: str, temporada: str, resultados: Iterable[ResultadoHistorico]
    ) -> None:
        """Sustituye la temporada completa de una liga."""
        with self._con:
            self._con.execute(
                "DELETE FROM historial WHERE liga = ? AND temporada = ?", (liga, temporada)
            )
            self._con.executemany(
                "INSERT OR REPLACE INTO historial (liga, temporada, fecha, local, visitante, "
                "marcador_local, marcador_visitante, extras) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        liga,
                        temporada,
                        r.fecha.isoformat(),
                        r.local,
                        r.visitante,
                        r.marcador_local,
                        r.marcador_visitante,
                        json.dumps(r.extras),
                    )
                    for r in resultados
                ],
            )

    def historial_de(self, liga: str) -> list[ResultadoHistorico]:
        filas = self._con.execute(
            "SELECT * FROM historial WHERE liga = ? ORDER BY fecha, id", (liga,)
        ).fetchall()
        return [_fila_a_resultado(fila) for fila in filas]

    # --- Predicciones ---

    def guardar_prediccion(self, prediccion: Prediccion) -> None:
        """Guarda o reemplaza la predicción de un partido."""
        columnas = ", ".join(_COLUMNAS_PREDICCION)
        valores = ", ".join(f":{c}" for c in _COLUMNAS_PREDICCION)
        with self._con:
            self._con.execute(
                f"INSERT OR REPLACE INTO predicciones ({columnas}) VALUES ({valores})",
                _prediccion_a_fila(prediccion),
            )

    def prediccion_de(self, partido_id: str) -> Prediccion | None:
        fila = self._con.execute(
            "SELECT * FROM predicciones WHERE partido_id = ?", (partido_id,)
        ).fetchone()
        return _fila_a_prediccion(fila) if fila else None

    def listar_predicciones(self, hasta: datetime | None = None) -> list[Prediccion]:
        """Predicciones (de partidos que empezaron antes de `hasta`), por hora de inicio."""
        consulta, parametros = "SELECT * FROM predicciones", []
        if hasta is not None:
            consulta, parametros = consulta + " WHERE inicio < ?", [_utc(hasta)]
        filas = self._con.execute(consulta + " ORDER BY inicio, partido_id", parametros).fetchall()
        return [_fila_a_prediccion(fila) for fila in filas]

    # --- Jugadores ---

    def reemplazar_jugadores(self, liga: str, jugadores: Iterable[Jugador]) -> None:
        with self._con:
            self._con.execute("DELETE FROM jugadores WHERE liga = ?", (liga,))
            self._con.executemany(
                "INSERT INTO jugadores (liga, equipo, nombre, rol, detalle, valor) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [(liga, j.equipo, j.nombre, j.rol.value, j.detalle, j.valor) for j in jugadores],
            )

    def jugadores_de(self, liga: str) -> list[Jugador]:
        filas = self._con.execute(
            "SELECT * FROM jugadores WHERE liga = ? ORDER BY equipo, rol, valor DESC, id", (liga,)
        ).fetchall()
        return [_fila_a_jugador(fila) for fila in filas]

    # --- Configuración ---

    def obtener_config(self, clave: str) -> str | None:
        fila = self._con.execute("SELECT valor FROM config WHERE clave = ?", (clave,)).fetchone()
        return fila["valor"] if fila else None

    def fijar_config(self, clave: str, valor: str) -> None:
        with self._con:
            self._con.execute(
                "INSERT INTO config (clave, valor) VALUES (?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
                (clave, valor),
            )
