from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fakes import DATOS, ObtenerFalso, respuesta_odds

from predictor import stake
from predictor.cartelera import Cartelera, _pronostico_mercado
from predictor.evaluacion import TOTAL
from predictor.fuentes import espn, football_data
from predictor.fuentes.odds_api import ClienteOddsApi
from predictor.modelos import (
    Fuente,
    Ganador,
    Jugador,
    Mercado,
    Pronostico3,
    ResultadoHistorico,
    Rol,
    Valor,
)
from predictor.valor import Umbrales

VILLA_CITY = "aca5dd297dbee71f576f7641569fe578"


class Reloj:
    def __init__(self, momento=datetime(2026, 10, 23, 15, 0, tzinfo=UTC)):
        self.momento = momento

    def __call__(self):
        return self.momento


@pytest.fixture
def reloj():
    return Reloj()


@pytest.fixture
def obtener():
    return ObtenerFalso(
        respuesta_odds("odds_soccer_epl.json", restantes=491),
        respuesta_odds("odds_basketball_nba.json", restantes=488),
    )


@pytest.fixture
def cartelera(repo, obtener, reloj):
    return Cartelera(repo, ClienteOddsApi("clave", obtener), reloj=reloj)


def test_actualizar_cuotas_guarda_partidos_y_creditos(cartelera, obtener):
    actualizadas = cartelera.actualizar_cuotas(["Premier League", "NBA"])

    assert actualizadas == ["Premier League", "NBA"]
    assert len(obtener.llamadas) == 2
    assert cartelera.creditos_restantes == 488
    assert len(cartelera.partidos(date(2026, 10, 24), ligas=["Premier League"])) == 3


def test_no_repite_consulta_mientras_las_cuotas_estan_vigentes(cartelera, obtener, reloj):
    cartelera.actualizar_cuotas(["Premier League"])
    reloj.momento += timedelta(minutes=59)

    assert cartelera.actualizar_cuotas(["Premier League"]) == []
    assert cartelera.actualizar_cuotas(["Premier League"], forzar=True) == ["Premier League"]
    reloj.momento += timedelta(minutes=61)
    assert cartelera.ligas_por_actualizar(["Premier League", "NBA"]) == ["Premier League", "NBA"]
    assert len(obtener.llamadas) == 2


def test_sin_creditos_suficientes_no_consulta(repo, cartelera, obtener):
    repo.fijar_config("odds_creditos_restantes", "5")

    with pytest.raises(ValueError, match="cuesta 6 créditos y quedan 5"):
        cartelera.actualizar_cuotas(["Premier League", "NBA"])
    assert obtener.llamadas == []


def test_sin_clave_no_actualiza_pero_muestra_lo_guardado(repo, cartelera):
    cartelera.actualizar_cuotas(["Premier League"])
    sin_clave = Cartelera(repo, None)

    assert not sin_clave.tiene_clave
    with pytest.raises(ValueError, match="ODDS_API_KEY"):
        sin_clave.actualizar_cuotas(["Premier League"])
    assert len(sin_clave.partidos(date(2026, 10, 24))) == 3


def test_partidos_filtra_por_dia_y_hora_de_chile(cartelera):
    cartelera.actualizar_cuotas(["Premier League", "NBA"])

    # NBA: 17:16 y 20:10 del 23 en Chile. Premier: 08:30 y 11:00 del 24.
    noche = cartelera.partidos(date(2026, 10, 23), desde_hora=18)
    manana = cartelera.partidos(date(2026, 10, 24), 8, 9)

    assert [p.liga for p in noche] == ["NBA", "NBA"]
    assert [p.id for p in manana] == [VILLA_CITY]
    assert cartelera.partidos(date(2026, 10, 24), ligas=["NBA"]) == []


def test_rango_de_horas_invalido(cartelera):
    with pytest.raises(ValueError, match="rango de horas"):
        cartelera.partidos(date(2026, 10, 24), 12, 12)


