# Plan: Predicción IA

**Source PRD**: `.claude/prds/predictor-apuestas.prd.md`
**Selected Milestone**: 3 — Predicción IA
**Complexity**: Large

## Summary
Cada partido de la pestaña **Partidos** muestra una predicción calculada por un modelo estadístico local:
goles o puntos esperados de cada equipo, el marcador más probable y la probabilidad de cada resultado.
También muestra over/under y hándicap en las líneas que ofrece Betano, los jugadores relevantes con sus
bajas y una lista de factores clave (forma, localía, descanso, lesiones, enfrentamientos directos,
tamaño de muestra). Cada predicción se guarda antes del inicio del partido. Al llegar el resultado real
se mide su acierto, y una nueva pestaña **Modelo** muestra la precisión por liga. Quedan para el hito 4
la marca de apuestas con valor y el contraste con la predicción propia y con webs de pronósticos.

## Decisiones tomadas (respuestas de Tomas)
| Tema | Decisión |
|---|---|
| Motor | **Modelo estadístico** gratuito y reproducible, sin LLM. |
| Jugadores y lesiones | **NBA gratis** (nba_api + reporte de lesiones de ESPN). **Fútbol con ESPN**: goleadores y asistidores, sin lesiones. |
| Cambio tras la Tarea 1 | API-Football gratis solo cubre 2022–2024 (verificado: *"Free plans do not have access to this season"*). Tomas confirmó reemplazarlo por ESPN. |
| Registro | **Se guarda cada predicción** antes del partido y se mide contra el resultado real. |

### Fuentes nuevas
| Dato | Fuente | Costo | Verificado |
|---|---|---|---|
| Lesiones NBA | `site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries` | Gratis, sin clave | ✅ 200, 24 equipos con jugador, estado (`Out`, `Day-To-Day`), fecha y comentario |
| Jugadores NBA (puntos, rebotes, asistencias, minutos) | nba_api `LeagueDashPlayerStats` (temporada actual, por partido) | Gratis | Paquete ya instalado; endpoint por confirmar en la Tarea 1 |
| Goleadores y asistidores fútbol | `sports.core.api.espn.com/v2/sports/soccer/leagues/{eng.1,ita.1,ger.1,esp.1,fra.1}/seasons/{año}/types/1/leaders` + una consulta por jugador (`$ref`) | Gratis, sin clave | ✅ 200 en las 5 ligas, temporada 2026-27 (Haaland 8 goles en 7 PJ) |
| Lesiones fútbol | — | — | ❌ ESPN no las publica: 599 jugadores de la Premier, todos "Active" |

No se agregan claves nuevas.

### Modelo
- **Fútbol: Poisson con fuerzas de ataque y defensa** (Maher / Dixon-Coles simplificado).
  - Se usan la temporada actual y la anterior. Cada partido pesa según su antigüedad (vida media de 180 días).
  - Las fuerzas se encogen hacia 1.0 cuando el equipo tiene pocos partidos. Así se manejan inicio de temporada y ascendidos.
  - Fórmula: λ_local = media_local_liga × ataque_local × defensa_visita, y λ_visita al revés.
  - Se arma la matriz de marcadores de 0 a 10 y de ella salen:
    - probabilidades 1X2;
    - marcador más probable;
    - over/under en cualquier línea, incluidas las asiáticas .25 y .75 (promedio de las dos medias líneas);
    - hándicap de la línea.
- **NBA: ratings ofensivo y defensivo** (puntos anotados y recibidos, ponderados por antigüedad) más ventaja de local estimada del propio historial.
  - Margen y total se modelan como Normal. La σ se estima de los residuos del historial (≈12 puntos para el margen y ≈18 para el total).
  - Ajuste por descanso: back-to-back con −X puntos. X se estima del historial y se documenta.
- **Factores** generados por reglas:
  - racha de los últimos 5;
  - diferencia entre rendimiento de local y de visita;
  - días de descanso;
  - jugadores destacados lesionados;
  - historial de enfrentamientos directos;
  - xG frente a goles (equipo que rinde por encima o por debajo de lo esperado);
  - advertencia de muestra chica.

  Las lesiones **no cambian los números** en este hito: se muestran como factor. Ajustar por bajas sin datos de impacto por jugador sería inventar.
