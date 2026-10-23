from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from predictor.ligas import temporadas
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


def test_apuesta_valida_con_valores_por_defecto(crear_apuesta):
    apuesta = crear_apuesta()

    assert apuesta.estado is Estado.PENDIENTE
    assert apuesta.casa == "Betano"
    assert apuesta.colocada is True
    assert apuesta.resultado_neto is None
    assert not apuesta.liquidada


def test_convierte_textos_a_enums_y_cuota_a_decimal(crear_apuesta):
    apuesta = crear_apuesta(deporte="Futbol", liga="LaLiga", cuota=2.1, estado="pendiente")

    assert apuesta.deporte is Deporte.FUTBOL
    assert apuesta.cuota == Decimal("2.1")


@pytest.mark.parametrize("cuota", [Decimal("1"), Decimal("0.5"), Decimal("-2")])
def test_rechaza_cuota_no_mayor_a_uno(crear_apuesta, cuota):
    with pytest.raises(ValueError, match="cuota"):
        crear_apuesta(cuota=cuota)


@pytest.mark.parametrize("monto", [0, -100])
def test_rechaza_monto_no_positivo(crear_apuesta, monto):
    with pytest.raises(ValueError, match="mayor a 0"):
        crear_apuesta(monto=monto)


@pytest.mark.parametrize("monto", [100.5, "1000", True])
def test_rechaza_monto_no_entero(crear_apuesta, monto):
    with pytest.raises(ValueError, match="entero"):
        crear_apuesta(monto=monto)


def test_rechaza_liga_que_no_corresponde_al_deporte(crear_apuesta):
    with pytest.raises(ValueError, match="liga"):
        crear_apuesta(deporte=Deporte.NBA, liga="LaLiga")


def test_rechaza_deporte_desconocido(crear_apuesta):
    with pytest.raises(ValueError):
        crear_apuesta(deporte="Tenis")


@pytest.mark.parametrize("campo", ["partido", "mercado", "seleccion"])
def test_rechaza_campos_obligatorios_vacios(crear_apuesta, campo):
    with pytest.raises(ValueError, match=campo):
        crear_apuesta(**{campo: "   "})


def test_pendiente_no_puede_tener_resultado(crear_apuesta):
    with pytest.raises(ValueError, match="pendiente"):
        crear_apuesta(resultado_neto=100)


def test_liquidada_debe_tener_resultado(crear_apuesta):
    with pytest.raises(ValueError, match="liquidada"):
        crear_apuesta(estado=Estado.GANADA)


@pytest.mark.parametrize(
    ("monto", "cuota", "esperado"),
    [
        (1000, "1.85", 1850),
        (1001, "1.85", 1852),  # 1851.85
        (1000, "1.8505", 1851),  # 1850.5 redondea hacia arriba
        (333, "3.00", 999),
    ],
)
def test_pago_bruto_redondea_al_peso(crear_apuesta, monto, cuota, esperado):
    assert crear_apuesta(monto=monto, cuota=Decimal(cuota)).pago_bruto() == esperado


def test_movimiento_valido():
    movimiento = Movimiento(tipo="deposito", monto=5000)

    assert movimiento.tipo is TipoMovimiento.DEPOSITO


def test_movimiento_rechaza_monto_no_positivo():
    with pytest.raises(ValueError):
        Movimiento(tipo=TipoMovimiento.RETIRO, monto=0)


def test_movimiento_rechaza_tipo_desconocido():
    with pytest.raises(ValueError):
        Movimiento(tipo="transferencia", monto=100)


def _partido(**cambios):
    datos = {
        "id": "x1",
        "deporte": Deporte.FUTBOL,
        "liga": "LaLiga",
        "local": "Real Madrid",
        "visitante": "Barcelona",
        "inicio": datetime(2026, 10, 26, 15, 0, tzinfo=UTC),
    }
    datos.update(cambios)
    return Partido(**datos)


def test_partido_valido_y_nombre():
    assert _partido().nombre == "Real Madrid vs Barcelona"


@pytest.mark.parametrize(
    ("cambios", "mensaje"),
    [
        ({"liga": "NBA"}, "no corresponde"),
        ({"local": " "}, "'local' es obligatorio"),
        ({"inicio": datetime(2026, 10, 26, 15, 0)}, "zona horaria"),
    ],
)
def test_partido_invalido(cambios, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        _partido(**cambios)


def test_cuota_convierte_tipos_y_valida():
    cuota = Cuota("x1", "pinnacle", "totals", "Over", 1.9, datetime.now(UTC), linea=2.5)

    assert cuota.mercado is Mercado.TOTALES
    assert (cuota.cuota, cuota.linea) == (Decimal("1.9"), Decimal("2.5"))
    assert Mercado.HANDICAP.etiqueta == "Hándicap"
    with pytest.raises(ValueError, match="mayor a 1.00"):
        Cuota("x1", "pinnacle", "h2h", "Draw", "1", datetime.now(UTC))


def test_resultado_historico_no_admite_marcador_negativo():
    with pytest.raises(ValueError, match="negativo"):
        ResultadoHistorico("NBA", "2026-27", date(2026, 10, 22), "A", "B", -1, 100)


@pytest.mark.parametrize(
    ("deporte", "hoy", "esperado"),
    [
        (Deporte.FUTBOL, date(2026, 10, 23), ("2627", "2526")),
        (Deporte.FUTBOL, date(2027, 5, 1), ("2627", "2526")),
        (Deporte.FUTBOL, date(2099, 8, 1), ("9900", "9899")),
        (Deporte.NBA, date(2026, 10, 23), ("2026-27", "2025-26")),
        (Deporte.NBA, date(2026, 9, 30), ("2025-26", "2024-25")),
    ],
)
def test_temporadas(deporte, hoy, esperado):
    assert temporadas(deporte, hoy) == esperado