def test_comparar_ordena_y_resume_las_cuotas(cartelera):
    cartelera.actualizar_cuotas(["Premier League"])
    [villa_city] = cartelera.partidos(date(2026, 10, 24), 8, 9)

    filas = cartelera.comparar(villa_city)

    assert [(f.mercado, f.seleccion, f.linea) for f in filas] == [
        (Mercado.GANADOR, "Aston Villa", None),
        (Mercado.GANADOR, "Draw", None),
        (Mercado.GANADOR, "Manchester City", None),
        (Mercado.TOTALES, "Over", Decimal("2.5")),
        (Mercado.TOTALES, "Under", Decimal("2.5")),
        (Mercado.TOTALES, "Over", Decimal("3.0")),
        (Mercado.TOTALES, "Under", Decimal("3.0")),
        (Mercado.TOTALES, "Over", Decimal("3.5")),
        (Mercado.TOTALES, "Under", Decimal("3.5")),
        (Mercado.HANDICAP, "Aston Villa", Decimal("0.75")),
        (Mercado.HANDICAP, "Manchester City", Decimal("-0.75")),
    ]  # las líneas ±1 y ±1.5 de una sola casa se omiten
    villa = filas[0]
    assert (villa.betano, villa.pinnacle) == (Decimal("4.75"), Decimal("5.08"))
    assert (villa.mejor, villa.casa_mejor) == (Decimal("5.3"), "Betfair")
    assert villa.promedio == Decimal("4.92")
    assert villa.casas == 9
    assert filas[3].betano is None


def _descargar_e0(liga, temporada):
    if temporada == "2627":
        return football_data.parsear(liga, temporada, (DATOS / "E0.csv").read_text("utf-8-sig"))
    return []


def test_actualizar_historial_una_vez_al_dia(repo, reloj):
    pedidas = []

    def futbol(liga, temporada):
        pedidas.append(temporada)
        return _descargar_e0(liga, temporada)

    def baloncesto(temporada):
        pedidas.append(temporada)
        return []

    cartelera = Cartelera(repo, None, futbol, baloncesto, reloj)

    assert cartelera.actualizar_historial(["Premier League", "NBA"]) == ["Premier League", "NBA"]
    assert pedidas == ["2627", "2526", "2026-27", "2025-26"]
    assert len(repo.historial_de("Premier League")) == 30

    reloj.momento += timedelta(hours=23)
    assert cartelera.actualizar_historial(["Premier League"]) == []
    assert cartelera.actualizar_historial(["Premier League"], forzar=True) == ["Premier League"]


def test_analizar_cruza_nombres_entre_fuentes(repo, obtener, reloj):
    cartelera = Cartelera(repo, ClienteOddsApi("clave", obtener), _descargar_e0, reloj=reloj)
    cartelera.actualizar_cuotas(["Premier League"])
    [villa_city] = cartelera.partidos(date(2026, 10, 24), 8, 9)
    sin_historial = cartelera.analizar(villa_city)

    cartelera.actualizar_historial(["Premier League"])
    analisis = cartelera.analizar(villa_city)

    assert sin_historial.local is None and sin_historial.cara_a_cara == []
    assert analisis.local.equipo == "Aston Villa"
    assert analisis.visitante.equipo == "Man City"  # nombre de football-data.co.uk
    assert analisis.local.jugados >= 1


EQUIPOS_NBA = [
    "Milwaukee Bucks",
    "Chicago Bulls",
    "Charlotte Hornets",
    "Atlanta Hawks",
    "Boston Celtics",
    "New York Knicks",
]


def _historial_nba(*extra):
    """Dos vueltas de todos contra todos en octubre; los Bucks anotan 12 puntos más."""

    def descargar(temporada):
        if temporada != "2026-27":
            return []
        filas, dia = [], date(2026, 10, 1)
        for local in EQUIPOS_NBA:
            for visita in EQUIPOS_NBA:
                if local != visita:
                    puntos_local = 112 + (12 if local == "Milwaukee Bucks" else 0)
                    puntos_visita = 108 + (12 if visita == "Milwaukee Bucks" else 0)
                    filas.append(
                        ResultadoHistorico(
                            "NBA", temporada, dia, local, visita, puntos_local, puntos_visita
                        )
                    )
                    dia = min(dia + timedelta(days=1), date(2026, 10, 20))
        return [*filas, *extra]

    return descargar


