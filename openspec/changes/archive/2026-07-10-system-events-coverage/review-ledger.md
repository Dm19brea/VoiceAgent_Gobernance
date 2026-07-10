# Review Ledger: System Event Coverage — PR 3 Evaluation Observations

**Verdict: PASS — recoverable evaluation errors now use stable retry identities while retaining message detail as provenance.**

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R3-001 | reliability | `backend/src/infrastructure/celery/tasks.py:143-151`; `backend/tests/test_build_evidences_task.py` | WARNING | verified | `identity_fields` now use only the stable operation and exception class; the free-form message remains payload provenance. The changing-request-ID retry regression records exactly one `system.error`. |

## Verification evidence

- Focused Celery suite: `uv run pytest tests/test_build_evidences_task.py -q` → `10 passed`.
- Scoped R3-001 re-review: `uv run pytest tests/test_build_evidences_task.py::test_recoverable_evaluation_error_ignores_volatile_message_in_retry_identity -q` → `1 passed`; source review confirms identity excludes `str(error)` and payload preserves it.
- Full backend suite: `uv run pytest -q` → `254 passed, 3 warnings`.
- Tracked PR 3 scope is limited to `backend/src/infrastructure/celery/tasks.py`, `backend/tests/test_build_evidences_task.py`, and `docs/design/vapi-event-coverage.md`; no webhook source changed.
- No migration is added by this slice; prior sequence-constraint migration remains the deployment prerequisite.

---

# Review Ledger: System Event Coverage Design

**Verdict: PASS — scoped re-review found no new findings on fix-touched lines.**

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R2-001 | reliability | `design.md:47` | CRITICAL | verified | Versioned canonical fingerprints now define terminal, threat, latency, and evaluation identities; no provider timestamp or unspecified key is used, and missing stable fields remain raw-only. |
| R2-002 | reliability | `design.md:45` | WARNING | verified | Both canonical append paths now lock the session before sequence assignment, with a `(session_id, sequence_number)` uniqueness constraint as defense in depth. |
| R2-003 | resilience | `design.md:49,73` | WARNING | verified | The design now requires one transaction and rollback of raw/error/lifecycle state, plus an injected second-insert-failure integration test. |

Scoped re-review: PASS. No new findings on fix-touched lines.

Checked: hexagonal boundary is sound; `model-output`/`hang` mappings match current code; `system.error` can coexist with `session.failed` if the new append path permits it; UUID5 on existing `events.event_id` needs no new migration. Existing marker-index deployment caveat remains separate.

---

# Review Ledger: System Event Coverage — PR 2 Vapi webhook

**Verdict: PASS — mid-call Vapi transcript threats are now safely promoted without lifecycle mutation.**

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R3-001 | reliability | `backend/src/domain/session.py:107-119`; `backend/src/adapters/rest/vapi.py:69-74` | CRITICAL | verified | Scoped re-review verified that only `system.flag_raised` is admitted while `ACTIVE`; raw landing precedes promotion, UUID5 identity suppresses the duplicate, and the domain method does not change `status` or `ended_at`. |
| R3-002 | reliability | `backend/tests/test_domain_session.py:155-176`; `backend/tests/test_vapi_webhook_ingestion.py:165-202` | WARNING | verified | Scoped re-review verified an actually active webhook flow (start → threat → duplicate threat): it persists 3 raw deliveries and exactly one flag while status remains active and `ended_at` remains unset. |

## Verification evidence

- Focused scoped tests: `3 passed` — active flag preservation, active error rejection, and duplicate active-transcript threat ingestion.
- Terminal `system.error` plus `session.failed` is atomic, retries are idempotent, and latency persistence remains best-effort/non-recursive.

## Required remediation

Scoped re-review: PASS. The active flag exception is constrained to `system.flag_raised`; `system.latency_measured` and `system.error` retain post-terminal semantics.

---

# Review Ledger: System Event Coverage — PR 1 Foundation

**Verdict: PASS — scoped fix verification completed.**

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R1-001 | reliability | `backend/src/application/use_cases/ingest_event.py:30-47`; `backend/tests/test_ingest_event_use_case.py:143-164` | CRITICAL | verified | Scoped re-review verified that the insert-race reload reapplies the duplicate-start and active-session guards, so a non-`session.started` event for an ENDED session returns without recording or raising; regression test passed. |
| R2-001 | readability | `backend/tests/test_governance_repository.py:185`; `backend/tests/test_record_system_observation.py:67-69` | WARNING | verified | Scoped re-review verified the explicit `Table` cast and `LogCaptureFixture` annotation; `uv run mypy src tests` succeeds across 85 source files. |

## Verification Evidence

- Focused tests: `20 passed` (fix-touched tests).
- Full backend suite: `239 passed, 2 pre-existing warnings`.
- Ruff: passed.
- Mypy: `Success: no issues found in 85 source files`.
- Migration: revision `c6f1e8a2b4d7` compiled successfully.
- Scope: no Vapi mapping, webhook, or Celery source changes; keep unrelated untracked `docs/design/evidence-coverage-by-quality-dimension.md` out of PR 1.
