import json
from pathlib import Path

import pytest

from predictor.nombres import clave, emparejar

EQUIPOS = json.loads((Path(__file__).parent / "datos" / "equipos.json").read_text("utf-8"))


@pytest.mark.parametrize(
    ("nombre", "esperada"),
    [
        ("1. FC Köln", "koln"),
        ("Atlético Madrid", "atletico madrid"),
        ("Ath Madrid", "atletico madrid"),
        ("Nott'm Forest", "nottingham forest"),
        ("FSV Mainz 05", "mainz"),
        ("LA Clippers", "los angeles clippers"),
    ],
)
def test_clave(nombre, esperada):
    assert clave(nombre) == esperada


@pytest.mark.parametrize("liga", list(EQUIPOS))
def test_todos_los_equipos_de_the_odds_api_tienen_equivalente_unico(liga):
    odds, historial = EQUIPOS[liga]["odds"], EQUIPOS[liga]["historial"]

    emparejados = {nombre: emparejar(nombre, historial) for nombre in odds}

    assert None not in emparejados.values(), emparejados
    assert len(set(emparejados.values())) == len(odds)


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Manchester United", "Man United"),
        ("Brighton and Hove Albion", "Brighton"),
        ("Paris Saint Germain", "Paris SG"),
        ("Paris FC", "Paris FC"),
        ("AC Milan", "Milan"),
        ("Inter Milan", "Inter"),
        ("Borussia Monchengladbach", "M'gladbach"),
        ("Hamburger SV", "Hamburg"),
    ],
)
def test_casos_dificiles(nombre, esperado):
    liga = next(liga for liga, e in EQUIPOS.items() if esperado in e["historial"])

    assert emparejar(nombre, EQUIPOS[liga]["historial"]) == esperado


def test_parecido_por_ortografia():
    assert emparejar("Bayern Munchen", ["Bayern Munich", "Dortmund"]) == "Bayern Munich"


def test_sin_equivalente_devuelve_none(caplog):
    assert emparejar("Real Madrid", ["Arsenal", "Chelsea"]) is None
    assert "Sin equivalencia" in caplog.text