def _figuras(liga, hoy):
    return [
        Jugador("NBA", "Milwaukee Bucks", "Giannis Antetokounmpo", Rol.DESTACADO, "31 pts", 31),
        Jugador("NBA", "Milwaukee Bucks", "Giannis Antetokounmpo", Rol.LESIONADO, "Out · Knee"),
        Jugador("NBA", "Chicago Bulls", "Josh Giddey", Rol.DESTACADO, "20 pts", 20),
    ]


@pytest.fixture
def cartelera_nba(repo, reloj):
    cartelera = Cartelera(
        repo,
        ClienteOddsApi("clave", ObtenerFalso(respuesta_odds("odds_basketball_nba.json"))),
        descargar_nba=_historial_nba(),
        reloj=reloj,
        descargar_jugadores=_figuras,
    )
    cartelera.actualizar_cuotas(["NBA"])
    cartelera.actualizar_historial(["NBA"])
    return cartelera


def _bucks_bulls(cartelera):
    return next(p for p in cartelera.partidos(date(2026, 10, 23)) if p.local == "Milwaukee Bucks")


def test_actualizar_jugadores_una_vez_al_dia_y_sigue_si_una_fuente_falla(repo, reloj):
    pedidas = []

    def descargar(liga, hoy):
        pedidas.append((liga, hoy))
        if liga == "Serie A":
            raise ValueError("No se pudo consultar ESPN (goleadores de Serie A): Timeout")
        return _figuras(liga, hoy) if liga == "NBA" else []

    cartelera = Cartelera(repo, None, reloj=reloj, descargar_jugadores=descargar)

    actualizadas, errores = cartelera.actualizar_jugadores(["Serie A", "NBA"])

    assert actualizadas == ["NBA"]
    assert errores == {"Serie A": "No se pudo consultar ESPN (goleadores de Serie A): Timeout"}
    assert pedidas == [("Serie A", date(2026, 10, 23)), ("NBA", date(2026, 10, 23))]
    assert len(repo.jugadores_de("NBA")) == 3
    reloj.momento += timedelta(hours=23)
    assert cartelera.actualizar_jugadores(["NBA"]) == ([], {})
    assert cartelera.actualizar_jugadores(["NBA"], forzar=True) == (["NBA"], {})


def test_jugadores_del_partido_por_equipo(cartelera_nba):
    cartelera_nba.actualizar_jugadores(["NBA"])

    local, visitante = cartelera_nba.jugadores(_bucks_bulls(cartelera_nba))

    assert [j.rol for j in local] == [Rol.DESTACADO, Rol.LESIONADO]
    assert [j.nombre for j in visitante] == ["Josh Giddey"]


def test_predecir_guarda_lineas_y_factores(repo, cartelera_nba):
    cartelera_nba.actualizar_jugadores(["NBA"])
    partido = _bucks_bulls(cartelera_nba)

    prediccion = cartelera_nba.predecir(partido)

    assert prediccion.modelo == "nba-ratings-1"
    assert (prediccion.local, prediccion.visitante) == ("Milwaukee Bucks", "Chicago Bulls")
    assert prediccion.prob_local > 0.7 and prediccion.prob_empate is None
    assert prediccion.linea_total == 261.5  # Betano: la línea con Over y Under más parejos
    over, under = (p.prob for p in prediccion.lineas if p.linea == 261.5)
    assert over + under == pytest.approx(1) and prediccion.prob_over == over
    assert prediccion.factores[0].startswith("Baja clave en Milwaukee Bucks: Giannis")
    assert repo.prediccion_de(partido.id) == prediccion


def test_prediccion_se_congela_al_empezar_el_partido(repo, cartelera_nba, reloj):
    partido = _bucks_bulls(cartelera_nba)
    antes = cartelera_nba.predecir(partido)

    reloj.momento = partido.inicio
    cartelera_nba._descargar_nba = _historial_nba(
        ResultadoHistorico(
            "NBA", "2026-27", date(2026, 10, 22), "Chicago Bulls", "Boston Celtics", 150, 80
        )
    )
    cartelera_nba.actualizar_historial(["NBA"], forzar=True)

    assert cartelera_nba.predecir(partido) == antes
    assert repo.listar_predicciones() == [antes]


