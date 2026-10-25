from decimal import Decimal

import pytest

from predictor.bitacora import FONDO_INICIAL_POR_DEFECTO, Metricas, calcular_resultado
from predictor.modelos import Deporte, Estado, Movimiento, TipoMovimiento, Valor


def test_saldo_inicial_es_el_fondo_por_defecto(bitacora):
    assert FONDO_INICIAL_POR_DEFECTO == 10_000
    assert bitacora.fondo_inicial == 10_000
    assert bitacora.saldo() == 10_000


def test_fondo_inicial_configurable(bitacora):
    bitacora.fijar_fondo_inicial(25_000)

    assert bitacora.saldo() == 25_000


def test_fondo_inicial_negativo_falla(bitacora):
    with pytest.raises(ValueError):
        bitacora.fijar_fondo_inicial(-1)


def test_apuesta_colocada_pendiente_descuenta_del_saldo(bitacora, crear_apuesta):
    bitacora.registrar_apuesta(crear_apuesta(monto=1000))

    assert bitacora.saldo() == 9_000


def test_no_permite_apostar_mas_que_el_saldo(bitacora, crear_apuesta):
    with pytest.raises(ValueError, match="Saldo insuficiente"):
        bitacora.registrar_apuesta(crear_apuesta(monto=10_001))


def test_apuesta_no_colocada_no_afecta_saldo_ni_requiere_fondos(bitacora, crear_apuesta):
    bitacora.registrar_apuesta(crear_apuesta(monto=50_000, colocada=False))

    assert bitacora.saldo() == 10_000


def test_no_permite_registrar_dos_veces(bitacora, crear_apuesta):
    guardada = bitacora.registrar_apuesta(crear_apuesta())

    with pytest.raises(ValueError, match="ya está registrada"):
        bitacora.registrar_apuesta(guardada)


@pytest.mark.parametrize(
    ("estado", "resultado", "saldo"),
    [
        (Estado.GANADA, 850, 10_850),
        (Estado.PERDIDA, -1000, 9_000),
        (Estado.NULA, 0, 10_000),
    ],
)
def test_liquidar(bitacora, crear_apuesta, estado, resultado, saldo):
    apuesta = bitacora.registrar_apuesta(crear_apuesta(monto=1000, cuota=Decimal("1.85")))

    liquidada = bitacora.liquidar(apuesta.id, estado)

    assert liquidada.estado is estado
    assert liquidada.resultado_neto == resultado
    assert bitacora.saldo() == saldo


def test_liquidar_con_resultado_manual(bitacora, crear_apuesta):
    apuesta = bitacora.registrar_apuesta(crear_apuesta(monto=1000, cuota=Decimal("1.85")))

    liquidada = bitacora.liquidar(apuesta.id, Estado.GANADA, resultado_neto=849)

    assert liquidada.resultado_neto == 849
    assert bitacora.saldo() == 10_849


def test_no_liquida_dos_veces(bitacora, crear_apuesta):
    apuesta = bitacora.registrar_apuesta(crear_apuesta())
    bitacora.liquidar(apuesta.id, Estado.GANADA)

    with pytest.raises(ValueError, match="ya está liquidada"):
        bitacora.liquidar(apuesta.id, Estado.PERDIDA)


@pytest.mark.parametrize("resultado_manual", [None, 100])
def test_liquidar_como_pendiente_falla(bitacora, crear_apuesta, resultado_manual):
    apuesta = bitacora.registrar_apuesta(crear_apuesta())

    with pytest.raises(ValueError, match="revertir"):
        bitacora.liquidar(apuesta.id, Estado.PENDIENTE, resultado_neto=resultado_manual)


def test_calcular_resultado_de_pendiente_falla(crear_apuesta):
    with pytest.raises(ValueError, match="pendiente"):
        calcular_resultado(crear_apuesta(), Estado.PENDIENTE)


def test_liquidar_inexistente_falla(bitacora):
    with pytest.raises(ValueError, match="no existe"):
        bitacora.liquidar(123, Estado.GANADA)


def test_revertir_vuelve_a_pendiente(bitacora, crear_apuesta):
    apuesta = bitacora.registrar_apuesta(crear_apuesta(monto=1000))
    bitacora.liquidar(apuesta.id, Estado.GANADA)

    revertida = bitacora.revertir(apuesta.id)

    assert revertida.estado is Estado.PENDIENTE
    assert revertida.resultado_neto is None
    assert bitacora.saldo() == 9_000


def test_revertir_pendiente_falla(bitacora, crear_apuesta):
    apuesta = bitacora.registrar_apuesta(crear_apuesta())

    with pytest.raises(ValueError, match="pendiente"):
        bitacora.revertir(apuesta.id)


