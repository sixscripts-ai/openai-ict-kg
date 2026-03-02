"""add ingestion jobs

Revision ID: 0002_ingestion_jobs
Revises: 0001_init
Create Date: 2026-03-02
"""

from alembic import op

revision = "0002_ingestion_jobs"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            source_system TEXT NOT NULL,
            source TEXT NOT NULL,
            domain TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_tenant_status ON ingestion_jobs (tenant_id, status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ingestion_jobs_tenant_status")
    op.execute("DROP TABLE IF EXISTS ingestion_jobs")
