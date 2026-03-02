from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Role = Literal["admin", "writer", "reader"]


class TokenRequest(BaseModel):
    subject: str
    tenant_id: str = Field(default="default")
    role: Role = Field(default="writer")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class NodeCreate(BaseModel):
    tenant_id: str = Field(default="default")
    title: str
    content: str
    domain: str = Field(default="knowledge-base")
    source_system: str | None = None
    external_id: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeResponse(NodeCreate):
    id: int
    created_at: datetime


class EdgeCreate(BaseModel):
    tenant_id: str = Field(default="default")
    source_node_id: int
    target_node_id: int
    relation_type: str = Field(default="related_to")
    weight: float = Field(default=1.0, ge=0.0)


class MemoryCreate(BaseModel):
    tenant_id: str = Field(default="default")
    title: str
    content: str
    domain: str = Field(default="memory")
    source_system: str | None = None
    external_id: str | None = None
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeUpsert(NodeCreate):
    source_system: str
    external_id: str


class MemoryUpsert(MemoryCreate):
    source_system: str
    external_id: str


class MemoryResponse(MemoryCreate):
    id: int
    created_at: datetime


class QueryRequest(BaseModel):
    tenant_id: str = Field(default="default")
    text: str
    top_k: int = Field(default=5, ge=1, le=50)
    include: Literal["all", "nodes", "memories"] = "all"
    domain: str | None = None
    rerank: bool = True


class QueryResult(BaseModel):
    item_type: Literal["node", "memory"]
    id: int
    title: str
    content: str
    domain: str
    score: float
    semantic_score: float = 0.0
    rerank_score: float = 0.0
    explanation: str = ""


class QueryResponse(BaseModel):
    query: str
    results: list[QueryResult]


class GraphResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    memories: list[dict[str, Any]]


class NeighborResponse(BaseModel):
    node_id: int
    neighbors: list[dict[str, Any]]


class PathResponse(BaseModel):
    from_node_id: int
    to_node_id: int
    path: list[int]


class MultiPathResponse(BaseModel):
    from_node_id: int
    to_node_id: int
    paths: list[list[int]]


class IngestRequest(BaseModel):
    tenant_id: str = Field(default="default")
    source_system: Literal["github", "web"]
    source: str
    domain: str = Field(default="knowledge-base")


class IngestJobResponse(BaseModel):
    id: int
    tenant_id: str
    source_system: str
    source: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    error: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class IngestJobListResponse(BaseModel):
    jobs: list[IngestJobResponse]
    total: int
