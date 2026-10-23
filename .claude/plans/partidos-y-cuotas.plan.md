# Plan: Partidos y cuotas

**Source PRD**: `.claude/prds/predictor-apuestas.prd.md`
**Selected Milestone**: 2 — Partidos y cuotas
**Complexity**: Large

## Summary
Nueva pestaña **Partidos** que trae de forma automática los partidos próximos de la NBA y de las 5 ligas
(Premier League, Serie A, Bundesliga, LaLiga y Ligue 1). Cada partido muestra cuotas de ganador, over/under
y hándicap. Se compara Betano con Pinnacle y otras casas confiables. La lista se filtra por día, hora,
deporte y liga. Cada partido incluye además estadísticas e historial: forma reciente, promedio a favor y
en contra, local/visita y enfrentamientos directos. Todo usa fuentes gratuitas y queda en caché en SQLite
para no gastar los 500 créditos/mes de The Odds API. La predicción (hito 3) y la marca de valor (hito 4)
quedan fuera de este hito.

## Decisiones tomadas (respuestas de Tomas)
| Tema | Decisión |
|---|---|
| Cuotas | Todo automático vía **The Odds API**. **Betano UK (`betano_uk`)** se usa como aproximación de Betano Chile. |
| Comparación | Stake no existe en la API → se reemplaza por **Pinnacle** (referencia del mercado) + otras casas. |
| Presupuesto | **Plan gratuito**: 500 créditos/mes. |
| Mercados | Ganador (`h2h`), Over/Under (`totals`), Hándicap (`spreads`). |
| Filtros | Por día, rango horario (hora de Chile), deporte y liga. |
| Estadísticas | La app trae estadísticas e historial de cada partido, para apoyar la predicción. |

### Fuentes de datos (todas gratuitas)
| Dato | Fuente | Costo |
|---|---|---|
| Partidos próximos + cuotas | The Odds API v4 `/sports/{key}/odds`, `markets=h2h,totals,spreads`, `bookmakers=` lista fija (≤10 casas cuenta como 1 región) | 3 créditos por liga → **18 por actualización completa** (~27 al mes) |
| Historial fútbol (resultados, tiros, córners, tarjetas) | CSV de football-data.co.uk (`/mmz4281/{2627,2526}/{E0,I1,D1,SP1,F1}.csv`) | Gratis, sin clave |
| Historial NBA (marcadores, rebotes, asistencias, % de tiro) | Paquete `nba_api` (`LeagueGameFinder`, temporadas 2026-27 y 2025-26) | Gratis, sin clave |

Casas consultadas (`bookmakers=`): `betano_uk`, `pinnacle`, `betfair_ex_eu`, `williamhill`, `marathonbet`,
`onexbet`, `unibet_eu`, `sport888`, `betsson`, `nordicbet`. La lista se valida en la tarea 1.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Naming | `src/predictor/bitacora.py:88` | Español snake_case; servicio de dominio con el repo inyectado en `__init__` (`Bitacora(repo)`) → `Cartelera(repo, cliente_odds, ...)` |
| Models | `src/predictor/modelos.py:60` | `@dataclass` con validación en `__post_init__` que lanza `ValueError` en español |
| Errors | `src/predictor/bitacora.py:163` | `ValueError` con mensaje para el usuario; la UI lo muestra con `st.error` vía `ejecutar()` (`app.py:36`) |
| Logging | `src/predictor/bitacora.py:13,103` | `logger = logging.getLogger(__name__)`, `logger.info` con `%s` en cada acción que cambia estado |
| Data access | `src/predictor/repositorio.py:117-126` | Solo `Repositorio` toca SQLite; esquema versionado con `PRAGMA user_version` y `_migrar()` → nueva migración **v2** |
| Config | `src/predictor/repositorio.py:189-193` | `obtener_config`/`fijar_config` para marcas de tiempo de actualización y créditos restantes |
| Tablas UI | `src/predictor/exportar.py:57-79` | Funciones `tabla_*` que devuelven `pd.DataFrame` con columnas renombradas en español |
| Tests | `tests/conftest.py:11-39`, `tests/test_bitacora.py` | `tests/test_<modulo>.py`, fixtures `repo` en `:memory:` y fábricas `crear_*`, `pytest.raises(ValueError, match=...)`, `parametrize` |

