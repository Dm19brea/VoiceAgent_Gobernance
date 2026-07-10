"""add event session sequence uniqueness

Revision ID: c6f1e8a2b4d7
Revises: d851eabb9809
Create Date: 2026-07-09 22:30:00.000000

Canonical event sequence assignment is serialized by the repository. This
constraint is defense in depth: it rejects any collision caused by a future
append path that bypasses the session row lock. The preflight deliberately
fails rather than silently deleting historical governance records.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "c6f1e8a2b4d7"
down_revision: Union[str, Sequence[str], None] = "d851eabb9809"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fail with a concrete collision before enforcing the invariant."""
    collision = op.get_bind().execute(
        text(
            """
            SELECT session_id, sequence_number, COUNT(*) AS event_count
            FROM events
            GROUP BY session_id, sequence_number
            HAVING COUNT(*) > 1
            ORDER BY session_id, sequence_number
            LIMIT 1
            """
        )
    ).mappings().first()
    if collision is not None:
        raise RuntimeError(
            "Cannot add uq_events_session_sequence while historical sequence "
            f"collisions exist: session_id={collision['session_id']!r}, "
            f"sequence_number={collision['sequence_number']}, count={collision['event_count']}. "
            "Resolve collisions explicitly before retrying the migration."
        )
    op.create_unique_constraint("uq_events_session_sequence", "events", ["session_id", "sequence_number"])


def downgrade() -> None:
    op.drop_constraint("uq_events_session_sequence", "events", type_="unique")