- **Versión del modelo** (`"poisson-1"`, `"nba-ratings-1"`): se guarda junto a cada predicción para poder comparar versiones más adelante.

### Evaluación
- **Registro:** la predicción se recalcula y se sobrescribe mientras el partido no empieza, y se congela al comenzar.
- **Cruce con el resultado:** cuando el historial trae el resultado, se cruza por liga, fecha (±1 día, hora de Chile) y nombres con `emparejar`.
- **Métricas por liga y en total:**
  - partidos evaluados;
  - acierto del resultado más probable (1X2, o ganador en la NBA);
  - Brier score;
  - error absoluto medio de goles o puntos;
  - acierto del over/under en la línea de Betano.
- **Línea base:** todas se comparan con un modelo ingenuo, que usa las tasas históricas de local, empate y visita.
- **Backtest walk-forward sobre 2025-26:**
  - qué hace: predice cada jornada usando solo los partidos anteriores;
  - ejecución: con datos reales una vez, para validar que el modelo supera a la línea base;
  - test: corre con datos de prueba.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Naming | `src/predictor/estadisticas.py:73` | Módulos y funciones en español snake_case. `calcular(...)` puro sobre `Sequence[ResultadoHistorico]`. Dataclasses `frozen` para resultados. |
| Errors | `src/predictor/cartelera.py:101` | `ValueError` con mensaje en español. La UI lo muestra con `ejecutar()` → `st.error`. |
| Secrets | `src/predictor/fuentes/odds_api.py` | Clave en el constructor desde env. `RequestException` → mensaje con `type(error).__name__` y `from None`. |
| Sources | `src/predictor/fuentes/football_data.py:68` | `descargar(..., obtener=requests.get)` inyectable. 404 → lista vacía. `logger.info` con `%s`. |
| Data access | `src/predictor/repositorio.py:200` | Esquema versionado con `PRAGMA user_version`. `_migrar` aplica `if version < N`. Reemplazo por liga dentro de `with self._con:`. |
| Service | `src/predictor/cartelera.py:50` | Dependencias inyectadas (`cliente`, `descargar_*`, `reloj`). Marcas de actualización en `config`. |
| Tables | `src/predictor/exportar.py:217` | `tabla_*` devuelve `DataFrame` con encabezados en español; valores mixtos como texto. |
| Tests | `tests/test_cartelera.py`, `tests/fakes.py` | Fixtures reales sin claves en `tests/datos/`. `ObtenerFalso`/`RespuestaFalsa`. `Reloj` controlable. Sin red. |

## Files to Change
| File | Action | Why |
|---|---|---|
| `src/predictor/modelos.py` | UPDATE | `Prediccion`, `Jugador` (destacado o lesionado) con validaciones |
| `src/predictor/fuentes/espn.py` | CREATE | Lesiones NBA y goleadores/asistidores de fútbol |
| `src/predictor/fuentes/nba.py` | UPDATE | `jugadores(temporada)` vía `LeagueDashPlayerStats` |
| `src/predictor/ligas.py` | UPDATE | Código de liga de ESPN por liga |
| `src/predictor/prediccion.py` | CREATE | Modelos Poisson y NBA (puros): esperados, probabilidades, líneas |
| `src/predictor/factores.py` | CREATE | Reglas de factores clave |
| `src/predictor/evaluacion.py` | CREATE | Cruce predicción ↔ resultado, métricas, línea base, backtest |
| `src/predictor/repositorio.py` | UPDATE | Esquema v3: `predicciones`, `jugadores` |
| `src/predictor/cartelera.py` | UPDATE | `actualizar_jugadores`, `predecir(partido)` (guarda), `evaluacion()` |
| `src/predictor/exportar.py` | UPDATE | `tabla_prediccion`, `tabla_jugadores`, `tabla_evaluacion`; hoja Excel "Predicciones" |
| `app.py` | UPDATE | Bloque de predicción, jugadores y factores en cada partido; pestaña "Modelo" |
| `tests/test_prediccion.py`, `test_factores.py`, `test_evaluacion.py`, `test_espn.py` | CREATE | Cobertura de lo nuevo |
| `tests/test_repositorio.py`, `test_cartelera.py`, `test_exportar.py`, `test_modelos.py` | UPDATE | v3, migración v2→v3, servicio y tablas |
| `tests/datos/` | UPDATE | Respuestas reales recortadas (ESPN, nba_api jugadores) sin claves |
| `README.md`, PRD | UPDATE | Fuentes nuevas, explicación del modelo; cerrar hito |

