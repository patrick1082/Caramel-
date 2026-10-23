# Plan: Bitácora y fondo

**Source PRD**: `.claude/prds/predictor-apuestas.prd.md`
**Selected Milestone**: 1 — Bitácora y fondo
**Complexity**: Medium

## Summary
Base de la app: una app web local en Python + Streamlit donde el usuario registra apuestas (colocadas y no colocadas), movimientos del fondo (depósitos/retiros), las liquida, y ve balances totales (saldo, ROI, % acierto) con exportación a Excel. Fondo inicial configurable, por defecto 10.000 CLP. Es la base de datos sobre la que los hitos 2–5 enganchan partidos, predicciones y % de billetera sugerido.

## Decisiones tomadas
- **Stack**: Python 3.14 + Streamlit (elegido por el usuario).
- **Moneda**: CLP, montos como enteros (sin decimales). Cuotas en formato decimal (ej. 1.85) con `Decimal`.
- **Persistencia**: SQLite (stdlib `sqlite3`), archivo local `data/bitacora.db` fuera de git.
- **Excel**: `pandas` + `openpyxl`.
- **Tests**: `pytest` + `pytest-cov`, objetivo ≥ 80% en la lógica de dominio (la UI Streamlit queda fuera de cobertura).

## Patterns to Mirror
| Category | Source | Pattern |
|---|---|---|
| Naming | — | No existe código previo en `caramel/`. Se adopta: módulos y funciones en `snake_case` en español (`bitacora`, `liquidar_apuesta`), clases `PascalCase` (`Apuesta`, `Movimiento`). |
| Errors | — | Sin precedente. Se adopta: validación en el dominio lanzando `ValueError` con mensaje claro; la UI captura y muestra `st.error`. |
| Data access | — | Sin precedente. Se adopta: un módulo repositorio (`repositorio.py`) como única capa que toca SQLite; el dominio no importa `sqlite3`. |
| Logging | — | Sin precedente. `logging` estándar, nivel INFO para altas/liquidaciones. |
| Tests | — | Sin precedente. `tests/test_<modulo>.py`, pytest con fixtures de BD SQLite en memoria (`:memory:`). |

## Modelo de datos (alcance del hito)
**Apuesta**: id, fecha_registro, fecha_evento, deporte (`NBA` / `Futbol`), liga, partido, mercado, seleccion, cuota, monto (CLP), casa (default `Betano`), colocada (bool — permite registrar apuestas *no* tomadas para la comparación de la hipótesis), prediccion_propia (texto), estado (`pendiente` / `ganada` / `perdida` / `nula`), resultado_neto (CLP, calculado al liquidar), nota.

**Movimiento**: id, fecha, tipo (`deposito` / `retiro`), monto, nota.

**Config**: fondo_inicial (default 10.000 CLP).

Reglas:
- Ganada → resultado_neto = round(monto × cuota) − monto. Perdida → −monto. Nula → 0.
- Saldo = fondo_inicial + depósitos − retiros + Σ resultado_neto (liquidadas, colocadas) − Σ monto (pendientes, colocadas).
- Apuestas con `colocada = False` no afectan el saldo; se reportan aparte (ROI "hipotético").
- No se puede registrar una apuesta colocada con monto > saldo disponible.
- cuota > 1.0, monto > 0; una apuesta liquidada no se vuelve a liquidar (sí se puede revertir a pendiente explícitamente).

Métricas del resumen: saldo actual, ganancia/pérdida total, ROI (Σ resultado / Σ monto liquidado), % acierto, nº apuestas por estado, desglose por deporte y liga, y las mismas métricas para no colocadas.

## Files to Change
| File | Action | Why |
|---|---|---|
| `.gitignore` | CREATE | Ignorar `data/`, `.venv/`, `__pycache__/`, exportaciones `.xlsx` |
| `pyproject.toml` | CREATE | Dependencias (streamlit, pandas, openpyxl; dev: pytest, pytest-cov, ruff) y config de pytest/ruff |
| `README.md` | CREATE | Cómo instalar y ejecutar |
| `src/predictor/__init__.py` | CREATE | Paquete |
| `src/predictor/modelos.py` | CREATE | Dataclasses `Apuesta`, `Movimiento`, enums de estado/deporte/tipo, validaciones |
| `src/predictor/repositorio.py` | CREATE | Esquema SQLite + CRUD de apuestas, movimientos y config |
| `src/predictor/bitacora.py` | CREATE | Lógica: registrar, liquidar, revertir, calcular saldo y resumen |
| `src/predictor/exportar.py` | CREATE | Excel con hojas `Apuestas`, `Movimientos`, `Resumen` |
| `app.py` | CREATE | UI Streamlit: alta de apuesta, liquidar, movimientos, panel de balances, botón descargar Excel |
| `tests/conftest.py` | CREATE | Fixture de repositorio en memoria |
| `tests/test_modelos.py` | CREATE | Validaciones |
| `tests/test_bitacora.py` | CREATE | Liquidación, saldo, ROI, no colocadas |
| `tests/test_repositorio.py` | CREATE | Persistencia ida y vuelta |
| `tests/test_exportar.py` | CREATE | Hojas y columnas del Excel |
| `.claude/prds/predictor-apuestas.prd.md` | UPDATE | Hito 1 → in-progress (hecho al generar este plan) |

