from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: str = "data/ict_kg.db") -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self.connection() as conn:
            conn.executescript(
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
                );

                CREATE TABLE IF NOT EXISTS edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    source_node_id INTEGER NOT NULL,
                    target_node_id INTEGER NOT NULL,
                    relation_type TEXT NOT NULL,
                    weight REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(source_node_id) REFERENCES nodes(id),
                    FOREIGN KEY(target_node_id) REFERENCES nodes(id)
                );

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
                );

                CREATE TABLE IF NOT EXISTS external_refs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    source_system TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tenant_id, source_system, external_id)
                );

                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tenant_id, operation, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id INTEGER,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS ingestion_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    chunk_hash TEXT NOT NULL,
                    node_id INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tenant_id, source_system, external_id, chunk_hash)
                );

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
                );
                """
            )

    def audit(self, tenant_id: str, actor: str, action: str, entity_type: str, entity_id: int | None, payload: dict[str, Any]) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (tenant_id, actor, action, entity_type, entity_id, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (tenant_id, actor, action, entity_type, entity_id, self.dumps(payload)),
            )

    def create_ingestion_job(self, tenant_id: str, source_system: str, source: str, domain: str) -> int:
        with self.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO ingestion_jobs (tenant_id, source_system, source, domain, status, result)
                VALUES (?, ?, ?, ?, 'queued', '{}')
                """,
                (tenant_id, source_system, source, domain),
            )
        return int(cur.lastrowid)

    def update_ingestion_job(self, job_id: int, status: str, result: dict[str, Any] | None = None, error: str | None = None) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE ingestion_jobs
                SET status = ?, result = ?, error = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, self.dumps(result or {}), error, job_id),
            )

    def get_ingestion_job(self, job_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["result"] = self.loads(payload.get("result", "{}"))
        return payload


    def list_ingestion_jobs(self, tenant_id: str, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        with self.connection() as conn:
            total_row = conn.execute("SELECT COUNT(*) AS c FROM ingestion_jobs WHERE tenant_id = ?", (tenant_id,)).fetchone()
            rows = conn.execute(
                """
                SELECT * FROM ingestion_jobs
                WHERE tenant_id = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (tenant_id, limit, offset),
            ).fetchall()
        jobs: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["result"] = self.loads(payload.get("result", "{}"))
            jobs.append(payload)
        return jobs, int(total_row["c"]) if total_row else 0

    def cancel_ingestion_job(self, job_id: int) -> bool:
        with self.connection() as conn:
            row = conn.execute("SELECT status FROM ingestion_jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return False
            if row["status"] in ("completed", "failed", "cancelled"):
                return False
            conn.execute(
                "UPDATE ingestion_jobs SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (job_id,),
            )
        return True

    @staticmethod
    def dumps(data: dict[str, Any]) -> str:
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def loads(data: str) -> dict[str, Any]:
        return json.loads(data) if data else {}
