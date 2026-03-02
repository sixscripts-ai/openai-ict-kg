from __future__ import annotations

import os

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .auth import AUTH_MODE, create_access_token, decode_access_token, role_allowed
from .models import (
    EdgeCreate,
    GraphResponse,
    IngestJobListResponse,
    IngestJobResponse,
    IngestRequest,
    MemoryCreate,
    MemoryResponse,
    MemoryUpsert,
    MultiPathResponse,
    NeighborResponse,
    NodeCreate,
    NodeResponse,
    NodeUpsert,
    PathResponse,
    QueryRequest,
    QueryResponse,
    TokenRequest,
    TokenResponse,
)
from .service import KnowledgeGraphService

app = FastAPI(title="Personal ICT Knowledge Graph", version="0.5.0")

# Allow requests from any origin (Vercel frontend, local dev, etc.)
_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = KnowledgeGraphService()


def get_identity(authorization: str = Header(default="")) -> dict[str, str]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    return {"subject": str(payload["sub"]), "tenant_id": str(payload["tenant_id"]), "role": str(payload.get("role", "reader"))}


def require_role(identity: dict[str, str], required: str) -> None:
    if not role_allowed(identity["role"], required):
        raise HTTPException(status_code=403, detail="Insufficient role")


def audit(identity: dict[str, str], action: str, entity_type: str, entity_id: int | None, payload: dict) -> None:
    service.db.audit(
        tenant_id=identity["tenant_id"],
        actor=identity["subject"],
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "auth_mode": AUTH_MODE}


@app.get("/ready")
def ready() -> dict[str, str]:
    return service.ready()


@app.get("/metrics")
def metrics(identity: dict[str, str] = Depends(get_identity)) -> dict[str, int]:
    require_role(identity, "admin")
    return service.get_metrics()


@app.post("/auth/token", response_model=TokenResponse)
def issue_token(payload: TokenRequest) -> TokenResponse:
    if AUTH_MODE == "jwks":
        raise HTTPException(status_code=400, detail="Local token minting disabled in jwks mode")
    return TokenResponse(access_token=create_access_token(payload.subject, payload.tenant_id, payload.role))


