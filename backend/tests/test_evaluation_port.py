"""M4.6 — Evaluator port: the deterministic engine conforms to the application boundary (R8)."""

from src.application.ports.evaluation import Evaluator
from src.domain.scoring.evaluator import DeterministicEvaluator


def test_deterministic_evaluator_satisfies_the_port() -> None:
    assert isinstance(DeterministicEvaluator(), Evaluator)


def test_object_without_evaluate_is_not_an_evaluator() -> None:
    assert not isinstance(object(), Evaluator)
