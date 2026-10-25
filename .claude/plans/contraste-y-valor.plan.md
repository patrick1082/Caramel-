# Plan: Contraste y valor

**Source PRD**: `.claude/prds/predictor-apuestas.prd.md`
**Selected Milestone**: 4 — Contraste y valor
**Complexity**: Large

## Summary
Cada partido muestra lado a lado cuatro opiniones del 1X2: **la de Tomas** (nueva, se ingresa en el
partido), **la del modelo** (hito 3), **ESPN BPI** (solo NBA) y **el mercado** (Pinnacle sin margen).
La tabla de cuotas marca las **apuestas con valor**: la cuota de Betano supera la cuota justa del modelo
por un umbral y además no es peor que el precio justo del mercado. Todas las opiniones se guardan antes
del inicio y la pestaña **Modelo** compara su acierto. Las apuestas registradas desde la cartelera
guardan si la app las marcó con valor, así el Resumen puede comparar el ROI de "con valor" y "sin valor"
(métrica principal del PRD). El % de billetera sugerido queda para el hito 5.

## Decisiones propuestas (pendientes de confirmar por Tomas)
| # | Tema | Propuesta | Alternativa |
|---|---|---|---|
| D1 | Predicción propia | Por partido: ganador (Local/Empate/Visita) y marcador opcional, más una nota. Editable hasta el inicio y congelada después. El texto libre "Mi predicción" de la apuesta se mantiene. | Probabilidades propias en % (permitiría Brier, pero cuesta más ingresarlas) |
| D2 | "Pronósticos web" | **ESPN BPI** en la NBA (verificado) y **mercado = Pinnacle sin margen** en todas las ligas. En fútbol no hay pronóstico web gratis y legal (ver Fuentes). | Scraping de Forebet/otros: descartado por los ToS (riesgo del PRD) |
| D3 | Umbral de valor | **Valor del modelo** cuando `p_modelo × cuota_Betano − 1 ≥ 5 %` y la cuota es ≤ 5,00. **Valor confirmado** cuando además la cuota de Betano ≥ cuota justa de Pinnacle. Los dos umbrales se pueden cambiar en Configuración. | Solo modelo, o solo mercado ("error de cuota") |
| D4 | Medir la hipótesis | La apuesta guarda `prob_modelo` y `valor` (sin valor, modelo o confirmado) cuando se registra desde la cartelera. El Resumen agrega el ROI por esa marca. | Marcarlo a mano en el formulario |

