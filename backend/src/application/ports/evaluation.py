from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from src.domain.evaluation_report import EvaluationReport
from src.domain.evidence import Evidence
from src.domain.session import Session


@runtime_checkable
class Evaluator(Protocol):
    """Boundary that turns a session's evidences into an evaluation (design D6, R8).

    Synchronous and side-effect free: the deterministic engine in ``domain/scoring``
    implements it today. A future LLM-as-judge can implement the same shape without
    touching the domain; persistence stays with the repository, not the evaluator.
    """

    def evaluate(self, session: Session, evidences: Sequence[Evidence]) -> EvaluationReport: ...
