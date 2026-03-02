# Personal ICT Knowledge Graph

A modular, deployable knowledge graph + memory API for ICT concepts, trading notes, and cross-system memory.

## What this program does
- Stores tenant-scoped ICT concepts, trade notes, and memory events.
- Connects concepts with graph edges and traverses neighbors/paths.
- Runs hybrid retrieval (embedding + reranker) with explainable scores.
- Ingests external sources through durable ingestion jobs.
- Provides auth, RBAC, audit logs, migration support, and CI checks.

## Features
- JWT auth with roles (`admin`, `writer`, `reader`) and optional JWKS mode.
- Tenant-scoped graph + memory persistence.
- Idempotent upserts + external reference mapping.
- Explainable retrieval (`semantic_score`, `rerank_score`, `explanation`).
- Graph reasoning APIs (neighbors, shortest path, multi-path).
- Durable ingestion jobs: queued/running/completed/failed/cancelled.
- Async ingestion with chunking + dedupe.
- Audit logging + `/ready` + `/metrics`.
- Alembic migrations + CI migration round-trip + retrieval benchmark gate.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn src.ict_kg.api:app --reload
```

## How to use this program

### 1) Choose auth mode
- Local mode (default): app can mint tokens via `/auth/token`.
- JWKS mode (production-like): set:
  - `ICT_KG_AUTH_MODE=jwks`
  - `ICT_KG_JWKS_URL=...`
  - optional `ICT_KG_JWT_ISSUER`, `ICT_KG_JWT_AUDIENCE`

### 2) Get a token (local mode)

```bash
curl -X POST http://127.0.0.1:8000/auth/token \
  -H "content-type: application/json" \
  -d '{"subject":"me","tenant_id":"default","role":"admin"}'
```

Use: `Authorization: Bearer <token>`.

### 3) Write data
- `POST /nodes`
- `PUT /nodes/upsert`
- `POST /edges`
- `POST /memories`
- `PUT /memories/upsert`

### 4) Query and reason
- `POST /query`
- `GET /graph?tenant_id=`
- `GET /nodes/{node_id}/neighbors?depth=&relation_type=&limit=`
- `GET /paths?from_node_id=&to_node_id=&max_hops=&relation_type=`
- `GET /paths/multi?from_node_id=&to_node_id=&k=&max_hops=&relation_type=`

### 5) Run ingestion jobs
- Create job: `POST /ingest/jobs`
- Get one job: `GET /ingest/jobs/{job_id}`
- List jobs: `GET /ingest/jobs?limit=&offset=`
- Cancel queued/running: `POST /ingest/jobs/{job_id}/cancel`

Optional worker loop:

```bash
PYTHONPATH=src python scripts/ingestion_worker.py
PYTHONPATH=src python scripts/supabase_check.py
```

### 6) Operate and validate
- Health: `GET /health`
- Readiness: `GET /ready`
- Metrics (admin): `GET /metrics`
- Retrieval benchmark gate:

```bash
PYTHONPATH=src ICT_KG_RECALL_THRESHOLD=0.66 python scripts/eval_retrieval.py
```


## Supabase setup (using your project credentials)

Set environment variables:

```bash
export SUPABASE_URL="https://ospatjmicmbjimznwnzi.supabase.co"
export SUPABASE_SECRET_KEY="<your-supabase-secret-key>"
```

Validate API access and discover exposed paths:

```bash
PYTHONPATH=src python scripts/supabase_check.py
```

Provision the database schema by running `scripts/supabase_schema.sql` in the Supabase SQL editor.

After provisioning, table endpoints become available under `/rest/v1/<table>`.

## Scripts

```bash
PYTHONPATH=src python scripts/ingest_sources.py
PYTHONPATH=src python scripts/eval_retrieval.py
PYTHONPATH=src python scripts/ingestion_worker.py
PYTHONPATH=src python scripts/supabase_check.py
```


## Frontend (React + D3)

A UI is now included at `web/` using your provided JSX layout/theme and connected to this backend API.

Run it:

```bash
cd web
npm install
npm run dev
```

Optional env (`web/.env`):

```bash
VITE_API_BASE=http://127.0.0.1:8000
VITE_TENANT_ID=default
VITE_ROLE=admin
```

The frontend calls:
- `/auth/token` (local mode)
- `/graph`, `/nodes`, `/edges`, `/query`
- displays graph/list/chat panels with D3 rendering

## Deployment

```bash
docker compose up --build
```

## Tests

```bash
pytest -q
```
