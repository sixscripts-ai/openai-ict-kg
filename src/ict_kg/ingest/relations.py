"""Relation triple extraction via LLM (Gemini or Ollama).

Called during ingestion when ENABLE_RELATION_EXTRACTION=true.
"""
from __future__ import annotations

import logging

from ..llm import extract_json_list, get_llm_client

logger = logging.getLogger(__name__)

RELATION_PROMPT = """\
You are an expert in ICT (Inner Circle Trader) concepts and forex trading methodology.

Extract subject-relation-object knowledge triples from the trading text below.
Return ONLY a JSON array — no explanation, no markdown fences.
Use short, specific relation types such as: precedes, confirms, targets, is_type_of,
requires, invalidates, sets_liquidity_for, aligns_with, occurs_during, mentioned_in.

Example output:
[
  {{"subject": "Liquidity Sweep", "relation": "precedes", "object": "Displacement"}},
  {{"subject": "Order Block", "relation": "targets", "object": "Fair Value Gap"}}
]

TEXT:
{text}
"""

NER_PROMPT = """\
You are an expert in ICT (Inner Circle Trader) forex trading concepts.

List all distinct ICT trading concepts mentioned in the text below.
Return ONLY a JSON array of concept name strings — no explanation, no markdown.
Include abbreviations separately if used (e.g. "FVG" and "Fair Value Gap").

Example output:
["Liquidity Sweep", "FVG", "Order Block", "Displacement", "Killzone"]

TEXT:
{text}
"""


def extract_concepts(text: str) -> list[str]:
    """Return a list of ICT concept names mentioned in *text*."""
    try:
        client = get_llm_client()
        raw = client.complete(NER_PROMPT.format(text=text[:3000]))
        result = extract_json_list(raw)
        return [str(c) for c in result if isinstance(c, str) and c.strip()]
    except Exception as exc:  # noqa: BLE001
        logger.warning("NER extraction failed: %s", exc)
        return []


def extract_triples(text: str) -> list[dict]:
    """Return (subject, relation, object) triples from *text*.

    Each element is a dict with keys: subject, relation, object.
    """
    try:
        client = get_llm_client()
        raw = client.complete(RELATION_PROMPT.format(text=text[:3000]))
        items = extract_json_list(raw)
        valid = []
        for item in items:
            if isinstance(item, dict) and all(k in item for k in ("subject", "relation", "object")):
                valid.append({
                    "subject": str(item["subject"]).strip(),
                    "relation": str(item["relation"]).strip().replace(" ", "_"),
                    "object":   str(item["object"]).strip(),
                })
        return valid
    except Exception as exc:  # noqa: BLE001
        logger.warning("Relation extraction failed: %s", exc)
        return []