@app.post("/nodes", response_model=NodeResponse)
def create_node(payload: NodeCreate, identity: dict[str, str] = Depends(get_identity)) -> dict:
    require_role(identity, "writer")
    if payload.tenant_id != identity["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    row = service.add_node(payload)
    audit(identity, "create_node", "node", row["id"], payload.model_dump())
    return row


@app.put("/nodes/upsert", response_model=NodeResponse)
def upsert_node(payload: NodeUpsert, identity: dict[str, str] = Depends(get_identity)) -> dict:
    require_role(identity, "writer")
    if payload.tenant_id != identity["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    row = service.upsert_node(payload)
    audit(identity, "upsert_node", "node", row["id"], payload.model_dump())
    return row


@app.post("/edges")
def create_edge(payload: EdgeCreate, identity: dict[str, str] = Depends(get_identity)) -> dict:
    require_role(identity, "writer")
    if payload.tenant_id != identity["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    row = service.add_edge(payload)
    audit(identity, "create_edge", "edge", row["id"], payload.model_dump())
    return row


@app.post("/memories", response_model=MemoryResponse)
def create_memory(payload: MemoryCreate, identity: dict[str, str] = Depends(get_identity)) -> dict:
    require_role(identity, "writer")
    if payload.tenant_id != identity["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    row = service.add_memory(payload)
    audit(identity, "create_memory", "memory", row["id"], payload.model_dump())
    return row


@app.put("/memories/upsert", response_model=MemoryResponse)
def upsert_memory(payload: MemoryUpsert, identity: dict[str, str] = Depends(get_identity)) -> dict:
    require_role(identity, "writer")
    if payload.tenant_id != identity["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    row = service.upsert_memory(payload)
    audit(identity, "upsert_memory", "memory", row["id"], payload.model_dump())
    return row


@app.post("/query", response_model=QueryResponse)
def query(payload: QueryRequest, identity: dict[str, str] = Depends(get_identity)) -> QueryResponse:
    require_role(identity, "reader")
    if payload.tenant_id != identity["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    rows = service.query(payload)
    audit(identity, "query", "search", None, payload.model_dump())
    return QueryResponse(query=payload.text, results=rows)


@app.get("/graph", response_model=GraphResponse)
def get_graph(tenant_id: str = Query(default="default"), identity: dict[str, str] = Depends(get_identity)) -> GraphResponse:
    require_role(identity, "reader")
    if tenant_id != identity["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    graph = service.graph(tenant_id=tenant_id)
    return GraphResponse(**graph)


@app.get("/nodes/{node_id}/neighbors", response_model=NeighborResponse)
def get_neighbors(
    node_id: int,
    depth: int = Query(default=1, ge=1, le=5),
    relation_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    identity: dict[str, str] = Depends(get_identity),
) -> NeighborResponse:
    require_role(identity, "reader")
    neighbors = service.neighbors(identity["tenant_id"], node_id=node_id, depth=depth, relation_type=relation_type, limit=limit)
    return NeighborResponse(node_id=node_id, neighbors=neighbors)


@app.get("/paths", response_model=PathResponse)
def get_path(
    from_node_id: int,
    to_node_id: int,
    max_hops: int = Query(default=6, ge=1, le=10),
    relation_type: str | None = Query(default=None),
    identity: dict[str, str] = Depends(get_identity),
) -> PathResponse:
    require_role(identity, "reader")
    path = service.shortest_path(identity["tenant_id"], from_node_id=from_node_id, to_node_id=to_node_id, max_hops=max_hops, relation_type=relation_type)
    return PathResponse(from_node_id=from_node_id, to_node_id=to_node_id, path=path)


@app.get("/paths/multi", response_model=MultiPathResponse)
def get_multi_paths(
    from_node_id: int,
    to_node_id: int,
    max_hops: int = Query(default=6, ge=1, le=10),
    k: int = Query(default=3, ge=1, le=10),
    relation_type: str | None = Query(default=None),
    identity: dict[str, str] = Depends(get_identity),
) -> MultiPathResponse:
    require_role(identity, "reader")
    paths = service.k_paths(identity["tenant_id"], from_node_id=from_node_id, to_node_id=to_node_id, max_hops=max_hops, k=k, relation_type=relation_type)
    return MultiPathResponse(from_node_id=from_node_id, to_node_id=to_node_id, paths=paths)


@app.post("/ingest/jobs", response_model=IngestJobResponse)
def create_ingest_job(
    payload: IngestRequest,
    background_tasks: BackgroundTasks,
    identity: dict[str, str] = Depends(get_identity),
) -> IngestJobResponse:
    require_role(identity, "writer")
    if payload.tenant_id != identity["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    job = service.create_ingestion_job(payload.tenant_id, payload.source_system, payload.source, payload.domain)
    background_tasks.add_task(service.process_ingestion_job, job["id"])
    audit(identity, "ingest_queued", "ingest_job", job["id"], payload.model_dump())
    return IngestJobResponse(**job)


@app.get("/ingest/jobs/{job_id}", response_model=IngestJobResponse)
def get_ingest_job(job_id: int, identity: dict[str, str] = Depends(get_identity)) -> IngestJobResponse:
    require_role(identity, "reader")
    job = service.get_ingestion_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["tenant_id"] != identity["tenant_id"]:
        raise HTTPException(status_code=403, detail="Tenant mismatch")
    return IngestJobResponse(**job)


@app.get("/ingest/jobs", response_model=IngestJobListResponse)
def list_ingest_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    identity: dict[str, str] = Depends(get_identity),
) -> IngestJobListResponse:
    require_role(identity, "reader")
    jobs, total = service.list_ingestion_jobs(identity["tenant_id"], limit=limit, offset=offset)
    return IngestJobListResponse(jobs=[IngestJobResponse(**j) for j in jobs], total=total)


@app.post("/ingest/jobs/{job_id}/cancel")
def cancel_ingest_job(job_id: int, identity: dict[str, str] = Depends(get_identity)) -> dict[str, bool]:
    require_role(identity, "writer")
    ok = service.cancel_ingestion_job(job_id=job_id, tenant_id=identity["tenant_id"])
    if not ok:
        raise HTTPException(status_code=409, detail="Job cannot be cancelled")
    audit(identity, "ingest_cancelled", "ingest_job", job_id, {"job_id": job_id})
    return {"cancelled": True}
