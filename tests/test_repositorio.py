from dataclasses import replace
from datetime import date

import pytest

from predictor.modelos import Estado, Movimiento, TipoMovimiento
from predictor.repositorio import Repositorio


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
