-- Run in Supabase SQL editor to provision ICT KG schema in public schema.

create table if not exists public.nodes (
  id bigserial primary key,
  tenant_id text not null default 'default',
  title text not null,
  content text not null,
  domain text not null,
  embedding_model text not null default 'local-deterministic-v1',
  metadata jsonb not null default '{}'::jsonb,
  embedding text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.edges (
  id bigserial primary key,
  tenant_id text not null default 'default',
  source_node_id bigint not null references public.nodes(id) on delete cascade,
  target_node_id bigint not null references public.nodes(id) on delete cascade,
  relation_type text not null,
  weight double precision not null,
  created_at timestamptz not null default now()
);

create table if not exists public.memories (
  id bigserial primary key,
  tenant_id text not null default 'default',
  title text not null,
  content text not null,
  domain text not null,
  embedding_model text not null default 'local-deterministic-v1',
  metadata jsonb not null default '{}'::jsonb,
  embedding text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.external_refs (
  id bigserial primary key,
  tenant_id text not null,
  entity_type text not null,
  entity_id bigint not null,
  source_system text not null,
  external_id text not null,
  created_at timestamptz not null default now(),
  unique (tenant_id, source_system, external_id)
);

create table if not exists public.idempotency_keys (
  id bigserial primary key,
  tenant_id text not null,
  operation text not null,
  idempotency_key text not null,
  entity_type text not null,
  entity_id bigint not null,
  created_at timestamptz not null default now(),
  unique (tenant_id, operation, idempotency_key)
);

create table if not exists public.audit_logs (
  id bigserial primary key,
  tenant_id text not null,
  actor text not null,
  action text not null,
  entity_type text not null,
  entity_id bigint,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.ingestion_chunks (
  id bigserial primary key,
  tenant_id text not null,
  source_system text not null,
  external_id text not null,
  chunk_hash text not null,
  node_id bigint,
  created_at timestamptz not null default now(),
  unique (tenant_id, source_system, external_id, chunk_hash)
);

create table if not exists public.ingestion_jobs (
  id bigserial primary key,
  tenant_id text not null,
  source_system text not null,
  source text not null,
  domain text not null,
  status text not null,
  error text,
  result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_ingestion_jobs_tenant_status on public.ingestion_jobs (tenant_id, status);
