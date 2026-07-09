"""add session marker uniqueness

Revision ID: d851eabb9809
Revises: 8e3c03e687de
Create Date: 2026-07-09 19:30:00.000000

Adds a partial unique index on ``events(session_id, event_type)`` scoped to
the post-terminal marker event types (``session.evaluation_triggered``,
``session.failed``). This backs the idempotent ``ON CONFLICT ... DO NOTHING``
insert used by the repository's ``append_marker_event`` — without it,
Postgres has no matching unique/exclusion constraint to infer the conflict
target from, and the insert raises.

The predicate string below MUST stay byte-identical to the one mirrored on
the ``EventModel`` ORM model (``src/infrastructure/db/models.py``), or the
two would describe different constraints.

DEPLOY CAVEAT: the server starts without running migrations (see commit
36aa530, "fix(api): start server without running migrations"), so this index
MUST be applied out-of-band (``alembic upgrade head`` against the target DB)
BEFORE this slice (session.evaluation_triggered) is deployed, or the
``ON CONFLICT`` insert in ``append_marker_event`` will raise in production.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'd851eabb9809'
down_revision: Union[str, Sequence[str], None] = '8e3c03e687de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        'uq_events_session_marker',
        'events',
        ['session_id', 'event_type'],
        unique=True,
        postgresql_where=text(
            "event_type IN ('session.evaluation_triggered', 'session.failed')"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('uq_events_session_marker', table_name='events')