## Tasks
### Task 0: Repositorio git propio
- **Action**: Hoy `caramel/` no es un repo: git resuelve al repo de `C:/Users/Tomas` (todo el home). Ejecutar `git init` dentro de `caramel/` para aislar el proyecto.
- **Validate**: `git rev-parse --show-toplevel` devuelve `.../Proyectos/caramel`.

### Task 1: Scaffolding del proyecto
- **Action**: `pyproject.toml`, `.gitignore`, `README.md`, entorno virtual `.venv`, instalar dependencias.
- **Mirror**: layout `src/` estándar.
- **Validate**: `python -c "import streamlit, pandas, openpyxl"` y `pytest` (0 tests, sin error).

### Task 2: Modelos y validaciones (TDD)
- **Action**: tests primero para cuota ≤ 1, monto ≤ 0, deporte/estado inválidos; luego `modelos.py`.
- **Validate**: `pytest tests/test_modelos.py`.

### Task 3: Repositorio SQLite (TDD)
- **Action**: crear esquema al iniciar, guardar/listar/actualizar apuestas y movimientos, leer/escribir fondo inicial.
- **Validate**: `pytest tests/test_repositorio.py`.

### Task 4: Lógica de bitácora (TDD)
- **Action**: registrar (con chequeo de saldo), liquidar ganada/perdida/nula, revertir, saldo, resumen global y por deporte/liga, métricas de no colocadas.
- **Validate**: `pytest tests/test_bitacora.py` con casos numéricos explícitos (ej. 10.000 inicial, apuesta 1.000 @ 1.85 ganada → saldo 10.850).

### Task 5: Exportación a Excel (TDD)
- **Action**: generar `.xlsx` en memoria (bytes) con 3 hojas, montos CLP sin decimales.
- **Validate**: `pytest tests/test_exportar.py` (reabre el archivo con `openpyxl` y verifica hojas/filas).

### Task 6: UI Streamlit
- **Action**: `app.py` con secciones: Resumen (métricas), Nueva apuesta (formulario), Apuestas pendientes (liquidar), Historial (tabla filtrable), Movimientos, Configuración (fondo inicial), botón "Descargar Excel".
- **Validate**: `streamlit run app.py` y prueba manual: registrar 3 apuestas (1 ganada, 1 perdida, 1 no colocada), un depósito, exportar y abrir el Excel.

### Task 7: Cierre
- **Action**: `ruff check`, cobertura, actualizar README, marcar hito 1 `complete` en el PRD.
- **Validate**: comandos de la sección Validation.

## Validation
```bash
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m pytest --cov=predictor --cov-report=term-missing   # ≥ 80%
.venv/Scripts/python -m streamlit run app.py                               # prueba manual
```

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| Python 3.14 sin wheels para alguna dependencia | Baja | Si falla la instalación, usar Python 3.12/3.13 vía `py -3.12` |
| `caramel/` está dentro de OneDrive: la sincronización puede bloquear/corromper `bitacora.db` | Media | Ruta de BD configurable; excluir `data/` de OneDrive o ubicarla fuera; el Excel exportado sirve de respaldo |
| Redondeo de pagos en CLP distinto al de Betano | Media | Regla única `round(monto × cuota)` documentada; permitir editar el resultado_neto manualmente al liquidar |
| Esquema no prevé campos de hitos 3–5 (predicción IA, % sugerido) | Media | Migraciones simples por versión de esquema (`PRAGMA user_version`) |
| Streamlit re-ejecuta el script en cada interacción → dobles registros | Baja | Formularios con `st.form` |

## Acceptance
- [ ] Registrar, liquidar y revertir apuestas colocadas y no colocadas
- [ ] Registrar depósitos y retiros; saldo correcto en todo momento
- [ ] Resumen con saldo, ganancia total, ROI, % acierto y desglose por deporte/liga
- [ ] Excel descargable con hojas Apuestas, Movimientos y Resumen
- [ ] Datos persisten entre reinicios de la app
- [ ] Tests pasan con ≥ 80% de cobertura en `src/predictor`
- [ ] `ruff check` sin errores
