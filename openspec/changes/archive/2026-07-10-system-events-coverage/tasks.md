# Tasks: System Event Coverage

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 650–850 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 foundation; PR 2 Vapi webhook; PR 3 Celery/verification |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | Safe canonical append foundation | PR 1 → main | Migration, locks, domain/use case, tests. |
| 2 | Vapi-derived observations | PR 2 → main | After PR 1 merges; raw provenance and atomic terminal flow. |
| 3 | Evaluation observations and regression verification | PR 3 → main | After PR 2 merges; task wiring and focused/full tests. |

## Phase 1: Persistence and Application Foundation

- [x] 1.1 **RED** — Add domain tests in `backend/tests/test_domain_session.py` for allowed post-terminal `system.latency_measured`, `system.error`, and `system.flag_raised`, and rejected types/status mutation.
- [x] 1.2 **GREEN** — Add `Session.append_system_observation` in `backend/src/domain/session.py`; preserve lifecycle state and validate only the three observation types.
- [x] 1.3 **RED→GREEN→REFACTOR** — Add `SystemObservationCommand` and `RecordSystemObservation` in `backend/src/application/commands.py` and `use_cases/record_system_observation.py`, using versioned canonical JSON/SHA-256/UUID5 identities and raw-only logging on missing stable fields.
- [x] 1.4 **RED→GREEN→REFACTOR** — Extend `backend/src/application/ports/governance_repository.py`, `use_cases/ingest_event.py`, and `infrastructure/repositories/governance_repository.py` so every canonical append locks the session before sequencing, handles insert races, and uses `ON CONFLICT (event_id) DO NOTHING`.
- [x] 1.5 **RED→GREEN→REFACTOR** — Add repository integration tests for concurrent normal/system appends and duplicate identities; modify `backend/src/infrastructure/db/models.py` and add an Alembic revision for `UNIQUE(session_id, sequence_number)` after a collision-preflight query.

## Phase 2: Vapi Webhook Observations

- [x] 2.1 **RED→GREEN→REFACTOR** — Test and implement pure helpers in `backend/src/adapters/rest/vapi_mapping.py` for terminal-error and normalized per-threat flag intents, deterministic fingerprints, raw links, and raw-only fallback.
- [x] 2.2 **RED→GREEN→REFACTOR** — Update `backend/src/adapters/rest/vapi.py` to assign/flush `RawEvent` IDs, emit post-commit webhook-ingestion latency in a separate best-effort transaction, and log non-recursively on observation persistence failure.
- [x] 2.3 **RED→GREEN→REFACTOR** — Add transaction tests proving terminal `system.error` plus `session.failed` commit atomically, retries remain idempotent, and injected second-insert failure rolls back raw/error/lifecycle writes.
- [x] 2.4 **RED→GREEN→REFACTOR** — Add regression tests that preserve `model-output` → `system.model_invocation`, `hang` → `system.warning`, and unsupported/specialized Vapi messages as raw-only.

## Phase 3: Evaluation and Verification

- [x] 3.1 **RED→GREEN→REFACTOR** — Update `backend/src/infrastructure/celery/tasks.py` to record `evidence_evaluation` latency, accepted platform findings, and recoverable errors through the use case; test recursion containment and no lifecycle mutation.
- [x] 3.2 Run focused domain/use-case/repository/webhook/task tests, migration upgrade checks, then the full backend suite; record any historical sequence collision remediation before rollout.
