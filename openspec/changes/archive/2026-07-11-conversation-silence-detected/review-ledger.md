# Design Review Ledger: conversation-silence-detected

Review lenses: risk, reliability. Three initial sweeps completed; a scoped re-review examined only the corrected lines for the five persisted findings.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| RELIABILITY-001 | reliability | `openspec/changes/conversation-silence-detected/design.md:13,52,72` | CRITICAL | verified | The corrected contract timestamps the aggregate at the last qualifying user's response start, defines `detected_at == intervals[-1].ended_at`, and requires a multi-gap timestamp test. The complete aggregate is therefore not timestamped before its final represented boundary. |
| RISK-001 | risk | `openspec/changes/conversation-silence-detected/design.md:14-15,67,72` | WARNING | verified | The corrected lifecycle limits new detector versions to unprocessed calls and explicitly forbids historical recalculation, backfill, supersession, or migration. Under the session row lock, persistence short-circuits on any existing `conversation.silence_detected` event by type regardless of UUID/version; otherwise it appends once. The concurrent-worker repository test verifies that this lock-scoped type check preserves at most one event and collision-free sequence assignment. |
| RELIABILITY-002 | reliability | `openspec/changes/conversation-silence-detected/design.md:40-52` | WARNING | verified | The example now has one interval for `count: 1`, and the contract explicitly requires `count == len(intervals)`. |
| RELIABILITY-003 | reliability | `openspec/changes/conversation-silence-detected/design.md:11,72` | WARNING | verified | The corrected design assigns a single consolidated raw-group index source to content and silence, fails derivation closed on formatted/raw count or role mismatch, and adds alignment/mismatch tests. |
| RELIABILITY-004 | reliability | `openspec/changes/conversation-silence-detected/design.md:67,72` | WARNING | verified | The corrected plan adds a repository test with two independent concurrent workers and asserts one event plus collision-free ingestion sequence under the session-row lock and event-ID conflict behavior. |

## Gate Result

**PASS** — all five findings are verified. The design is safe to advance to task planning. No code changes were made.

## PR 1 Apply Review

Review lenses: reliability, resilience, readability. Four sweeps completed: two behavioral/evidence sweeps, one resilience/tooling sweep, and one readability sweep. The final two behavioral sweeps and the readability sweep were dry.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| RELIABILITY-PR1-001 | reliability | `backend/tests/test_conversation_silence_detection.py:75-113` | WARNING | verified | Scoped re-review confirms a reversed boundary within the assistant turn at line 81 and an explicit pre-epoch assistant boundary at lines 99-113. Both exercise the detector and fail closed. The exact repository test source passed at runtime: 20 tests in 0.02s. |
| RELIABILITY-PR1-002 | reliability | `backend/tests/test_conversation_silence_detection.py:152-176` | WARNING | verified | Scoped re-review confirms runtime mutation attempts for `TimedTurn.turn_index`, `SilenceInterval.duration_ms`, and `SilenceAggregate.count`, each requiring `FrozenInstanceError`; policy immutability remains covered separately. The exact repository test source passed all 20 tests. |
| RESILIENCE-PR1-001 | resilience | `openspec/changes/conversation-silence-detected/apply-progress.md:22-26` | SUGGESTION | info | Exact-source evidence is trustworthy when the symlink target is absolute. Scoped re-review used `$PWD/backend/tests/test_conversation_silence_detection.py` as the target plus isolated `--rootdir`, `/dev/null` config, `--noconftest`, and disabled cacheprovider; 20 tests passed without inspecting denied `backend/.env`. The relative target shown in the apply-progress example should not be copied literally because a symlink resolves it relative to `/private/tmp`. |

### PR 1 Gate Result

**PASS** — scoped re-review verified RELIABILITY-PR1-001 and RELIABILITY-PR1-002. Pre-epoch and per-turn reversed boundaries now fail closed under direct tests; `TimedTurn`, `SilenceInterval`, and `SilenceAggregate` immutability is runtime-protected. The exact repository test source passed all 20 tests, and Ruff passed. No open BLOCKER, CRITICAL, or WARNING findings remain for PR 1.

## PR 2 Apply Review

Review lenses: reliability, resilience, readability. Four finite sweeps completed: three behavioral/evidence sweeps and one readability sweep. After the first sweep identified the timestamp-test coverage gap below, the next two behavioral sweeps and the readability sweep were dry.

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| RELIABILITY-PR2-001 | reliability | `backend/tests/test_conversation_content_mapping.py:225-280` | WARNING | verified | Scoped re-review confirms direct runtime cases for timezone-aware `Z` and offset ISO acceptance, plus fail-closed handling of naive ISO, boolean, positive infinity, and a huge out-of-range epoch. The numeric parser now avoids applying `isfinite` to arbitrary-size integers and catches `OverflowError` from conversion inside the guarded block. The exact current test source passed 12 tests in 0.01s; Ruff format/check and mypy passed for both PR 2 paths. |
| RESILIENCE-PR2-001 | resilience | `openspec/changes/conversation-silence-detected/apply-progress.md:31-35` | SUGGESTION | verified | The documented absolute-symlink isolation strategy was reproduced against the exact current repository test source. The focused suite passed 10 tests without reading the policy-denied `backend/.env`; Ruff format/check and mypy also passed for the two PR 2 paths. |
| READABILITY-PR2-001 | readability | `backend/src/adapters/rest/vapi_mapping.py:364-461` | SUGGESTION | info | The provider adapter keeps consolidation, strict formatted/raw alignment, role normalization, and timestamp parsing in small transport-only helpers; detector policy is not imported or invoked here beyond the `TimedTurn` transport type. No Phase 3/4 persistence or pipeline behavior appears in the reviewed slice. |

### PR 2 Gate Result

**PASS** — scoped re-review verified RELIABILITY-PR2-001. Timezone-aware ISO values are accepted; naive ISO, boolean, non-finite, negative, and overflowing epoch values fail closed, including the huge-integer `OverflowError` path. The exact focused test suite passed 12 tests; Ruff format/check and mypy passed. No open BLOCKER, CRITICAL, or WARNING findings remain for PR 2. Publication must be built from the remote `main` baseline and restricted to `backend/src/adapters/rest/vapi_mapping.py` and `backend/tests/test_conversation_content_mapping.py`; the local Git state is not suitable as publication-diff evidence.
