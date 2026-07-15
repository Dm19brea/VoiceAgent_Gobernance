# Cobertura de evidencias por dimensión de calidad

Este documento registra qué evidencias se necesitan para calcular cada dimensión de calidad de `TFM - Plataforma de Gobernanza para Agentes de Voz/3.3 Dimensiones de calidad y métricas.md`, y si el backend las calcula actualmente.

## Leyenda de disponibilidad (Readiness)

La columna **Readiness** responde a "¿se puede construir ahora mismo?", con independencia de si la evidencia ya se calcula:

- **Ready now** — todos los eventos fuente requeridos ya se persisten; solo falta el cálculo en `build_evidences()`.
- **Ready (caveat)** — construible ahora, pero el evento fuente disponible no coincide del todo con la semántica prevista de la métrica (se documenta en cada fila).
- **Needs redefinition** — la métrica se diseñó en torno a `conversation.turn_started` / `conversation.turn_ended`, que ahora son **live-only y nunca se persisten**. El conteo (numerador) puede ser construible, pero la tasa/denominador debe re-basarse (por ejemplo, `agent_turns` / `total_turns` derivados de los eventos de contenido).
- **Blocked** — falta emitir uno o más eventos fuente requeridos; primero hace falta instrumentar esos eventos.

## Cobertura actual de evidencias

