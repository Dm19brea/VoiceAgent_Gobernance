"""M4.5 — Blocking flag detection (design D4, spec R5)."""

from uuid import uuid4

from src.domain.enums import Dimension, EvidenceType
from src.domain.evidence import Evidence
from src.domain.scoring.flags import (
    FLAG_SESSION_NOT_COMPLETED,
    detect_blocking_flags,
)


def _completed_evidence() -> Evidence:
    return Evidence(
        session_id="call-1",
        evidence_type=EvidenceType.DIRECT,
        criterion="session_completed",
        conclusion="The session completed",
        dimension=Dimension.TECHNICAL,
        source_events=[uuid4()],
    )


def test_no_flags_when_session_completed_evidence_is_present() -> None:
    assert detect_blocking_flags([_completed_evidence()]) == []


def test_session_not_completed_flag_when_evidence_is_absent() -> None:
    flags = detect_blocking_flags([])

    assert len(flags) == 1
    assert flags[0].code == FLAG_SESSION_NOT_COMPLETED
    assert flags[0].reason  # records a human-readable reason (R5)


def test_flag_detection_is_deterministic() -> None:
    evidences = [_completed_evidence()]

    assert detect_blocking_flags(evidences) == detect_blocking_flags(evidences)
