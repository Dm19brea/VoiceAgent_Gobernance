import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "validation" / "m7"
PROTOCOL = DOCS / "validation-protocol.md"
SCHEMA = DOCS / "templates" / "validation-result.schema.json"
EXAMPLE = DOCS / "templates" / "validation-result.example.json"
SCENARIOS = {"confirmation", "rescheduling", "cancellation"}
DIAGNOSTIC_CODES = {
    "SESSION_TIMEOUT",
    "SESSION_FAILED",
    "EVALUATION_TIMEOUT",
    "EVALUATOR_FAILED",
    "API_ERROR",
}
FORMAT_CHECKER = jsonschema.FormatChecker()


@FORMAT_CHECKER.checks("date-time")  # type: ignore[untyped-decorator]
def _is_calendar_valid_date_time(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _artifacts() -> tuple[str, dict[str, Any], dict[str, Any]]:
    return PROTOCOL.read_text(), json.loads(SCHEMA.read_text()), json.loads(EXAMPLE.read_text())


def _scenario_card(protocol: str, scenario: str) -> str:
    heading = f"## Scenario: {scenario.title()}"
    _, _, remainder = protocol.partition(heading)
    return remainder.partition("## Scenario:")[0]


def _validate(schema: dict[str, Any], record: dict[str, Any]) -> list[jsonschema.ValidationError]:
    validator = jsonschema.Draft202012Validator(schema, format_checker=FORMAT_CHECKER)
    return list(validator.iter_errors(record))


def test_m7_artifacts_define_only_the_approved_scenarios_and_verdicts() -> None:
    protocol, schema, example = _artifacts()

    assert set(schema["properties"]["scenario_id"]["enum"]) == SCENARIOS
    assert set(schema["properties"]["verdict"]["enum"]) == {"PASS", "FAIL"}
    assert set(example["scenario_id"] for _ in [None]) <= SCENARIOS
    assert all(protocol.count(f"## Scenario: {scenario.title()}") == 1 for scenario in SCENARIOS)


def test_m7_each_scenario_card_declares_complete_preconditions_and_outcome_contract() -> None:
    protocol, _, _ = _artifacts()
    required_topics = {
        "Objective",
        "Inputs",
        "Preconditions",
        "Allowed behavior",
        "Forbidden behavior",
        "Observable outcome",
        "Required evidence",
        "PASS assertion",
        "FAIL assertion",
    }
    outcomes = {
        "confirmation": "confirmed without changing its scheduled details",
        "rescheduling": "moves to the intended fictitious replacement slot and no unrelated appointment changes",  # noqa: E501
        "cancellation": "cancelled and no replacement booking is created",
    }

    for scenario in SCENARIOS:
        card = _scenario_card(protocol, scenario)
        assert card, f"missing {scenario} card"
        for topic in required_topics:
            assert f"| {topic} |" in card, f"{scenario} card omits {topic}"
        assert outcomes[scenario] in card.lower()
        assert "FAIL" in card and "diagnostic" in card.lower()


def test_m7_protocol_refuses_unsafe_or_incomplete_preconditions_with_diagnostics() -> None:
    protocol, schema, example = _artifacts()

    refusal_rule = (
        "If any condition fails, do not proceed. Record `FAIL` with a diagnostic "
        "that identifies the unmet condition."
    )
    assert refusal_rule in protocol
    for scenario in SCENARIOS:
        card = _scenario_card(protocol, scenario)
        assert "fictitious" in card.lower()
        assert "governed assistant is registered" in card.lower()
        assert "validation environment" in card.lower()
    record = deepcopy(example)
    record.update(
        verdict="FAIL",
        diagnostics=[{"code": "PRECONDITION_UNMET", "message": "unmet unsafe precondition"}],
    )  # noqa: E501
    assert not _validate(schema, record)


def test_m7_contract_requires_a_complete_fictitious_per_run_record() -> None:
    _, schema, example = _artifacts()
    required = {
        "protocol_version",
        "scenario_id",
        "run_id",
        "call_or_session_id",
        "environment",
        "timestamps",
        "observed_outcome",
        "governance_trace",
        "evidence",
        "diagnostics",
        "verdict",
    }

    assert required <= set(schema["required"])
    assert not _validate(schema, example)
    assert "pii" not in json.dumps(example).lower()


def test_m7_schema_enforces_evidence_names_verdicts_and_timestamps() -> None:
    _, schema, example = _artifacts()

    for scenario in SCENARIOS:
        for mismatched_scenario in SCENARIOS - {scenario}:
            record = deepcopy(example)
            record["scenario_id"] = scenario
            record["evidence"][0]["name"] = (
                f"m7-v1-{mismatched_scenario}-fx-call-001-report-r1.json"
            )
            errors = _validate(schema, record)
            assert errors, f"{scenario} accepted {mismatched_scenario} evidence"
        record = deepcopy(example)
        record.update(scenario_id=scenario)
        record["evidence"][0]["name"] = f"m7-v1-{scenario}-fx-call-001-validation-report-r1.json"
        assert not _validate(schema, record)

    record = deepcopy(example)
    record["verdict"] = "FAIL"
    assert _validate(schema, record)
    for code in {"SESSION_TIMEOUT", "EVALUATION_TIMEOUT", "EVALUATOR_FAILED", "PRECONDITION_UNMET"}:
        record = deepcopy(example)
        record["diagnostics"] = [{"code": code, "message": "failure diagnostic"}]
        assert _validate(schema, record)
    record = deepcopy(example)
    record["timestamps"]["prepared_at"] = "not-a-timestamp"
    assert _validate(schema, record)


def test_m7_operator_validation_path_asserts_calendar_valid_timestamps() -> None:
    protocol, schema, example = _artifacts()

    assert "calendar_format_checker" in protocol

    for field in ("prepared_at", "completed_at"):
        record = deepcopy(example)
        record["timestamps"][field] = "2026-02-31T10:00:00Z"
        assert _validate(schema, record), f"accepted calendar-invalid {field}"

    assert not _validate(schema, example)


def test_m7_protocol_excludes_real_calls_aggregation_and_production_claims() -> None:
    protocol, schema, example = _artifacts()
    combined = f"{protocol}\n{json.dumps(schema)}\n{json.dumps(example)}".lower()

    for forbidden in ("aggregate", "statistics", "production threshold", "production-ready"):
        assert forbidden not in combined
    assert "zero real vapi calls" in protocol.lower()
    assert "m7.3" in protocol.lower() and "m7.4" in protocol.lower()
    diagnostic_codes = set(
        schema["properties"]["diagnostics"]["items"]["properties"]["code"]["enum"]
    )
    assert diagnostic_codes >= DIAGNOSTIC_CODES


def test_m7_protocol_uses_safe_bounded_inert_shell_examples() -> None:
    protocol, _, _ = _artifacts()

    assert "deadline" in protocol.lower() and "interval" in protocol.lower()
    assert "eval " not in protocol and "source " not in protocol
    assert '"$SCENARIO_ID"' in protocol and '"$RUN_ID"' in protocol
