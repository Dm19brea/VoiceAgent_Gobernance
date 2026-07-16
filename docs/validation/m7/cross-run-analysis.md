# M7.4 — Análisis cross-run de la validación M7

Análisis agregado de las tres ejecuciones M7.3 registradas en `results/`. Este documento no altera el contrato por ejecución de M7.2: consume los registros ya validados y extrae conclusiones transversales.

## Entradas

Nueve artefactos commiteados en `docs/validation/m7/results/` (registro de resultado, informe de evaluación y traza de eventos por escenario), generados contra el entorno `local` en la revisión `main-815cf0f` el 2026-07-16. Los tres registros validan contra `templates/validation-result.schema.json` con un validador Draft 2020-12 con format assertion habilitada, según exige el protocolo.

## Resumen de ejecuciones

| Escenario | Run | Sesión | Duración llamada | Veredicto | Score global |
|---|---|---|---|---|---|
| Confirmación | `local-run-001` | `019f6bd3…62d1` | 83,9 s | **PASS** | 87,90 |
| Reprogramación | `local-run-002` | `019f6bda…5447` | 84,4 s | **PASS** | 87,65 |
| Cancelación | `local-run-003` | `019f6bdd…beb2` | 72,7 s | **PASS** | 99,48 |

Resultado agregado: **3/3 PASS**, sin blocking flags en ningún informe, todas por encima del umbral de aprobación (75,0). Los tres resultados observados coinciden con la aserción PASS de su escenario: la cita se confirmó sin cambios, se movió al slot previsto sin reservas colaterales y se canceló sin crear reemplazo.

## Comportamiento por dimensión

| Dimensión | Confirmación | Reprogramación | Cancelación | Lectura cross-run |
|---|---|---|---|---|
| Conversational | 100,0 | 100,0 | 100,0 | Estable: máxima en las tres |
| Risk | 100,0 | 100,0 | 100,0 | Estable: sin amenazas ni flags |
| Technical | 45,56 | 44,44 | 97,67 | **Alta varianza** (ver abajo) |
| Operational | — | — | — | Sin métricas en las tres (excluida del scoring) |

### La varianza técnica la explica la latencia por turno

| Escenario | Turnos | Latencia media | Latencia máxima | Score technical |
|---|---|---|---|---|
| Cancelación | 5 | 1,60 s | 2,04 s | 97,67 |
| Confirmación | 5 | 3,14 s | 4,91 s | 45,56 |
| Reprogramación | 6 | 3,42 s | 12,36 s | 44,44 |

La correlación es directa: la única fuente de dispersión entre ejecuciones es la latencia de respuesta por turno. Es un resultado esperable del montaje: las llamadas atravesaron un túnel efímero hacia un entorno de desarrollo local, por lo que la dimensión técnica mide en gran parte las condiciones del entorno y no una propiedad estable del agente. La punta de 12,4 s de la reprogramación es el peor caso observado.

### La dimensión operational no puntuó en ninguna ejecución

Ninguna de las tres sesiones generó métricas operacionales, así que la dimensión quedó excluida del score global por diseño (una dimensión sin métricas no puntúa cero: se excluye). Cross-run, esto significa que el score global de M7 se sostiene sobre tres dimensiones, no cuatro. Queda como observación para el catálogo de métricas: las llamadas de gestión de citas no ejercitan ninguna métrica operacional.

## Conclusiones

1. **La gobernanza queda validada extremo a extremo en las tres operaciones**: ingesta de webhooks, correlación de sesión, traza de eventos canónicos, construcción de evidencias, juez LLM e informe reproducible, con referencias cruzadas verificables en cada registro.
2. **El veredicto PASS es robusto entre escenarios** (margen mínimo de +12,65 sobre el umbral), y la variación entre ejecuciones proviene de una única causa medible (latencia), no del comportamiento conversacional ni de riesgo.
3. **El protocolo M7.2 resultó operable tal cual**: los tres registros se produjeron y validaron por la vía obligatoria (format assertion calendar-aware) sin necesitar cambios de plantilla ni de schema.

## Limitaciones

- Una sola ejecución por escenario: sin base estadística para variabilidad intra-escenario.
- Entorno local con túnel efímero: las latencias técnicas no son representativas de un despliegue estable (Railway).
- Las tres ejecuciones fueron PASS: la ruta de `FAIL` y los códigos de diagnóstico del protocolo no quedaron ejercitados por ninguna ejecución real.
- La dimensión operational no quedó cubierta por este tipo de llamadas.
