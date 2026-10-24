# Predictor de apuestas

Herramienta personal para NBA y fútbol europeo (Premier League, Serie A, Bundesliga, LaLiga, Ligue 1).
Requisitos en [`.claude/prds/predictor-apuestas.prd.md`](.claude/prds/predictor-apuestas.prd.md).

**Hito 1 — Bitácora y fondo**: registro de apuestas colocadas y no colocadas, liquidación,
depósitos/retiros, balances (saldo, ROI, % acierto por deporte y liga) y exportación a Excel.

**Hito 2 — Partidos y cuotas**: pestaña *Partidos* con los partidos del día filtrados por
hora (Chile), deporte y liga; cuotas de ganador, over/under y hándicap de Betano y otras casas, con
la mejor cuota y el promedio; forma reciente de cada equipo y enfrentamientos directos.

**Hito 3 — Predicción** (actual): cada partido muestra la predicción de un modelo estadístico
local (probabilidades, marcador esperado, total frente a la línea de Betano, probabilidad y cuota
justa en cada línea), figuras y bajas, y factores clave. Las predicciones se guardan y la pestaña
*Modelo* mide su acierto frente a una línea base.

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
| Figuras NBA (3 por equipo, por puntos) | stats.nba.com vía `nba_api` | Gratis |
| Lesiones NBA | API pública de ESPN (sin clave) | Gratis |
| Goleadores y asistidores fútbol | API pública de ESPN (sin clave) | Gratis |

- Betano Chile no está en The Odds API: se usa **Betano (UK)** como aproximación. Stake tampoco
  está; se usa **Pinnacle** como referencia de mercado. Betano UK no ofrece hándicap NBA.
- El botón *Actualizar* solo consulta las ligas cuyas cuotas tienen más de 1 hora y muestra antes
  cuántos créditos gastará (las 6 ligas = 18 créditos). El historial se descarga como mucho una vez
  al día por liga (temporada actual y anterior), igual que los jugadores. Si ESPN o stats.nba.com
  fallan, se muestra un aviso y el resto se actualiza igual.
- ESPN no publica lesiones de fútbol (todos los jugadores figuran como activos), así que en fútbol
  solo se muestran goleadores y asistidores. Los endpoints de ESPN no son oficiales y pueden cambiar.

La clave de The Odds API se lee de la variable de entorno `ODDS_API_KEY`; nunca se guarda en la
base de datos ni en el repositorio. Sin clave, la app muestra las cuotas ya guardadas.

```powershell
$env:ODDS_API_KEY = "tu-clave"; .venv\Scripts\python -m streamlit run app.py
```

### Modelo de predicción

Es estadístico, gratis y reproducible (sin LLM ni claves). Usa la temporada actual y la anterior,
y cada partido pesa según su antigüedad (vida media de 180 días).

- **Fútbol (`poisson-1`)**: fuerzas de ataque y defensa por equipo (Maher). Goles esperados del
  local = media de goles de local en la liga × ataque local × defensa visita (al revés para la
  visita). Con la matriz de marcadores de 0 a 10 goles salen el 1X2, el marcador más probable y la
  probabilidad en cualquier línea de over/under o hándicap, incluidas las asiáticas (.25 y .75).
- **NBA (`nba-ratings-1`)**: ratings ofensivo y defensivo más la ventaja de local del propio
  historial. Margen y total se tratan como normales, con desviaciones estimadas de los residuos
  (12 y 18 puntos por defecto si hay menos de 30 partidos). Un equipo que jugó el día anterior pierde
  1,5 puntos.
- **Encogimiento**: a cada equipo se le suman 3 partidos de un equipo promedio, así que con poca
  muestra (inicio de temporada, ascendidos) las fuerzas tienden a la media de la liga.
- **Factores**: frases generadas por reglas (rachas, localía, descanso, bajas, enfrentamientos
  directos, goles frente a xG y aviso de muestra chica), 6 como máximo. Las lesiones **no cambian
  los números**: se muestran solo como factor.
- **Registro y medición**: la predicción se recalcula mientras el partido no empieza y se congela al
  comenzar. Cuando el historial trae el resultado, la pestaña *Modelo* muestra por liga el acierto
  del resultado más probable, el Brier score (menor es mejor), el error medio de goles o puntos y el
  acierto del over/under en la línea de Betano, comparados con una **línea base** que solo usa las
  tasas históricas de local, empate y visita de la liga.
- **Backtest** (pestaña *Modelo*): predice cada fecha del historial guardado usando solo los
  partidos anteriores. Con la temporada 2025-26 real (2.963 partidos) el modelo acertó el 58,5 %
  frente al 48,7 % de la línea base (Brier 0,525 frente a 0,585) y superó a la base en todas las
  ligas. No mide over/under porque no hay líneas históricas.

Límites: no conoce alineaciones, lesiones de fútbol, traspasos ni motivación; con muestra chica es
poco fiable (se advierte en los factores). Una probabilidad del modelo no es una recomendación de
apuesta.

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