No existe código HTTP en el repo. Patrón nuevo propuesto: cada cliente recibe una función `obtener` inyectable
(por defecto `requests.get`). Los tests pasan un falso con JSON/CSV de `tests/datos/`, sin red, igual que se
inyecta el repo en `Bitacora`.

## Files to Change
| File | Action | Why |
|---|---|---|
| `pyproject.toml` | UPDATE | Dependencias `requests`, `nba_api`, `tzdata` (zona horaria `America/Santiago` en Windows) |
| `src/predictor/modelos.py` | UPDATE | `Mercado` (StrEnum h2h/totals/spreads), dataclasses `Partido`, `Cuota`, `ResultadoHistorico` |
| `src/predictor/ligas.py` | CREATE | Mapa liga → `sport_key` de The Odds API, código football-data y temporadas |
| `src/predictor/nombres.py` | CREATE | Normaliza nombres de equipos entre fuentes (alias + `difflib`) |
| `src/predictor/fuentes/__init__.py` | CREATE | Paquete de clientes externos |
| `src/predictor/fuentes/odds_api.py` | CREATE | `ClienteOddsApi`: pide cuotas por liga, parsea a `Partido`/`Cuota` y lee créditos restantes de los headers |
| `src/predictor/fuentes/football_data.py` | CREATE | Descarga y parsea CSV de temporada → `ResultadoHistorico` |
| `src/predictor/fuentes/nba.py` | CREATE | Envuelve `nba_api`, une las 2 filas de cada `GAME_ID` → `ResultadoHistorico` |
| `src/predictor/repositorio.py` | UPDATE | Migración v2: tablas `partidos`, `cuotas`, `historial` + métodos de guardado y consulta |
| `src/predictor/estadisticas.py` | CREATE | Funciones puras: forma (últimos 5), promedios a favor/en contra, local/visita, H2H |
| `src/predictor/cartelera.py` | CREATE | Servicio `Cartelera`: actualizar cuotas/historial con caché y tope de créditos, filtrar partidos, comparar cuotas, estadísticas |
| `src/predictor/exportar.py` | UPDATE | `tabla_partidos`, `tabla_cuotas` (Betano vs Pinnacle vs mejor vs promedio), `tabla_estadisticas` |
| `app.py` | UPDATE | Pestaña **Partidos** (filtros, botón actualizar, créditos, detalle por partido) + clave de API en Configuración |
| `README.md` | UPDATE | Variable `ODDS_API_KEY`, fuentes, consumo de créditos |
| `tests/datos/odds_nba.json`, `odds_epl.json`, `E0.csv`, `nba_juegos.json` | CREATE | Respuestas reales recortadas para tests sin red |
| `tests/test_odds_api.py`, `test_football_data.py`, `test_nba.py`, `test_nombres.py`, `test_estadisticas.py`, `test_cartelera.py` | CREATE | Cobertura de cada módulo |
| `tests/test_repositorio.py` | UPDATE | Migración v1 → v2 conserva apuestas; CRUD de partidos/cuotas/historial |
| `.claude/prds/predictor-apuestas.prd.md` | UPDATE | Hito 2 `in-progress`; preguntas abiertas resueltas (fuentes, mercados, acceso a cuotas) |

## Tasks
### Task 1: Dependencias y verificación de fuentes
- **Action**: Agregar `requests>=2.32`, `nba_api>=1.10`, `tzdata` a `pyproject.toml` y reinstalar. Con la clave de Tomas:
  llamar a `/v4/sports` (gratis) para confirmar los `sport_key` de las 5 ligas. Hacer una sola llamada `/odds` de prueba
  (3 créditos) para confirmar que `betano_uk` y `pinnacle` traen NBA y fútbol. Guardar la respuesta recortada como fixture.
  Descargar un CSV de football-data y un lote de `nba_api` para los fixtures.
- **Mirror**: `pyproject.toml` existente (setuptools, extras `dev`).
- **Validate**: `.venv/Scripts/python -c "import requests, nba_api, zoneinfo; zoneinfo.ZoneInfo('America/Santiago')"`

### Task 2: Modelos y ligas
- **Action**: Agregar `Mercado`, `Partido` (id de la API, deporte, liga, local, visitante, inicio en UTC con tz),
  `Cuota` (partido_id, casa, mercado, selección, línea opcional, cuota `Decimal` > 1, actualizada) y
  `ResultadoHistorico` (liga, temporada, fecha, local, visitante, marcador local/visita y `extras: dict` con
  tiros, rebotes, etc.). Crear `ligas.py`, donde `LIGAS` sigue siendo la fuente única de nombres.
