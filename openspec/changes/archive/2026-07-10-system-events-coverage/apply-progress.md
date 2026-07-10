# Apply Progress: System Event Coverage — PR 3 Evaluation Observations

**Status:** implemented locally; ready for fresh review and maintainer approval (not committed, staged, pushed, or PR-created).
**Delivery:** stacked PR slice 3 → `main`, based on merged PR #15.
**Completed tasks:** 1.1–3.2 / 11

## Implemented

- Retained the PR 1 foundation: versioned canonical SHA-256/UUID5 identities, raw provenance, locked/idempotent canonical appends, and sequence uniqueness migration.
- Retained the PR 2 webhook observations: terminal errors, transcript threats, and best-effort webhook-ingestion latency while preserving raw landing.
- Added evaluation observations through `RecordSystemObservation` only:
  - one retry-safe `system.latency_measured` for `evidence_evaluation` with local timestamps and duration;
  - one `system.flag_raised` per accepted deterministic-evaluation blocking finding, with code, reason, and report provenance;
  - one retry-safe `system.error` for a recoverable evaluation failure, preserving the original exception and session lifecycle.
- Isolated evaluation-observation persistence in a separate best-effort transaction. A failure to record an observation only logs once and never recursively emits another error.
- Updated `docs/design/vapi-event-coverage.md` to show complete system-event coverage and the concrete Vapi/platform sources.

## TDD Cycle Evidence

| Task | RED | GREEN | REFACTOR |
|---|---|---|---|
| 1.1–2.4 | Prior completed foundation and webhook evidence retained. | Prior focused/full validation retained. | Prior PR 1/PR 2 review corrections retained. |
| 3.1 | Added recoverable-error and accepted-finding retry tests before Celery observation wiring; both failed with zero system observations (`2 failed, 6 passed`). | `backend/tests/test_build_evidences_task.py` passes 9 tests after wiring latency, flags, and isolated error persistence. | Extracted command construction and isolated best-effort persistence helpers; recursion-containment test verifies exactly one logging-only failure. |
| 3.1 correction (R3-001) | Added a retry test where one `RuntimeError` class carries changing request IDs; it failed with two `system.error` events. | The focused suite passes 10 tests after removing free-form error text from the identity. | Stable identity now uses operation + exception class; message stays as payload provenance. |
| 3.2 | The initial live upgrade exposed schema/version drift and stopped without a workaround. | After authorized reconciliation, `alembic current`, `alembic heads`, and no-op `alembic upgrade head` report `c6f1e8a2b4d7 (head)`; collision preflight returns `None`. | No migration/code refactor required; reconciliation records an already-equivalent local schema. |

## Verification

- Focused Celery task suite: `10 passed`.
- Full backend suite: `254 passed, 3 warnings` (pre-existing Starlette/httpx deprecation plus Celery coroutine warnings from webhook task dispatch tests).
- Ruff: `All checks passed`; format: `85 files already formatted`.
- Mypy: `Success: no issues found in 85 source files`.
- `git diff --check`: passed.
- Functional examples:
  1. Retrying a recoverable `RuntimeError("evaluator dependency unavailable")` records exactly one `system.error` with classification `recoverable_evaluation_failure`; the session remains `ENDED` with its original `ended_at`.
  2. Retrying an evaluation of a failed session records exactly one `system.flag_raised` (`session_failed`) and one `system.latency_measured`; the session remains `FAILED` with its original `ended_at`.

## Rollout Preflight

The authorized local reconciliation stamped the already-equivalent schema to `c6f1e8a2b4d7`. `alembic current`, `alembic heads`, and `alembic upgrade head` now agree on that head; the explicit historical sequence-collision query returns `None`. No migration files or implementation code changed during reconciliation.
