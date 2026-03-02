from __future__ import annotations

import asyncio
import hashlib
from collections import Counter, deque
from typing import Any

from .db import Database
from .embeddings import (
    cosine_similarity,
    decode_embedding,
    encode_embedding,
    get_embedding_provider,
    get_reranker,
)
from .ingest.connectors import ingest_github_repo_async, ingest_web_page_async
from .models import EdgeCreate, MemoryCreate, MemoryUpsert, NodeCreate, NodeUpsert, QueryRequest, QueryResult


class KnowledgeGraphService:
    def __init__(self, db: Database | None = None) -> None:
        self.db = db or Database()
        self.embedding_provider = get_embedding_provider()
        self.reranker = get_reranker()
        self.metrics: Counter[str] = Counter()

    def _embed(self, title: str, content: str) -> tuple[str, str]:
        emb = self.embedding_provider.embed(f"{title}\n{content}")
        return encode_embedding(emb), self.embedding_provider.name

    def add_node(self, data: NodeCreate) -> dict[str, Any]:
        self.metrics["node_writes"] += 1
        if data.idempotency_key:
            hit = self._idempotency_lookup(data.tenant_id, "create_node", data.idempotency_key)
            if hit:
                return self._get_entity("node", hit)

        embedding, model_name = self._embed(data.title, data.content)
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO nodes (tenant_id, title, content, domain, embedding_model, metadata, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (data.tenant_id, data.title, data.content, data.domain, model_name, self.db.dumps(data.metadata), embedding),
            )
            row = conn.execute("SELECT * FROM nodes WHERE id = ?", (cur.lastrowid,)).fetchone()
            if data.source_system and data.external_id:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO external_refs (tenant_id, entity_type, entity_id, source_system, external_id)
                    VALUES (?, 'node', ?, ?, ?)
                    """,
                    (data.tenant_id, cur.lastrowid, data.source_system, data.external_id),
                )
            if data.idempotency_key:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO idempotency_keys (tenant_id, operation, idempotency_key, entity_type, entity_id)
                    VALUES (?, 'create_node', ?, 'node', ?)
                    """,
                    (data.tenant_id, data.idempotency_key, cur.lastrowid),
                )
        return self._hydrate(row)

    def upsert_node(self, data: NodeUpsert) -> dict[str, Any]:
        existing = self._find_by_external_ref(data.tenant_id, data.source_system, data.external_id, "node")
        if existing:
            return existing
        return self.add_node(data)

    def add_edge(self, data: EdgeCreate) -> dict[str, Any]:
        self.metrics["edge_writes"] += 1
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO edges (tenant_id, source_node_id, target_node_id, relation_type, weight)
                VALUES (?, ?, ?, ?, ?)
                """,
                (data.tenant_id, data.source_node_id, data.target_node_id, data.relation_type, data.weight),
            )
            row = conn.execute("SELECT * FROM edges WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def add_memory(self, data: MemoryCreate) -> dict[str, Any]:
        self.metrics["memory_writes"] += 1
        if data.idempotency_key:
            hit = self._idempotency_lookup(data.tenant_id, "create_memory", data.idempotency_key)
            if hit:
                return self._get_entity("memory", hit)

        embedding, model_name = self._embed(data.title, data.content)
        with self.db.connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO memories (tenant_id, title, content, domain, embedding_model, metadata, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (data.tenant_id, data.title, data.content, data.domain, model_name, self.db.dumps(data.metadata), embedding),
            )
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (cur.lastrowid,)).fetchone()
            if data.source_system and data.external_id:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO external_refs (tenant_id, entity_type, entity_id, source_system, external_id)
                    VALUES (?, 'memory', ?, ?, ?)
                    """,
                    (data.tenant_id, cur.lastrowid, data.source_system, data.external_id),
                )
            if data.idempotency_key:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO idempotency_keys (tenant_id, operation, idempotency_key, entity_type, entity_id)
                    VALUES (?, 'create_memory', ?, 'memory', ?)
                    """,
                    (data.tenant_id, data.idempotency_key, cur.lastrowid),
                )
        return self._hydrate(row)

    def upsert_memory(self, data: MemoryUpsert) -> dict[str, Any]:
        existing = self._find_by_external_ref(data.tenant_id, data.source_system, data.external_id, "memory")
        if existing:
            return existing
        return self.add_memory(data)

    def query(self, request: QueryRequest) -> list[QueryResult]:
        self.metrics["queries"] += 1
        query_embedding = self.embedding_provider.embed(request.text)
        results: list[QueryResult] = []

        with self.db.connection() as conn:
            if request.include in ("all", "nodes"):
                query = "SELECT * FROM nodes WHERE tenant_id = ?"
                params: list[Any] = [request.tenant_id]
                if request.domain:
                    query += " AND domain = ?"
                    params.append(request.domain)
                for row in conn.execute(query + " ORDER BY id DESC", params):
                    semantic = cosine_similarity(query_embedding, decode_embedding(row["embedding"]))
                    rerank = self.reranker.score(request.text, row["title"], row["content"], row["created_at"]) if request.rerank else 0.0
                    score = (0.7 * semantic) + (0.3 * rerank)
                    results.append(
                        QueryResult(
                            item_type="node",
                            id=row["id"],
                            title=row["title"],
                            content=row["content"],
                            domain=row["domain"],
                            score=score,
                            semantic_score=semantic,
                            rerank_score=rerank,
                            explanation=f"semantic={semantic:.3f};rerank={rerank:.3f}",
                        )
                    )

            if request.include in ("all", "memories"):
                query = "SELECT * FROM memories WHERE tenant_id = ?"
                params = [request.tenant_id]
                if request.domain:
                    query += " AND domain = ?"
                    params.append(request.domain)
                for row in conn.execute(query + " ORDER BY id DESC", params):
                    semantic = cosine_similarity(query_embedding, decode_embedding(row["embedding"]))
                    rerank = self.reranker.score(request.text, row["title"], row["content"], row["created_at"]) if request.rerank else 0.0
                    score = (0.7 * semantic) + (0.3 * rerank)
                    results.append(
                        QueryResult(
                            item_type="memory",
                            id=row["id"],
                            title=row["title"],
                            content=row["content"],
                            domain=row["domain"],
                            score=score,
                            semantic_score=semantic,
                            rerank_score=rerank,
                            explanation=f"semantic={semantic:.3f};rerank={rerank:.3f}",
                        )
                    )

        return sorted(results, key=lambda r: r.score, reverse=True)[: request.top_k]

    def graph(self, tenant_id: str = "default") -> dict[str, list[dict[str, Any]]]:
        with self.db.connection() as conn:
            nodes = [self._hydrate(row) for row in conn.execute("SELECT * FROM nodes WHERE tenant_id = ? ORDER BY id", (tenant_id,))]
            edges = [dict(row) for row in conn.execute("SELECT * FROM edges WHERE tenant_id = ? ORDER BY id", (tenant_id,))]
            memories = [self._hydrate(row) for row in conn.execute("SELECT * FROM memories WHERE tenant_id = ? ORDER BY id", (tenant_id,))]
        return {"nodes": nodes, "edges": edges, "memories": memories}

    def neighbors(self, tenant_id: str, node_id: int, depth: int = 1, relation_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        frontier = {node_id}
        seen = {node_id}
        output: list[dict[str, Any]] = []
        with self.db.connection() as conn:
            for _ in range(max(depth, 1)):
                if not frontier or len(output) >= limit:
                    break
                placeholders = ",".join(["?"] * len(frontier))
                base = (
                    f"SELECT * FROM edges WHERE tenant_id = ? AND (source_node_id IN ({placeholders}) OR target_node_id IN ({placeholders}))"
                )
                params: list[Any] = [tenant_id, *frontier, *frontier]
                if relation_type:
                    base += " AND relation_type = ?"
                    params.append(relation_type)
                rows = conn.execute(base, params).fetchall()
                next_frontier: set[int] = set()
                for row in rows:
                    if len(output) >= limit:
                        break
                    source = int(row["source_node_id"])
                    target = int(row["target_node_id"])
                    output.append(dict(row))
                    if source not in seen:
                        seen.add(source)
                        next_frontier.add(source)
                    if target not in seen:
                        seen.add(target)
                        next_frontier.add(target)
                frontier = next_frontier
        return output

    def shortest_path(self, tenant_id: str, from_node_id: int, to_node_id: int, max_hops: int = 6, relation_type: str | None = None) -> list[int]:
        paths = self.k_paths(tenant_id, from_node_id, to_node_id, max_hops=max_hops, k=1, relation_type=relation_type)
        return paths[0] if paths else []

    def k_paths(
        self,
        tenant_id: str,
        from_node_id: int,
        to_node_id: int,
        max_hops: int = 6,
        k: int = 3,
        relation_type: str | None = None,
    ) -> list[list[int]]:
        adjacency: dict[int, set[int]] = {}
        with self.db.connection() as conn:
            sql = "SELECT source_node_id, target_node_id, relation_type FROM edges WHERE tenant_id = ?"
            for row in conn.execute(sql, (tenant_id,)):
                if relation_type and row["relation_type"] != relation_type:
                    continue
                source = int(row["source_node_id"])
                target = int(row["target_node_id"])
                adjacency.setdefault(source, set()).add(target)
                adjacency.setdefault(target, set()).add(source)

        found: list[list[int]] = []
        queue: deque[list[int]] = deque([[from_node_id]])
        while queue and len(found) < k:
            path = queue.popleft()
            if len(path) > max_hops + 1:
                continue
            head = path[-1]
            if head == to_node_id:
                found.append(path)
                continue
            for neighbor in adjacency.get(head, set()):
                if neighbor in path:
                    continue
                queue.append(path + [neighbor])
        return found

    async def ingest_source_async(self, tenant_id: str, source_system: str, source: str, domain: str) -> dict[str, Any]:
        if source_system == "github":
            items = await ingest_github_repo_async(source)
        else:
            items = [await ingest_web_page_async(source)]

        inserted = 0
        skipped = 0
        for item in items:
            for chunk in self._chunk_text(item.content):
                chunk_hash = hashlib.sha256(chunk.encode("utf-8")).hexdigest()
                if self._chunk_exists(tenant_id, item.source_system, item.external_id, chunk_hash):
                    skipped += 1
                    continue
                node = self.upsert_node(
                    NodeUpsert(
                        tenant_id=tenant_id,
                        title=item.title,
                        content=chunk,
                        domain=domain,
                        source_system=item.source_system,
                        external_id=f"{item.external_id}:{chunk_hash[:12]}",
                        metadata={"source": source},
                    )
                )
                self._mark_chunk(tenant_id, item.source_system, item.external_id, chunk_hash, node["id"])
                inserted += 1

        self.metrics["ingested_chunks"] += inserted
        return {"inserted_chunks": inserted, "skipped_chunks": skipped, "items": len(items)}

    def process_ingestion_job(self, job_id: int) -> None:
        job = self.db.get_ingestion_job(job_id)
        if not job:
            return
        self.db.update_ingestion_job(job_id, status="running", result={})
        try:
            result = asyncio.run(self.ingest_source_async(job["tenant_id"], job["source_system"], job["source"], job["domain"]))
            self.db.update_ingestion_job(job_id, status="completed", result=result)
        except Exception as exc:  # noqa: BLE001
            self.metrics["ingest_failures"] += 1
            self.db.update_ingestion_job(job_id, status="failed", error=str(exc), result={})

    def create_ingestion_job(self, tenant_id: str, source_system: str, source: str, domain: str) -> dict[str, Any]:
        job_id = self.db.create_ingestion_job(tenant_id, source_system, source, domain)
        job = self.db.get_ingestion_job(job_id)
        if job is None:
            raise RuntimeError("Failed to create ingestion job")
        self.metrics["ingestion_jobs"] += 1
        return job

    def get_ingestion_job(self, job_id: int) -> dict[str, Any] | None:
        return self.db.get_ingestion_job(job_id)


    def list_ingestion_jobs(self, tenant_id: str, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self.db.list_ingestion_jobs(tenant_id=tenant_id, limit=limit, offset=offset)

    def cancel_ingestion_job(self, job_id: int, tenant_id: str) -> bool:
        job = self.db.get_ingestion_job(job_id)
        if not job or job["tenant_id"] != tenant_id:
            return False
        cancelled = self.db.cancel_ingestion_job(job_id)
        if cancelled:
            self.metrics["ingestion_cancellations"] += 1
        return cancelled

    def ready(self) -> dict[str, str]:
        with self.db.connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ready", "embedding_provider": self.embedding_provider.name}

    def get_metrics(self) -> dict[str, int]:
        return dict(self.metrics)

    def _chunk_exists(self, tenant_id: str, source_system: str, external_id: str, chunk_hash: str) -> bool:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM ingestion_chunks
                WHERE tenant_id = ? AND source_system = ? AND external_id = ? AND chunk_hash = ?
                """,
                (tenant_id, source_system, external_id, chunk_hash),
            ).fetchone()
        return row is not None

    def _mark_chunk(self, tenant_id: str, source_system: str, external_id: str, chunk_hash: str, node_id: int) -> None:
        with self.db.connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO ingestion_chunks (tenant_id, source_system, external_id, chunk_hash, node_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tenant_id, source_system, external_id, chunk_hash, node_id),
            )

    @staticmethod
    def _chunk_text(text: str, max_chars: int = 1500) -> list[str]:
        normalized = " ".join(text.split())
        if not normalized:
            return []
        return [normalized[i : i + max_chars] for i in range(0, len(normalized), max_chars)]

    def _find_by_external_ref(self, tenant_id: str, source_system: str, external_id: str, entity_type: str) -> dict[str, Any] | None:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT entity_id FROM external_refs
                WHERE tenant_id = ? AND source_system = ? AND external_id = ? AND entity_type = ?
                """,
                (tenant_id, source_system, external_id, entity_type),
            ).fetchone()
            if not row:
                return None
        return self._get_entity(entity_type, row["entity_id"])

    def _get_entity(self, entity_type: str, entity_id: int) -> dict[str, Any]:
        with self.db.connection() as conn:
            table = "nodes" if entity_type == "node" else "memories"
            row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (entity_id,)).fetchone()
        return self._hydrate(row)

    def _idempotency_lookup(self, tenant_id: str, operation: str, key: str) -> int | None:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT entity_id FROM idempotency_keys
                WHERE tenant_id = ? AND operation = ? AND idempotency_key = ?
                """,
                (tenant_id, operation, key),
            ).fetchone()
        return None if row is None else int(row["entity_id"])

    def _hydrate(self, row: Any) -> dict[str, Any]:
        payload = dict(row)
        payload["metadata"] = self.db.loads(payload.get("metadata", "{}"))
        payload.pop("embedding", None)
        return payload