- **Mirror**: validación en `__post_init__` como `Apuesta` (`modelos.py:60-77`).
- **Validate**: `pytest tests/test_modelos.py`

### Task 3: Normalización de nombres
- **Action**: `normalizar(nombre, liga) -> str`. Pasar a minúsculas, quitar acentos y sufijos (FC, AFC, CF) y aplicar un
  diccionario de alias por liga (p. ej. "Man United" ↔ "Manchester United", "Inter" ↔ "Inter Milan").
  Si no hay coincidencia exacta, usar `difflib.get_close_matches` con un umbral. Cuando no se resuelva,
  dejar un `logger.warning` (sin excepción) para ampliar el alias.
- **Mirror**: funciones puras como `calcular_resultado` (`bitacora.py:56`).
- **Validate**: `pytest tests/test_nombres.py`. Incluir un test que cruce los 20 equipos de cada fixture de odds con su CSV.

### Task 4: Cliente The Odds API
- **Action**: `ClienteOddsApi(api_key, obtener=requests.get)`. Su método `cuotas(liga) -> ResultadoOdds(partidos, cuotas,
  creditos_restantes, creditos_usados)` pide `regions` omitido, `bookmakers=<lista>`, `markets=h2h,totals,spreads`,
  `oddsFormat=decimal` y `dateFormat=iso`. Errores: 401 → `ValueError("Clave de API inválida")`;
  429 o créditos agotados → `ValueError` claro; timeout de 15 s. La clave nunca se loguea.
- **Mirror**: mensajes `ValueError` en español; `logger.info("Cuotas %s: %s partidos, %s créditos restantes", ...)`.
- **Validate**: `pytest tests/test_odds_api.py`. Casos: parseo de los 3 mercados, empate en fútbol, líneas de spread/total,
  casa sin un mercado, headers de créditos, 401 y 429.

### Task 5: Clientes de historial
- **Action**: `football_data.descargar(liga, temporada, obtener)` parsea fecha `dd/mm/yyyy` y las columnas
  FTHG/FTAG/HS/AS/HST/AST/HC/AC. `nba.descargar(temporada, buscar=LeagueGameFinder)` empareja local y visita por `MATCHUP`
  ("vs." = local) e incluye PTS/REB/AST/FG_PCT. Ambos devuelven `list[ResultadoHistorico]`.
- **Mirror**: inyección de dependencia como en el cliente de odds.
- **Validate**: `pytest tests/test_football_data.py tests/test_nba.py`

### Task 6: Repositorio v2
- **Action**: `_migrar()` pasa de v1 a v2 sin tocar las tablas existentes. Tablas nuevas:
  `partidos(id PK, deporte, liga, local, visitante, inicio)`,
  `cuotas(partido_id, casa, mercado, seleccion, linea, cuota, actualizada, PK compuesta)` con reemplazo en cada actualización,
  e `historial(liga, temporada, fecha, local, visitante, marcador_local, marcador_visitante, extras JSON, UNIQUE)`.
  Métodos: `guardar_partidos`, `reemplazar_cuotas(liga, ...)`, `listar_partidos(desde, hasta, ligas)`, `cuotas_de(partido_id)`,
  `guardar_historial`, `historial_de(liga, equipo)`. Los partidos ya empezados se ocultan al listar y se purgan tras 2 días.
- **Mirror**: `_migrar` y conversión `_fila_a_*` (`repositorio.py:85-126`).
- **Validate**: `pytest tests/test_repositorio.py`. Incluir un test que cree una BD v1 con apuestas, la abra con el código
  nuevo y verifique que las apuestas siguen y `user_version == 2`.

### Task 7: Estadísticas
- **Action**: `estadisticas(equipo, historial, ultimos=5)` → `Estadisticas` (frozen). Campos: forma ("G G E P G" o "G P G"),
  promedio a favor y en contra (total, local y visita), partidos jugados y extras promedio.
  `cara_a_cara(local, visitante, historial, ultimos=5)` devuelve los enfrentamientos directos.
- **Mirror**: `Metricas` frozen con propiedades derivadas (`bitacora.py:20-36`).
- **Validate**: `pytest tests/test_estadisticas.py`. Casos: equipo sin historial (valores `None`, sin división por cero).

