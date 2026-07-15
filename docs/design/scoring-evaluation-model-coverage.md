# Cobertura del modelo de scoring y evaluación

Este documento contrasta el diseño de `TFM - Plataforma de Gobernanza para Agentes de Voz/3.4 Modelo de scoring y evaluación.md` con el backend actual. La infraestructura principal de evaluación está implementada y, tras el cambio `scoring-wire-evidences`, el catálogo de scoring ya **consume las evidencias M-C01–M-R04 calculables** mediante una tabla declarativa `METRIC_SPECS`; por tanto, las evidencias documentadas en [evidence-coverage-by-quality-dimension.md](./evidence-coverage-by-quality-dimension.md) **ya mueven las puntuaciones** de su dimensión y la nota global.

## Leyenda de estado

- **Implementado** — el comportamiento del apartado 3.4 existe de extremo a extremo.
- **Parcial** — existe la estructura o una variante funcional, pero no cumple todavía todo el diseño.
- **Pendiente** — no existe implementación equivalente.
- **Bloqueado** — depende de evidencias o eventos que aún no están disponibles con la semántica requerida.

## Resumen ejecutivo

| Área del diseño 3.4 | Estado | Cobertura actual / brecha principal |
|---|---|---|
| Normalización 0–100 | **Implementado** | Existen funciones puras para porcentajes directos e inversos, binarios, ocurrencias y latencias por tramos, con saturación en `[0, 100]`. |
| Puntuación por dimensión | **Implementado** | Media ponderada de las métricas presentes; las dimensiones vacías se excluyen en vez de recibir un cero. |
| Score global | **Implementado** | Media ponderada con pesos 3/3/2/4 y umbral de aprobado en 75. |
| Catálogo de métricas en alcance | **Implementado (calculables)** | `build_metrics()` itera `METRIC_SPECS` y cablea 9 métricas con evidencia disponible (M-C01/02/03, M-T01/02/03/04, M-R01/02/04). Las métricas relacionadas con herramientas están fuera de alcance; quedan pendientes M-C04 y M-C05. |
| Pesos configurables por agente | **Pendiente** | Los pesos de métricas y dimensiones están fijados en código; el agente no contiene configuración de scoring. La tabla `METRIC_SPECS` es el precursor natural de esa configuración. |
| Flags bloqueantes | **Implementado en alcance** | Se bloquea por `session_failed`, ausencia de `session_completed`, objetivo no completado (M-C03) y error técnico no recuperado (M-R02). |
| Informe persistido | **Parcial** | Se persisten scores, resultado, flags y snapshot de métricas; faltan cabecera ampliada, incidencias, oportunidades y desviaciones de umbral. |
| API del informe | **Parcial** | Expone score global, scores dimensionales, resultado y flags, pero no el detalle de métricas ni sus evidencias. |
| Trazabilidad hasta `event_id` | **Parcial** | Las evidencias conservan `source_events`, pero `Metric` no referencia evidencias ni eventos; la cadena completa no se puede recorrer desde el informe. |
| Ejecución automática e idempotente | **Implementado** | La tarea construye evidencias, evalúa y reemplaza el informe único de la sesión dentro del mismo flujo transaccional. |

## Cobertura de normalización y agregación

| Regla del diseño | Estado | Evidencia actual del backend / brecha |
|---|---|---|
| Porcentaje directo: `score = valor` | **Implementado** | `percentage_direct()` en `backend/src/domain/scoring/normalisation.py`, con saturación a 0–100. El catálogo la usa en M-C01 (con reescala `×100` previa). |
| Porcentaje inverso: `score = 100 − valor` | **Implementado** | `percentage_inverse()` implementa la fórmula y la saturación. El catálogo la usa en M-C02, M-T03 y M-R04 (con reescala `×100` previa). |
| Latencia lineal entre umbral óptimo y degradado | **Implementado** | `latency()` devuelve 100/0 en los extremos y redondea la interpolación intermedia. El catálogo la aplica a M-T01 (1,5/3,0 s), M-T02 (3,0/5,0 s) y a la métrica legacy `duration` (300/900 s). |
| Binaria: `valor × 100` | **Implementado** | `binary()` normaliza cualquier valor truthy a 100 y falsy a 0; se usa en M-C03, M-R02 y en la métrica legacy `engagement`. |
| Ocurrencias con penalización | **Implementado** | `occurrences()` resta `count × penalty` y satura a 0. El catálogo la consume en M-R01 con `penalty=33`. |
| Media ponderada por dimensión | **Implementado** | `dimension_score()` calcula `Σ(score × peso) / Σ(peso)`. El evaluador agrupa métricas por `Dimension`. |
| Media ponderada global | **Implementado** | `global_score()` usa pesos Conversational=3, Operational=3, Technical=2 y Risk=4. Solo pondera dimensiones presentes. |
| Tres niveles métrica → dimensión → global | **Implementado** | `Metric`, `_score_by_dimension()` y `global_score()` materializan los tres niveles. |
| Pesos configurables por agente | **Pendiente** | Los pesos dimensionales son una constante global y los pesos métricos se instancian en `build_metrics()`; no hay configuración por `agent_id`. |

