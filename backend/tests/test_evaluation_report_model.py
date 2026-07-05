"""M4.6 — EvaluationReportModel schema (design D7)."""

from src.infrastructure.db.models import EvaluationReportModel


def test_evaluation_reports_table_name() -> None:
    assert EvaluationReportModel.__tablename__ == "evaluation_reports"


def test_evaluation_reports_has_expected_columns() -> None:
    columns = set(EvaluationReportModel.__table__.columns.keys())

    assert columns == {
        "report_id",
        "session_id",
        "score_global",
        "result",
        "score_conversational",
        "score_operational",
        "score_technical",
        "score_risk",
        "blocking_flags",
        "metrics",
        "generated_at",
    }


def test_one_report_per_session() -> None:
    assert EvaluationReportModel.__table__.columns["session_id"].unique is True
