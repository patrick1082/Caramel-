# Predictor de apuestas

Herramienta personal para NBA y fútbol europeo (Premier League, Serie A, Bundesliga, LaLiga, Ligue 1).
Requisitos en [`.claude/prds/predictor-apuestas.prd.md`](.claude/prds/predictor-apuestas.prd.md).

**Hito 1 — Bitácora y fondo**: registro de apuestas colocadas y no colocadas, liquidación,
depósitos/retiros, balances (saldo, ROI, % acierto por deporte y liga) y exportación a Excel.

**Hito 2 — Partidos y cuotas** (actual): pestaña *Partidos* con los partidos del día filtrados por
hora (Chile), deporte y liga; cuotas de ganador, over/under y hándicap de Betano y otras casas, con
la mejor cuota y el promedio; forma reciente de cada equipo y enfrentamientos directos.

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

### Fuentes de partidos y cuotas

| Dato | Fuente | Costo |
|---|---|---|
| Partidos y cuotas | [The Odds API](https://the-odds-api.com) (plan gratuito: 500 créditos/mes) | 3 créditos por liga |
| Historial fútbol | CSV de [football-data.co.uk](https://www.football-data.co.uk) | Gratis |
| Historial NBA | stats.nba.com vía `nba_api` | Gratis |

- Betano Chile no está en The Odds API: se usa **Betano (UK)** como aproximación. Stake tampoco
  está; se usa **Pinnacle** como referencia de mercado. Betano UK no ofrece hándicap NBA.
- El botón *Actualizar* solo consulta las ligas cuyas cuotas tienen más de 1 hora y muestra antes
  cuántos créditos gastará (las 6 ligas = 18 créditos). El historial se descarga como mucho una vez
  al día por liga (temporada actual y anterior).

La clave de The Odds API se lee de la variable de entorno `ODDS_API_KEY`; nunca se guarda en la
base de datos ni en el repositorio. Sin clave, la app muestra las cuotas ya guardadas.

```powershell
$env:ODDS_API_KEY = "tu-clave"; .venv\Scripts\python -m streamlit run app.py
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
