"""init schema

Revision ID: 0001_init
Revises:
Create Date: 2026-03-02
"""

from alembic import op

revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL DEFAULT 'default',
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            domain TEXT NOT NULL,
            embedding_model TEXT NOT NULL DEFAULT 'local-deterministic-v1',
            metadata TEXT NOT NULL,
            embedding TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL DEFAULT 'default',
            source_node_id INTEGER NOT NULL,
            target_node_id INTEGER NOT NULL,
            relation_type TEXT NOT NULL,
            weight REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL DEFAULT 'default',
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            domain TEXT NOT NULL,
            embedding_model TEXT NOT NULL DEFAULT 'local-deterministic-v1',
            metadata TEXT NOT NULL,
            embedding TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS external_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            source_system TEXT NOT NULL,
            external_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, source_system, external_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, operation, idempotency_key)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id INTEGER,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ingestion_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            source_system TEXT NOT NULL,
            external_id TEXT NOT NULL,
            chunk_hash TEXT NOT NULL,
            node_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, source_system, external_id, chunk_hash)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_chunks")
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS idempotency_keys")
    op.execute("DROP TABLE IF EXISTS external_refs")
    op.execute("DROP TABLE IF EXISTS memories")
    op.execute("DROP TABLE IF EXISTS edges")
    op.execute("DROP TABLE IF EXISTS nodes")
