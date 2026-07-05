# M4 — Evaluation & scoring (SDD)

Change name: `m4-evaluation-scoring` · Store: engram · Mode: interactive

## 1. Proposal

### Intent
Turn a session's evidences into an objective evaluation: normalise metrics to 0–100, aggregate
into per-dimension scores and a global score, detect blocking flags, and produce a persisted
`EvaluationReport` (docs 3.3, 3.4). This is the thesis's evaluable core — deterministic and
reproducible.

### Confirmed design decisions
1. **Deterministic scoring behind a port.** Implement the doc 3.4 model (normalise → weighted
   aggregation → global score → blocking flags) as the core, hidden behind a hexagonal
   `EvaluationPort`. An LLM-as-judge can plug in later as a second evaluator **without touching the
   domain**. Reproducible today, extensible tomorrow.
2. **General engine, evidence-available metrics.** Build the full scoring engine (normalisation,
   aggregation, global score, flags, report) as a general, extensible piece, but feed it only the
   metrics computable from the current evidences. More metrics plug in as more evidence types are
   captured — no fake metrics.

### Metrics available now (from the 6 M3 evidences)
The doc 3.3 catalogue (17 metrics) mostly needs data we do not yet capture (tool.*, latency,
silences, interruptions, errors). M4 defines a **pragmatic metric set** derived from our real
evidences, organised into the four dimensions and run through the general engine:

| Metric (M4) | Dimension | From evidence | Normalisation |
|---|---|---|---|
| turn count / balance | conversational | total/agent/user turns | occurrences / ratio |
| session completed | technical | `session_completed` | binary |
| session duration | technical | `session_duration_seconds` | latency-style threshold |
| clean ending | risk/operational | `ended_reason` | categorical → binary |

(Exact set, normalisation type and weights settled in design.)

### Scope (M4.1–M4.6)
| Sub | Deliverable |
|-----|-------------|
| M4.1 | One dimension end-to-end: a metric normalised + a dimension score (TDD) |
| M4.2 | Normalisation functions (percentage direct/inverse, binary, occurrences, latency) + edge cases |
| M4.3 | The remaining computable metrics/dimensions |
| M4.4 | Scoring: per-dimension weighted aggregation + global score (dimension weights) |
| M4.5 | Blocking flags (those detectable now: session not completed, session failed) |
| M4.6 | `EvaluationReport` entity + use case (evidences → metrics → scores → flags → report), behind `EvaluationPort`; persist |

### Approach (hexagonal, inside-out)
Pure domain scoring functions first (normalisation, aggregation) with TDD, then the
`EvaluationReport` + use case behind an `EvaluationPort`, so the deterministic engine is swappable.

### Out of scope (deferred)
- LLM-as-judge implementation (a future `EvaluationPort` adapter).
- Metrics needing unavailable events (tool.*, latency, silences, interruptions, errors).
- Multi-session agent validation (doc 3.5).
- Per-agent configurable weights (defaults now; `agent.evaluation_config` later).

### Open questions (resolve in design)
- The concrete metric set, each metric's normalisation type, and weights (per dimension + global).
- The `EvaluationPort` interface shape.
- How the report is triggered (chain after the evidence-build task, or a separate task).

### Risks
- Few metrics now → coarse scores; be honest that the **engine** is the contribution and metrics
  grow with data.
- Determinism must hold end-to-end (no clock or randomness in scoring).

## 2. Spec

### Requirements

- **R1 — Normalisation (doc 3.4.2).** A pure function per type maps a raw value to `0–100`,
  clamped to `[0, 100]`:
  - `percentage_direct` → `value`; `percentage_inverse` → `100 − value`;
  - `binary` → `0`/`1` becomes `0`/`100`;
  - `occurrences` → `max(0, 100 − occurrences × penalty)`;
  - `latency` → `100` if `value ≤ optimal`, `0` if `value ≥ degraded`, linear between.
- **R2 — Metric.** A computed metric carries `code`, `dimension`, `raw_value`,
  `normalized_score` (0–100), `weight`, `unit`.
- **R3 — Dimension score.** Weighted mean of the normalised scores of that dimension's metrics.
  A dimension with no metrics is excluded from scoring (not scored 0).
- **R4 — Global score.** Weighted mean of the dimension scores using dimension weights
  (doc 3.4.4 defaults: conversational 3, operational 3, technical 2, risk 4). Excluded dimensions
  do not contribute.
- **R5 — Blocking flags.** Conditions that force `result = failed` regardless of score. M4 detects
  those observable now: *session not completed* and *session failed*. Each flag records its reason.
- **R6 — Result.** `passed` when `global_score ≥ 75` (doc 3.4.4) **and** no blocking flags;
  otherwise `failed`.
- **R7 — EvaluationReport.** Immutable entity: `report_id`, `session_id`, `score_global`,
  per-dimension scores, `result`, `blocking_flags`, `metrics` snapshot, `generated_at`.
- **R8 — EvaluationPort.** The application defines an interface producing an evaluation from a
  session's evidences; the deterministic engine implements it (an LLM-judge could implement it
  later). The report is persisted via the repository.
- **R9 — Determinism.** The same evidences yield the same report content (except `report_id` and
  `generated_at`).
- **R10 — Evidence-driven.** Metrics are computed from the session's evidences (M3). Metrics with
  no supporting evidence are omitted, never faked.

### Scenarios (become tests)

- **S1** `percentage_direct(87)=87`; `percentage_inverse(8)=92`; `binary(1)=100`, `binary(0)=0`;
  `occurrences(2, penalty=33)=34`; `latency(2000, optimal=1500, degraded=3000)=67`; values clamp
  to `[0,100]`.