| Dimensión | Métrica / criterio del doc 3.3 | Evidencias / eventos fuente requeridos | ¿Se calcula ahora? | Readiness | Evidencia actual del backend / brecha |
|---|---|---|---:|---|---|
| Conversational | M-C01 — Tasa de finalización de turnos | `conversation.interruption_detected` (+ turnos de contenido) | **Sí** | Implementado | **Implementado (PR #28).** `criterion="turn_completion_rate"` = `(agent_turns − interrupciones) / agent_turns` en `build_evidences`; denominador derivado de contenido, no de `turn_*`. Guarda de denominador 0. |
| Conversational | M-C02 — Tasa de silencios prolongados | `conversation.silence_detected` | **Sí** | Implementado | **Implementado (PR #28).** `criterion="prolonged_silence_rate"` = `silence_detected.count / total_turns`. |
| Conversational | M-C03 — Cumplimiento del objetivo de conversación | `conversation.goal_achieved`, `conversation.goal_failed` | **Sí** | Implementado | **Implementado (PR #28).** `criterion="goal_completion"` = `1.0` si hay `goal_achieved`, si no `0.0`. |
| Conversational | M-C04 — Tasa de subobjetivos completados | `conversation.topic_change`, `conversation.goal_achieved`, `conversation.goal_failed` | No | Aplazado | Aplazado por decisión de producto: el evento solo aporta `count` de cambios de tema (detectados), no resolución por subobjetivo. No falta evento, falta señal de resolución. |
| Conversational | M-C05 — Cambios de tema iniciados por el agente | `conversation.topic_change` con `source=agent` | No | Blocked | `topic_change` se emite, pero su payload solo lleva `count`/`topics`/`reason` — **no incluye atribución `source=agent`** por cambio. El judge debe exponer la atribución de fuente antes de que esta métrica sea posible. |
| Conversational | Evidencia MVP existente — turnos totales | `conversation.agent_response`, `conversation.user_input` | Sí | — | `total_turns` se calcula como evidencia inferida. |
| Conversational | Evidencia MVP existente — turnos del agente | `conversation.agent_response` | Sí | — | `agent_turns` se calcula como evidencia inferida. |
| Conversational | Evidencia MVP existente — turnos del usuario | `conversation.user_input` | Sí | — | `user_turns` se calcula como evidencia inferida. |
| Operational | Evidencia MVP existente — motivo de finalización | payload de `session.ended` `report.ended_reason` | Sí | — | `ended_reason` se calcula como evidencia directa. Da soporte a la interpretación operativa, pero no es una de las métricas operativas del doc 3.3. |
| Technical | M-T01 — Latencia media de respuesta | `end-of-call-report.artifact.performanceMetrics.turnLatencies[].turnLatency` | **Sí** | Implementado | `criterion="mean_turn_latency_seconds"`: media exacta de latencias Vapi válidas, en segundos, trazada al evento terminal. |
| Technical | M-T02 — Latencia máxima de respuesta | `end-of-call-report.artifact.performanceMetrics.turnLatencies[].turnLatency` | **Sí** | Implementado | `criterion="max_turn_latency_seconds"`: máximo real sin recorte, en segundos, trazado al evento terminal. |
| Technical | M-T03 — Tasa de errores técnicos | `system.error` | **Sí** | Implementado | **Implementado (PR #29).** `criterion="technical_error_rate"` = `count(system.error) / total_turns` (turnos de contenido, no `turn_*`). Guarda de denominador 0. |
| Technical | M-T04 — Número de invocaciones al modelo | `system.model_invocation` | **Sí** | Implementado | **Implementado (PR #29).** `criterion="model_invocation_count"` = conteo de `system.model_invocation`. Helpers `_turns`/`_rate` ya aceptan `dimension`. |
| Technical | Evidencia MVP existente — duración de sesión | `session.started`, `session.ended`, timestamps de sesión | Sí | — | `session_duration_seconds` se calcula como evidencia inferida. |
| Technical | Evidencia MVP existente — sesión completada | `session.ended` | Sí | — | `session_completed` se calcula como evidencia directa. Una traza `session.failed` produce ahora una evidencia `session_failed` distinta. |
| Risk | M-R01 — Número de flags de gobernanza | `system.flag_raised` | **Sí** | Implementado | **Implementado (PR #30).** `criterion="governance_flag_count"` = conteo de `system.flag_raised`, vía `_turns(..., dimension=Dimension.RISK)`. |
| Risk | M-R02 — Errores técnicos no recuperados | `system.error`, `session.failed` | **Sí** | Implementado | **Implementado (PR #30).** `criterion="unrecovered_error_present"` = binaria `1.0` si hay `system.error` **y** terminal `session.failed`, si no `0.0`. |
| Risk | M-R04 — Tasa de advertencias del sistema | `system.warning`, turnos de contenido | **Sí** | Implementado | **Implementado.** `criterion="system_warning_rate"` = `count(system.warning) / total_turns`; usa turnos de contenido, guarda de denominador 0, no satura valores superiores a `1.0` y traza solo los eventos `system.warning`. |

## Qué calcula el backend hoy

`backend/src/domain/evidence_builder.py` calcula actualmente solo estas evidencias:

| Criterio de evidencia | Dimensión | Tipo | Fuente |
|---|---|---|---|
| `total_turns` | Conversational | inferida | `conversation.agent_response`, `conversation.user_input` |
| `agent_turns` | Conversational | inferida | `conversation.agent_response` |
| `user_turns` | Conversational | inferida | `conversation.user_input` |
| `goal_completion` (M-C03) | Conversational | inferida | `conversation.goal_achieved` / `goal_failed` — **PR #28** |
| `turn_completion_rate` (M-C01) | Conversational | inferida | `conversation.interruption_detected` / `agent_turns` — **PR #28** |
| `prolonged_silence_rate` (M-C02) | Conversational | inferida | `conversation.silence_detected.count` / `total_turns` — **PR #28** |
| `model_invocation_count` (M-T04) | Technical | inferida | conteo de `system.model_invocation` — **PR #29** |
| `technical_error_rate` (M-T03) | Technical | inferida | `system.error` / `total_turns` — **PR #29** |
| `session_duration_seconds` | Technical | inferida | timestamps de sesión más referencias a `session.started` / `session.ended` |
| `session_completed` | Technical | directa | `session.ended` (terminación limpia) |
| `session_failed` | Technical | directa | `session.failed` (terminación por error no controlado; mutuamente excluyente con `session_completed`) |
| `governance_flag_count` (M-R01) | Risk | inferida | conteo de `system.flag_raised` — **PR #30** |
| `unrecovered_error_present` (M-R02) | Risk | inferida | `system.error` + `session.failed` (binaria 1/0) — **PR #30** |
| `system_warning_rate` (M-R04) | Risk | inferida | `system.warning` / `total_turns` |
| `ended_reason` | Operational | directa | evento terminal `payload.report.ended_reason` (`session.ended` o `session.failed`) |

## Resumen del estado de implementación

**Implementado (PR #28)** — dimensión Conversational: `M-C01` (`turn_completion_rate`), `M-C02` (`prolonged_silence_rate`), `M-C03` (`goal_completion`).

**Implementado (PR #29)** — dimensión Technical: `M-T04` (`model_invocation_count`), `M-T03` (`technical_error_rate`). Incluyó el refactor de los helpers `_turns`/`_rate` para aceptar `dimension`.

**Implementado (PR #30)** — dimensión Risk: `M-R01` (`governance_flag_count`), `M-R02` (`unrecovered_error_present`).

**Implementado** — `M-R04` (`system_warning_rate`) usa `system.warning / total_turns`, con turnos de contenido y valores superiores a `1.0` cuando corresponda.

**Implementado**: `M-T01` / `M-T02` usan las latencias reales por turno del `end-of-call-report` de Vapi; los valores ausentes o inválidos no generan evidencias.

**Aplazado / Blocked**: `M-C04` (aplazado — sin señal de resolución por subobjetivo) y `M-C05` (falta atribución `source=agent`).

## Siguiente paso

Conversational (PR #28), Technical (PR #29) y Risk (PR #30, M-R04) ya tienen cubiertas sus métricas viables. No queda ningún slice de evidencias **Ready-now** pendiente.

1. **Latencia** — M-T01/M-T02 implementadas desde `performanceMetrics.turnLatencies`; mantener validado el contrato proveedor.
2. **Aplazadas / bloqueadas** — `M-C04` (aplazada: sin señal de resolución por subobjetivo) y `M-C05` (falta `source=agent`). Requieren nuevas señales conversacionales.

Nota transversal: las evidencias con métrica en alcance ya están cableadas al catálogo de scoring (`build_metrics`). Las evidencias auxiliares sin especificación de métrica siguen sin afectar a la nota.
