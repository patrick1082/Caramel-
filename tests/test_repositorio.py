import sqlite3
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from predictor.modelos import (
    Cuota,
    Deporte,
    Estado,
    Mercado,
    Movimiento,
    Partido,
    ResultadoHistorico,
    TipoMovimiento,
)
from predictor.repositorio import _ESQUEMA_V1, Repositorio

AHORA = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def _partido(id_="p1", liga="Premier League", inicio=AHORA, **cambios) -> Partido:
    datos = {
        "id": id_,
        "deporte": Deporte.NBA if liga == "NBA" else Deporte.FUTBOL,
        "liga": liga,
        "local": "Arsenal",
        "visitante": "Everton",
        "inicio": inicio,
    }
    datos.update(cambios)
    return Partido(**datos)


def _cuota(partido_id="p1", **cambios) -> Cuota:
    datos = {
        "partido_id": partido_id,
        "casa": "pinnacle",
        "mercado": Mercado.GANADOR,
        "seleccion": "Arsenal",
        "cuota": Decimal("1.55"),
        "actualizada": AHORA,
    }
    datos.update(cambios)
    return Cuota(**datos)


def test_agregar_asigna_id_y_conserva_todos_los_campos(repo, crear_apuesta):
    original = crear_apuesta(
        colocada=False, prediccion_propia="Lakers por 6", nota="sin LeBron", casa="Stake"
    )

    guardada = repo.agregar_apuesta(original)
    leida = repo.obtener_apuesta(guardada.id)

    assert guardada.id is not None
    assert leida == guardada
    assert replace(leida, id=None) == original


def test_obtener_inexistente_devuelve_none(repo):
    assert repo.obtener_apuesta(999) is None


def test_listar_devuelve_en_orden_de_registro(repo, crear_apuesta):
    primera = repo.agregar_apuesta(crear_apuesta(partido="A vs B"))
    segunda = repo.agregar_apuesta(crear_apuesta(partido="C vs D"))

    assert repo.listar_apuestas() == [primera, segunda]


def test_actualizar_persiste_liquidacion(repo, crear_apuesta):
    guardada = repo.agregar_apuesta(crear_apuesta())
    liquidada = replace(guardada, estado=Estado.GANADA, resultado_neto=850)

    repo.actualizar_apuesta(liquidada)

    assert repo.obtener_apuesta(guardada.id) == liquidada


def test_actualizar_inexistente_falla(repo, crear_apuesta):
    with pytest.raises(ValueError, match="no existe"):
        repo.actualizar_apuesta(crear_apuesta(id=42))


def test_eliminar_apuesta(repo, crear_apuesta):
    guardada = repo.agregar_apuesta(crear_apuesta())

    repo.eliminar_apuesta(guardada.id)

    assert repo.listar_apuestas() == []
    with pytest.raises(ValueError, match="no existe"):
        repo.eliminar_apuesta(guardada.id)


def test_movimientos_ida_y_vuelta(repo):
    deposito = repo.agregar_movimiento(
        Movimiento(tipo=TipoMovimiento.DEPOSITO, monto=5000, fecha=date(2026, 10, 1), nota="sueldo")
    )
    retiro = repo.agregar_movimiento(Movimiento(tipo=TipoMovimiento.RETIRO, monto=2000))

    assert repo.listar_movimientos() == [deposito, retiro]
    assert deposito.id is not None


def test_config_por_defecto_vacia_y_sobrescribible(repo):
    assert repo.obtener_config("fondo_inicial") is None

    repo.fijar_config("fondo_inicial", "10000")
    repo.fijar_config("fondo_inicial", "20000")

    assert repo.obtener_config("fondo_inicial") == "20000"


def test_datos_persisten_al_reabrir_archivo(tmp_path, crear_apuesta):
    ruta = tmp_path / "bitacora.db"
    repo = Repositorio(ruta)
    guardada = repo.agregar_apuesta(crear_apuesta())
    repo.fijar_config("fondo_inicial", "15000")
    repo.cerrar()

    reabierto = Repositorio(ruta)

    assert reabierto.listar_apuestas() == [guardada]
    assert reabierto.obtener_config("fondo_inicial") == "15000"
    reabierto.cerrar()