## Tasks
### Task 1: Verificar fuentes y guardar fixtures ✅ (fuentes) 
- **Action**: API-Football descartado (plan gratis sin temporada actual). ESPN fútbol: goleadores ✅, lesiones ❌. Guardar recortes de ESPN (NBA lesiones, fútbol leaders + atletas) y `LeagueDashPlayerStats` en `tests/datos/`.
- **Mirror**: Tarea 1 del hito 2.
- **Validate**: fixtures presentes y sin claves.

### Task 2: Modelos de dominio
- **Action**:
  - `Prediccion(partido_id, liga, local, visitante, inicio, modelo, creada, esperado_local, esperado_visitante, prob_local, prob_empate|None, prob_visitante, total_esperado, marcador_probable, factores: list[str])`. Valida probabilidades en [0, 1] que sumen ≈ 1 y esperados ≥ 0.
  - `Jugador(liga, equipo, nombre, rol, detalle, valor)`.
- **Mirror**: `Cuota` / `ResultadoHistorico` en `modelos.py`.
- **Validate**: `pytest tests/test_modelos.py`.

### Task 3: Fuentes de jugadores y lesiones
- **Action**:
  - `espn.lesiones_nba(obtener)` y `espn.goleadores(liga, temporada, obtener)` (resuelve cada `$ref` de atleta y equipo con caché por id).
  - `nba.jugadores(temporada, buscar)`: los 3 primeros por puntos de cada equipo.
  - Errores de red con `type(error).__name__`; un fallo de jugadores no bloquea cuotas ni historial.
- **Mirror**: `fuentes/football_data.py`.
- **Validate**: `pytest tests/test_espn.py tests/test_historial_fuentes.py`.

### Task 4: Modelo de predicción
- **Action**:
  - `prediccion.futbol(local, visitante, historial, hoy)` y `prediccion.nba(...)` devuelven un `Pronostico` (esperados, matriz o distribuciones).
  - Helpers `prob_over(linea)` y `prob_handicap(seleccion, linea)` para las líneas de Betano, incluidas las asiáticas .25 y .75.
  - Si un equipo no tiene historial, devuelve `None`.
- **Mirror**: funciones puras como `estadisticas.calcular`.
- **Validate**: `pytest tests/test_prediccion.py`. Casos:
  - las probabilidades suman 1;
  - equipos iguales con localía dan ventaja local;
  - más goles a favor dan más λ;
  - el encogimiento con 0 partidos produce la media de la liga;
  - líneas enteras y asiáticas;
  - σ de la NBA estimada de los residuos.

### Task 5: Factores clave
- **Action**: `factores.generar(partido, analisis, pronostico, jugadores, historial)` devuelve una lista de frases en español, ordenada por relevancia y de 6 como máximo.
- **Mirror**: `estadisticas.py`.
- **Validate**: `pytest tests/test_factores.py`. Cubre cada regla: activa, inactiva y umbrales.

### Task 6: Repositorio v3
- **Action**:
  - `predicciones` (PK `partido_id`, factores en JSON) y `jugadores` (reemplazo por liga).
  - Métodos `guardar_prediccion`, `predicciones(desde, hasta)` y `reemplazar_jugadores` / `jugadores_de(liga)`.
  - Migración v2→v3 sin pérdida.
- **Mirror**: `reemplazar_cartelera`, `test_migra_base_v1_sin_perder_apuestas`.
- **Validate**: `pytest tests/test_repositorio.py`.

### Task 7: Evaluación y backtest
- **Action**:
  - `evaluacion.cruzar(predicciones, historial)` y `evaluacion.metricas(...)` → `MetricasModelo` por liga y total, más la línea base.
  - `evaluacion.backtest(liga, historial, desde)`: walk-forward.
- **Mirror**: `bitacora.calcular_metricas`.
- **Validate**: `pytest tests/test_evaluacion.py`, más un backtest real único con 2025-26 (5 ligas + NBA). Reportar acierto y Brier contra la línea base.