def test_eliminar_apuesta_libera_saldo(bitacora, crear_apuesta):
    apuesta = bitacora.registrar_apuesta(crear_apuesta(monto=1000))

    bitacora.eliminar_apuesta(apuesta.id)

    assert bitacora.apuestas() == []
    assert bitacora.saldo() == 10_000


def test_depositos_y_retiros_ajustan_saldo(bitacora):
    bitacora.registrar_movimiento(Movimiento(tipo=TipoMovimiento.DEPOSITO, monto=5_000))
    bitacora.registrar_movimiento(Movimiento(tipo=TipoMovimiento.RETIRO, monto=3_000))

    assert bitacora.saldo() == 12_000
    assert len(bitacora.movimientos()) == 2


def test_no_permite_retirar_mas_que_el_saldo(bitacora, crear_apuesta):
    bitacora.registrar_apuesta(crear_apuesta(monto=1000))

    with pytest.raises(ValueError, match="Saldo insuficiente"):
        bitacora.registrar_movimiento(Movimiento(tipo=TipoMovimiento.RETIRO, monto=9_001))


def test_metricas_roi_y_acierto():
    metricas = Metricas(ganadas=3, perdidas=1, nulas=1, apostado=4_000, resultado=1_000)

    assert metricas.roi == pytest.approx(0.25)
    assert metricas.acierto == pytest.approx(0.75)


def test_metricas_sin_apuestas_decididas():
    assert Metricas().roi is None
    assert Metricas().acierto is None


def test_resumen_completo(bitacora, crear_apuesta):
    nba_ganada = bitacora.registrar_apuesta(crear_apuesta(monto=1000, cuota=Decimal("2.00")))
    liga_perdida = bitacora.registrar_apuesta(
        crear_apuesta(deporte=Deporte.FUTBOL, liga="LaLiga", partido="Barça vs Madrid", monto=500)
    )
    nula = bitacora.registrar_apuesta(crear_apuesta(monto=300))
    bitacora.registrar_apuesta(crear_apuesta(monto=200))  # pendiente
    no_colocada = bitacora.registrar_apuesta(
        crear_apuesta(monto=1000, cuota=Decimal("3.00"), colocada=False)
    )
    bitacora.liquidar(nba_ganada.id, Estado.GANADA)
    bitacora.liquidar(liga_perdida.id, Estado.PERDIDA)
    bitacora.liquidar(nula.id, Estado.NULA)
    bitacora.liquidar(no_colocada.id, Estado.GANADA)
    bitacora.registrar_movimiento(Movimiento(tipo=TipoMovimiento.DEPOSITO, monto=2_000))
    bitacora.registrar_movimiento(Movimiento(tipo=TipoMovimiento.RETIRO, monto=1_000))

    resumen = bitacora.resumen()

    assert resumen.fondo_inicial == 10_000
    assert resumen.depositos == 2_000
    assert resumen.retiros == 1_000
    assert resumen.en_juego == 200
    # 10.000 + 2.000 - 1.000 + 1.000 - 500 + 0 - 200
    assert resumen.saldo == 11_300
    assert resumen.saldo == bitacora.saldo()
    assert resumen.ganancia == 500

    colocadas = resumen.colocadas
    assert (colocadas.total, colocadas.pendientes) == (4, 1)
    assert (colocadas.ganadas, colocadas.perdidas, colocadas.nulas) == (1, 1, 1)
    assert colocadas.apostado == 1_500
    assert colocadas.roi == pytest.approx(500 / 1_500)
    assert colocadas.acierto == pytest.approx(0.5)

    assert resumen.no_colocadas.total == 1
    assert resumen.no_colocadas.resultado == 2_000

    assert set(resumen.por_deporte) == {"NBA", "Futbol"}
    assert resumen.por_deporte["NBA"].resultado == 1_000
    assert resumen.por_liga["LaLiga"].resultado == -500


def test_resumen_por_valor_incluye_las_no_colocadas(bitacora, crear_apuesta):
    confirmada = bitacora.registrar_apuesta(
        crear_apuesta(cuota=Decimal("2.10"), prob_modelo=0.55, valor=Valor.CONFIRMADO)
    )
    solo_modelo = bitacora.registrar_apuesta(
        crear_apuesta(prob_modelo=0.6, valor=Valor.MODELO, colocada=False)
    )
    sin_valor = bitacora.registrar_apuesta(crear_apuesta())
    bitacora.liquidar(confirmada.id, Estado.GANADA)
    bitacora.liquidar(solo_modelo.id, Estado.PERDIDA)
    bitacora.liquidar(sin_valor.id, Estado.GANADA)

    por_valor = bitacora.resumen().por_valor

    assert list(por_valor) == ["confirmado", "modelo", "ninguno"]
    assert por_valor[Valor.CONFIRMADO].roi == pytest.approx(1.10)
    assert por_valor[Valor.MODELO].roi == pytest.approx(-1.0)
    assert por_valor[Valor.NINGUNO].resultado == 850
