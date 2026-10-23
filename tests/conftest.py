from datetime import date
from decimal import Decimal

import pytest

from predictor.bitacora import Bitacora
from predictor.modelos import Apuesta, Deporte
from predictor.repositorio import Repositorio


@pytest.fixture
def repo():
    repositorio = Repositorio(":memory:")
    yield repositorio
    repositorio.cerrar()


@pytest.fixture
def bitacora(repo):
    return Bitacora(repo)


@pytest.fixture
def crear_apuesta():
    def _crear(**cambios) -> Apuesta:
        datos = {
            "deporte": Deporte.NBA,
            "liga": "NBA",
            "partido": "Lakers vs Celtics",
            "mercado": "Ganador",
            "seleccion": "Lakers",
            "cuota": Decimal("1.85"),
            "monto": 1000,
            "fecha_evento": date(2026, 10, 25),
        }
        datos.update(cambios)
        return Apuesta(**datos)

    return _crear
