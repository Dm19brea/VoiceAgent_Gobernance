import dataclasses
from uuid import uuid4

import pytest

from src.domain.enums import Dimension, EvidenceType
from src.domain.evidence import Evidence


def _evidence() -> Evidence:
    return Evidence(
        session_id="call-1",
        evidence_type=EvidenceType.INFERRED,
        criterion="total_turns",
        conclusion="The session had 4 turns",
        dimension=Dimension.CONVERSATIONAL,
        source_events=[uuid4(), uuid4()],
        value=4.0,
    )


def test_evidence_construction() -> None:
    evidence = _evidence()

    assert evidence.evidence_type is EvidenceType.INFERRED
    assert evidence.dimension is Dimension.CONVERSATIONAL
    assert evidence.value == 4.0
    assert len(evidence.source_events) == 2
    assert evidence.evidence_id is not None
    assert evidence.generated_at is not None


def test_evidence_value_is_optional() -> None:
    evidence = Evidence(
        session_id="call-1",
        evidence_type=EvidenceType.DIRECT,
        criterion="session_completed",
        conclusion="The session completed",
        dimension=Dimension.TECHNICAL,
        source_events=[uuid4()],
    )

    assert evidence.value is None


def test_evidence_is_immutable() -> None:
    evidence = _evidence()

    with pytest.raises(dataclasses.FrozenInstanceError):
        evidence.conclusion = "changed"  # type: ignore[misc]
