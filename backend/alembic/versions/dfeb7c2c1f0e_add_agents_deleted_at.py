"""add agents deleted_at

Revision ID: dfeb7c2c1f0e
Revises: c6f1e8a2b4d7
Create Date: 2026-07-15 00:00:00.000000

Nullable, non-destructive column enabling soft delete of agents (R2/R4).
Existing rows get ``deleted_at = NULL`` (still active); no backfill, no data
loss. Downgrade drops the column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "dfeb7c2c1f0e"
down_revision: Union[str, Sequence[str], None] = "c6f1e8a2b4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("agents", "deleted_at")
