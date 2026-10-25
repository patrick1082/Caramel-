import pytest

from predictor import stake
from predictor.modelos import Valor
from predictor.valor import Valoracion


def _valoracion(valor, modelo=0.5, mercado=0.46):
    return Valoracion(None, modelo, mercado, None, valor)


def test_kelly():
    assert stake.kelly(0.5, 2.3) == pytest.approx(0.15 / 1.3)
    assert stake.kelly(0.4, 2.0) == 0.0  # EV negativo: no apostar


@pytest.mark.parametrize(
    ("modelo", "mercado", "esperado"),
    [
        (0.5, 0.46, 0.25 * (0.46 * 2.3 - 1) / 1.3),  # usa la más prudente: el mercado
        (0.46, 0.5, 0.25 * (0.46 * 2.3 - 1) / 1.3),  # o el modelo
        (0.5, None, 0.25 * 0.15 / 1.3),  # sin mercado, solo el modelo
        (0.7, 0.65, stake.TOPE),
        (0.5, 0.44, stake.PISO),
    ],
)
def test_confirmado_usa_un_cuarto_de_kelly_entre_piso_y_tope(modelo, mercado, esperado):
    valoracion = _valoracion(Valor.CONFIRMADO, modelo, mercado)
    assert stake.fraccion(valoracion, 2.3) == pytest.approx(esperado)


def test_sin_confirmar_va_con_un_porcentaje_fijo():
    assert stake.fraccion(_valoracion(Valor.MODELO), 2.3) == stake.SOLO_MODELO
    assert stake.fraccion(_valoracion(Valor.NINGUNO), 1.4) == stake.SIN_VALOR


def test_monto_redondea_hacia_abajo_y_respeta_el_minimo():
    assert stake.monto(100_000, 0.0112) == 1_100
    assert stake.monto(100_000, stake.TOPE) == 3_000
    assert stake.monto(5_000, 0.01) == 0  # $50: bajo el mínimo
    assert stake.monto(0, 0.01) == 0
    assert stake.monto(-2_000, 0.01) == 0