## Fuentes (verificadas el 2026-10-24)
| Dato | Fuente | Costo | Verificado |
|---|---|---|---|
| Probabilidad de victoria NBA (BPI, "Matchup Predictor") | `site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=AAAAMMDD` (ids y equipos) + `.../summary?event={id}` (`predictor.homeTeam.gameProjection`) | Gratis, sin clave; 1 + N consultas por día | ✅ 8 partidos del 24-10 con valores reales (CLE 80,5 % vs BKN). Algunos vienen 50/50, que parece ser "sin calcular" → se tratan como ausentes. Fixtures: `tests/datos/espn_scoreboard_nba.json`, `espn_predictor_nba.json` |
| Predictor ESPN fútbol | `sports.core.api.espn.com/.../predictor` | — | ❌ `"Predictor is not supported for sport: soccer, league: eng.1"` |
| ClubElo (probabilidades de partidos) | `api.clubelo.com/Fixtures` | — | ❌ `"Fixtures API deactivated"`; los ratings diarios responden 502 |
| Mercado sin margen | Cuotas de Pinnacle ya guardadas (si no hay, promedio de las casas); normalización proporcional `(1/c) / Σ(1/c)` | Sin costo extra | ✅ Ya en la base (hito 2) |
| Cuotas históricas fútbol (para backtest de valor) | Columnas `AvgH/AvgD/AvgA` (promedio previo al partido) de los CSV de football-data | Gratis | ✅ Presentes en `tests/datos/E0.csv` (2026-27). Sin equivalente en la NBA |

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Naming | `src/predictor/evaluacion.py:144` | Funciones puras en español (`calcular_metricas`, `por_liga`, `cruzar`), dataclasses `frozen` |
| Errors | `src/predictor/fuentes/espn.py:28` | `_json(url, que, obtener)`: `RequestException` → `ValueError` en español con `type(error).__name__`, `from None` |
| Sources | `src/predictor/fuentes/espn.py:47` | `obtener: Obtener = requests.get` inyectable, parser tolerante (salta los datos incompletos), `logger.info("...: %s", n)` |
| Name matching | `src/predictor/nombres.py` | `emparejar` para cruzar los equipos de ESPN con los de The Odds API |
| Data access | `src/predictor/repositorio.py:316` | `_migrar` con `if version < N` y `_ESQUEMA_V4`; tabla sin FK a `partidos` (igual que `predicciones`, línea 91) |
| Service | `src/predictor/cartelera.py:336` | `predecir`: se recalcula antes del inicio y se congela después; dependencias inyectadas (`reloj`, `descargar_*`) y marcas de vigencia en `config` |
| Config | `src/predictor/bitacora.py:95` | Valor en `config` con un default constante y validación en el setter |
| Tables | `src/predictor/exportar.py:229` | `tabla_*` → `DataFrame` con columnas en español; columnas opcionales solo si hay datos |
| UI | `app.py:219` | Todo dentro del `st.expander` del partido; acciones con `ejecutar(mensaje, accion, ...)` |
| Tests | `tests/test_espn.py:13`, `tests/fakes.py` | Fixtures reales recortadas en `tests/datos/`, `ObtenerFalso`/`RespuestaFalsa`, `Reloj` de `test_cartelera`, sin red |

## Files to Change
| File | Action | Why |
|---|---|---|
| `src/predictor/modelos.py` | UPDATE | `PrediccionPropia`, `Pronostico3` (fuente + probabilidades 1X2), `Valor` (enum); `Apuesta.prob_modelo`, `Apuesta.valor` |
| `src/predictor/valor.py` | CREATE | Puro: probabilidades sin margen, EV, clasificación de valor de cada fila de cuotas |
| `src/predictor/fuentes/espn.py` | UPDATE | `bpi_nba(fecha)`: probabilidades por partido (local, visitante) |
| `src/predictor/fuentes/football_data.py` | UPDATE | Leer `AvgH/AvgD/AvgA` al historial |
| `src/predictor/repositorio.py` | UPDATE | Esquema v4: `predicciones_propias`, `pronosticos`, columnas nuevas en `apuestas` e `historial` |
| `src/predictor/evaluacion.py` | UPDATE | Métricas por fuente (modelo, mercado, ESPN, propia); backtest de la estrategia de valor en fútbol |
| `src/predictor/cartelera.py` | UPDATE | `actualizar_bpi`, `pronosticos(partido)`, `valorar(partido)`, guardar y leer la predicción propia, umbrales |
| `src/predictor/bitacora.py` | UPDATE | ROI separado por marca de valor en el `Resumen` |
| `src/predictor/exportar.py` | UPDATE | `tabla_contraste`, columnas de valor en `tabla_cuotas`, `tabla_valor_del_dia`, evaluación por fuente, columnas nuevas en Excel |
| `app.py` | UPDATE | Formulario de predicción propia y contraste en el partido; lista "Valor del día"; registro desde la cartelera; umbrales en Configuración; Modelo por fuente |
| `tests/test_valor.py` | CREATE | Sin margen, EV, umbrales y casos borde |
| `tests/test_espn.py`, `test_historial_fuentes.py`, `test_repositorio.py`, `test_cartelera.py`, `test_evaluacion.py`, `test_bitacora.py`, `test_exportar.py`, `test_modelos.py` | UPDATE | Cobertura de lo nuevo, migración v3→v4 |
| `tests/datos/espn_scoreboard_nba.json`, `espn_predictor_nba.json` | CREATE | ✅ Ya guardados (recortados, sin datos personales) |
| `README.md`, PRD | UPDATE | Fuentes nuevas, criterio de valor y cierre del hito |

