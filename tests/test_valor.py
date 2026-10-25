from datetime import UTC, datetime
from decimal import Decimal

import pytest

from predictor.cartelera import FilaComparacion
from predictor.modelos import Mercado, Prediccion, ProbabilidadLinea, Valor
from predictor.valor import (
    Umbrales,
    Valoracion,
    clasificar,
    ev,
    prob_estimada,
    prob_modelo,
    probabilidades_mercado,
    sin_margen,
    sugerir,
    valorar,
)

LOCAL, VISITA = "Aston Villa", "Manchester City"


def _fila(mercado, seleccion, betano, pinnacle, promedio=None, linea=None):
    def d(valor):
        return None if valor is None else Decimal(str(valor))

    cuotas = [c for c in (betano, pinnacle) if c is not None]
    return FilaComparacion(
        mercado=Mercado(mercado),
        seleccion=seleccion,
        linea=d(linea),
        betano=d(betano),
        pinnacle=d(pinnacle),
        mejor=d(max(cuotas)),
        casa_mejor="Betano (UK)",
        promedio=d(promedio or pinnacle or betano),
        casas=len(cuotas),
    )


def _prediccion():
    return Prediccion(
        partido_id="x",
        liga="Premier League",
        local=LOCAL,
        visitante=VISITA,
        inicio=datetime(2026, 10, 24, 11, 30, tzinfo=UTC),
        modelo="poisson-1",
        creada=datetime(2026, 10, 23, 15, tzinfo=UTC),
        esperado_local=1.1,
        esperado_visitante=1.6,
        prob_local=0.30,
        prob_empate=0.25,
        prob_visitante=0.45,
        lineas=[ProbabilidadLinea(Mercado.TOTALES, "Over", 2.5, 0.5)],
        linea_total=2.5,
    )


FILAS = [
    _fila("h2h", LOCAL, 3.1, 3.0),
    _fila("h2h", "Draw", 3.5, 3.6),
    _fila("h2h", VISITA, 2.5, 2.4),
    _fila("totals", "Over", 2.2, 2.6, linea=2.5),
    _fila("totals", "Under", 1.6, 1.5, linea=2.5),
    _fila("totals", "Over", 3.4, None, linea=3.5),  # sin pareja
]


def test_sin_margen_normaliza_y_valida():
    assert sin_margen([Decimal(2), Decimal(2)]) == [0.5, 0.5]
    probs = sin_margen([3.0, 3.6, 2.4])
    assert sum(probs) == pytest.approx(1)
    assert probs == pytest.approx([0.3243, 0.2703, 0.4054], abs=1e-4)
    with pytest.raises(ValueError, match="dos cuotas"):
        sin_margen([2.0])
    with pytest.raises(ValueError, match="dos cuotas"):
        sin_margen([2.0, 1.0])


def test_ev():
    assert ev(0.55, Decimal("2")) == pytest.approx(0.10)
    assert ev(0.5, 1.8) == pytest.approx(-0.10)


def test_probabilidades_mercado_agrupa_selecciones_complementarias():
    probs = probabilidades_mercado(FILAS, LOCAL)

    assert probs[(Mercado.GANADOR, VISITA, None)] == pytest.approx(0.4054, abs=1e-4)
    assert probs[(Mercado.TOTALES, "Over", Decimal("2.5"))] == pytest.approx(0.3659, abs=1e-4)
    assert (Mercado.TOTALES, "Over", Decimal("3.5")) not in probs


def test_probabilidades_mercado_usa_el_promedio_si_falta_pinnacle():
    filas = [
        _fila("h2h", LOCAL, 2.0, None, promedio=1.9),
        _fila("h2h", VISITA, 2.0, 1.9),
        _fila("totals", "Over", 1.9, 1.9),  # sin línea: se ignora
    ]

    probs = probabilidades_mercado(filas, LOCAL)

    assert probs == {
        (Mercado.GANADOR, LOCAL, None): pytest.approx(0.5),
        (Mercado.GANADOR, VISITA, None): pytest.approx(0.5),
    }


def test_probabilidades_mercado_empareja_handicap_opuesto():
    filas = [
        _fila("spreads", LOCAL, 1.9, 1.8, linea=-5.5),
        _fila("spreads", VISITA, 1.9, 2.0, linea=5.5),
        _fila("spreads", LOCAL, 2.6, 2.5, linea=5.5),  # su pareja sería el visitante -5.5
    ]

    probs = probabilidades_mercado(filas, LOCAL)

    assert probs[(Mercado.HANDICAP, LOCAL, Decimal("-5.5"))] == pytest.approx(0.5263, abs=1e-4)
    assert (Mercado.HANDICAP, LOCAL, Decimal("5.5")) not in probs


