# M7.2 validation scenario protocol

This protocol gives M7.3 operators a repeatable, outcome-based method for three fictitious appointment scenarios. It defines templates only: M7.2 makes **zero real Vapi calls** and records no execution evidence.

## Quick path

1. Confirm every preflight condition and use fictitious identifiers only.
2. In M7.3, run one approved scenario, wait within the declared deadline, and inspect its governance trace.
3. Create one result record from the schema and assign `PASS` or `FAIL`.

## Preconditions

- The governed assistant is registered in the selected validation environment.
- All appointment, caller, and replacement-slot identifiers are fictitious safe slugs.
- The environment name and version are known before the run starts.
- The operator can inspect the terminal session, events, evidence, and report references.

If any condition fails, do not proceed. Record `FAIL` with a diagnostic that identifies the unmet condition.

## Scenario: Confirmation

| Topic | Requirement |
|---|---|
| Objective | Confirm the intended fictitious appointment. |
| Inputs | One valid fictitious appointment and a known validation environment. |
| Preconditions | The governed assistant is registered; the appointment identifiers are fictitious safe slugs; the validation environment is identified; and terminal session, event, evidence, and report references can be inspected. |
| Allowed behavior | Complete the confirmation outcome and retain the governance trace. |
| Forbidden behavior | Change the appointment or introduce an unapproved side effect. |
| Observable outcome | The intended fictitious appointment is confirmed without changing its scheduled details. |
| Required evidence | Session/event reference and a named report or trace file. |
| PASS assertion | The appointment is confirmed, required governance references exist, and named evidence is available. |
| FAIL assertion | FAIL if any precondition is unsafe or incomplete, the appointment is not confirmed, a forbidden side effect occurs, or required evidence is absent; include a diagnostic identifying the unmet condition or outcome. |

## Scenario: Rescheduling

| Topic | Requirement |
|---|---|
| Objective | Move a fictitious appointment to its intended fictitious replacement slot. |
| Inputs | One valid fictitious appointment, replacement slot, and known validation environment. |
| Preconditions | The governed assistant is registered; appointment and replacement-slot identifiers are fictitious safe slugs; the validation environment is identified; and terminal session, event, evidence, and report references can be inspected. |
| Allowed behavior | Complete the move and retain the governance trace. |
| Forbidden behavior | Create an unintended booking or change an unrelated appointment. |
| Observable outcome | The intended fictitious appointment moves to the intended fictitious replacement slot and no unrelated appointment changes. |
| Required evidence | Session/event reference and a named report or trace file. |
| PASS assertion | The intended move occurs without a forbidden side effect and named evidence is available. |
| FAIL assertion | FAIL if any precondition is unsafe or incomplete, the intended move does not occur, a forbidden side effect occurs, or required evidence is absent; include a diagnostic identifying the unmet condition or outcome. |

## Scenario: Cancellation

| Topic | Requirement |
|---|---|
| Objective | Cancel the intended fictitious appointment. |
| Inputs | One valid fictitious appointment and a known validation environment. |
| Preconditions | The governed assistant is registered; the appointment identifier is a fictitious safe slug; the validation environment is identified; and terminal session, event, evidence, and report references can be inspected. |
| Allowed behavior | Complete the cancellation outcome and retain the governance trace. |
| Forbidden behavior | Create a replacement booking. |
| Observable outcome | The intended fictitious appointment is cancelled and no replacement booking is created. |
| Required evidence | Session/event reference and a named report or trace file. |
| PASS assertion | The appointment is cancelled, no replacement is created, and named evidence is available. |
| FAIL assertion | FAIL if any precondition is unsafe or incomplete, the appointment is not cancelled, a replacement booking is created, or required evidence is absent; include a diagnostic identifying the unmet condition or outcome. |

## Bounded evaluation and diagnostics

Use a fixed polling interval and deadline. A timeout or evaluator failure is `FAIL`, never an indefinite wait. The following protocol diagnostic codes are classification labels, not claims about existing provider or application statuses: `SESSION_TIMEOUT`, `SESSION_FAILED`, `EVALUATION_TIMEOUT`, `EVALUATOR_FAILED`, and `API_ERROR`.

The following inert shell snippet only prints the selected identifiers; it does not contact a provider or start a call.

```sh
SCENARIO_ID="${SCENARIO_ID:-confirmation}"
RUN_ID="${RUN_ID:-fx-run-001}"
INTERVAL_SECONDS=10
DEADLINE_EPOCH=0
printf 'scenario=%s run=%s interval=%s deadline=%s\n' "$SCENARIO_ID" "$RUN_ID" "$INTERVAL_SECONDS" "$DEADLINE_EPOCH"
```

## Evidence and result record

Store names using `m7-v1-{scenario_id}-{call_or_session_id}-{evidence_kind}-{revision_or_utc}.{ext}`. Every segment is a lowercase safe slug. For example: `m7-v1-confirmation-fx-call-001-report-r1.json`.

Validate each M7.3 record with `templates/validation-result.schema.json` using a Draft 2020-12 validator **with format assertion enabled**. `format` is annotation-only by default in JSON Schema 2020-12, so a bare generic validator is not an acceptable operator path. The following safe local check rejects invalid calendar dates (for example, `2026-02-31T10:00:00Z`) without contacting Vapi:

```python
import json
from datetime import datetime
from jsonschema import Draft202012Validator, FormatChecker

schema = json.load(open("templates/validation-result.schema.json"))
record = json.load(open("validation-result.json"))
calendar_format_checker = FormatChecker()

@calendar_format_checker.checks("date-time")
def is_calendar_valid_date_time(value):
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False

validator = Draft202012Validator(schema, format_checker=calendar_format_checker)
validator.validate(record)
```

The accompanying example is fictitious and shape-only; it is not a record of an executed call.

## Milestone boundaries

- **M7.2:** this protocol and empty-use templates only.
- **M7.3:** may execute the three calls and populate per-run evidence.
- **M7.4:** handles any later cross-run analysis separately; it does not alter this per-run contract.

## Operator checklist

- [ ] Preconditions are true and all values are fictitious.
- [ ] Exactly one approved scenario is selected.
- [ ] Polling uses the declared interval and deadline.
- [ ] Governance and evidence references are named deterministically.
- [ ] The result validates and has exactly one `PASS` or `FAIL` verdict.
