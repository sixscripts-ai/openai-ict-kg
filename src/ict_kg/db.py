from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
import psycopg2.extras


_DATABASE_URL = os.environ.get("DATABASE_URL", "")


class Database:
    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or _DATABASE_URL
        if not self.dsn:
            raise RuntimeError(
                "DATABASE_URL environment variable is required for PostgreSQL backend."
            )
        self._init_db()

    @contextmanager
    def connection(self) -> Generator[psycopg2.extensions.connection, None, None]:
        conn = psycopg2.connect(self.dsn)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _execute(self, conn: Any, sql: str, params: tuple = ()) -> Any:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return cur

    def _init_db(self) -> None:
        stmts = [
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                domain TEXT NOT NULL,
                embedding_model TEXT NOT NULL DEFAULT 'local-deterministic-v1',
                metadata TEXT NOT NULL,
                embedding TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS edges (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                source_node_id INTEGER NOT NULL REFERENCES nodes(id),
                target_node_id INTEGER NOT NULL REFERENCES nodes(id),
                relation_type TEXT NOT NULL,
                weight REAL NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS memories (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL DEFAULT 'default',
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                domain TEXT NOT NULL,
                embedding_model TEXT NOT NULL DEFAULT 'local-deterministic-v1',
                metadata TEXT NOT NULL,
                embedding TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS external_refs (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                source_system TEXT NOT NULL,
                external_id TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(tenant_id, source_system, external_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS idempotency_keys (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(tenant_id, operation, idempotency_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                payload TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ingestion_chunks (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                source_system TEXT NOT NULL,
                external_id TEXT NOT NULL,
                chunk_hash TEXT NOT NULL,
                node_id INTEGER,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(tenant_id, source_system, external_id, chunk_hash)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS ingestion_jobs (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                source_system TEXT NOT NULL,
                source TEXT NOT NULL,
                domain TEXT NOT NULL,
                status TEXT NOT NULL,
                error TEXT,
                result TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
        ]
        with self.connection() as conn:
            for stmt in stmts:
                self._execute(conn, stmt)

    def audit(self, tenant_id: str, actor: str, action: str, entity_type: str, entity_id: int | None, payload: dict[str, Any]) -> None:
        with self.connection() as conn:
            self._execute(
                conn,
                """
                INSERT INTO audit_logs (tenant_id, actor, action, entity_type, entity_id, payload)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (tenant_id, actor, action, entity_type, entity_id, self.dumps(payload)),
            )

    def create_ingestion_job(self, tenant_id: str, source_system: str, source: str, domain: str) -> int:
        with self.connection() as conn:
            cur = self._execute(
                conn,
                """
                INSERT INTO ingestion_jobs (tenant_id, source_system, source, domain, status, result)
                VALUES (%s, %s, %s, %s, 'queued', '{}')
                RETURNING id
                """,
                (tenant_id, source_system, source, domain),
            )
            row = cur.fetchone()
        return int(row["id"])

    def update_ingestion_job(self, job_id: int, status: str, result: dict[str, Any] | None = None, error: str | None = None) -> None:
        with self.connection() as conn:
            self._execute(
                conn,
                """
                UPDATE ingestion_jobs
                SET status = %s, result = %s, error = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (status, self.dumps(result or {}), error, job_id),
            )

    def get_ingestion_job(self, job_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            cur = self._execute(conn, "SELECT * FROM ingestion_jobs WHERE id = %s", (job_id,))
            row = cur.fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["result"] = self.loads(payload.get("result", "{}"))
        # Normalize datetime fields to strings for JSON serialisation
        for k in ("created_at", "updated_at"):
            if payload.get(k) is not None:
                payload[k] = str(payload[k])
        return payload

    def list_ingestion_jobs(self, tenant_id: str, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        with self.connection() as conn:
            total_cur = self._execute(conn, "SELECT COUNT(*) AS c FROM ingestion_jobs WHERE tenant_id = %s", (tenant_id,))
            total_row = total_cur.fetchone()
            rows_cur = self._execute(
                conn,
                """
                SELECT * FROM ingestion_jobs
                WHERE tenant_id = %s
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (tenant_id, limit, offset),
            )
            rows = rows_cur.fetchall()
        jobs: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["result"] = self.loads(payload.get("result", "{}"))
            for k in ("created_at", "updated_at"):
                if payload.get(k) is not None:
                    payload[k] = str(payload[k])
            jobs.append(payload)
        return jobs, int(total_row["c"]) if total_row else 0

    def cancel_ingestion_job(self, job_id: int) -> bool:
        with self.connection() as conn:
            cur = self._execute(conn, "SELECT status FROM ingestion_jobs WHERE id = %s", (job_id,))
            row = cur.fetchone()
            if not row:
                return False
            if row["status"] in ("completed", "failed", "cancelled"):
                return False
            self._execute(
                conn,
                "UPDATE ingestion_jobs SET status = 'cancelled', updated_at = NOW() WHERE id = %s",
                (job_id,),
            )
        return True

    @staticmethod
    def dumps(data: dict[str, Any]) -> str:
        return json.dumps(data, separators=(",", ":"), ensure_ascii=False)

    @staticmethod
    def loads(data: str) -> dict[str, Any]:
        return json.loads(data) if data else {}