def test_predecir_futbol_con_linea_de_pinnacle_y_handicap(repo, obtener, reloj):
    cartelera = Cartelera(repo, ClienteOddsApi("clave", obtener), _descargar_e0, reloj=reloj)
    cartelera.actualizar_cuotas(["Premier League"])
    [villa_city] = cartelera.partidos(date(2026, 10, 24), 8, 9)
    assert cartelera.predecir(villa_city) is None  # todavía sin historial

    cartelera.actualizar_historial(["Premier League"])
    prediccion = cartelera.predecir(villa_city)

    assert prediccion.modelo == "poisson-1" and prediccion.marcador_probable
    assert prediccion.linea_total in {2.5, 3.0, 3.5}  # Betano no ofrece totales en este partido
    handicap = {(p.seleccion, p.linea) for p in prediccion.lineas if p.mercado is Mercado.HANDICAP}
    assert ("Aston Villa", 0.75) in handicap and ("Manchester City", -0.75) in handicap


def test_evaluacion_y_backtest(cartelera_nba, reloj):
    partido = _bucks_bulls(cartelera_nba)
    cartelera_nba.predecir(partido)
    assert cartelera_nba.evaluacion()[TOTAL].partidos == 0

    reloj.momento += timedelta(days=1)
    cartelera_nba._descargar_nba = _historial_nba(
        ResultadoHistorico(
            "NBA", "2026-27", date(2026, 10, 23), "Milwaukee Bucks", "Chicago Bulls", 120, 100
        )
    )
    cartelera_nba.actualizar_historial(["NBA"], forzar=True)

    metricas = cartelera_nba.evaluacion()
    assert metricas[TOTAL].partidos == 1 and metricas[TOTAL].acierto == 1
    assert [e.prediccion.partido_id for e in cartelera_nba.evaluadas()] == [partido.id]
    assert cartelera_nba.backtest(["NBA"])[TOTAL].partidos == 0  # 31 partidos < mínimo
    assert cartelera_nba.backtest(["NBA"], minimo=10)[TOTAL].partidos == 0  # ya calculado
    cartelera_nba.actualizar_historial(["NBA"], forzar=True)
    assert cartelera_nba.backtest(["NBA"], minimo=10)[TOTAL].partidos > 0


class BpiFalso:
    """ESPN BPI del 23-10 (hora de Nueva York); falla mientras `error` tenga texto."""

    def __init__(self):
        self.dias: list[date] = []
        self.error = ""

    def __call__(self, dia):
        self.dias.append(dia)
        if self.error:
            raise ValueError(self.error)
        return [
            espn.BpiNba(
                "Milwaukee Bucks",
                "Chicago Bulls",
                datetime(2026, 10, 23, 20, 15, tzinfo=UTC),
                0.7,
                0.3,
            ),
            espn.BpiNba(
                "Boston Celtics",
                "New York Knicks",
                datetime(2026, 10, 23, 23, 0, tzinfo=UTC),
                0.6,
                0.4,
            ),
            # Otro día y equipos cruzados: no corresponden a ningún partido guardado.
            espn.BpiNba(
                "Charlotte Hornets",
                "Atlanta Hawks",
                datetime(2026, 10, 25, 23, 0, tzinfo=UTC),
                0.5,
                0.5,
            ),
            espn.BpiNba(
                "New York Knicks",
                "Boston Celtics",
                datetime(2026, 10, 23, 23, 0, tzinfo=UTC),
                0.45,
                0.55,
            ),
        ]


def test_actualizar_bpi_empareja_partidos_y_reintenta_si_falla(repo, cartelera_nba, reloj):
    bpi = cartelera_nba._descargar_bpi = BpiFalso()
    bpi.error = "ESPN respondió con error 503 (partidos NBA)"

    assert cartelera_nba.actualizar_bpi() == ([], {"2026-10-23": bpi.error})
    assert repo.listar_pronosticos() == []

    bpi.error = ""
    assert cartelera_nba.actualizar_bpi() == ([date(2026, 10, 23)], {})
    bucks = _bucks_bulls(cartelera_nba)
    assert repo.pronosticos_de(bucks.id) == [
        Pronostico3(bucks.id, Fuente.ESPN, 0.7, None, 0.3, reloj.momento)
    ]
    assert [p.prob_local for p in repo.listar_pronosticos()] == [0.7, 0.6]  # Hornets sin BPI

    reloj.momento += timedelta(minutes=59)
    assert cartelera_nba.actualizar_bpi() == ([], {})
    assert cartelera_nba.actualizar_bpi(forzar=True) == ([date(2026, 10, 23)], {})
    assert bpi.dias == [date(2026, 10, 23)] * 3


