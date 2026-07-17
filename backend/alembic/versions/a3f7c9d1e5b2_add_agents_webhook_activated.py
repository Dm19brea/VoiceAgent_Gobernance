"""add agents webhook_activated

Revision ID: a3f7c9d1e5b2
Revises: 191402a211d6
Create Date: 2026-07-17 00:00:00.000000

Non-destructive column enabling per-agent webhook credential activation.
Existing rows backfill to ``webhook_activated = false`` via ``server_default``
(NOT activated), matching the model's ``server_default`` so tests that build
the schema via ``Base.metadata.create_all`` stay in sync with real deploys.
Downgrade drops only the new column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a3f7c9d1e5b2"
down_revision: Union[str, Sequence[str], None] = "191402a211d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "webhook_activated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "webhook_activated")
