from __future__ import annotations

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS is_homeroom SMALLINT NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE lessons ADD COLUMN IF NOT EXISTS is_hidden SMALLINT NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.drop_column("lessons", "is_homeroom")
    op.drop_column("lessons", "is_hidden")