## Tasks
### Task 1: Verificar fuentes y guardar fixtures ✅
- **Action**: comprobar ESPN BPI, ESPN fútbol, ClubElo y las cuotas históricas de football-data; guardar respuestas recortadas.
- **Validate**: hecho durante la planificación (tabla de Fuentes).

### Task 2: Modelos de dominio
- **Action**: `PrediccionPropia(partido_id, liga, local, visitante, inicio, ganador: "local"|"empate"|"visitante", marcador_local|None, marcador_visitante|None, nota, creada)`. Valida: empate prohibido en la NBA, marcador coherente con el ganador y no negativo, inicio con zona horaria. `Pronostico3(partido_id, fuente, prob_local, prob_empate|None, prob_visitante, actualizada)`. Comparte la validación de suma 1 con `Prediccion` (extraer `_validar_probabilidades`). `Valor(StrEnum)`: `ninguno`, `modelo`, `confirmado`. `Apuesta` suma `prob_modelo: float | None = None` y `valor: Valor = Valor.NINGUNO`.
- **Mirror**: `Prediccion.__post_init__` (`modelos.py`).
- **Validate**: `pytest tests/test_modelos.py`.

### Task 3: Cálculo de valor (puro)
- **Action**: `valor.py`:
  - `sin_margen(cuotas: dict[str, Decimal]) -> dict[str, float]` (proporcional).
  - `probabilidades_mercado(filas, partido)`: Pinnacle 1X2 sin margen; si no está, el promedio de las casas; None si falta alguna selección. También por línea (over/under y hándicap) con el par Pinnacle de la misma línea.
  - `ev(prob, cuota) = prob × cuota − 1`.
  - `clasificar(fila, prob_modelo, prob_mercado, umbral_modelo=0.05, cuota_maxima=5.0, umbral_mercado=0.0) -> Valor`. Sin Betano o sin `prob_modelo` → `ninguno`.
- **Mirror**: funciones puras como `evaluacion.py`.
- **Validate**: `pytest tests/test_valor.py` (márgenes conocidos, línea sin pareja, cuota > máxima, empate).

### Task 4: Fuentes
- **Action**: `espn.bpi_nba(fecha, obtener)`: scoreboard del día (fecha de Nueva York) y luego un `summary` por evento. Devuelve `[(local, visitante, prob_local, prob_visitante)]`. Descarta 50/50 exacto y valores fuera de 0–100; si falla un `summary`, se loguea y sigue con el resto. `football_data`: guardar `AvgH/AvgD/AvgA` en el `ResultadoHistorico` (campo nuevo `cuotas: tuple[float, float, float] | None`).
- **Mirror**: `espn.lesiones_nba`, `football_data.descargar`.
- **Validate**: `pytest tests/test_espn.py tests/test_historial_fuentes.py` con los fixtures nuevos y `E0.csv`.

### Task 5: Repositorio v4
- **Action**: `_ESQUEMA_V4`:
  - `predicciones_propias` (PK `partido_id`) y `pronosticos` (PK `partido_id, fuente`), ambas sin FK.
  - `ALTER TABLE apuestas ADD prob_modelo REAL, ADD valor TEXT NOT NULL DEFAULT 'ninguno'`.
  - `ALTER TABLE historial ADD cuotas TEXT`.
  - Borrar las marcas de vigencia del historial de fútbol para que se vuelva a descargar con cuotas.
  - Métodos `guardar/obtener/listar_prediccion_propia` y `guardar_pronostico`, `pronosticos_de`, `listar_pronosticos`.
- **Mirror**: `_ESQUEMA_V3`, `guardar_prediccion`.
- **Validate**: `pytest tests/test_repositorio.py`, que incluye migrar una base v3 con datos sin perder nada.

