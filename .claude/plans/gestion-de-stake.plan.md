# Plan: Gestión de stake

**Source PRD**: `.claude/prds/predictor-apuestas.prd.md`
**Selected Milestone**: 5 — Gestión de stake
**Complexity**: Medium

## Summary
Al registrar una apuesta, la app sugiere qué **% del saldo** apostar y el monto en CLP. La sugerencia
depende de la marca de valor del hito 4 y respeta límites por apuesta, por día y un stop-loss. La
apuesta guarda el % sugerido para medir la disciplina (métrica del PRD: 100 % de las apuestas con %
sugerido) y para comparar lo apostado con lo sugerido. Un backtest simula la evolución del fondo con
la regla elegida sobre el historial de fútbol, para ver la caída máxima antes de usarla.

## Decisiones propuestas (pendientes de confirmar por Tomas)
| # | Tema | Propuesta | Alternativa |
|---|---|---|---|
| D1 | Regla de stake | **Escalonada por valor**. ✅ Confirmado: **¼ de Kelly** con la probabilidad del **mercado** sin margen (la mejor calibrada según el backtest del hito 4). Se usa el mínimo con el Kelly del modelo, con piso de 1 % y tope de 3 %. ⚠️ Solo modelo: **0,5 %** fijo. Sin valor o a mano: **1 %** fijo. | Kelly fraccional con la probabilidad del modelo, que en el backtest apostó de más en lo que perdió; o un % plano para todo |
| D2 | Base del % | **Saldo disponible** actual: fondo + movimientos + resultados − montos en juego. Así el stake baja solo cuando el fondo cae. | Fondo inicial fijo (stake constante) |
| D3 | Límites | Tope por apuesta **3 %**. Exposición del día (apuestas colocadas pendientes con fecha de hoy + la nueva) **≤ 10 %**. **Stop-loss**: si el saldo cae a ≤ 70 % del máximo histórico, la sugerencia es 0 y aparece un aviso. Los tres se configuran. | Stop-loss por pérdida diaria |
| D4 | Obligatoriedad | Solo **aviso**: si el monto supera lo sugerido o algún límite, se muestra en rojo y se puede registrar igual; la apuesta queda marcada "fuera de límite". Una casilla de Configuración permite **bloquear**. | Bloquear siempre |
| D5 | Redondeo | Monto sugerido redondeado a **100 CLP** hacia abajo, con un mínimo configurable de **100 CLP**. Si queda bajo el mínimo, la sugerencia es "no apostar". | Sin redondeo |

Con el fondo de 10.000 CLP: 1 % = 100 CLP, 3 % = 300 CLP y 10 % al día = 1.000 CLP.

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Naming | `src/predictor/valor.py:23` | `Umbrales` `frozen` con defaults constantes y validación en `__post_init__`; funciones puras (`ev`, `clasificar`) |
| Config | `src/predictor/cartelera.py:340` | `umbrales` / `fijar_umbrales`: dict `_UMBRALES` clave→campo en `config`, log al fijar |
| Errors | `src/predictor/bitacora.py:121` | `ValueError` en español con los montos (`Saldo insuficiente: disponible …`), que `ejecutar` muestra en la UI |
| Data access | `src/predictor/repositorio.py:412` | `_migrar` con `if version < 5:` y `_ESQUEMA_V5` (`ALTER TABLE apuestas ADD COLUMN`) |
| Service | `src/predictor/bitacora.py:184` | `resumen()` agrega con `_agrupar`; `Resumen` `frozen` con campos nuevos al final |
| Backtest | `src/predictor/evaluacion.py` (`backtest_valor`) | Walk-forward sobre `Evaluada`, resultado por liga en un dataclass con propiedades derivadas |
| Tables | `src/predictor/exportar.py` | `tabla_*` → `DataFrame` con `COLUMNAS_*` en español; `_porcentaje` |
| UI | `app.py` (`registrar`, form `nueva_apuesta`, form `umbrales`) | Selector fuera del form, `ejecutar(mensaje, accion, …)`, avisos con `st.warning` |
| Tests | `tests/conftest.py` (`repo`, `bitacora`, `crear_apuesta`), `tests/test_app.py` | `Repositorio(":memory:")`, sin red; AppTest con base temporal |