- **S2** A dimension score is the weighted mean of its metrics' normalised scores.
- **S3** The global score is the weighted mean of dimension scores using the dimension weights.
- **S4** A blocking flag (session not completed) forces `result = failed` even with a high score.
- **S5** High global score and no blocking flags → `result = passed`.
- **S6** Evaluating a session's evidences yields a report with a global score, per-dimension
  scores, a result, and a metrics snapshot.
- **S7** Determinism: the same evidences produce the same report content.
- **S8** A session with no evidences (or a dimension with no metrics) does not crash; scoring uses
  only the available dimensions.

## 3. Design

### D1 — Normalisation (domain, pure)
`domain/scoring/normalisation.py`: one pure function per type, each returning a clamped `0–100`
`float`: `percentage_direct`, `percentage_inverse`, `binary`, `occurrences(penalty)`,
`latency(optimal, degraded)`. No state, no clock.

### D2 — Metric catalogue for M4
Computed from the M3 evidences (numeric) plus the session's normalised `report` (categorical).
Metrics whose source evidence is absent are omitted (R10). Operational is excluded (no data yet).

| code | dimension | source | normalisation | weight |
|---|---|---|---|---|
| `engagement` | conversational | `agent_turns > 0` and `user_turns > 0` | binary | 3 |
| `completion` | technical | `session_completed` evidence present | binary | 3 |
| `duration` | technical | `session_duration_seconds` value | latency(optimal=300, degraded=900) | 1 |
| `clean_ending` | risk | `ended_reason` not in a bad-reasons set | binary | 3 |

### D3 — Scoring (domain, pure)
`domain/scoring/engine.py`: `dimension_score(metrics)` = weighted mean of normalised scores;
`global_score(dimension_scores)` = weighted mean using dimension weights
(conversational 3, technical 2, risk 4; operational excluded). Empty dimensions are skipped.

### D4 — Blocking flags
`session_not_completed` when the `session_completed` evidence is absent. Extensible
(`session_failed` added once failures are produced). Any active flag → `result = failed`.

### D5 — Result & report entity
`result = passed` iff `global_score ≥ 75` and no blocking flags. `EvaluationReport`
(`domain/evaluation_report.py`, frozen): `report_id`, `session_id`, `score_global`, per-dimension
scores (nullable), `result`, `blocking_flags` (list), `metrics` (snapshot list), `generated_at`.
New enum `EvaluationResult` (`passed`/`failed`).

### D6 — Evaluation port + deterministic evaluator
`application/ports/evaluation.py`: `Evaluator` Protocol — `evaluate(session, evidences) ->
EvaluationReport`. The deterministic implementation lives in `domain/scoring/` (pure). A future
LLM-judge implements the same Protocol without touching the domain. Metrics come from evidences;
the categorical `clean_ending` reads the session's normalised `report` (still Vapi-free).

### D7 — Persistence
`EvaluationReportModel` (`report_id` PK, `session_id` FK unique, the four dimension scores,
`score_global`, `result`, `blocking_flags` JSONB, `metrics` JSONB, `generated_at`). One Alembic
migration. Repository port gains `add_report(report)` and `get_report_by_session(session_id)`.

### D8 — Trigger
The Celery evidence task, after persisting evidences, runs the deterministic evaluator and persists
the report in the same run (evidences → report). Idempotent (report replaced per session). May be
split into a chained task later.

### D9 — Layer placement
```
domain/        scoring/ (normalisation, engine, deterministic evaluator) · evaluation_report.py · enums (EvaluationResult)
application/   ports/evaluation.py (Evaluator) · repository port += add_report / get_report_by_session
infrastructure/ EvaluationReportModel + migration · repo impl · celery task runs the evaluator
```
Dependency rule holds: scoring is pure domain; the port lets an LLM-judge slot in later.

## 4. Tasks

Test-first (RED → GREEN → REFACTOR). Grouped by area; each group ships as one commit.

### M4.1–M4.2 — Scoring primitives (`domain/scoring/`, pure)
- [x] **T1** Normalisation functions: `percentage_direct`, `percentage_inverse`, `binary`,
  `occurrences`, `latency`. Tests use the doc 3.4.2 example values + clamping (S1).
- [x] **T2** `Metric` value object; `dimension_score` (weighted mean) and `global_score`
  (weighted mean with dimension weights, empty dimensions skipped). Tests (S2, S3).

### M4.3 — Metric catalogue (`domain/scoring/`)
- [x] **T3** `build_metrics(session, evidences) -> list[Metric]` — `engagement`, `completion`,
  `duration`, `clean_ending`; metrics with no source evidence are omitted (R10).

### M4.4–M4.5 — Report + evaluator (`domain/`)
- [ ] **T4** `EvaluationResult` enum, `EvaluationReport` frozen entity, blocking-flag detection
  (`session_not_completed`).
- [ ] **T5** `DeterministicEvaluator.evaluate(session, evidences) -> EvaluationReport` tying
  metrics → dimension scores → global → flags → result. Tests (S4, S5, S6, S7, S8).

### M4.6 — Port, persistence, trigger
- [ ] **T6** `Evaluator` Protocol (`application/ports/evaluation.py`).
- [ ] **T7** `EvaluationReportModel` + Alembic migration.
- [ ] **T8** Repository port `add_report` / `get_report_by_session`; fake + SQLAlchemy impl.
- [ ] **T9** Celery task: after evidences, run the evaluator and persist the report. Integration
  test (eager, real DB).

*DoD: a closed session's evidences yield a persisted EvaluationReport with a deterministic score;
CI green.*

### Review workload
Solo project, direct-to-`main`, one commit per group. No PR chain.