def test_pronosticos_reune_modelo_mercado_y_espn_y_se_congelan(cartelera_nba, reloj):
    cartelera_nba._descargar_bpi = BpiFalso()
    cartelera_nba.actualizar_bpi()
    partido = _bucks_bulls(cartelera_nba)
    prediccion = cartelera_nba.predecir(partido)

    pronosticos = cartelera_nba.pronosticos(partido)

    assert list(pronosticos) == [Fuente.ESPN, Fuente.MERCADO, Fuente.MODELO]
    modelo, mercado = pronosticos[Fuente.MODELO], pronosticos[Fuente.MERCADO]
    assert (modelo.prob_local, modelo.prob_empate) == (prediccion.prob_local, None)
    assert mercado.prob_empate is None
    assert mercado.prob_local + mercado.prob_visitante == pytest.approx(1)
    assert mercado.favorito is Ganador.VISITANTE  # el mercado real no ve a los Bucks del fixture

    reloj.momento = partido.inicio
    cartelera_nba._descargar_nba = _historial_nba(
        ResultadoHistorico(
            "NBA", "2026-27", date(2026, 10, 22), "Chicago Bulls", "Boston Celtics", 150, 80
        )
    )
    cartelera_nba.actualizar_historial(["NBA"], forzar=True)
    assert cartelera_nba.pronosticos(partido) == pronosticos


def test_pronostico_del_mercado_en_futbol_sin_historial(cartelera):
    cartelera.actualizar_cuotas(["Premier League"])
    [villa_city] = cartelera.partidos(date(2026, 10, 24), 8, 9)

    pronosticos = cartelera.pronosticos(villa_city)

    assert list(pronosticos) == [Fuente.MERCADO]  # el modelo todavía no puede predecir
    mercado = pronosticos[Fuente.MERCADO]
    probs = (mercado.prob_local, mercado.prob_empate, mercado.prob_visitante)
    assert sum(probs) == pytest.approx(1)
    assert mercado.prob_local < 1 / 5.08  # Pinnacle 5.08 para Villa, sin el margen
    assert mercado.favorito is Ganador.VISITANTE
    sin_empate = [f for f in cartelera.comparar(villa_city) if f.seleccion != "Draw"]
    assert _pronostico_mercado(villa_city, sin_empate, mercado.actualizada) is None


def test_umbrales_por_defecto_y_guardados(cartelera):
    assert cartelera.umbrales == Umbrales()

    cartelera.fijar_umbrales(Umbrales(modelo=0.1, cuota_maxima=3.0, mercado=0.02))

    assert cartelera.umbrales == Umbrales(modelo=0.1, cuota_maxima=3.0, mercado=0.02)


def test_valorar_y_valor_del_dia_respetan_los_umbrales(cartelera_nba, reloj):
    partidos = cartelera_nba.partidos(date(2026, 10, 23))
    partido = _bucks_bulls(cartelera_nba)

    valoraciones = cartelera_nba.valorar(partido, cartelera_nba.predecir(partido))

    assert [v.fila for v in valoraciones] == cartelera_nba.comparar(partido)

    cartelera_nba.fijar_umbrales(Umbrales(modelo=0.0, cuota_maxima=100.0))
    oportunidades = cartelera_nba.valor_del_dia(partidos)
    assert oportunidades and all(o.valoracion.valor is not Valor.NINGUNO for o in oportunidades)
    evs = [o.valoracion.ev for o in oportunidades]
    assert evs == sorted(evs, reverse=True) and min(evs) >= 0
    assert {o.partido.id for o in oportunidades} <= {p.id for p in partidos}

    cartelera_nba.fijar_umbrales(Umbrales(cuota_maxima=1.01))
    assert cartelera_nba.valor_del_dia(partidos) == []
    cartelera_nba.fijar_umbrales(Umbrales(modelo=0.0, cuota_maxima=100.0))
    reloj.momento = datetime(2026, 10, 24, tzinfo=UTC)  # ya empezaron todos
    assert cartelera_nba.valor_del_dia(partidos) == []