## Files to Change
| File | Action | Why |
|---|---|---|
| `src/predictor/stake.py` | CREATE | Puro: `Limites` (configurables), `kelly(p, cuota)`, `sugerir(valor, cuota, p_modelo, p_mercado, saldo, expuesto_hoy, maximo, limites) -> Sugerencia` (fracción, monto, motivo, avisos) |
| `src/predictor/modelos.py` | UPDATE | `Apuesta.stake_sugerido: float \| None` (fracción) y `fuera_de_limite: bool` |
| `src/predictor/repositorio.py` | UPDATE | Esquema v5: dos columnas nuevas en `apuestas`; migración v4→v5 |
| `src/predictor/bitacora.py` | UPDATE | `limites` / `fijar_limites`, `expuesto_hoy(fecha)`, `saldo_maximo()`, `sugerir(...)`; `registrar_apuesta` marca o bloquea según D4. `Resumen`: disciplina (% con sugerencia, % dentro de límite) y ROI por cumplimiento |
| `src/predictor/evaluacion.py` | UPDATE | `simular_fondo(evaluadas, umbrales, limites, fondo)`: saldo final, caída máxima y racha perdedora con la regla D1 |
| `src/predictor/exportar.py` | UPDATE | Columnas "Stake sugerido (%)" y "Fuera de límite" en Apuestas; `tabla_simulacion`; disciplina en el Resumen del Excel |
| `app.py` | UPDATE | Nueva apuesta: sugerencia (%, CLP, motivo) que rellena el monto y avisa si se pasa. "Valor del día" con columna Stake. Resumen: disciplina. Configuración: límites. Modelo: simulación del fondo |
| `tests/test_stake.py` | CREATE | Kelly, escalones, topes, exposición, stop-loss, redondeo y mínimo |
| `tests/test_bitacora.py`, `test_repositorio.py`, `test_evaluacion.py`, `test_exportar.py`, `test_modelos.py`, `test_app.py` | UPDATE | Lo nuevo y la migración v4→v5 |
| `README.md`, PRD | UPDATE | Regla de stake, límites, resultado de la simulación y cierre del hito |

## Tasks
### Task 1: Cálculo de stake (puro)
- **Action**: `stake.py` con `Limites(maximo_apuesta=0.03, maximo_dia=0.10, stop_loss=0.70, fraccion_kelly=0.25, solo_modelo=0.005, sin_valor=0.01, monto_minimo=100)` validados. `kelly(p, cuota) = max(0, (p·c − 1)/(c − 1))`. `sugerir` aplica D1 → tope por apuesta → espacio libre del día → stop-loss → redondeo D5, y devuelve el motivo de cada recorte.
- **Mirror**: `valor.py` (`Umbrales`, `clasificar`).
- **Validate**: `pytest tests/test_stake.py`.

### Task 2: Modelo y repositorio v5
- **Action**: `Apuesta.stake_sugerido` (0–1 o `None`) y `fuera_de_limite`; `_ESQUEMA_V5` con `ALTER TABLE`; lectura y escritura.
- **Mirror**: `prob_modelo` / `valor` del hito 4 (v4).
- **Validate**: `pytest tests/test_modelos.py tests/test_repositorio.py`; la migración se prueba con una base v4 poblada.

