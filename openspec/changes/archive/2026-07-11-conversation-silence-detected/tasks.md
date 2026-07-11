# Tasks: Aggregate User-Response Silence Detection

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | 500–650 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 detector → PR 2 mapping → PR 3 persistence/wiring |
| Delivery strategy | ask-on-risk |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|---|---|---|---|
| 1 | Pure detector contract | PR 1 | Base `main`; independent behavior and tests |
| 2 | Trustworthy timed-turn mapping | PR 2 | Base `main` after PR 1 merges |
| 3 | Retry-safe persistence and pipeline | PR 3 | Base `main` after PR 2 merges |

## Phase 1: Pure Detector (RED → GREEN → REFACTOR)

- [x] 1.1 **RED:** Create `backend/tests/test_conversation_silence_detection.py` covering 5999/6000/>6000 ms, assistant→user only, terminal/pre/post exclusions, malformed/non-finite/negative/inconsistent boundaries, three-gap aggregation, chronological intervals, `count == len(intervals)`, and last qualifying user-start timestamp.
- [x] 1.2 **GREEN:** Create `backend/src/application/use_cases/detect_conversation_silence.py` with immutable `SilencePolicy`, `TimedTurn`, `SilenceInterval`, `SilenceAggregate`, and provider-independent detection sufficient for 1.1.
- [x] 1.3 **REFACTOR:** Centralize threshold/version constants, validation, and typed immutable results without changing detector tests.

## Phase 2: Timed-Turn Mapping (RED → GREEN → REFACTOR)

- [x] 2.1 **RED:** Extend `backend/tests/test_conversation_content_mapping.py` for first-fragment start/final-fragment end, one normalized monotonic index shared with content, invalid boundary normalization, and fail-closed role/count alignment.
- [x] 2.2 **GREEN:** Modify `backend/src/adapters/rest/vapi_mapping.py` to consolidate raw bot/user groups into aligned `TimedTurn` values and expose no silence input on alignment failure.
- [x] 2.3 **REFACTOR:** Keep transport parsing separate from the detector and verify existing content mapping remains unchanged.

## Phase 3: Canonical Persistence (RED → GREEN → REFACTOR)

- [x] 3.1 **RED:** Extend `backend/tests/test_record_conversation_signals.py` for the canonical payload, immutable `assistant-user-interior-gap/v1` UUID5 inputs, post-terminal allowlist, type-based short-circuit after lock, equivalent redelivery, and no historical reprocessing across versions.
- [x] 3.2 **GREEN:** Update signal command/recorder and `backend/src/domain/session.py` to append `conversation.silence_detected` once with identity, threshold, count, intervals, and chronological timestamp.
- [x] 3.3 **RED/GREEN:** Extend `backend/tests/test_governance_repository.py`; make two independent same-session workers yield one event, one next sequence, and no collision through row locking plus conflict-safe insertion.
- [x] 3.4 **REFACTOR:** Keep identity creation and existing-event-by-type lookup explicit and version-lifecycle comments auditable.

## Phase 4: Isolated Pipeline Wiring (RED → GREEN → REFACTOR)

- [x] 4.1 **RED:** Extend `backend/tests/test_build_evidences_task.py` for zero/one aggregate, multiple intervals, later ingestion sequence with earlier timestamp, redelivery, malformed timing isolation, and silence-step failure not blocking content, scoring, or LLM judge.
- [x] 4.2 **GREEN:** Modify `backend/src/infrastructure/celery/tasks.py` to run `_record_conversation_silence` in its own transaction after content and before the judge, catching and logging all failures.
- [x] 4.3 **REFACTOR:** Run focused suites, then the backend suite; confirm every spec scenario and no regression in existing conversation events.
