# Predictor de Apuestas (NBA + Fútbol Europeo)

## Problem
Tomas apuesta en Betano basándose en sus propias predicciones, pero no tiene una forma sistemática de contrastarlas con datos, con pronósticos de terceros ni con las cuotas de otros proveedores. Sin ese contraste no puede distinguir qué apuestas tienen valor real y cuáles no, ni medir si su criterio gana o pierde dinero en el tiempo. El costo de no resolverlo es apostar a ciegas sobre un fondo inicial de 10.000 que se pretende hacer crecer.

## Evidence
- Assumption — needs validation via registro histórico de apuestas (la bitácora del propio MVP generará esta evidencia).
- No existen intentos previos (Excel, apps, tipsters) con los que comparar.
- Necesidad declarada por el usuario: contrastar predicciones propias contra una base de datos y pronósticos web antes de decidir cada apuesta.

## Users
- **Primary**: Tomas, apostador individual en Betano, que antes de cada jornada de NBA o de ligas europeas quiere revisar los partidos próximos y decidir qué apuestas colocar.
- **Not for**: terceros, suscriptores ni clientes (uso personal únicamente); usuarios que buscan apuestas automáticas.

## Hypothesis
We believe **contrastar mis predicciones con un modelo propio y con pronósticos web, detectando valor en las cuotas** will **mejorar la selección de apuestas** for **mí, apostando en NBA y fútbol europeo**.
We'll know we're right when **el ROI de las apuestas filtradas por la app supera al de las no filtradas durante 3 meses o 100 apuestas**.

## Success Metrics
| Metric | Target | How measured |
|---|---|---|
| ROI apuestas recomendadas vs. no recomendadas | ROI recomendadas > ROI no recomendadas | Bitácora, tras 3 meses o 100 apuestas |
| Balance del fondo | > 10.000 iniciales al cierre del período | Balance total de la bitácora |
| Precisión del modelo vs. predicción propia | TBD — needs validation via primer mes de uso | Comparación de aciertos registrados en bitácora |
| Disciplina de stake | 100% de apuestas registradas con % de billetera sugerido | Bitácora |

## Scope
**MVP**
- Cobertura: **NBA** y fútbol de **Premier League, Serie A, Bundesliga, LaLiga y Ligue 1**.
- Consulta bajo demanda de partidos próximos.
- Predicción por partido con detalle aproximado: puntos/goles a favor y en contra, jugadores relevantes y factores que afectan el pronóstico (lesiones, forma, etc.).
- Ingreso de la predicción propia del usuario y comparación contra la predicción de la IA y pronósticos web.
- Detección de valor: comparar cuotas de **Betano** (casa base) con **Stake** u otros proveedores confiables para identificar errores de cuota.
- Sugerencia de **% de la billetera** a apostar por cada apuesta, sobre un fondo inicial de 10.000.
- **Bitácora** de apuestas con balances totales, **exportable a Excel**.

**Out of scope**
- Colocar apuestas automáticamente — el usuario apuesta manualmente en Betano.
- Otros deportes y ligas — se evaluarán tras validar la hipótesis.
- Uso multiusuario o comercialización — producto personal.
- Apuestas en vivo, alertas móviles — TBD — needs validation con el usuario (no confirmado).

## Delivery Milestones
<!-- Business outcomes, not engineering tasks. /plan turns each into a plan. -->
<!-- Status: pending | in-progress | complete -->

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | Bitácora y fondo | El usuario registra apuestas, ve balances totales y exporta a Excel | complete | `.claude/plans/bitacora-y-fondo.plan.md` |
| 2 | Partidos y cuotas | El usuario consulta partidos próximos (NBA + 5 ligas) con cuotas de Betano y proveedores de comparación | pending | — |
| 3 | Predicción IA | Cada partido muestra predicción con puntos/goles, jugadores y factores clave | pending | — |
| 4 | Contraste y valor | El usuario ve su predicción vs. IA vs. pronósticos web, con apuestas de valor marcadas | pending | — |
| 5 | Gestión de stake | La app sugiere % de billetera por apuesta y lo registra en la bitácora | pending | — |

## Open Questions
- [x] Formato de la app: app web local en Python + Streamlit.
- [ ] Fuentes de datos de partidos, estadísticas y lesiones: ¿gratuitas o de pago? ¿Presupuesto mensual?
- [ ] Acceso a cuotas de Betano y Stake: ¿existe un medio permitido por sus términos de servicio?
- [ ] ¿Qué webs de pronósticos se usarán para el contraste?
- [x] Moneda del fondo de 10.000: CLP.
- [ ] Criterio para sugerir % de billetera (conservador vs. agresivo) y límites máximos por apuesta/día.
- [ ] Mercados a cubrir: ganador, hándicap, over/under, props de jugadores.
- [ ] Umbral para considerar una cuota "con valor".

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Términos de servicio de Betano/Stake prohíben extracción automática de cuotas | Alta | Alta | Validar ToS; preferir proveedores de cuotas con API oficial |
| Stake no disponible o restringido en el país del usuario | Media | Media | Definir proveedores de comparación alternativos |
| Datos de lesiones/alineaciones desactualizados distorsionan predicciones | Media | Alta | Mostrar fecha de actualización de cada dato |
| Muestra pequeña (100 apuestas) no permite concluir si el modelo tiene ventaja | Alta | Media | Registrar también apuestas no tomadas para comparar |
| Pérdida del fondo por sobreconfianza en el modelo | Media | Alta | Límites máximos de stake y stop-loss configurables |
| Costo de APIs de datos supera la ganancia esperada | Media | Media | Fijar presupuesto mensual antes de elegir fuentes |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*