### Task 3: Bitácora
- **Action**: `limites` en `config` (mismo patrón que los umbrales). `expuesto_hoy`: suma de las apuestas colocadas pendientes de la fecha. `saldo_maximo`: máximo del saldo reconstruido en orden cronológico, nunca menor al fondo inicial. `sugerir(valor, cuota, p_modelo, p_mercado, fecha)`. `registrar_apuesta` calcula si el monto está fuera de límite: lo marca o, con bloqueo activo, lanza un `ValueError`. El `Resumen` suma `disciplina` y `por_cumplimiento` (dentro / fuera de límite).
- **Mirror**: `fondo_inicial` / `fijar_fondo_inicial`, `resumen`.
- **Validate**: `pytest tests/test_bitacora.py`.

### Task 4: Simulación del fondo
- **Action**: `simular_fondo`: recorre el backtest de valor de fútbol en orden de fecha con 10.000 CLP iniciales y apuesta lo que diría `sugerir`, incluida la exposición diaria. Reporta saldo final, ROI sobre lo apostado, caída máxima y la peor racha. Se compara con un 1 % plano. El resultado real 2025-26 se anota en este plan.
- **Mirror**: `backtest_valor`, `ResultadoValor`.
- **Validate**: `pytest tests/test_evaluacion.py`, más un script en el scratchpad con el historial real.

### Task 5: Tablas y UI
- **Action**:
  - **Nueva apuesta**: bajo el selector "Desde la cartelera", la sugerencia ("1,0 % del saldo · $100 · sin valor"). Rellena el monto, y los avisos aparecen si el monto escrito la supera o rompe un límite. En una apuesta a mano se usa la regla "sin valor".
  - **Valor del día**: columna "Stake (CLP)".
  - **Resumen**: disciplina y ROI dentro / fuera de límite.
  - **Configuración**: form de límites y casilla de bloqueo.
  - **Modelo**: tabla de la simulación bajo la casilla del backtest.
  - **Excel**: columnas nuevas.
- **Mirror**: `registrar`, form `umbrales`, `tabla_backtest_valor`.
- **Validate**: `pytest tests/test_exportar.py tests/test_app.py`.

### Task 6: Docs y PRD
- **Action**: README con la regla, los límites, que **el stake no reduce el riesgo de un modelo sin ventaja** y el resultado de la simulación. PRD: hito 5 en `complete` y la pregunta del criterio de % resuelta. En este plan, las desviaciones.
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
| Kelly con una probabilidad mal calibrada apuesta de más | Alta | Probabilidad del mercado, ¼ de Kelly, tope de 3 % y escalón fijo bajo para "solo modelo" |
| Con 10.000 CLP los montos son chicos (100–300 CLP) y pueden quedar bajo el mínimo de Betano Chile | Media | `monto_minimo` configurable; bajo el mínimo la sugerencia es "no apostar" en vez de subir el monto |
| El stake no arregla un modelo sin ventaja (ROI −15,9 % en "solo modelo") | Alta | La simulación muestra la caída esperada; stop-loss al 70 % del máximo |
| Saldo máximo mal reconstruido con depósitos o retiros | Media | Tests con movimientos intercalados; los depósitos cuentan como base y no como ganancia |
| Apuestas antiguas sin `stake_sugerido` | Cierta | `None` = "sin sugerencia"; la disciplina solo cuenta desde el hito 5 |
| Migración v4→v5 | Baja | Test con una base v4 poblada |

## Acceptance
- [ ] Nueva apuesta muestra el % y el monto sugeridos con su motivo y rellena el monto
- [ ] Límites por apuesta, por día y stop-loss configurables; aviso (o bloqueo opcional) al pasarlos
- [ ] Cada apuesta nueva guarda `stake_sugerido` y si quedó fuera de límite
- [ ] El Resumen y el Excel muestran la disciplina y el ROI dentro / fuera de límite
- [ ] La simulación del fondo en fútbol 2025-26 queda reportada
- [ ] Migración v4→v5 sin pérdida; tests sin red; cobertura ≥ 90 % en lo nuevo
- [ ] All tasks complete
- [ ] Validation passes
- [ ] Patterns mirrored, not reinvented
