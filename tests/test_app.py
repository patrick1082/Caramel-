"""Prueba de humo de la interfaz: la app carga y registra desde la cartelera, sin red ni clave."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from predictor.cartelera import Cartelera
from predictor.ligas import CASA_BASE, CASA_REFERENCIA
from predictor.modelos import Cuota, Deporte, Mercado, Partido, Valor
from predictor.repositorio import Repositorio
from predictor.valor import Umbrales

APP = Path(__file__).parent.parent / "app.py"


@pytest.fixture
def ruta_bd(tmp_path, monkeypatch):
    ruta = tmp_path / "bitacora.db"
    ahora = datetime.now(UTC)
    partido = Partido(
        "p1", Deporte.FUTBOL, "Premier League", "Arsenal", "Chelsea", ahora + timedelta(minutes=30)
    )
    precios = {CASA_BASE: ("2.40", "3.40", "3.20"), CASA_REFERENCIA: ("2.10", "3.50", "3.80")}
    cuotas = [
        Cuota("p1", casa, Mercado.GANADOR, seleccion, cuota, ahora)
        for casa, valores in precios.items()
        for seleccion, cuota in zip(("Arsenal", "Draw", "Chelsea"), valores, strict=True)
    ]
    repo = Repositorio(ruta)
    repo.reemplazar_cartelera("Premier League", [partido], cuotas)
    repo.cerrar()
    monkeypatch.setenv("PREDICTOR_DB", str(ruta))
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    st.cache_resource.clear()
    yield ruta
    st.cache_resource.clear()


def _app() -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.run()
    assert not app.exception
    return app


def _por_etiqueta(widgets, etiqueta: str):
    return next(w for w in widgets if w.label == etiqueta)


def test_la_app_carga_todas_las_pestanas(ruta_bd):
    app = _app()

    assert [t.label for t in app.tabs][:4] == ["Partidos", "Modelo", "Resumen", "Nueva apuesta"]


def test_registra_una_apuesta_desde_la_cartelera(ruta_bd):
    app = _app()
    _por_etiqueta(app.selectbox, "Desde la cartelera (opcional)").select_index(1).run()
    assert not app.exception
    assert _por_etiqueta(app.text_input, "Partido").value == "Arsenal vs Chelsea"
    assert _por_etiqueta(app.number_input, "Cuota").value == 2.40

    _por_etiqueta(app.button, "Registrar apuesta").click().run()
    assert not app.exception

    repo = Repositorio(ruta_bd)
    [apuesta] = repo.listar_apuestas()
    repo.cerrar()
    assert apuesta.liga == "Premier League"
    assert apuesta.prob_modelo is None or 0 < apuesta.prob_modelo < 1
    assert isinstance(apuesta.valor, Valor)


def test_guarda_los_umbrales(ruta_bd):
    app = _app()
    _por_etiqueta(app.number_input, "Cuota máxima").set_value(3.0)
    _por_etiqueta(app.button, "Guardar umbrales").click().run()
    assert not app.exception

    repo = Repositorio(ruta_bd)
    assert Cartelera(repo, None).umbrales == Umbrales(0.05, 3.0, 0.0)
    repo.cerrar()