def test_sugeridas_da_a_lo_sumo_una_apuesta_probable_por_partido(cartelera_nba, reloj):
    partidos = cartelera_nba.partidos(date(2026, 10, 23))

    sugeridas = cartelera_nba.sugeridas(partidos, minimo=0.0)

    ids = [s.partido.id for s in sugeridas]
    assert ids and len(ids) == len(set(ids)) and set(ids) <= {p.id for p in partidos}
    assert all(s.prob >= 0.55 for s in cartelera_nba.sugeridas(partidos))
    assert [s.partido.inicio for s in sugeridas] == sorted(s.partido.inicio for s in sugeridas)
    assert all(stake.SOLO_MODELO <= s.stake <= stake.TOPE for s in sugeridas)
    for s in sugeridas:
        assert s.cuota == (s.valoracion.fila.betano or s.valoracion.fila.promedio)
        assert s.de_betano == (s.valoracion.fila.betano is not None)
        assert s.ev == pytest.approx(s.prob * float(s.cuota) - 1)
    assert cartelera_nba.sugeridas(partidos, minimo=0.999) == []
    assert cartelera_nba.apuestas_del_dia(partidos) == (
        cartelera_nba.valor_del_dia(partidos),
        cartelera_nba.sugeridas(partidos),
    )
    reloj.momento = datetime(2026, 10, 24, tzinfo=UTC)  # ya empezaron todos
    assert cartelera_nba.sugeridas(partidos, minimo=0.0) == []


def test_prediccion_propia_se_reemplaza_y_se_congela_al_inicio(cartelera_nba, reloj):
    partido = _bucks_bulls(cartelera_nba)
    assert cartelera_nba.prediccion_propia(partido) is None

    cartelera_nba.guardar_prediccion_propia(partido, "visitante", nota="  sin Giannis ")
    propia = cartelera_nba.guardar_prediccion_propia(partido, Ganador.LOCAL, 118, 104)

    assert cartelera_nba.prediccion_propia(partido) == propia
    assert (propia.ganador, propia.marcador_local, propia.nota) == (Ganador.LOCAL, 118, "")
    assert propia.creada == reloj.momento and propia.liga == "NBA"
    with pytest.raises(ValueError, match="no hay empate"):
        cartelera_nba.guardar_prediccion_propia(partido, "empate")

    reloj.momento = partido.inicio
    with pytest.raises(ValueError, match="ya empezó"):
        cartelera_nba.guardar_prediccion_propia(partido, "visitante")
    assert cartelera_nba.prediccion_propia(partido) == propia


def test_evaluacion_por_fuente_y_backtest_de_valor(cartelera_nba, reloj):
    cartelera_nba._descargar_bpi = BpiFalso()
    cartelera_nba.actualizar_bpi()
    partido = _bucks_bulls(cartelera_nba)
    cartelera_nba.pronosticos(partido, cartelera_nba.predecir(partido))
    cartelera_nba.guardar_prediccion_propia(partido, Ganador.VISITANTE)
    assert cartelera_nba.evaluacion_por_fuente() == {}

    reloj.momento += timedelta(days=1)
    cartelera_nba._descargar_nba = _historial_nba(
        ResultadoHistorico(
            "NBA", "2026-27", date(2026, 10, 23), "Milwaukee Bucks", "Chicago Bulls", 120, 100
        )
    )
    cartelera_nba.actualizar_historial(["NBA"], forzar=True)

    metricas = cartelera_nba.evaluacion_por_fuente()
    assert list(metricas) == ["Mía", "Modelo", "ESPN BPI", "Mercado", "Línea base"]
    assert [m.acierto for m in metricas.values()] == [0, 1, 1, 0, 1]
    assert cartelera_nba.backtest_valor(["NBA"], minimo=10) == {}  # la NBA no trae cuotas