### Task 8: Servicio Cartelera
- **Action**: `Cartelera(repo, cliente_odds, descargar_futbol, descargar_nba, reloj=datetime.now)`.
  - `actualizar_cuotas(ligas, forzar=False)`: salta las ligas actualizadas hace menos de 60 min salvo `forzar`. Si los
    créditos restantes son menores que lo necesario, lanza `ValueError` antes de llamar. Guarda los créditos en config.
  - `actualizar_historial(ligas)`: como máximo una vez al día por liga.
  - `partidos(dia, hora_desde, hora_hasta, ligas)`: el filtro va en hora de Chile.
  - `comparar(partido)`: por mercado/selección/línea entrega Betano, Pinnacle, mejor cuota (y su casa) y promedio.
  - `estadisticas(partido)`: estadísticas de local, visita y H2H.
- **Mirror**: `Bitacora` (`bitacora.py:88-200`) con logging en cada acción.
- **Validate**: `pytest tests/test_cartelera.py`. Casos: caché evita una segunda llamada, `forzar` la hace, sin créditos falla,
  filtro horario cruza la medianoche UTC, comparación sin Betano muestra "—".

### Task 9: Tablas y UI
- **Action**: Agregar `tabla_partidos`, `tabla_cuotas` y `tabla_estadisticas` en `exportar.py`. En `app.py`, crear la pestaña **Partidos** como primera pestaña:
  - filtros de día (hoy por defecto), rango horario (slider), deporte y ligas (multiselect);
  - botón "Actualizar cuotas", con el costo estimado en créditos y los créditos restantes;
  - "Actualizado hace X min";
  - un expander por partido con la hora de Chile, las cuotas por mercado y las estadísticas e H2H.

  La clave se lee de `ODDS_API_KEY`. Sin clave, la pestaña muestra cómo configurarla y no falla.
- **Mirror**: `ejecutar()` para errores, `st.dataframe(..., hide_index=True, width="stretch")`, `@st.cache_resource`.
- **Validate**: AppTest headless con un cliente falso (sin red): filtrar, actualizar, ver detalle y comprobar el caso sin clave. Al final, prueba manual en el navegador con la clave real.

### Task 10: Docs y PRD
- **Action**: En el README, documentar `ODDS_API_KEY`, las fuentes y el consumo estimado. En el PRD, marcar el hito 2 como `complete` al terminar y cerrar las preguntas resueltas.
- **Validate**: lectura.

## Validation
```bash
.venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m ruff format --check .
.venv/Scripts/python -m pytest --cov=predictor --cov-report=term-missing
```
Meta: ≥ 90% de cobertura en módulos nuevos y 61 tests existentes en verde. Los tests no usan red.

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Betano UK no coincide con Betano Chile (cuotas y líneas distintas) | Alta | Se rotula "Betano (UK)" en la UI; la cuota real de betano.cl se sigue anotando en la bitácora |
| `betano_uk` no cubre NBA o algunas ligas | Media | Se verifica en la tarea 1; si falta, la tabla muestra "—" y queda la comparación entre las demás casas |
| 500 créditos se agotan | Media | Caché de 60 min, tope previo a cada llamada, contador visible y actualización por liga (no todas) |
| `stats.nba.com` (detrás de `nba_api`) bloquea o responde lento | Media | Timeout, historial cacheado una vez al día y error claro sin romper la pestaña |
| Nombres de equipos distintos entre fuentes | Alta | `nombres.py` con alias y test que cruza todos los equipos de los fixtures |
| football-data.co.uk cambia formato o URL | Baja | Parser tolerante a columnas faltantes; extras opcionales |
| Clave de API filtrada | Baja | Solo variable de entorno; nunca en BD, logs ni git |
| Pinnacle con cuotas con retraso | Baja | Se muestra `last_update` de cada casa |

## Acceptance
- [ ] Pestaña Partidos lista partidos de NBA y las 5 ligas filtrables por día, hora, deporte y liga
- [ ] Cada partido muestra ganador, over/under y hándicap con Betano (UK), Pinnacle, mejor cuota y promedio
- [ ] Cada partido muestra forma, promedios a favor/en contra, local/visita y H2H
- [ ] Créditos restantes visibles; una actualización completa ≤ 18 créditos; caché evita llamadas repetidas
- [ ] La bitácora del hito 1 sigue funcionando y la BD v1 migra sin pérdida
- [ ] All tasks complete
- [ ] Validation passes
- [ ] Patterns mirrored, not reinvented