@pytest.mark.parametrize(
    "cuota, p_modelo, p_mercado, esperado",
    [
        (None, 0.6, 0.6, Valor.NINGUNO),
        (Decimal("2.5"), None, 0.6, Valor.NINGUNO),
        (Decimal("6.0"), 0.3, 0.3, Valor.NINGUNO),  # sobre la cuota máxima
        (Decimal("2.0"), 0.52, 0.6, Valor.NINGUNO),  # EV 4 % < 5 %
        (Decimal("2.0"), 0.55, None, Valor.MODELO),
        (Decimal("2.0"), 0.55, 0.45, Valor.MODELO),  # el mercado lo contradice
        (Decimal("2.0"), 0.55, 0.50, Valor.CONFIRMADO),  # cuota = cuota justa del mercado
    ],
)
def test_clasificar(cuota, p_modelo, p_mercado, esperado):
    assert clasificar(cuota, p_modelo, p_mercado) is esperado


def test_clasificar_con_umbrales_propios():
    umbrales = Umbrales(modelo=0.15, cuota_maxima=10, mercado=0.05)

    assert clasificar(Decimal("2.0"), 0.55, 0.6, umbrales) is Valor.NINGUNO
    assert clasificar(Decimal("8.0"), 0.15, 0.135, umbrales) is Valor.CONFIRMADO
    assert clasificar(Decimal("2.0"), 0.6, 0.5, umbrales) is Valor.MODELO


@pytest.mark.parametrize(
    "cambios, mensaje",
    [({"modelo": -0.1}, "entre 0 %"), ({"mercado": 2}, "entre 0 %"), ({"cuota_maxima": 1}, "1.00")],
)
def test_umbrales_invalidos(cambios, mensaje):
    with pytest.raises(ValueError, match=mensaje):
        Umbrales(**cambios)


def test_prob_modelo_por_mercado():
    prediccion = _prediccion()

    assert prob_modelo(FILAS[1], prediccion) == 0.25
    assert prob_modelo(FILAS[3], prediccion) == 0.5
    assert prob_modelo(FILAS[5], prediccion) is None


def test_valorar_marca_cada_fila():
    valoraciones = valorar(FILAS, _prediccion(), LOCAL)

    assert [v.valor for v in valoraciones] == [
        Valor.NINGUNO,
        Valor.NINGUNO,
        Valor.CONFIRMADO,  # modelo 45 % y mercado 40,5 % con cuota 2,50
        Valor.MODELO,  # modelo 50 % al over, mercado 36,6 %
        Valor.NINGUNO,  # sin probabilidad del modelo para el under
        Valor.NINGUNO,
    ]
    assert valoraciones[2].ev == pytest.approx(0.125)
    assert valoraciones[4].ev is None
    assert valoraciones[0].fila is FILAS[0]


def test_valorar_sin_prediccion_solo_muestra_el_mercado():
    valoraciones = valorar(FILAS, None, LOCAL)

    assert {v.valor for v in valoraciones} == {Valor.NINGUNO}
    assert valoraciones[2].prob_mercado == pytest.approx(0.4054, abs=1e-4)


def _valoracion(fila, modelo, mercado):
    return Valoracion(fila, modelo, mercado, None, Valor.NINGUNO)


def test_prob_estimada_promedia_modelo_y_mercado():
    fila = _fila("h2h", LOCAL, 2.0, 2.1)
    assert prob_estimada(_valoracion(fila, 0.6, 0.5)) == pytest.approx(0.55)
    assert prob_estimada(_valoracion(fila, None, 0.5)) == 0.5
    assert prob_estimada(_valoracion(fila, 0.7, None)) == 0.7
    assert prob_estimada(_valoracion(fila, None, None)) is None


def test_sugerir_elige_el_mejor_ev_entre_las_probables():
    favorito = _valoracion(_fila("h2h", LOCAL, 1.30, 1.32), 0.80, 0.76)  # EV -1,4 %
    over = _valoracion(_fila("totals", "Over", 1.95, 2.0, linea=2.5), 0.58, 0.56)  # EV +11 %
    improbable = _valoracion(_fila("h2h", VISITA, 5.0, 5.2), 0.30, 0.20)  # gran EV, poco probable
    sin_betano = _valoracion(_fila("totals", "Under", None, 1.9, linea=2.5), 0.50, 0.50)

    valoracion, prob = sugerir([favorito, over, improbable, sin_betano])

    assert valoracion is over and prob == pytest.approx(0.57)
    assert sugerir([favorito, improbable]) == (favorito, pytest.approx(0.78))
    assert sugerir([improbable, sin_betano]) is None
    assert sugerir([favorito], minimo=0.9) is None


def test_sugerir_usa_el_promedio_si_betano_no_ofrece_la_cuota():
    sin_betano = _valoracion(_fila("h2h", LOCAL, None, 1.9, promedio=1.85), 0.6, 0.56)
    assert sugerir([sin_betano]) == (sin_betano, pytest.approx(0.58))
