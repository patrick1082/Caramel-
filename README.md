# Caramel

Predictor de apuestas personal para NBA y fútbol europeo (Premier League, Serie A, Bundesliga, LaLiga, Ligue 1).
Requisitos en [`.claude/prds/predictor-apuestas.prd.md`](.claude/prds/predictor-apuestas.prd.md).

**Hito 1 — Bitácora y fondo**: registro de apuestas colocadas y no colocadas, liquidación,
depósitos/retiros, balances (saldo, ROI, % acierto por deporte y liga) y exportación a Excel.

**Hito 2 — Partidos y cuotas**: pestaña *Partidos* con los partidos del día filtrados por
hora (Chile), deporte y liga; cuotas de ganador, over/under y hándicap de Betano y otras casas, con
la mejor cuota y el promedio; forma reciente de cada equipo y enfrentamientos directos.

**Hito 3 — Predicción**: cada partido muestra la predicción de un modelo estadístico
local (probabilidades, marcador esperado, total frente a la línea de Betano, probabilidad y cuota
justa en cada línea), figuras y bajas, y factores clave. Las predicciones se guardan y la pestaña
*Modelo* mide su acierto frente a una línea base.

**Hito 4 — Contraste y valor** (actual): cada partido muestra lado a lado mi predicción, la del
modelo, ESPN BPI (NBA) y el mercado; la tabla de cuotas marca las apuestas con valor, la pestaña
*Partidos* lista el "Valor del día" y el *Resumen* compara el ROI con y sin valor.

**Apuestas sugeridas**: debajo del "Valor del día", una apuesta por partido por empezar (si existe)
con acierto estimado de 55 % o más, escrita en palabras ("Gana Arsenal", "Más de 2.5 goles",
"Lakers -4.5"). El acierto estimado promedia el modelo y el mercado (Pinnacle sin margen); entre
las que pasan el umbral se elige la de mayor EV. Probable no es lo mismo que rentable: un EV
negativo indica que la cuota paga menos de lo que vale el riesgo.

Cada sugerencia indica qué **% de la banca** apostar y el **monto** con el saldo disponible:

- **Valor confirmado**: ¼ de Kelly, `(p·c − 1)/(c − 1)`, con la probabilidad más prudente (la menor
  entre el modelo y el mercado), entre 1 % y 3 %.
- **Solo modelo**: 0,5 % (esa estrategia perdió dinero en el backtest).
- **Sin valor**: 1 %.
- Nunca más de 3 % en una apuesta, para que una racha mala no se lleve la banca. El monto se
  redondea hacia abajo a $100; si no llega a $100 queda vacío (no apostar). La página muestra
  también cuánto de la banca se arriesga si se apuestan todas.

## Instalación

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

## Uso

Es una aplicación de escritorio (Qt, tema oscuro):

```bash
.venv/Scripts/caramel            # o: .venv/Scripts/python -m predictor.escritorio
```

La barra lateral lleva a cada página (Partidos, Modelo, Resumen, Nueva apuesta, Pendientes,
Historial, Movimientos, Configuración), muestra el saldo y exporta la bitácora a Excel. Las
descargas (*Actualizar*, backtest) corren en segundo plano sin congelar la ventana.

Los datos se guardan en `data/bitacora.db` (SQLite). Para usar otra ubicación —recomendado si la
carpeta del proyecto está en OneDrive— define la variable `PREDICTOR_DB`:

```powershell
$env:PREDICTOR_DB = "E:\datos\bitacora.db"; .venv\Scripts\predictor
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
| Probabilidad de victoria NBA (BPI) | API pública de ESPN (sin clave) | Gratis (1 + 1 consulta por partido) |

- Betano Chile no está en The Odds API: se usa **Betano (UK)** como aproximación. Stake tampoco
  está; se usa **Pinnacle** como referencia de mercado. Betano UK no ofrece hándicap NBA.
- El botón *Actualizar* solo consulta las ligas cuyas cuotas tienen más de 1 hora y muestra antes
  cuántos créditos gastará (las 6 ligas = 18 créditos). El historial se descarga como mucho una vez
  al día por liga (temporada actual y anterior), igual que los jugadores. Si ESPN o stats.nba.com
  fallan, se muestra un aviso y el resto se actualiza igual.
- ESPN no publica lesiones de fútbol (todos los jugadores figuran como activos), así que en fútbol
  solo se muestran goleadores y asistidores. Los endpoints de ESPN no son oficiales y pueden cambiar.

La clave de The Odds API se lee de la variable de entorno `ODDS_API_KEY`; nunca se guarda en la
base de datos ni en el repositorio. **Sin clave no aparece ningún partido**: la cartelera viene solo
de esa API, y el botón Actualizar descarga únicamente el historial, los jugadores y el ESPN BPI.
Para dejarla guardada en tu usuario de Windows (una vez; luego abre la app de nuevo):

```powershell
setx ODDS_API_KEY "tu-clave"
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

### Contraste y apuestas de valor

- **Opiniones del 1X2**: la mía (ganador, marcador opcional y nota, se ingresa en el partido), la
  del modelo, **ESPN BPI** (solo NBA; los 50/50 exactos se tratan como "sin calcular") y **el
  mercado**: las cuotas de Pinnacle (o el promedio de casas) sin margen, `(1/c) / Σ(1/c)`. En fútbol
  no hay un pronóstico web gratis y legal: el predictor de ESPN no cubre fútbol, la API de ClubElo
  está desactivada y el scraping de webs de pronósticos va contra sus términos.
- Todas se guardan y se congelan al inicio del partido. La pestaña *Modelo* compara su acierto
  ("Por opinión"); la mía no tiene Brier porque solo elige ganador.
- **Valor**: EV = probabilidad del modelo × cuota de Betano − 1.
  - **Solo modelo**: EV ≥ 5 % y cuota ≤ 5,00.
  - **Confirmado**: además, el EV con la probabilidad del mercado es ≥ 0 %, es decir, la cuota de
    Betano no es peor que el precio justo del mercado.
  - Los tres umbrales se cambian en *Configuración*.
- **Bitácora**: una apuesta registrada desde la cartelera (*Nueva apuesta → Desde la cartelera*)
  guarda la probabilidad del modelo y la marca de valor, recalculada con la cuota que escribes (la de
  Betano Chile). El *Resumen* y el Excel muestran el ROI por marca, incluidas las no colocadas.
- **Backtest de valor** (pestaña *Modelo*, fútbol): con el historial 2024-25 + 2025-26 y 1 unidad
  a la cuota promedio previa, la estrategia "solo modelo" hizo 840 apuestas con 28,8 % de acierto y
  **ROI −15,9 %**, frente a −2,9 % de apostar siempre al favorito. Solo la Premier League quedó en
  positivo (+3,6 %). El mercado sin margen acierta más que el modelo (53,3 % frente a 51,4 %, Brier
  0,582 frente a 0,599), así que el valor "solo del modelo" es casi siempre desacuerdo con un mercado
  que sabe más. Es una aproximación: no usa la cuota de Betano ni la confirmación del mercado.

**El valor no es una garantía.** Es una estimación del modelo con cuotas de Betano UK; la prueba
real es el ROI de la bitácora tras 100 apuestas o 3 meses.

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
