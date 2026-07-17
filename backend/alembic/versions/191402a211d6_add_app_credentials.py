"""add app_credentials

Revision ID: 191402a211d6
Revises: dfeb7c2c1f0e
Create Date: 2026-07-17 00:00:00.000000

Singleton table (``id = 1`` enforced via CHECK constraint) holding the
dashboard username/password hash and the app-owned ``jwt_secret`` /
``vapi_webhook_secret``, plus ``session_epoch`` for global session
revocation. This table MUST stay byte-identical to the ``AppCredentials``
SQLAlchemy model (including the CHECK constraint), because tests build the
schema via ``Base.metadata.create_all`` instead of running this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "191402a211d6"
down_revision: Union[str, Sequence[str], None] = "dfeb7c2c1f0e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_credentials",
        sa.Column("id", sa.Integer(), nullable=False, default=1),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("jwt_secret", sa.String(), nullable=False),
        sa.Column("vapi_webhook_secret", sa.String(), nullable=False),
        sa.Column("session_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("id = 1", name="ck_app_credentials_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("app_credentials")
