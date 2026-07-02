from src.infrastructure.db.models import RawEvent


def test_raw_events_table_name() -> None:
    assert RawEvent.__tablename__ == "raw_events"


def test_raw_events_has_expected_columns() -> None:
    columns = set(RawEvent.__table__.columns.keys())

    assert columns == {"id", "event_type", "payload", "received_at"}
