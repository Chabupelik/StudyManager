from __future__ import annotations

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE group_members ADD COLUMN IF NOT EXISTS is_duty_exempt BOOLEAN DEFAULT FALSE NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("group_members", "is_duty_exempt")
