# Predictor de apuestas

Herramienta personal para NBA y fútbol europeo (Premier League, Serie A, Bundesliga, LaLiga, Ligue 1).
Requisitos en [`.claude/prds/predictor-apuestas.prd.md`](.claude/prds/predictor-apuestas.prd.md).

**Hito 1 — Bitácora y fondo** (actual): registro de apuestas colocadas y no colocadas, liquidación,
depósitos/retiros, balances (saldo, ROI, % acierto por deporte y liga) y exportación a Excel.

## Instalación

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

## Uso

```bash
.venv/Scripts/python -m streamlit run app.py
```

Los datos se guardan en `data/bitacora.db` (SQLite). Para usar otra ubicación —recomendado si la
carpeta del proyecto está en OneDrive— define la variable `PREDICTOR_DB`:

```powershell
$env:PREDICTOR_DB = "E:\datos\bitacora.db"; .venv\Scripts\python -m streamlit run app.py
```

Reglas de cálculo:

- Ganada: `round(monto × cuota) − monto` (se puede ajustar a mano al liquidar).
  Perdida: `−monto`. Nula: `0`.
- Saldo = fondo inicial + depósitos − retiros + resultados liquidados − montos en juego.
- Las apuestas **no colocadas** no tocan el saldo; se reportan aparte como resultado hipotético.

## Tests

```bash
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m pytest --cov=predictor --cov-report=term-missing
```