### Diferencia semántica importante

Excluir una dimensión sin métricas evita penalizar datos no disponibles y está documentado en el dominio. Sin embargo, también permite que el score global se calcule sobre una cobertura parcial. El informe no expone hoy un indicador de completitud del catálogo, por lo que un score alto no demuestra que las cuatro dimensiones del diseño hayan sido evaluadas.

## Cobertura del catálogo de métricas

`build_metrics()` itera la tabla declarativa `METRIC_SPECS` (`backend/src/domain/scoring/metric_spec.py`): cada fila mapea un `criterion` de evidencia a un `Metric` vía `transform` (conversión de unidad) y luego `normalize` (saturado 0–100). Las métricas cuya evidencia fuente falta se omiten (R10). Métricas cableadas del doc 3.4:

| Métrica | Código | Dimensión | Fuente (`criterion`) | Transform → normalización | Peso |
|---|---|---|---|---|---:|
| Tasa de finalización de turnos | M-C01 | Conversational | `turn_completion_rate` | `×100` → directa | 2 |
| Tasa de silencios prolongados | M-C02 | Conversational | `prolonged_silence_rate` | `×100` → inversa | 1 |
| Cumplimiento del objetivo | M-C03 | Conversational | `goal_completion` | identidad → binaria | 4 |
| Latencia media de respuesta | M-T01 | Technical | `mean_turn_latency_seconds` | identidad → latencia 1,5/3,0 s | 3 |
| Latencia máxima de respuesta | M-T02 | Technical | `max_turn_latency_seconds` | identidad → latencia 3,0/5,0 s | 2 |
| Tasa de errores técnicos | M-T03 | Technical | `technical_error_rate` | `×100` → inversa | 3 |
| Nº de invocaciones al modelo | M-T04 | Technical | `model_invocation_count` | identidad → informativa | 0 |
| Nº de flags de gobernanza | M-R01 | Risk | `governance_flag_count` | identidad → ocurrencias (penalty 33) | 3 |
| Error no recuperado | M-R02 | Risk | `unrecovered_error_present` | identidad → binaria | 3 |
| Tasa de advertencias del sistema | M-R04 | Risk | `system_warning_rate` | `×100` → inversa | 1 |

Además se conservan dos métricas legacy tratadas inline: `engagement` (Conversational, binaria, peso 3, de `agent_turns`/`user_turns` > 0) y `duration` (Technical, latencia 300/900 s, peso 1, de `session_duration_seconds`). Las métricas MVP `completion` y `clean_ending` se **retiraron** por duplicar señal ya cubierta por M-T03/M-R01–M-R04.

Notas de diseño relevantes: las cuatro métricas-tasa aplican `×100` antes de normalizar porque las evidencias son ratios en `[0,1]`; M-T04 queda con **peso 0** (informativa: aparece en el informe pero no entra en la media ponderada, al no existir umbral de referencia en el doc 3.3). La cobertura de cada métrica fuente está detallada en [evidence-coverage-by-quality-dimension.md](./evidence-coverage-by-quality-dimension.md).

## Cobertura de flags bloqueantes

| Condición del diseño 3.4.5 | Estado | Implementación actual / brecha |
|---|---|---|
| Objetivo no completado (M-C03) | **Implementado** | `detect_blocking_flags` activa `FLAG_GOAL_NOT_COMPLETED` cuando la evidencia `goal_completion` tiene valor por debajo de `0,5`. Dispara de forma independiente. |
| Error técnico no recuperado (M-R02) | **Implementado** | `detect_blocking_flags` activa `FLAG_UNRECOVERED_ERROR` cuando la evidencia `unrecovered_error_present` tiene valor a partir de `0,5`. Dispara de forma independiente y puede coexistir con `FLAG_SESSION_FAILED`. |
| Sesión finalizada con error | **Implementado** | La evidencia `session_failed` activa `FLAG_SESSION_FAILED`. Es mutuamente excluyente con el flag de sesión no completada. |
| Ausencia de finalización correcta | **Implementado adicional** | La ausencia de `session_completed` activa `FLAG_SESSION_NOT_COMPLETED`; esta condición amplía el diseño 3.4.5. |
| El flag fuerza resultado negativo | **Implementado** | `_result()` devuelve `failed` si existe cualquier flag, independientemente del score. |
| Referencia a eventos causales en el flag | **Pendiente** | `BlockingFlag` solo contiene `code` y `reason`; no conserva `event_id` ni identificadores de evidencias. |

