"""Persistencia en SQLite. Única capa del proyecto que habla con la base de datos."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from predictor.modelos import Apuesta, Movimiento

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