### Task 6: Servicio
- **Action**: en `Cartelera`:
  - `actualizar_bpi()` dentro de `actualizar` (vigencia 1 h, errores separados como los de jugadores).
  - `pronosticos(partido)`: devuelve modelo, mercado y ESPN. Antes del inicio recalcula y guarda; después del inicio lee lo guardado, igual que `predecir`.
  - `valorar(partido, prediccion)`: por cada fila de `comparar`, la probabilidad del modelo, la del mercado, el EV y la clase de `Valor`.
  - `valor_del_dia(partidos)`: solo las filas con valor, ordenadas por EV.
  - `guardar_prediccion_propia(...)`: rechaza la escritura si el partido ya empezó.
  - Umbrales leídos de `config` con sus defaults.
- **Mirror**: `predecir`, `actualizar_jugadores`, `Bitacora.fondo_inicial`.
- **Validate**: `pytest tests/test_cartelera.py` (congelado, BPI con fallo, umbral cambiado, predicción propia tardía rechazada).

### Task 7: Evaluación
- **Action**: generalizar `cruzar`/`MetricasModelo` para comparar por fuente: acierto y Brier del modelo, el mercado, ESPN y la línea base, más el acierto de la propia (sin Brier, porque solo es un pick). Agregar `backtest_valor(liga, historial, umbral)`: walk-forward del modelo contra `AvgH/D/A`, apostando 1 unidad cuando hay valor. Devuelve apuestas, aciertos, ROI y el ROI de apostar siempre al favorito como comparación.
- **Mirror**: `evaluacion.backtest`.
- **Validate**: `pytest tests/test_evaluacion.py`. Correr también sobre el historial real 2025-26 y reportar el resultado.

### Task 8: Bitácora
- **Action**: `Resumen.por_valor: dict[Valor, Metricas]` (ROI con valor vs. sin valor); registrar acepta `prob_modelo` y `valor`.
- **Mirror**: `_agrupar` (`bitacora.py:81`).
- **Validate**: `pytest tests/test_bitacora.py`.

### Task 9: Tablas y UI
- **Action**:
  - **Partido**:
    - formulario "Mi predicción" (ganador, marcador y nota), deshabilitado desde el inicio;
    - `tabla_contraste` con filas Mía, Modelo, ESPN BPI y Mercado, y columnas Local, Empate y Visita en %, Favorito y Marcador;
    - una línea de resumen ("Coinciden tú, el modelo y el mercado: gana X" o "Solo tú das a X");
    - `tabla_cuotas` con columnas Mercado (%), EV (%) y Valor (✅ confirmado / ⚠️ solo modelo).
  - **Pestaña Partidos**: arriba, la tabla "Valor del día" del filtro actual.
  - **Nueva apuesta**: un selector "Desde la cartelera" (partido y fila), fuera del form, que rellena partido, mercado, selección, cuota, `prob_modelo` y `valor`.
  - **Resumen**: el ROI con valor vs. sin valor.
  - **Modelo**: tabla por fuente y la casilla del backtest de valor.
  - **Configuración**: los umbrales.
  - **Excel**: columnas nuevas en Apuestas y una hoja "Contraste".
- **Mirror**: `mostrar_prediccion`, `tabla_cuotas`, el formulario `nueva_apuesta`.
- **Validate**: `pytest tests/test_exportar.py` más la prueba de humo con AppTest y una base precargada (sin red ni clave).

### Task 10: Docs y PRD
- **Action**: en el README, las fuentes nuevas, el criterio de valor y que **el valor no es una garantía**, más el resultado del backtest de valor. En el PRD, el hito 4 en `complete` y las preguntas abiertas de webs y umbral marcadas como resueltas. En este plan, las desviaciones.
- **Validate**: la validación completa.