### Task 8: Servicio
- **Action**:
  - Agregar a `Cartelera`:
    - `actualizar_jugadores(ligas)`: una vez al día por liga;
    - `predecir(partido)`: calcula, genera factores y guarda si el partido no empezó, o devuelve la congelada si ya empezó;
    - `evaluacion()`.
  - Si ESPN o nba_api fallan, se avisa y el resto de la actualización sigue.
- **Mirror**: `actualizar_historial`, `analizar`.
- **Validate**: `pytest tests/test_cartelera.py`.

### Task 9: Tablas y UI
- **Action**:
  - En cada partido, sobre las cuotas, mostrar:
    - métricas de marcador esperado y probabilidades 1X2 (o la probabilidad de ganar en la NBA);
    - el total esperado;
    - una tabla con la probabilidad del modelo en las líneas over/under y hándicap de Betano;
    - jugadores destacados y bajas de cada equipo;
    - factores.
  - Pestaña **Modelo**: tabla de métricas por liga frente a la línea base y la lista de predicciones evaluadas.
  - Excel: hoja "Predicciones".
- **Mirror**: pestaña Partidos y `tabla_*` del hito 2.
- **Validate**: `pytest tests/test_exportar.py` y humo con AppTest sobre una base precargada sin red.

### Task 10: Docs y PRD
- **Action**:
  - README: fuentes, clave, cómo funciona el modelo y sus límites.
  - PRD: hito 3 `complete`.
- **Validate**: revisión manual.

## Desviaciones durante la implementación
- **Back-to-back NBA**: constante fija `FATIGA_B2B = 1.5` puntos, no estimada del historial.
- **Encogimiento**: se suman `PRIOR = 3` partidos de un equipo promedio a cada equipo, en lugar de una fuerza inicial específica para ascendidos. `pronosticar` devuelve `None` si un equipo no está en el historial o ambos son el mismo.
- **Zona horaria del historial** (`ZONA_HISTORIAL`): la fecha del partido se toma en hora de París (fútbol) o de Nueva York (NBA) para que descanso y back-to-back calcen con las fechas de las fuentes.
- **Línea principal de totales**: la de Betano con Over y Under más parejos; si Betano no ofrece totales (fútbol), se usa la de Pinnacle.
- **Evaluación**: `calcular_metricas` / `por_liga` en lugar de `metricas`; el error medio del total queda vacío (mezcla goles y puntos).
- **Backtest 2025-26 real**: total 2.963 partidos, acierto 58,5 % vs 48,7 % de la base y Brier 0,525 vs 0,585. Supera a la base en las 6 ligas.

## Validation
```bash
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m pytest --cov=predictor --cov-report=term-missing
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Sin lesiones de fútbol | Cierta | Se avisa en los factores; opción futura: API-Football pagado |
| Endpoints de ESPN no oficiales: pueden cambiar o desaparecer | Media | Parser tolerante. Si falla, el partido se muestra sin lesiones y con un aviso, sin romper la pestaña |
| stats.nba.com bloquea o responde lento | Media | Timeout de 30 s, una vez al día, caché en SQLite |
| Modelo con poca muestra al inicio de temporada (octubre) | Alta | Se usa también la temporada anterior con peso por antigüedad, se encoge hacia la media y se advierte en los factores |
| Ascendidos sin historial en la liga | Alta | Encogimiento a una fuerza inicial de recién ascendido (media de los ascendidos previos); se marca en los factores |
| Falsa confianza en el modelo | Media | La pestaña Modelo muestra el acierto real frente a la línea base. No hay marca de valor hasta el hito 4 |
| Desajuste de nombres en jugadores y lesiones | Media | Reusar `emparejar` y loguear los no emparejados |

## Acceptance
- [x] Cada partido con historial muestra esperados, probabilidades, probabilidades en las líneas de Betano, jugadores (y bajas en NBA) y factores
- [x] Las predicciones quedan guardadas antes del inicio y se congelan al empezar
- [x] La pestaña Modelo muestra el acierto por liga frente a la línea base
- [x] El backtest 2025-26 supera a la línea base en Brier (resultado reportado)
- [x] Si ESPN o nba_api fallan, la app sigue funcionando con un aviso
- [x] Ninguna clave en repo, base de datos ni logs
- [x] Migración v2→v3 sin pérdida; tests sin red; cobertura ≥ 90 % en los módulos nuevos
- [x] All tasks complete
- [x] Validation passes
- [x] Patterns mirrored, not reinvented
