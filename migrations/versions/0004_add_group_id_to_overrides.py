"""Add group_id to overrides

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-16
"""

from __future__ import annotations

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # 1. Add column (idempotent)
    op.execute(
        "ALTER TABLE overrides ADD COLUMN IF NOT EXISTS group_id INTEGER DEFAULT 1 NOT NULL"
    )

    # 2. Index (idempotent)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_overrides_group_id ON overrides(group_id)"
    )

    # 3. Foreign key (idempotent)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_overrides_group_id'
            ) THEN
                ALTER TABLE overrides
                    ADD CONSTRAINT fk_overrides_group_id
                    FOREIGN KEY (group_id) REFERENCES groups(id)
                    ON DELETE CASCADE;
            END IF;
        END $$;
        """
    )

    # 4. Update unique constraint
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_override'
            ) THEN
                ALTER TABLE overrides DROP CONSTRAINT uq_override;
            END IF;
        END $$;
        """
    )
    op.create_unique_constraint(
        "uq_override", "overrides", ["date", "time", "group_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_override", "overrides", type_="unique")
    op.create_unique_constraint("uq_override", "overrides", ["date", "time"])

    op.drop_constraint("fk_overrides_group_id", "overrides", type_="foreignkey")
    op.drop_index(op.f("ix_overrides_group_id"), table_name="overrides")
    op.drop_column("overrides", "group_id")