## Cobertura del informe de evaluación

| Contenido requerido por 3.4.6 | Persistido | Expuesto por API | Estado / brecha |
|---|---:|---:|---|
| Identificadores de informe y sesión, fecha de generación | Sí | Sí | **Implementado.** `EvaluationReport` incluye `report_id`, `session_id` y `generated_at`. |
| Identificador de agente, fecha y duración | Parcial | No | La sesión y las evidencias contienen esos datos, pero el informe no los incorpora. |
| Conteos de turnos y eventos | No | No | **Pendiente.** No forman parte de `EvaluationReport`. |
| Score global | Sí | Sí | **Implementado.** |
| Puntuaciones por dimensión | Sí | Sí | **Implementado.** Son `None` cuando la dimensión no tiene métricas. |
| Estado `superada` / `no superada` | Sí | Sí | **Implementado con contrato inglés.** Los valores persistidos/API son `passed` y `failed`. |
| Flags bloqueantes | Sí | Sí | **Parcial.** Incluye código y razón, sin eventos causales. |
| Valor, score normalizado y peso de cada métrica | Sí | No | El snapshot JSONB persiste `Metric`; `ReportOut` no expone la lista. |
| Evidencias asociadas y desviación de umbrales | No | No | **Pendiente.** `Metric` no enlaza con `evidence_id` y no guarda umbrales de referencia. |
| Incidencias detectadas y contexto | No | No | **Pendiente.** Los eventos pueden consultarse por separado, pero el informe no compone esta sección. |
| Oportunidades de mejora y patrones recurrentes | No | No | **Pendiente.** No existe análisis ni representación de recomendaciones. |

El modelo SQL garantiza un único informe por sesión y guarda `blocking_flags` y `metrics` como JSONB. `add_report()` reemplaza el informe anterior, lo que hace repetible la evaluación, aunque cambia `report_id` y `generated_at` en cada ejecución.

## Cobertura de trazabilidad

La cadena disponible actualmente es:

```text
score_global
  └── score_dimensión
        └── Metric (valor, score normalizado, peso)

Evidence (criterio, valor)
  └── source_events (event_id[])
```

La brecha está entre `Metric` y `Evidence`: el catálogo localiza evidencias por `criterion`, pero el objeto métrica no conserva `evidence_id`, el criterio fuente ni sus `source_events`. Además, la API del informe omite el snapshot de métricas. Por ello, la trazabilidad hasta `event_id` existe en los datos de evidencia, pero no como navegación completa desde el score global.

## Flujo de evaluación actual

`build_session_evidences_async()` ejecuta el flujo siguiente:

1. Registra de forma idempotente `session.evaluation_triggered`.
2. Construye y persiste las evidencias disponibles.
3. Ejecuta `DeterministicEvaluator` y reemplaza el informe de la sesión.
4. Confirma evidencias e informe en la misma transacción.
5. Registra después observaciones de latencia y flags de evaluación.
6. Deriva después contenido, silencios y señales conversacionales post-terminales.

El orden de los pasos 5 y 6 implica una limitación adicional: las señales conversacionales derivadas durante esa ejecución no forman parte de las evidencias ni del informe calculados en el paso 2. Para incorporarlas se necesita una evaluación posterior o reordenar el pipeline, manteniendo idempotencia y consistencia transaccional.

## Siguiente paso

El cableado del catálogo en alcance y los flags de M-C03/M-R02 **ya están implementados**, con tests de normalización, pesos, reescala `×100`, exclusión de métricas ausentes y de peso 0, y prueba de que una evidencia nueva mueve la nota global. Pendiente, en este orden:

1. definir pesos y umbrales configurables por agente (la tabla `METRIC_SPECS` es su precursor);
2. revisar los umbrales inventados por falta de referencia en el doc 3.3: par óptimo/degradado de M-T02 (3,0/5,0 s) y el tratamiento informativo (peso 0) de M-T04;
3. cerrar el enlace `Metric → Evidence → event_id` y exponerlo en el informe;
4. ampliar el informe con incidencias, cobertura evaluada y oportunidades de mejora;
5. corregir el orden del pipeline para que las señales post-terminales participen en la primera evaluación útil.
