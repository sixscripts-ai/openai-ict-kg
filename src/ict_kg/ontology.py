"""ICT Knowledge Graph — Hardcoded ontology and fuzzy matcher.

Defines explicit ICT concept relationships and a utility to match
node titles against ontology entries using simple substring matching.
"""
from __future__ import annotations

from typing import NamedTuple


class OntologyEdge(NamedTuple):
    subject: str
    relation: str
    obj: str


# ---------------------------------------------------------------------------
# ICT Concept Ontology
# ---------------------------------------------------------------------------

ICT_ONTOLOGY: list[OntologyEdge] = [
    # ── Setup sequence ─────────────────────────────────────────────────────
    OntologyEdge("Liquidity Sweep",         "precedes",           "Displacement"),
    OntologyEdge("Displacement",            "confirms",           "Order Block"),
    OntologyEdge("Order Block",             "targets",            "Fair Value Gap"),
    OntologyEdge("Judas Swing",             "is_type_of",         "Liquidity Sweep"),
    OntologyEdge("Liquidity Grab",          "is_type_of",         "Liquidity Sweep"),
    OntologyEdge("Stop Hunt",               "is_type_of",         "Liquidity Sweep"),

    # ── Market structure ───────────────────────────────────────────────────
    OntologyEdge("MSS",                     "confirms",           "Trend Change"),
    OntologyEdge("Market Structure Shift",  "confirms",           "Trend Change"),
    OntologyEdge("CISD",                    "confirms",           "Structure Break"),
    OntologyEdge("BOS",                     "is_type_of",         "Market Structure"),
    OntologyEdge("Break of Structure",      "is_type_of",         "Market Structure"),
    OntologyEdge("MSS",                     "is_type_of",         "Market Structure"),
    OntologyEdge("Market Structure Shift",  "is_type_of",         "Market Structure"),
    OntologyEdge("CHoCH",                   "is_type_of",         "Market Structure"),
    OntologyEdge("Change of Character",     "is_type_of",         "Market Structure"),

    # ── Imbalance hierarchy ────────────────────────────────────────────────
    OntologyEdge("Fair Value Gap",          "is_type_of",         "Imbalance"),
    OntologyEdge("FVG",                     "is_type_of",         "Imbalance"),
    OntologyEdge("Volume Imbalance",        "is_type_of",         "Imbalance"),
    OntologyEdge("Void",                    "is_type_of",         "Imbalance"),
    OntologyEdge("Consequent Encroachment", "is_part_of",         "Fair Value Gap"),
    OntologyEdge("Imbalance",               "is_type_of",         "Price Action"),
    OntologyEdge("Market Structure",        "is_type_of",         "Price Action"),

    # ── Premium / Discount ────────────────────────────────────────────────
    OntologyEdge("Premium Zone",            "is_type_of",         "Price Level"),
    OntologyEdge("Discount Zone",           "is_type_of",         "Price Level"),
    OntologyEdge("Equilibrium",             "divides",            "Premium Zone"),
    OntologyEdge("Equilibrium",             "divides",            "Discount Zone"),
    OntologyEdge("SIBI",                    "is_type_of",         "Fair Value Gap"),
    OntologyEdge("BISI",                    "is_type_of",         "Fair Value Gap"),

    # ── Liquidity concepts ────────────────────────────────────────────────
    OntologyEdge("Buyside Liquidity",       "is_type_of",         "Liquidity"),
    OntologyEdge("Sellside Liquidity",      "is_type_of",         "Liquidity"),
    OntologyEdge("Equal Highs",             "represents",         "Buyside Liquidity"),
    OntologyEdge("Equal Lows",              "represents",         "Sellside Liquidity"),
    OntologyEdge("Previous High",           "represents",         "Buyside Liquidity"),
    OntologyEdge("Previous Low",            "represents",         "Sellside Liquidity"),

    # ── Order types ───────────────────────────────────────────────────────
    OntologyEdge("Breaker Block",           "is_type_of",         "Order Block"),
    OntologyEdge("Rejection Block",         "is_type_of",         "Order Block"),
    OntologyEdge("Propulsion Block",        "is_type_of",         "Order Block"),
    OntologyEdge("Mitigation Block",        "is_type_of",         "Order Block"),

    # ── Sessions (temporal sequence) ──────────────────────────────────────
    OntologyEdge("Asia Session",            "sets_liquidity_for", "London Session"),
    OntologyEdge("London Session",          "sets_liquidity_for", "New York Session"),
    OntologyEdge("Asia Session",            "session_precedes",   "London Session"),
    OntologyEdge("London Session",          "session_precedes",   "New York Session"),
    OntologyEdge("London Killzone",         "aligns_with",        "London Session"),
    OntologyEdge("New York Killzone",       "aligns_with",        "New York Session"),
    OntologyEdge("New York AM",             "session_precedes",   "New York PM"),
    OntologyEdge("Silver Bullet",           "occurs_during",      "New York AM"),

    # ── Timeframes ────────────────────────────────────────────────────────
    OntologyEdge("HTF",                     "confirms",           "LTF"),
    OntologyEdge("Higher Timeframe",        "confirms",           "Lower Timeframe"),
    OntologyEdge("Monthly",                 "timeframe_precedes", "Weekly"),
    OntologyEdge("Weekly",                  "timeframe_precedes", "Daily"),
    OntologyEdge("Daily",                   "timeframe_precedes", "4h"),
    OntologyEdge("4h",                      "timeframe_precedes", "1h"),
    OntologyEdge("1h",                      "timeframe_precedes", "15m"),
    OntologyEdge("15m",                     "timeframe_precedes", "5m"),
    OntologyEdge("5m",                      "timeframe_precedes", "1m"),
]

# ---------------------------------------------------------------------------
# Fuzzy matcher
# ---------------------------------------------------------------------------

def _normalise(s: str) -> str:
    return s.lower().replace("-", " ").replace("_", " ").strip()


def find_matching_node_pairs(
    node_titles: list[tuple[int, str]],
) -> list[tuple[int, int, str]]:
    """Return (source_id, target_id, relation) triples for nodes whose
    titles match ontology entries.

    Parameters
    ----------
    node_titles:
        List of (node_id, title) pairs from the database.

    Returns
    -------
    List of (source_node_id, target_node_id, relation_type) to insert.
    """
    # Build a lookup: normalised term -> list of node_ids
    term_to_ids: dict[str, list[int]] = {}
    for node_id, title in node_titles:
        norm = _normalise(title)
        # Also register partial matches (single words that appear in long titles)
        term_to_ids.setdefault(norm, []).append(node_id)
        for word in norm.split():
            if len(word) >= 4:  # skip tiny words
                term_to_ids.setdefault(word, []).append(node_id)

    results: list[tuple[int, int, str]] = []

    for edge in ICT_ONTOLOGY:
        subj_norm = _normalise(edge.subject)
        obj_norm = _normalise(edge.obj)

        subj_ids = _match(term_to_ids, subj_norm)
        obj_ids = _match(term_to_ids, obj_norm)

        for s_id in subj_ids:
            for t_id in obj_ids:
                if s_id != t_id:
                    results.append((s_id, t_id, edge.relation))

    return results


def _match(term_to_ids: dict[str, list[int]], norm: str) -> list[int]:
    """Return node ids whose normalised title contains or equals *norm*."""
    ids: list[int] = []
    for term, node_ids in term_to_ids.items():
        if norm in term or term in norm:
            ids.extend(node_ids)
    return list(set(ids))