## Validation
```bash
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m pytest --cov=predictor --cov-report=term-missing
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Valor falso: el modelo está mal calibrado en cuotas altas o con poca muestra | Alta | Cuota máxima de 5,00, el "confirmado" exige que el mercado no contradiga y el backtest de valor muestra el ROI real antes de confiar |
| Betano UK ≠ Betano Chile: el valor puede no existir en la cuota real | Alta | La cuota de la apuesta se escribe a mano y el valor se recalcula con ella al registrar; se avisa en la UI |
| Sin pronóstico web en fútbol | Cierta | Se usa el mercado (Pinnacle) como opinión externa; queda documentado |
| ESPN BPI no oficial, 50/50 sin calcular al inicio de temporada | Media | Se descartan los 50/50 exactos; si falla, el contraste muestra "—" y aparece un aviso sin romper la pestaña |
| El backtest de valor usa la cuota promedio y no la de Betano | Media | Se reporta como aproximación; la medición real es el ROI de la bitácora |
| Muestra chica para comparar ROI con y sin valor | Alta | Ya contemplado en el PRD (100 apuestas o 3 meses); se registran también las no colocadas |
| Migración v3→v4 con `ALTER TABLE` | Baja | Test de migración con una base v3 poblada |

## Acceptance
- [x] Cada partido permite ingresar mi predicción y muestra el contraste Mía / Modelo / ESPN BPI (NBA) / Mercado
- [x] La tabla de cuotas muestra Mercado (%), EV (%) y la marca de valor con los umbrales configurables
- [x] La lista "Valor del día" muestra las filas con valor del filtro
- [x] Las apuestas registradas desde la cartelera guardan `prob_modelo` y `valor`; el Resumen muestra el ROI con y sin valor
- [x] Las opiniones quedan guardadas y congeladas al inicio; la pestaña Modelo compara acierto por fuente
- [x] El backtest de valor en fútbol 2025-26 queda reportado
- [x] Si ESPN falla, la app sigue con un aviso; ninguna clave en repo, base ni logs
- [x] Migración v3→v4 sin pérdida; tests sin red; cobertura ≥ 90 % en lo nuevo
- [x] All tasks complete
- [x] Validation passes
- [x] Patterns mirrored, not reinvented

## Desviaciones
- La hoja "Contraste" del Excel guarda la evaluación por fuente (acierto y Brier de cada opinión), no
  las opiniones partido a partido.
- `Resumen.por_valor` incluye también las apuestas no colocadas, para que la muestra crezca más rápido.
- El umbral del mercado quedó como EV mínimo según el mercado (0 % por defecto), que equivale a
  "cuota de Betano ≥ cuota justa del mercado" y se puede subir.
- La UI muestra un aviso permanente junto al "Valor del día": ⚠️ solo modelo perdió en el backtest.
- Prueba de humo de la interfaz en `tests/test_app.py` (AppTest, base temporal, sin red ni clave).

## Resultados
### Backtest de valor, fútbol 2025-26 (tarea 7, 2026-10-25)
Walk-forward con el historial 2024-25 + 2025-26 de las 5 ligas, apostando 1 unidad a la cuota promedio
(`AvgH/D/A`) cuando `EV del modelo ≥ 5 %` y la cuota es ≤ 5,00.

| Liga | Partidos | Apuestas | Acierto | ROI valor | ROI favorito |
|---|---|---|---|---|---|
| Bundesliga | 304 | 139 | 25,9 % | −34,9 % | −1,6 % |
| LaLiga | 377 | 185 | 33,0 % | −11,0 % | +1,4 % |
| Ligue 1 | 303 | 145 | 24,1 % | −31,7 % | −3,3 % |
| Premier League | 377 | 192 | 30,7 % | +3,6 % | −10,1 % |
| Serie A | 377 | 179 | 28,5 % | −14,2 % | −0,7 % |
| **Total** | **1738** | **840** | **28,8 %** | **−15,9 %** | **−2,9 %** |

- 1X2: el modelo acierta 51,4 % (Brier 0,599), la línea base 44,0 % (0,649) y **el mercado sin margen
  53,3 % (0,582)**. El mercado está mejor calibrado que el modelo.
- Subir el umbral no lo arregla: 10 % → −16,2 %, 20 % → −16,1 %; 30 % da +5,5 % con 121 apuestas (ruido).
- Conclusión: el "valor solo del modelo" es en su mayoría desacuerdo con un mercado que sabe más. La
  marca ✅ confirmado (que el mercado no contradiga) es la que importa y la UI debe advertir que
  ⚠️ solo modelo históricamente perdió.