def test_migra_base_v1_sin_perder_apuestas(tmp_path, crear_apuesta):
    ruta = tmp_path / "v1.db"
    con = sqlite3.connect(ruta)
    con.executescript(_ESQUEMA_V1)
    con.execute(
        "INSERT INTO apuestas (fecha_registro, fecha_evento, deporte, liga, partido, mercado, "
        "seleccion, cuota, monto, casa, colocada, prediccion_propia, estado, resultado_neto, "
        "nota) VALUES ('2026-10-01T10:00:00', '2026-10-02', 'NBA', 'NBA', 'A vs B', 'Ganador', "
        "'A', '1.9', 1000, 'Betano', 1, '', 'pendiente', NULL, '')"
    )
    con.commit()
    con.close()

    repo = Repositorio(ruta)

    assert [a.partido for a in repo.listar_apuestas()] == ["A vs B"]
    assert repo._con.execute("PRAGMA user_version").fetchone()[0] == 2
    assert repo.listar_partidos(AHORA, AHORA + timedelta(days=1)) == []
    repo.cerrar()


def test_cartelera_ida_y_vuelta_en_utc(repo):
    chile = timezone(timedelta(hours=-3))
    partido = _partido(inicio=datetime(2026, 10, 24, 9, 0, tzinfo=chile))
    cuotas = [
        _cuota(),
        _cuota(mercado=Mercado.TOTALES, seleccion="Over", linea=Decimal("2.5"), cuota="1.9"),
    ]

    repo.reemplazar_cartelera("Premier League", [partido], cuotas)

    [leido] = repo.listar_partidos(AHORA - timedelta(hours=1), AHORA + timedelta(hours=1))
    assert leido == replace(partido, inicio=AHORA)
    assert sorted(repo.cuotas_de("p1"), key=lambda c: c.mercado) == sorted(
        cuotas, key=lambda c: c.mercado
    )


def test_reemplazar_cartelera_solo_afecta_a_esa_liga(repo):
    repo.reemplazar_cartelera("Premier League", [_partido("p1")], [_cuota("p1")])
    repo.reemplazar_cartelera(
        "NBA", [_partido("n1", liga="NBA", local="Bulls", visitante="Bucks")], [_cuota("n1")]
    )

    repo.reemplazar_cartelera("Premier League", [_partido("p2")], [])

    ids = [p.id for p in repo.listar_partidos(AHORA, AHORA + timedelta(minutes=1))]
    assert ids == ["n1", "p2"]
    assert repo.cuotas_de("p1") == []
    assert len(repo.cuotas_de("n1")) == 1


def test_listar_partidos_filtra_por_rango_y_liga(repo):
    repo.reemplazar_cartelera(
        "Premier League",
        [_partido("tarde", inicio=AHORA + timedelta(hours=5)), _partido("ahora")],
        [],
    )
    repo.reemplazar_cartelera("NBA", [_partido("nba", liga="NBA")], [])

    rango = (AHORA, AHORA + timedelta(hours=5))
    assert [p.id for p in repo.listar_partidos(*rango)] == ["nba", "ahora"]  # fin excluido
    assert [p.id for p in repo.listar_partidos(*rango, ligas=["NBA"])] == ["nba"]
    assert repo.listar_partidos(*rango, ligas=[]) == []


def test_historial_reemplaza_la_temporada(repo):
    def resultado(fecha, temporada="2627", **extras):
        return ResultadoHistorico(
            "Premier League", temporada, fecha, "Arsenal", "Everton", 2, 1, extras
        )

    repo.guardar_historial("Premier League", "2526", [resultado(date(2026, 3, 1), "2526")])
    repo.guardar_historial("Premier League", "2627", [resultado(date(2026, 9, 1))])
    nuevo = resultado(date(2026, 9, 8), tiros=(12.0, 7.0))

    repo.guardar_historial("Premier League", "2627", [nuevo, resultado(date(2026, 9, 1))])

    historial = repo.historial_de("Premier League")
    assert [r.fecha for r in historial] == [date(2026, 3, 1), date(2026, 9, 1), date(2026, 9, 8)]
    assert historial[-1] == nuevo
    assert repo.historial_de("NBA") == []
