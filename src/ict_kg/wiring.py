"""Auto-wiring module: generates edges between existing nodes using
three strategies:

1. Semantic similarity — cosine similarity on stored embeddings
2. Domain matching — same-domain nodes at a lower threshold
3. ICT ontology — explicit typed relations from src/ict_kg/ontology.py
"""
from __future__ import annotations

import psycopg2.extras

from .db import Database
from .embeddings import cosine_similarity, decode_embedding
from .ontology import find_matching_node_pairs

# Thresholds
SEMANTIC_THRESHOLD = 0.75  # cross-domain similar_to
DOMAIN_THRESHOLD = 0.65    # same-domain related_to


def auto_wire_edges(db: Database, tenant_id: str = "default") -> dict[str, int]:
    """Generate edges for all strategies. Returns counts per strategy."""
    with db.connection() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            "SELECT id, title, domain, embedding FROM nodes WHERE tenant_id = %s",
            (tenant_id,),
        )
        nodes = cur.fetchall()

    if not nodes:
        return {"semantic": 0, "domain": 0, "ontology": 0}

    node_list = [dict(n) for n in nodes]
    counts = {
        "semantic": _wire_semantic(db, tenant_id, node_list),
        "domain":   _wire_domain(db, tenant_id, node_list),
        "ontology": _wire_ontology(db, tenant_id, node_list),
    }
    return counts


# ---------------------------------------------------------------------------
# Strategy 1 — Semantic similarity
# ---------------------------------------------------------------------------

def _wire_semantic(db: Database, tenant_id: str, nodes: list[dict]) -> int:
    inserted = 0
    pairs_to_check = [
        (nodes[i], nodes[j])
        for i in range(len(nodes))
        for j in range(i + 1, len(nodes))
    ]
    for a, b in pairs_to_check:
        emb_a = decode_embedding(a["embedding"])
        emb_b = decode_embedding(b["embedding"])
        sim = cosine_similarity(emb_a, emb_b)
        if sim >= SEMANTIC_THRESHOLD:
            if _insert_edge(db, tenant_id, a["id"], b["id"], "similar_to"):
                inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Strategy 2 — Domain matching
# ---------------------------------------------------------------------------

def _wire_domain(db: Database, tenant_id: str, nodes: list[dict]) -> int:
    inserted = 0
    # Group by domain
    by_domain: dict[str, list[dict]] = {}
    for n in nodes:
        by_domain.setdefault(n["domain"], []).append(n)

    for domain_nodes in by_domain.values():
        if len(domain_nodes) < 2:
            continue
        for i in range(len(domain_nodes)):
            for j in range(i + 1, len(domain_nodes)):
                a, b = domain_nodes[i], domain_nodes[j]
                emb_a = decode_embedding(a["embedding"])
                emb_b = decode_embedding(b["embedding"])
                sim = cosine_similarity(emb_a, emb_b)
                if DOMAIN_THRESHOLD <= sim < SEMANTIC_THRESHOLD:
                    # Only emit domain edges for pairs below semantic threshold
                    # (above it already handled as similar_to)
                    if _insert_edge(db, tenant_id, a["id"], b["id"], "related_to"):
                        inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Strategy 3 — ICT ontology fuzzy match
# ---------------------------------------------------------------------------

def _wire_ontology(db: Database, tenant_id: str, nodes: list[dict]) -> int:
    node_titles = [(n["id"], n["title"]) for n in nodes]
    edges = find_matching_node_pairs(node_titles)
    inserted = 0
    for source_id, target_id, relation in edges:
        if _insert_edge(db, tenant_id, source_id, target_id, relation):
            inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _insert_edge(
    db: Database,
    tenant_id: str,
    source_id: int,
    target_id: int,
    relation: str,
) -> bool:
    """Insert edge if it doesn't already exist. Returns True if inserted."""
    with db.connection() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        # Check if edge already exists in either direction
        cur.execute(
            """
            SELECT id FROM edges
            WHERE tenant_id = %s
              AND relation_type = %s
              AND (
                (source_node_id = %s AND target_node_id = %s)
                OR (source_node_id = %s AND target_node_id = %s)
              )
            """,
            (tenant_id, relation, source_id, target_id, target_id, source_id),
        )
        if cur.fetchone():
            return False
        cur.execute(
            """
            INSERT INTO edges (tenant_id, source_node_id, target_node_id, relation_type, weight)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (tenant_id, source_id, target_id, relation, 1.0),
        )
    return True
